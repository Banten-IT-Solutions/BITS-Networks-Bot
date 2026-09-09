#!/usr/bin/env python3
# BITS Networks Bot - Telegram management bot for BITS-WRT (OpenWrt)
# Fitur: Status, Internet (Huawei HiLink API), Momo, Tailscale, Klien, Sistem
# Optimasi: log file + rotasi, ubus-first, cache status, rate-limit, healthcheck,
#           background monitor (WAN up/down, suhu, disk, laporan harian).

import logging
import logging.handlers
import asyncio
import subprocess
import re
import os
import time
import json
import urllib.request
import urllib.error
from telegram import Update, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import NetworkError
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, Application, MessageHandler, filters

# ================= KONFIGURASI DASAR =================
CONFIG_FILE = "bitsnetworksbot"
TOKEN = ""
ALLOWED_USERS = []
ENABLED_COMMANDS = {}

LOG_FILE = "/var/log/bitsnetworksbot.log"
DIV = "━" * 24
BRAND = "BITS Networks Bot"


def div_for(*lines):
    """Garis ━ selebar baris terpanjang (perkiraan lebar tampil Telegram)."""
    w = 0
    for ln in lines:
        t = re.sub(r"<[^>]+>", "", str(ln) if ln is not None else "")
        cw = 0
        for c in t:
            o = ord(c)
            if o == 0xFE0F:
                continue
            cw += 2 if o > 0x2500 else 1
        w = max(w, cw)
    return "━" * max(w, 20)

# Cache & rate-limit
STATUS_CACHE = {"ts": 0, "text": ""}
STATUS_TTL = 10
LAST_CMD = {}
RATE_MIN_INTERVAL = 2.0

# Monitor state
MON_STATE = {"wan_up": None, "last_temp_alert": 0, "last_disk_alert": 0,
             "last_ram_alert": 0, "last_daily": "", "macs": set(),
             "temp_max": 0, "wan_down": 0, "daily_date": ""}
TEMP_ALERT_C = 78.0
DISK_ALERT_PCT = 85
RAM_ALERT_PCT = 90
TEMP_COOLDOWN = 3600
is_polling_running = False

# Wizard jadwal Bandix per user
WIZ = {}
DAY_ID = {1: "Sen", 2: "Sel", 3: "Rab", 4: "Kam", 5: "Jum", 6: "Sab", 7: "Min"}

# ================= LOGGING (file + rotasi) =================
logger = logging.getLogger("bitsbot")
logger.setLevel(logging.INFO)
_fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=200 * 1024, backupCount=2)
_fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(_fh)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ================= HELPER UMUM =================
def esc(text):
    """Escape karakter khusus HTML."""
    if text is None:
        return "-"
    return (str(text).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def run(cmd, timeout=8):
    """Jalankan perintah shell, kembalikan stdout (string kosong bila gagal)."""
    try:
        if isinstance(cmd, str):
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               timeout=timeout, executable="/bin/sh")
        else:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        logger.error(f"run gagal [{cmd}]: {e}")
        return ""


def ubus(obj, method, args=None):
    """Panggil ubus, kembalikan dict (kosong bila gagal)."""
    try:
        cmd = ["ubus", "call", obj, method]
        if args is not None:
            cmd.append(json.dumps(args))
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if r.returncode != 0:
            return {}
        return json.loads(r.stdout or "{}")
    except Exception as e:
        logger.error(f"ubus {obj} {method} gagal: {e}")
        return {}


def uci_get(path, default=""):
    out = run(["uci", "-q", "get", path])
    return out if out else default

# ================= KONFIGURASI UCI =================
def execute_command_uci(command_args):
    try:
        r = subprocess.run(command_args, shell=True, capture_output=True, text=True,
                           timeout=5, executable="/bin/sh")
        return r.stdout.strip()
    except Exception:
        return ""


def load_config():
    global TOKEN, ALLOWED_USERS, ENABLED_COMMANDS

    def get_opt(option, default=""):
        cmd = f"uci get {CONFIG_FILE}.config.{option} 2>/dev/null"
        res = execute_command_uci(cmd)
        return res if res else default

    try:
        TOKEN = get_opt("token", "")
        users = set()
        for u in get_opt("allowed_users", "").split(","):
            u = u.strip()
            if u.isdigit():
                users.add(int(u))
        ALLOWED_USERS = list(users)
        for cmd in ["status", "devices", "reboot", "internet", "momo",
                    "tailscale", "sistem", "jadwal", "monitor", "docker",
                    "tools", "firewall"]:
            ENABLED_COMMANDS[cmd] = get_opt(f"enable_{cmd}", "1") == "1"
        logger.info("Konfigurasi dimuat: %d users, %s", len(ALLOWED_USERS), ENABLED_COMMANDS)
    except Exception as e:
        logger.error(f"Gagal memuat konfigurasi UCI: {e}")

# ================= OTORISASI & RATE-LIMIT =================
def is_allowed(user_id):
    return str(user_id) in [str(u) for u in ALLOWED_USERS]


def check_authorization_manual(update: Update, target):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not is_allowed(user_id):
        logger.warning(f"ACCESS DENIED: user {user_id}")
        asyncio.create_task(target.reply_text("🔒 <b>Akses ditolak.</b> ID Anda tidak terdaftar.", parse_mode="HTML"))
        return False
    return True


def check_enabled_manual(command_name, target):
    if not ENABLED_COMMANDS.get(command_name, True):
        asyncio.create_task(target.reply_text(
            f"⚙️ Perintah <b>{esc(command_name)}</b> dinonaktifkan di LuCI.", parse_mode="HTML"))
        return False
    return True


async def rate_ok(update: Update, target):
    uid = update.effective_user.id if update.effective_user else 0
    now = time.monotonic()
    last = LAST_CMD.get(uid, 0)
    if now - last < RATE_MIN_INTERVAL:
        try:
            await target.reply_text("⏳ <b>Santai…</b> tunggu 2 detik.", parse_mode="HTML")
        except Exception:
            pass
        return False
    LAST_CMD[uid] = now
    return True

# ================= PENGIRIM PESAN =================
async def send(target, text, reply_markup=None):
    """Kirim teks (potong per 4000 char bila perlu), tangani error jaringan."""
    try:
        if len(text) <= 4000:
            await target.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            for i in range(0, len(text), 4000):
                await target.reply_text(text[i:i + 4000], parse_mode="HTML",
                                        reply_markup=reply_markup if i + 4000 >= len(text) else None)
                await asyncio.sleep(0.3)
        return True
    except NetworkError as e:
        logger.error(f"Kirim pesan gagal (network): {e}")
    except Exception as e:
        logger.error(f"Kirim pesan gagal: {e}")
    return False


def panel_text(title, body):
    """Teks panel: judul + garis selebar konten + body + garis."""
    div = div_for(title, *((body or "").split("\n")))
    return f"<b>{esc(title)}</b>\n{div}\n{body}\n{div}"


async def show_panel(query, title, body, buttons):
    """Edit pesan menjadi panel + tombol (rasa aplikasi profesional)."""
    text = panel_text(title, body)
    try:
        await query.edit_message_text(text, parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.warning(f"Edit panel gagal, kirim baru: {e}")
        try:
            await query.message.reply_text(text, parse_mode="HTML",
                                           reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e2:
            logger.error(f"Kirim panel gagal: {e2}")


def btn_main_menu():
    return [[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_main")]]

# ================= DATA SISTEM (ubus-first) =================
def get_uptime():
    out = run("uptime")
    return out.split(",")[0].strip() if out else "-"


def get_uptime_precise():
    """Uptime ramah: '1 Hari 12 Jam 41 Menit'."""
    try:
        with open("/proc/uptime") as f:
            sec = float(f.read().split()[0])
    except Exception:
        return get_uptime()
    d = int(sec // 86400)
    h = int((sec % 86400) // 3600)
    m = int((sec % 3600) // 60)
    parts = []
    if d:
        parts.append(f"{d} Hari")
    if h:
        parts.append(f"{h} Jam")
    if m:
        parts.append(f"{m} Menit")
    return " ".join(parts) if parts else "Kurang 1 Menit"


def html_esc(text):
    """Escape karakter khusus untuk parse_mode HTML."""
    if text is None:
        return "-"
    return (str(text).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def get_loadavg():
    """Load average 1/5/15 menit dari /proc/loadavg."""
    try:
        with open("/proc/loadavg") as f:
            a, b, c = f.read().split()[:3]
        return f"{a} · {b} · {c}"
    except Exception:
        return "-"


def get_mem():
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                p = line.split()
                if p[0] in ("MemTotal:", "MemAvailable:"):
                    info[p[0]] = int(p[1])
        used = (info["MemTotal:"] - info["MemAvailable:"]) / 1024
        total = info["MemTotal:"] / 1024
        pct = used / total * 100 if total else 0
        return used, total, pct
    except Exception:
        return 0, 0, 0


def get_cpu_temp():
    for p in ("/sys/class/thermal/thermal_zone0/temp",
              "/sys/class/hwmon/hwmon0/temp1_input"):
        try:
            with open(p) as f:
                return int(f.read().strip()) / 1000
        except Exception:
            continue
    return None


def get_disk():
    try:
        st = os.statvfs("/overlay")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        pct = used / total * 100 if total else 0
        return used / 1024 / 1024, total / 1024 / 1024, pct
    except Exception:
        return 0, 0, 0


def get_swap():
    """(used_mb, total_mb) atau None bila swap mati."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                p = line.split()
                if p[0] in ("SwapTotal:", "SwapFree:"):
                    info[p[0]] = int(p[1])
        total = info.get("SwapTotal:", 0)
        if total <= 0:
            return None
        return (total - info.get("SwapFree:", 0)) / 1024, total / 1024
    except Exception:
        return None


BANDIX_CACHE = {"ts": 0, "devs": []}
BANDIX_TTL = 120


def fmt_bytes(n):
    try:
        n = float(n or 0)
    except Exception:
        return "-"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.1f}{u}" if u != "B" else f"{int(n)}B"
        n /= 1024


def bandix_devices():
    """Daftar trafik per perangkat dari Bandix (cache 2 menit)."""
    import time as _t
    now = _t.monotonic()
    if now - BANDIX_CACHE["ts"] < BANDIX_TTL and BANDIX_CACHE["devs"]:
        return BANDIX_CACHE["devs"]
    try:
        end_ms = int(_t.time() * 1000)
        devs = ubus("luci.bandix", "getStatus",
                    {"start_ms": end_ms - 86400000, "end_ms": end_ms}).get("d", [])
        if isinstance(devs, list):
            BANDIX_CACHE.update(ts=now, devs=devs)
            return devs
    except Exception as e:
        logger.error(f"Bandix gagal: {e}")
    return BANDIX_CACHE["devs"]


def bandix_by_mac(mac):
    m = (mac or "").lower()
    for d in bandix_devices():
        if str(d.get("mac", "")).lower() == m:
            return d
    return None


TS_COUNT_CACHE = {"ts": 0, "val": None}
TS_TTL = 60


def tailscale_counts():
    """(online, total) peer Tailscale. None bila gagal."""
    now = time.monotonic()
    if now - TS_COUNT_CACHE["ts"] < TS_TTL:
        return TS_COUNT_CACHE["val"]
    val = None
    try:
        r = subprocess.run(["tailscale", "status", "--json"], capture_output=True,
                           text=True, timeout=10)
        d = json.loads(r.stdout or "{}")
        peers = d.get("Peer", {})
        if isinstance(peers, dict):
            online = sum(1 for v in peers.values()
                         if isinstance(v, dict) and v.get("Online"))
            val = (online, len(peers))
    except Exception:
        val = None
    TS_COUNT_CACHE.update(ts=now, val=val)
    return val


TRAF_CACHE = {"ts": 0, "val": None}
TRAF_TTL = 120


def daily_traffic():
    """Total trafik WAN hari ini (down, up bytes) via Bandix."""
    now = time.monotonic()
    if now - TRAF_CACHE["ts"] < TRAF_TTL:
        return TRAF_CACHE["val"]
    val = None
    try:
        lt = time.localtime()
        start_ms = int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                                    0, 0, 0, 0, 0, -1)) * 1000)
        end_ms = int(time.time() * 1000)
        devs = ubus("luci.bandix", "getStatus",
                    {"start_ms": start_ms, "end_ms": end_ms}).get("d", [])
        dl = sum(float(x.get("w_rx_b", 0) or 0)
                 for x in devs if isinstance(x, dict))
        ul = sum(float(x.get("w_tx_b", 0) or 0)
                 for x in devs if isinstance(x, dict))
        val = (dl, ul)
    except Exception:
        val = None
    TRAF_CACHE.update(ts=now, val=val)
    return val


def bandix_today():
    """Daftar trafik per perangkat hari ini (sejak tengah malam)."""
    try:
        lt = time.localtime()
        start_ms = int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                                    0, 0, 0, 0, 0, -1)) * 1000)
        end_ms = int(time.time() * 1000)
        devs = ubus("luci.bandix", "getStatus",
                    {"start_ms": start_ms, "end_ms": end_ms}).get("d", [])
        return devs if isinstance(devs, list) else []
    except Exception as e:
        logger.error(f"bandix today gagal: {e}")
        return []


def get_wan_ip():
    d = ubus("network.interface.wan", "status")
    try:
        addrs = d.get("ipv4-address", [])
        if addrs:
            return addrs[0].get("address", "-")
    except Exception:
        pass
    out = run(["ip", "-4", "addr", "show", "dev", "eth1"])
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", out)
    return m.group(1) if m else "-"


def get_iface_ip(dev):
    out = run(["ip", "-4", "addr", "show", "dev", dev])
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", out)
    return m.group(1) if m else "-"


def status_text_cached():
    now = time.monotonic()
    if now - STATUS_CACHE["ts"] < STATUS_TTL and STATUS_CACHE["text"]:
        return STATUS_CACHE["text"]
    used, total, pct = get_mem()
    temp = get_cpu_temp()
    dused, dtotal, dpct = get_disk()
    swap = get_swap()
    traf = daily_traffic()
    temp_s = f"{temp:.0f}°C" + (" 🔥" if temp and temp >= TEMP_ALERT_C else "") if temp is not None else "-"
    ram_s = f"🧠 <b>RAM :</b> {used:.0f} / {total:.0f} MB ({pct:.0f}%)"
    if swap and swap[0] > 0:
        ram_s += f" 💱 <b>Swap :</b> {swap[0]:.0f}MB"
    lan_traf = ""
    if traf:
        lan_traf = f" ⬇️ {fmt_bytes(traf[0])} · ⬆️ {fmt_bytes(traf[1])}"
    txt = (f"🌡 <b>CPU :</b> {temp_s} 📈 <b>Load :</b> {esc(get_loadavg())}\n"
           f"{ram_s}\n"
           f"💽 <b>Disk :</b> {dused:.0f} / {dtotal:.0f} MB ({dpct:.0f}%)\n"
           f"🕒 <b>Uptime :</b> {esc(get_uptime_precise())}\n\n"
           f"🔀 <b>Uplink :</b> {uplink_text()}\n"
           f"🌐 <b>WAN :</b> {esc(wan_public_line())}\n"
           f"🛡 <b>VPN :</b> {esc(vpn_public_line())}\n"
           f"🏠 <b>LAN :</b> {esc(get_iface_ip('br-lan'))}{lan_traf}")
    STATUS_CACHE.update(ts=now, text=txt)
    return txt

# ================= PUBLIC IP & UPLINK =================
PUB_IP_CACHE = {"ts": 0, "ip": "", "isp": "", "city": "", "country": ""}


def public_ip():
    now = time.monotonic()
    if now - PUB_IP_CACHE["ts"] < 300 and PUB_IP_CACHE["ip"]:
        return PUB_IP_CACHE
    try:
        req = urllib.request.Request(
            "http://ip-api.com/json?fields=query,isp,city,country", method="GET")
        req.add_header("User-Agent", "Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
        if d and d.get("status") != "fail":
            PUB_IP_CACHE.update(ts=now, ip=d.get("query", "-"),
                                isp=d.get("isp", "-"), city=d.get("city", ""),
                                country=d.get("country", ""))
            return PUB_IP_CACHE
    except Exception as e:
        logger.error(f"public ip gagal: {e}")
    try:
        ip = run("curl -s -m 8 https://ifconfig.me")
        if ip:
            PUB_IP_CACHE.update(ts=now, ip=ip, isp="-", city="", country="")
    except Exception:
        pass
    return PUB_IP_CACHE


def short_isp(name):
    """Ringkas nama ISP/org jadi label pendek."""
    n = (name or "").strip()
    low = n.lower()
    for key, short in (("cloudflare", "Cloudflare"), ("selular", "Telkomsel"),
                       ("telekomunikasi", "Telkom"), ("telkom", "Telkom"),
                       ("indosat", "Indosat"), ("axis", "AXIS"),
                       ("smartfren", "Smartfren"), ("xl", "XL")):
        if key in low:
            return short
    if not n:
        return "-"
    return (n.replace("PT ", "").replace("PT.", "").replace(", Inc.", "")
            .replace(" Inc.", "").strip()) or "-"


PUB_DUAL_CACHE = {"ts": 0, "wan_ip": "-", "wan_isp": "", "vpn_ip": "-", "vpn_isp": ""}


def _http_json(url):
    """GET JSON dengan 1x retry. Kembalikan dict atau None."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "curl/8.0")
    last = None
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:
            last = e
    if last:
        logger.error(f"GET {url} gagal: {last}")
    return None


def _http_text(url):
    """GET teks dengan 1x retry. Kembalikan string atau None."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "curl/8.0")
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                return r.read().decode("utf-8", "ignore").strip()
        except Exception:
            pass
    return None


def _demote_nobody():
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)


def _direct_run(args, timeout=8):
    """Jalankan perintah sebagai nobody (uid 65534) → bypass redirect momo/sing-box."""
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout + 3, preexec_fn=_demote_nobody)
        return r.stdout if r.returncode == 0 else ""
    except Exception as e:
        logger.error(f"direct run gagal [{args}]: {e}")
        return ""


def _direct_json(url):
    raw = _direct_run(["curl", "-s", "-m", "8", url])
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _direct_text(url):
    return _direct_run(["curl", "-s", "-m", "8", url]) or None


def public_ip_dual():
    """IP publik ganda: WAN asli (direct/bypass momo) + egress VPN (proxied)."""
    now = time.monotonic()
    if now - PUB_DUAL_CACHE["ts"] < 300 and PUB_DUAL_CACHE["wan_ip"] != "-":
        return PUB_DUAL_CACHE
    vpn_ip, vpn_isp = "-", ""
    d = _http_json("https://ipinfo.io/json")
    if d and d.get("ip"):
        vpn_ip = str(d.get("ip"))
        vpn_isp = short_isp(d.get("org", ""))
    else:
        vpn_ip = _http_text("https://checkip.amazonaws.com") or "-"
    wan_ip, wan_isp = "-", ""
    d = _direct_json("https://ipinfo.io/json")
    if d and d.get("ip"):
        wan_ip = str(d.get("ip"))
        wan_isp = short_isp(d.get("org", ""))
    else:
        wan_ip = _direct_text("https://api.ipify.org") or "-"
    PUB_DUAL_CACHE.update(ts=now, wan_ip=wan_ip, wan_isp=wan_isp,
                          vpn_ip=vpn_ip, vpn_isp=vpn_isp)
    return PUB_DUAL_CACHE


def wan_public_line():
    """IP publik WAN asli (baca cache, non-blocking)."""
    ip = PUB_DUAL_CACHE.get("wan_ip") or "-"
    isp = PUB_DUAL_CACHE.get("wan_isp") or ""
    return f"{ip} · {isp}" if isp else ip


def vpn_public_line():
    """IP egress VPN (baca cache, non-blocking)."""
    ip = PUB_DUAL_CACHE.get("vpn_ip") or "-"
    isp = PUB_DUAL_CACHE.get("vpn_isp") or ""
    return f"{ip} · {isp}" if isp else ip


def _link_chk(label, dev):
    return f"{label} {'✅' if get_iface_ip(dev) != '-' else '❌'}"


def uplink_text():
    return " · ".join([_link_chk("🔗 Modem", "eth1"), _link_chk("📱 Smartphone", "usb0")])


def vpn_text():
    return " · ".join([_link_chk("🛡 Momo", "momo-tun"), _link_chk("🌀 Tailscale", "tailscale0")])


# ================= HUAWEI HILINK API =================
HILINK = "http://192.168.8.1"

def hilink_session():
    """Ambil (session_cookie, token). Kembalikan (None, None) bila gagal."""
    try:
        req = urllib.request.Request(HILINK + "/api/webserver/SesTokInfo", method="GET")
        with urllib.request.urlopen(req, timeout=8) as r:
            xml = r.read().decode("utf-8", "ignore")
        ses = re.search(r"<SesInfo>(.*?)</SesInfo>", xml)
        tok = re.search(r"<TokInfo>(.*?)</TokInfo>", xml)
        if ses and tok:
            return ses.group(1), tok.group(1)
    except Exception as e:
        logger.error(f"HiLink session gagal: {e}")
    return None, None


def hilink_get(path):
    """GET endpoint HiLink dengan session. Kembalikan XML string / ''."""
    ses, tok = hilink_session()
    if not ses:
        return ""
    try:
        req = urllib.request.Request(HILINK + path, method="GET")
        req.add_header("Cookie", ses)
        req.add_header("__RequestVerificationToken", tok)
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception as e:
        logger.error(f"HiLink GET {path} gagal: {e}")
        return ""


def hilink_value(xml, tag):
    m = re.search(rf"<{tag}>(.*?)</{tag}>", xml or "")
    return m.group(1).strip() if m else "-"


def signal_bars(mode, rssi=None, rsrp=None):
    """Konversi sinyal ke bar 1-5 + emoji."""
    try:
        v = int(rsrp) if (rsrp and str(rsrp).lstrip("-").isdigit()) else None
        if v is not None:
            lvl = 1 if v <= -110 else 2 if v <= -100 else 3 if v <= -90 else 4 if v <= -80 else 5
        else:
            v = int(str(rssi).rstrip("dBm")) if rssi else -100
            lvl = 1 if v <= -95 else 2 if v <= -90 else 3 if v <= -85 else 4 if v <= -75 else 5
        return "▰" * lvl + "▱" * (5 - lvl) + f" ({lvl}/5)"
    except Exception:
        return "-"


def internet_text():
    wan = get_wan_ip()
    teth = get_iface_ip("usb0")
    lines = [f"🌐 <b>WAN (eth1):</b> {esc(wan)}",
             f"📱 <b>Tethering (usb0):</b> {esc(teth if teth != '-' else 'tidak tersambung')}"]
    sig = hilink_get("/api/device/signal")
    if sig and "<error>" not in sig:
        mode = hilink_value(sig, "mode")
        mode_map = {"0": "No Service", "1": "GSM", "2": "GPRS", "3": "EDGE", "4": "WCDMA",
                    "5": "HSDPA", "6": "HSUPA", "7": "HSPA", "8": "TD-SCDMA", "9": "HSPA+",
                    "10": "EVDO", "11": "EVDO-A", "12": "EVDO-RevB", "13": "1xRTT",
                    "14": "UMB", "15": "1xEVDV", "16": "3xRTT", "17": "HSPA+64QAM",
                    "18": "HSPA+MIMO", "19": "LTE", "20": "NR", "21": "NR NSA", "22": "NR SA"}
        mname = mode_map.get(mode, mode)
        rssi, rsrp, sinr = hilink_value(sig, "rssi"), hilink_value(sig, "rsrp"), hilink_value(sig, "sinr")
        bars = signal_bars(mode, rssi if rssi != "-" else None, rsrp if rsrp != "-" else None)
        plmn = hilink_get("/api/net/current-plmn")
        op = hilink_value(plmn, "FullName") if plmn and "<error>" not in plmn else "-"
        if op == "-":
            op = hilink_value(plmn, "ShortName") if plmn else "-"
        lines += ["", "📶 <b>Sinyal Huawei E5577:</b>", f"{bars}",
                  f"• Mode: {esc(mname)}", f"• Operator: {esc(op)}",
                  f"• RSSI: {esc(rssi)}   SINR: {esc(sinr)}",
                  f"• RSRP: {esc(rsrp)}   Cell: {esc(hilink_value(sig, 'cell_id'))}"]
    else:
        lines += ["", "📶 <b>Sinyal Huawei:</b> <i>tidak terbaca (modem sibuk/offline)</i>"]
    try:
        devs = [d for d in bandix_today()
                if str(d.get("conn", "")) != "router"]
        devs.sort(key=lambda d: float(d.get("t_rx_b", 0) or 0)
                  + float(d.get("t_tx_b", 0) or 0), reverse=True)
        if devs:
            lines += ["", "📈 <b>Top Trafik Hari Ini:</b>"]
            for d in devs[:3]:
                tot = float(d.get("t_rx_b", 0) or 0) + float(d.get("t_tx_b", 0) or 0)
                nm = d.get("host") or d.get("ip4") or d.get("mac")
                lines.append(f"• {esc(str(nm))}: {fmt_bytes(tot)}")
    except Exception as e:
        logger.error(f"Top trafik gagal: {e}")
    return "\n".join(lines)

# ================= MOMO =================
def momo_text():
    prof = uci_get("momo.config.profile", "-")
    prof = prof[len("file:"):] if prof.startswith("file:") else prof
    st = run("/etc/init.d/momo status").splitlines()
    state = st[0].strip() if st else "?"
    tun = get_iface_ip("momo-tun")
    sched = uci_get("momo.config.scheduled_restart", "0")
    return (f"🛡 <b>State :</b> {esc(state.capitalize())}\n"
            f"📄 <b>Profil :</b> {esc(prof)}\n"
            f"🔀 <b>TUN :</b> {esc(tun if tun != '-' else 'down')}\n"
            f"⏰ <b>Schedule Restart :</b> {esc('Ya' if sched == '1' else 'Tidak')}")

# ================= TAILSCALE =================
def tailscale_text():
    try:
        r = subprocess.run(["tailscale", "status", "--json"], capture_output=True,
                           text=True, timeout=10)
        d = json.loads(r.stdout or "{}")
    except Exception as e:
        return f"🌀 <b>Tailscale :</b> <i>Gagal Baca Status ({esc(str(e)[:60])})</i>"
    state = d.get("BackendState", "?")
    ips = ", ".join(a for a in d.get("TailscaleIPs", [])
                  if re.match(r"^\d+\.\d+\.\d+\.\d+$", a)) or "-"
    peers = d.get("Peer", {})
    n = len(peers) if isinstance(peers, dict) else 0
    self = d.get("Self", {}) if isinstance(d.get("Self"), dict) else {}
    host = self.get("HostName", "-")
    return (f"🌀 <b>State :</b> {esc(state)}\n"
            f"🖥 <b>Hostname :</b> {esc(host)}\n"
            f"🔢 <b>IP Tail :</b> {esc(ips)}\n"
            f"👥 <b>Peers Online :</b> {n}")

# ================= KLIEN =================
def parse_dhcp_leases():
    devs = []
    try:
        with open("/tmp/dhcp.leases") as f:
            for line in f:
                p = line.split()
                if len(p) >= 4:
                    devs.append({"mac": p[1], "ip": p[2],
                                 "host": p[3] if p[3] != "*" else "Tanpa nama"})
    except Exception as e:
        logger.error(f"Baca dhcp.leases gagal: {e}")
    return devs


def get_client_count():
    """Klien aktif via Bandix (kecuali router). Fallback ke jumlah lease."""
    devs = [d for d in bandix_devices()
            if str(d.get("conn", "")).lower() != "router"]
    return len(devs) if devs else len(parse_dhcp_leases())


def get_static_macs():
    macs = set()
    try:
        with open("/etc/config/dhcp") as f:
            for line in f:
                if "option mac" in line:
                    m = re.search(r"'([0-9A-Fa-f:]+)'", line)
                    if m:
                        macs.add(m.group(1).lower())
    except Exception:
        pass
    return macs


def blocked_macs():
    out = run(["uci", "show", "firewall"])
    return set(re.findall(r"BOTBLOCK([0-9A-F]{12})", out))


def klien_text():
    devs = parse_dhcp_leases()
    if not devs:
        return "👥 <i>tidak ada klien aktif.</i>"
    statics = get_static_macs()
    blocked = blocked_macs()
    try:
        devs.sort(key=lambda d: list(map(int, d["ip"].split("."))))
    except Exception:
        pass
    blocks = []
    for d in devs:
        mac_n = d["mac"].replace(":", "").upper()
        if mac_n in blocked:
            status = "🚫 Blocked"
        elif d["mac"].lower() in statics:
            status = "✅ Connected ⭐ Static"
        else:
            status = "✅ Connected"
        rx = tx = 0.0
        b = bandix_by_mac(d["mac"])
        if b:
            rx = float(b.get("t_rx_b", 0) or 0)
            tx = float(b.get("t_tx_b", 0) or 0)
        blocks.append(
            f"👥 {esc(d['host'])}\n"
            f"🌐 {esc(d['ip'])}\n"
            f"{status}\n"
            f"⬇️ {fmt_bytes(rx)} ⬆️ {fmt_bytes(tx)}")
    legend = ("✅ Connected   ⭐ Static   🚫 Blocked\n"
              "🚫 = Block   ✅ = Unblock")
    return "\n\n".join(blocks) + "\n\n" + legend


def block_client(mac_noccolon):
    mac = ":".join(mac_noccolon[i:i + 2] for i in range(0, 12, 2))
    name = f"BOTBLOCK{mac_noccolon.upper()}"
    if name in run(["uci", "show", "firewall"]):
        return "sudah diblokir"
    run(["uci", "add", "firewall", "rule"])
    run(["uci", "set", f"firewall.@rule[-1].name={name}"])
    run(["uci", "set", "firewall.@rule[-1].src=lan"])
    run(["uci", "set", f"firewall.@rule[-1].src_mac={mac}"])
    run(["uci", "set", "firewall.@rule[-1].target=REJECT"])
    run(["uci", "commit", "firewall"])
    run(["/etc/init.d/firewall", "reload"])
    return "diblokir"


def unblock_client(mac_noccolon):
    name = f"BOTBLOCK{mac_noccolon.upper()}"
    out = run(["uci", "show", "firewall"])
    refs = []
    for line in out.splitlines():
        if name in line:
            i = line.find(".name=")
            if i > 0:
                refs.append(line[:i])

    def sort_key(ref):
        mm = re.search(r"\[(\d+)\]", ref)
        return int(mm.group(1)) if mm else -1

    for ref in sorted(set(refs), key=sort_key, reverse=True):
        run(["uci", "delete", ref])
    if refs:
        run(["uci", "commit", "firewall"])
        run(["/etc/init.d/firewall", "reload"])
        return "dibuka"
    return "tidak ditemukan"

# ================= DOCKER =================
def docker_rows():
    out = run("docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'")
    rows = []
    for line in out.splitlines():
        p = line.split("\t")
        if len(p) >= 3:
            rows.append({"name": p[0], "image": p[1], "status": p[2],
                         "ports": p[3] if len(p) > 3 else "-"})
    return rows


def docker_text():
    rows = docker_rows()
    if not rows:
        return "🐳 <i>tidak ada container.</i>"
    blocks = []
    for r in rows:
        up = "Up" in r["status"] or "healthy" in r["status"].lower()
        ic = "🟢" if up else "🔴"
        blocks.append(f"{ic} {esc(r['name'])}\n"
                      f"💽 {esc(r['image'])}\n"
                      f"🕒 {esc(r['status'])}")
    return "\n\n".join(blocks)


def docker_stats_text():
    out = run("docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}'")
    if not out:
        return "🐳 <i>Gagal baca stats.</i>"
    blocks = []
    for line in out.splitlines():
        p = line.split("\t")
        if len(p) >= 4:
            blocks.append(f"🟢 {esc(p[0])}\n"
                          f"🧠 CPU {esc(p[1])}\n"
                          f"💽 RAM {esc(p[2])}\n"
                          f"🌐 Net {esc(p[3])}")
    return "\n\n".join(blocks)


def docker_images_text():
    out = run("docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}'")
    if not out:
        return "🐳 <i>Tidak ada image.</i>"
    lines = []
    for line in out.splitlines()[:20]:
        p = line.split("\t")
        lines.append(f"💽 {esc(p[0])} — {esc(p[1]) if len(p) > 1 else '?'}")
    return "\n".join(lines)


def docker_logs(name):
    out = run(f"docker logs --tail 30 {name} 2>&1")
    if not out:
        return f"🐳 Log <code>{name}</code> kosong."
    return f"📜 <b>Log {name}:</b>\n<pre>{out[-3000:]}</pre>"


def docker_ctl(op, name):
    out = run(f"docker {op} {name} 2>&1")
    time.sleep(2)
    tail = esc(out[:200]) if out else "ok"
    return f"✅ <b>docker {op} {name}</b> selesai.\n<pre>{tail}</pre>"


def docker_prune():
    out = run("docker system prune -f 2>&1 | tail -n 8")
    reclaimed = "0B"
    m = re.search(r"Total reclaimed space:\s*([^\n]+)", out)
    if m:
        reclaimed = m.group(1).strip()
    return f"🧹 <b>Docker Prune Berhasil</b>\n💽 <b>Total Reclaimed Space :</b> {esc(reclaimed)}"


# ================= TOOLS =================
def net_ping(host):
    out = run(["ping", "-c", "3", "-W", "2", host])
    if not out:
        return f"❌ <b>Ping {esc(host)}</b> → Tidak Ada Balasan (Loss -)."
    recv = re.search(r"(\d+)(?: packets)? received", out)
    avg = re.search(r"min/avg/max[^=]*=\s*[\d.]+\/([\d.]+)\/", out)
    loss = re.search(r"(\d+)% packet loss", out)
    r = int(recv.group(1)) if recv else 0
    a = avg.group(1) if avg else "-"
    l = loss.group(1) if loss else "-"
    if r > 0:
        return f"✅ <b>Ping {esc(host)}</b> → {r}/3 Balasan · Rata² {a} ms (Loss {l}%)."
    return f"❌ <b>Ping {esc(host)}</b> → Tidak Ada Balasan (Loss {l}%)."


def net_trace(host):
    out = run(["traceroute", "-w", "1", "-q", "1", "-m", "15", host], timeout=30)
    if not out:
        return f"❌ <b>Trace {esc(host)}</b> → Gagal."
    ips = re.findall(r"\((\d+\.\d+\.\d+\.\d+)\)", out)
    if not ips:
        ips = re.findall(r"^\s*\d+\s+(\d+\.\d+\.\d+\.\d+)", out, re.M)
    if not ips:
        return f"❌ <b>Trace {esc(host)}</b> → Tidak Terjangkau."
    hops = "\n".join(f"   → {ip}" for ip in ips[:15])
    return f"🛰 <b>Trace {esc(host)}</b> → {len(ips)} Hop\n{hops}"


def net_dns(host):
    out = run(["nslookup", host])
    if not out:
        return f"❌ <b>DNS {esc(host)}</b> → Gagal."
    srv = re.search(r"Server:\s+(\S+)", out)
    addrs = [a for a in re.findall(r"Address:\s*(\S+)", out)
             if not srv or not a.startswith(srv.group(1))]
    if not addrs:
        return f"❌ <b>DNS {esc(host)}</b> → Tidak Ditemukan."
    return f"🔍 <b>DNS {esc(host)}</b> → " + ", ".join(addrs[:4])


def net_speedtest():
    try:
        out = run(["speedtest-go", "--json"], timeout=80)
        d = json.loads(out or "{}")
        servers = d.get("servers", []) or []
        if not servers:
            return "⚠️ <i>Speedtest gagal (server tidak ditemukan).</i>"
        s = servers[0]
        ui = d.get("user_info", {}) or {}
        lat = s.get("latency", 0) / 1e6 or 0
        jit = s.get("jitter", 0) / 1e6 or 0
        dl = s.get("dl_speed", 0) or 0
        ul = s.get("ul_speed", 0) or 0
        name = s.get("name", "?")
        sponsor = s.get("sponsor", "")
        country = s.get("country", "")
        isp = ui.get("Isp", "?")
        ip = ui.get("IP", "?")
        return (f"🖥 <b>Server :</b> {esc(name)} ({esc(country)})" + (f" — {esc(sponsor)}" if sponsor else "") + "\n"
                f"📡 <b>ISP :</b> {esc(isp)}\n"
                f"🌐 <b>IP :</b> {esc(ip)}\n\n"
                f"📶 <b>Ping :</b> {lat:.0f} ms 🔀 <b>Jitter :</b> {jit:.1f} ms\n"
                f"⬇️ <b>Download :</b> {dl * 8 / 1e6:.1f} Mbps ⬆️ <b>Upload :</b> {ul * 8 / 1e6:.1f} Mbps")
    except Exception as e:
        return f"⚠️ Speedtest gagal: {esc(str(e)[:80])}"


def storage_text():
    out = run("df -h")
    rows = []
    for ln in out.splitlines()[1:]:
        p = ln.split()
        if len(p) >= 6:
            mnt = p[5]
            if len(mnt) > 26:
                mnt = mnt[:26] + ".."
            rows.append(f"💽 {esc(mnt)} {p[2]}/{p[1]} ({p[4]})")
    return "\n".join(rows[:10]) if rows else "💽 <i>Tidak Terbaca.</i>"


def firewall_text():
    n4 = run(["nft", "list", "ruleset"]) or ""
    tables = len(re.findall(r"table \w+ \w+", n4))
    chains = len(re.findall(r"\n\tchain \S+", n4))
    rules = len(re.findall(r"\n\s+(accept|drop|reject|return|jump|snat|dnat|masquerade|log|limit|counter|notrack)", n4))
    return (f"• Tabel: {tables}\n"
            f"• Chain: {chains}\n"
            f"• Rule: {rules}")


def ssh_sessions_text():
    out = run("netstat -tn 2>/dev/null | grep ':22 ' | grep ESTABLISHED")
    if not out:
        return "🖥 Tidak Ada Sesi Aktif."
    seen = set()
    peers = []
    for ln in out.splitlines():
        p = ln.split()
        peer = p[4].rsplit(":", 1)[0] if len(p) > 4 else "?"
        if peer not in seen:
            seen.add(peer)
            peers.append(f"• <code>{peer}</code>")
    return "\n".join(peers) if peers else "🖥 Tidak Ada Sesi Aktif."


def suhu_text():
    t = get_cpu_temp()
    if t is None:
        return "🌡 <i>Sensor Suhu Tidak Terbaca.</i>"
    return f"🌡 {t:.1f}°C" + (" 🔥 <b>PANAS!</b>" if t >= TEMP_ALERT_C else "")


def host_to_mac(arg):
    a = (arg or "").strip().lower()
    for d in parse_dhcp_leases():
        if d["ip"] == a or d["host"].lower() == a or d["mac"].lower() == a:
            return d["mac"]
    return None


def _blk_result(macn):
    r = block_client(macn)
    head = f"🚫 {macn} Sudah Di Block." if r == "sudah diblokir" else f"🚫 {macn} Berhasil Di Block."
    return head + "\n\n" + klien_text()


def _unblk_result(macn):
    r = unblock_client(macn)
    head = f"⚠️ {macn} Tidak Ditemukan." if r == "tidak ditemukan" else f"✅ {macn} Berhasil Di Unblock."
    return head + "\n\n" + klien_text()


def block_gate(arg):
    mac = host_to_mac(arg)
    if not mac:
        return f"⚠️ <code>{esc(arg)}</code> tidak ditemukan di lease DHCP."
    return _blk_result(mac.replace(":", "").upper())


def unblock_gate(arg):
    mac = host_to_mac(arg)
    if not mac:
        return f"⚠️ <code>{esc(arg)}</code> tidak ditemukan di lease DHCP."
    return _unblk_result(mac.replace(":", "").upper())


# ================= JADWAL BANDIX =================
def sched_list():
    try:
        d = ubus("luci.bandix", "getScheduleLimits")
        lims = (d.get("data", {}) or {}).get("limits", []) or []
        return lims if isinstance(lims, list) else []
    except Exception as e:
        logger.error(f"sched list gagal: {e}")
        return []


def sched_add(mac, start, end, days, down_bps, up_bps):
    import json as _j
    try:
        r = ubus("luci.bandix", "setScheduleLimit", {
            "mac": mac, "start_time": start, "end_time": end,
            "days": _j.dumps(sorted(days)),
            "wan_rx_rate_limit": int(down_bps), "wan_tx_rate_limit": int(up_bps)})
        if r.get("success") is True or r.get("status") == "success":
            return True, ""
        return False, str(r)[:150]
    except Exception as e:
        return False, str(e)[:150]


def sched_del(rule_id):
    try:
        r = ubus("luci.bandix", "deleteScheduleLimit", {"id": str(rule_id)})
        if r.get("success") is True or r.get("status") == "success":
            return True
        return False
    except Exception:
        return False


def sched_rule_text(r):
    import json as _j
    ts = r.get("time_slot") or {}
    start = ts.get("start") or r.get("start_time") or "?"
    end = ts.get("end") or r.get("end_time") or "?"
    days = ts.get("days")
    if days is None:
        raw = r.get("days")
        try:
            days = _j.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            days = []
    days = days or []
    dn = ",".join(DAY_ID.get(int(x), str(x)) for x in days) if days else "-"
    def lim(v):
        try:
            v = int(v or 0)
        except Exception:
            v = 0
        return "♾" if v <= 0 else f"{v // 1024}KB/s"
    mac = r.get("mac", "?")
    host = None
    for d in parse_dhcp_leases():
        if d["mac"].lower() == str(mac).lower():
            host = d["host"]
            break
    who = f"{host} (<code>{mac}</code>)" if host else f"<code>{mac}</code>"
    return (f"• {who}\n  ⏰ {start}–{end} • {dn}\n"
            f"  ↓ {lim(r.get('wan_rx_rate_limit'))}   ↑ {lim(r.get('wan_tx_rate_limit'))}")


def valid_hhmm(t):
    import re as _re
    m = _re.match(r"^(\d{1,2}):(\d{2})$", (t or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return f"{h:02d}:{mi:02d}"
    return None


def day_buttons(sel):
    rows, row = [], []
    for i in range(1, 8):
        mark = "✅" if i in sel else "▫️"
        row.append(InlineKeyboardButton(f"{mark}{DAY_ID[i]}", callback_data=f"day_{i}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✅ Selesai", callback_data="days_done"),
                 InlineKeyboardButton("❌ Batal", callback_data="sch_cancel")])
    return rows


# ================= PANEL & TOMBOL =================
def main_buttons():
    items = []
    if ENABLED_COMMANDS.get("status"):
        items.append(("📊 Status", "menu_status"))
    if ENABLED_COMMANDS.get("internet"):
        items.append(("🌐 Internet", "menu_internet"))
    if ENABLED_COMMANDS.get("devices"):
        items.append(("👥 Klien", "menu_klien"))
    if ENABLED_COMMANDS.get("docker"):
        items.append(("🐳 Docker", "menu_docker"))
    if ENABLED_COMMANDS.get("tools"):
        items.append(("📡 Tools", "menu_jaringan"))
    if ENABLED_COMMANDS.get("firewall") or ENABLED_COMMANDS.get("sistem"):
        items.append(("🔥 Keamanan", "menu_keamanan"))
    if ENABLED_COMMANDS.get("momo") or ENABLED_COMMANDS.get("tailscale"):
        items.append(("🛡 Layanan", "menu_layanan"))
    if ENABLED_COMMANDS.get("sistem"):
        items.append(("⚙ Sistem", "menu_sistem"))
    rows = []
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(items[i][0], callback_data=items[i][1])]
        if i + 1 < len(items):
            row.append(InlineKeyboardButton(items[i + 1][0], callback_data=items[i + 1][1]))
        rows.append(row)
    return rows


def build_main_menu_keyboard():
    kb = main_buttons() + [[InlineKeyboardButton("📚 Menu", callback_data="menu_main")]]
    return InlineKeyboardMarkup(kb)

# ================= HANDLER PANEL =================
async def need_auth_rate(update, target, feat=None):
    if not check_authorization_manual(update, target):
        return False
    # callback sudah di-rate-limit di button_callback; hindari double-hit
    if update.callback_query is None:
        if not await rate_ok(update, target):
            return False
    if feat and not check_enabled_manual(feat, target):
        return False
    return True


def greeting():
    """Salam sesuai jam."""
    try:
        h = int(time.strftime("%H"))
    except Exception:
        return "Halo"
    if 4 <= h < 11:
        return "Selamat Pagi"
    if 11 <= h < 15:
        return "Selamat Siang"
    if 15 <= h < 19:
        return "Selamat Sore"
    return "Selamat Malam"


START_DATA_CACHE = {"ts": 0, "data": None}
START_TTL = 10


def start_data_cached():
    """Semua data /start, di-cache (hemat baca disk + ubus berulang)."""
    now = time.monotonic()
    if now - START_DATA_CACHE["ts"] < START_TTL and START_DATA_CACHE["data"]:
        return START_DATA_CACHE["data"]
    try:
        klien = get_client_count()
    except Exception:
        klien = 0
    data = {
        "pub": public_ip_dual(),
        "mem": get_mem(),
        "temp": get_cpu_temp(),
        "disk": get_disk(),
        "swap": get_swap(),
        "klien": klien,
        "tailscale": tailscale_counts(),
        "trafik": daily_traffic(),
    }
    START_DATA_CACHE.update(ts=now, data=data)
    return data


async def handle_start(update, context):
    target = update.message if update.message else update.callback_query.message
    if not await need_auth_rate(update, target):
        return
    name = ""
    try:
        if update.effective_user and update.effective_user.first_name:
            name = f", {update.effective_user.first_name.title()}"
    except Exception:
        pass
    data = await asyncio.to_thread(start_data_cached)
    pub = data["pub"]
    pct = data["mem"][2] if data["mem"] else 0
    temp = data["temp"]
    dpct = data["disk"][2] if data["disk"] else 0
    klien = data["klien"]
    ts = data["tailscale"]
    traf = data["trafik"]
    swap = data["swap"]

    wan_ip = html_esc(pub.get("wan_ip") or "-")
    wan_isp = html_esc(pub.get("wan_isp") or "-")
    vpn_ip = html_esc(pub.get("vpn_ip") or "-")
    vpn_isp = html_esc(pub.get("vpn_isp") or "-")
    temp_s = f"{temp:.0f}°C" if temp is not None else "-"

    stats = f"🌡 CPU {temp_s} · 🧠 RAM {pct:.0f}% · 💽 Disk {dpct:.0f}%"
    swap_s = f"💱 Swap {swap[0]:.0f}MB" if swap is not None and swap[0] > 0 else ""
    ts_s = f"{ts[0]}/{ts[1]} Online" if ts else "-"
    traf_s = f"⬇️ {fmt_bytes(traf[0])} · ⬆️ {fmt_bytes(traf[1])}" if traf else ""
    line2 = " · ".join(p for p in (swap_s, traf_s) if p) or "-"

    header = "🤖 <b>BITS Networks</b>"
    mid = "\n".join([
        f"👋 {html_esc(greeting())}{html_esc(name)}!",
        "",
        f"🖥️ BITS-WRT 🟢 Online · {html_esc(get_uptime_precise())}",
        "",
        f"🌐 <b>WAN :</b> <code>{wan_ip}</code> · {wan_isp}",
        f"🛡 <b>VPN :</b> <code>{vpn_ip}</code> · {vpn_isp}",
        "",
        f"🔀 <b>Uplink :</b> {uplink_text()}",
        f"👥 <b>Klien :</b> {klien} Online",
        f"🌀 <b>Tailscale :</b> {ts_s}",
        "",
        stats,
        line2,
    ])
    footer = "📋 <i>Silakan Pilih Menu Di Bawah Ini.</i>"
    div = div_for(header, *mid.split("\n"), footer)
    body = f"{header}\n{div}\n{mid}\n{div}\n{footer}"
    try:
        await target.reply_text(body, parse_mode="HTML",
                                reply_markup=InlineKeyboardMarkup(main_buttons()))
    except Exception as e:
        logger.error(f"Start gagal: {e}")


async def handle_status(update, context, query=None):
    target = update.message if update.message else update.callback_query.message
    if not await need_auth_rate(update, target, "status"):
        return
    await asyncio.to_thread(public_ip_dual)
    body = status_text_cached()
    if query:
        await show_panel(query, "📊 Status Router", body,
                         [[InlineKeyboardButton("🔄 Refresh", callback_data="menu_status")],
                          *btn_main_menu()])
    else:
        await send(target, panel_text("📊 Status Router", body))


async def handle_internet(update, context, query=None):
    target = update.message if update.message else update.callback_query.message
    if not await need_auth_rate(update, target, "internet"):
        return
    body = await asyncio.to_thread(internet_text)
    if query:
        await show_panel(query, "🌐 Internet", body,
                         [[InlineKeyboardButton("🔄 Refresh", callback_data="menu_internet")],
                          *btn_main_menu()])
    else:
        await send(target, panel_text("🌐 Internet", body))


async def handle_momo(update, context, query=None):
    target = update.message if update.message else update.callback_query.message
    if not await need_auth_rate(update, target, "momo"):
        return
    body = momo_text()
    btns = [[InlineKeyboardButton("🔄 Refresh", callback_data="menu_momo"),
             InlineKeyboardButton("🧹 Clear Log", callback_data="act_momo_clear")],
            [InlineKeyboardButton("♻ Restart Momo", callback_data="act_momo_restart")],
            *btn_main_menu()]
    if query:
        await show_panel(query, "🛡 Momo VPN", body, btns)
    else:
        await send(target, panel_text("🛡 Momo VPN", body),
                   reply_markup=InlineKeyboardMarkup(btns))


async def handle_tailscale(update, context, query=None):
    target = update.message if update.message else update.callback_query.message
    if not await need_auth_rate(update, target, "tailscale"):
        return
    body = await asyncio.to_thread(tailscale_text)
    btns = [[InlineKeyboardButton("🔄 Refresh", callback_data="menu_tailscale"),
             InlineKeyboardButton("♻ Restart", callback_data="act_ts_restart")],
            *btn_main_menu()]
    if query:
        await show_panel(query, "🌀 Tailscale", body, btns)
    else:
        await send(target, panel_text("🌀 Tailscale", body),
                   reply_markup=InlineKeyboardMarkup(btns))


async def handle_klien(update, context, query=None):
    target = update.message if update.message else update.callback_query.message
    if not await need_auth_rate(update, target, "devices"):
        return
    devs = parse_dhcp_leases()
    try:
        devs.sort(key=lambda d: list(map(int, d["ip"].split("."))))
    except Exception:
        pass
    blocked = blocked_macs()
    body = klien_text()
    btns = []
    for d in devs[:8]:
        mac_n = d["mac"].replace(":", "").upper()
        if len(mac_n) != 12:
            continue
        if mac_n in blocked:
            btns.append([InlineKeyboardButton(f"✅ {d['ip']}", callback_data=f"unblk_{mac_n}")])
        else:
            btns.append([InlineKeyboardButton(f"🚫 {d['ip']}", callback_data=f"blk_{mac_n}")])
    btns.append([InlineKeyboardButton("🔄 Refresh", callback_data="menu_klien"),
                 InlineKeyboardButton("⏰ Jadwal", callback_data="menu_sched")])
    btns += btn_main_menu()
    if query:
        await show_panel(query, "👥 Klien", body, btns)
    else:
        await send(target, panel_text("👥 Klien", body),
                   reply_markup=InlineKeyboardMarkup(btns))


async def handle_sched(update, context, query=None):
    target = update.message if update.message else update.callback_query.message
    if not await need_auth_rate(update, target, "jadwal"):
        return
    lims = await asyncio.to_thread(sched_list)
    if lims:
        body = "⏰ <b>Aturan Jadwal Aktif :</b>\n\n" + "\n\n".join(sched_rule_text(r) for r in lims)
    else:
        body = "⏰ <b>Belum Ada Pengaturan Jadwal.</b>\n\n🏠 Atur Limit Speed & Waktu Internet."
    btns = []
    for i, r in enumerate(lims[:6]):
        rid = str(r.get("id", "") or "")
        btns.append([InlineKeyboardButton(f"🗑 Hapus #{i + 1}", callback_data=f"schdel_{rid}")])
    btns.append([InlineKeyboardButton("➕ Tambah Aturan", callback_data="sch_add")])
    btns.append([InlineKeyboardButton("👥 Klien", callback_data="menu_klien")])
    btns += btn_main_menu()
    if query:
        await show_panel(query, "⏰ Jadwal", body, btns)
    else:
        await send(target, panel_text("⏰ Jadwal", body),
                   reply_markup=InlineKeyboardMarkup(btns))


async def handle_sistem(update, context, query=None):
    target = update.message if update.message else update.callback_query.message
    if not await need_auth_rate(update, target, "sistem"):
        return
    body = "Pilih Menu Yang Ingin Digunakan"
    btns = [[InlineKeyboardButton("💽 Storage", callback_data="menu_storage"),
             InlineKeyboardButton("🌡 Suhu", callback_data="menu_suhu")],
            [InlineKeyboardButton("🧹 Cleanup RAM", callback_data="act_cleanup"),
             InlineKeyboardButton("📜 Lihat Log", callback_data="act_log")],
            [InlineKeyboardButton("💾 Backup", callback_data="act_backup"),
             InlineKeyboardButton("🔄 Reboot", callback_data="reboot_prompt")],
            *btn_main_menu()]
    if query:
        await show_panel(query, "⚙ Sistem", body, btns)
    else:
        await send(target, panel_text("⚙ Sistem", body),
                   reply_markup=InlineKeyboardMarkup(btns))

async def handle_docker(update, context, query=None):
    target = update.message if update.message else update.callback_query.message
    if not await need_auth_rate(update, target, "docker"):
        return
    body = await asyncio.to_thread(docker_text)
    btns = [[InlineKeyboardButton("📈 Stats", callback_data="menu_docker_stats"),
             InlineKeyboardButton("💿 Images", callback_data="menu_docker_images")],
            [InlineKeyboardButton("🧹 Prune", callback_data="act_docker_prune")],
            *btn_main_menu()]
    if query:
        await show_panel(query, "🐳 Container", body, btns)
    else:
        await send(target, panel_text("🐳 Container", body),
                   reply_markup=InlineKeyboardMarkup(btns))


async def cmd_docker(update, context):
    target = update.message
    if not await need_auth_rate(update, target, "docker"):
        return
    args = context.args or []
    if not args:
        body = await asyncio.to_thread(docker_text)
        await send(target, panel_text("🐳 Container", body))
        return
    op = args[0].lower()
    if op in ("start", "stop", "restart"):
        if len(args) < 2:
            await send(target, f"⚠️ Contoh: <code>/docker {op} &lt;nama&gt;</code>")
            return
        await send(target, await asyncio.to_thread(docker_ctl, op, args[1]))
    elif op == "logs":
        if len(args) < 2:
            await send(target, "⚠️ Contoh: <code>/docker logs &lt;nama&gt;</code>")
            return
        await send(target, await asyncio.to_thread(docker_logs, args[1]))
    elif op == "stats":
        await send(target, panel_text("📈 Docker Stats", await asyncio.to_thread(docker_stats_text)))
    elif op == "images":
        await send(target, panel_text("💿 Images", await asyncio.to_thread(docker_images_text)))
    elif op == "prune":
        await send(target, await asyncio.to_thread(docker_prune))
    else:
        await send(target, "⚠️ Pakai: /docker, /docker start|stop|restart &lt;nama&gt;, /docker logs &lt;nama&gt;, /docker stats, /docker images, /docker prune")


def _tool_handler(feat, label, func):
    async def h(update, context):
        target = update.message
        if not await need_auth_rate(update, target, feat):
            return
        arg = " ".join(context.args or []) if context.args else ""
        if not arg:
            await send(target, f"⚠️ Contoh: <code>/{label} &lt;host&gt;</code>" if feat == "tools" else f"⚠️ Contoh: <code>/{label} &lt;arg&gt;</code>")
            return
        await send(target, await asyncio.to_thread(func, arg))
    return h


cmd_ping = _tool_handler("tools", "ping", net_ping)
cmd_trace = _tool_handler("tools", "trace", net_trace)
cmd_dns = _tool_handler("tools", "dns", net_dns)
cmd_blokir = _tool_handler("devices", "blokir", block_gate)
cmd_buka = _tool_handler("devices", "buka", unblock_gate)


async def cmd_speedtest(update, context):
    target = update.message
    if not await need_auth_rate(update, target, "tools"):
        return
    await send(target, "🚀 <b>Speedtest…</b> Tunggu Sebentar.")
    await send(target, panel_text("🚀 Speedtest", await asyncio.to_thread(net_speedtest)))


async def cmd_storage(update, context):
    target = update.message
    if not await need_auth_rate(update, target, "sistem"):
        return
    await send(target, panel_text("💽 Storage", await asyncio.to_thread(storage_text)))


async def cmd_suhu(update, context):
    target = update.message
    if not await need_auth_rate(update, target, "sistem"):
        return
    await send(target, suhu_text())


async def cmd_firewall(update, context):
    target = update.message
    if not await need_auth_rate(update, target, "firewall"):
        return
    body = firewall_text()
    await send(target, panel_text("🔥 Firewall", body),
               reply_markup=InlineKeyboardMarkup(
                   [[InlineKeyboardButton("♻ Restart Firewall", callback_data="act_fw_restart")],
                    *btn_main_menu()]))


async def cmd_ssh(update, context):
    target = update.message
    if not await need_auth_rate(update, target, "sistem"):
        return
    await send(target, panel_text("🖥 Sesi SSH", await asyncio.to_thread(ssh_sessions_text)))


def act_fw_restart():
    run("/etc/init.d/firewall restart")
    time.sleep(3)
    return "♻ <b>Firewall di-restart.</b>\n\n" + firewall_text()


# kompatibilitas perintah lama
async def status(update, context):
    await handle_status(update, context)


async def devices(update, context):
    await handle_klien(update, context)


async def help_command(update, context):
    await handle_start(update, context)

# ================= AKSI =================
async def do_action(query, target, label, func, *args):
    try:
        await query.edit_message_text(f"⏳ <b>{esc(label)}…</b>", parse_mode="HTML")
    except Exception:
        pass
    try:
        result = await asyncio.to_thread(func, *args)
    except Exception as e:
        logger.error(f"Aksi {label} gagal: {e}")
        result = f"❌ Gagal: {esc(str(e)[:120])}"
    try:
        await query.edit_message_text(result, parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup(btn_main_menu()))
    except Exception as e:
        logger.error(f"Edit hasil aksi gagal: {e}")


def act_cleanup():
    run("sync && sysctl -w vm.drop_caches=3 >/dev/null 2>&1")
    return "🧹 <b>Cleanup Selesai</b>"


def act_log():
    out = run("logread 2>/dev/null | tail -n 60")
    if not out:
        return "📜 <i>Log Kosong.</i>"
    lines = out.splitlines()
    err = sum(1 for l in lines if "err " in l or "error" in l.lower())
    warn = sum(1 for l in lines if "warn" in l)
    last = [re.sub(r"^\S+\s+\S+\s+\S+\s+", "", l) for l in lines[-5:]]
    body = "\n".join(f"<code>{esc(l)[:100]}</code>" for l in last)
    text = f"🔥 <b>Error :</b> {err} 🛡 <b>Warning :</b> {warn}\n\n{body}"
    return panel_text("📜 Ringkasan Log", text)


def act_backup():
    fn = f"/tmp/bits-backup-{time.strftime('%Y%m%d-%H%M')}.tar.gz"
    r = run(f"sysupgrade -b {fn} 2>&1 | tail -n 3")
    if not os.path.exists(fn):
        return f"❌ Backup gagal:\n<pre>{esc(r[:300])}</pre>"
    return f"OK:{fn}"


def act_momo(op):
    if op == "restart":
        run("/etc/init.d/momo restart")
        time.sleep(6)
        return "♻ <b>Momo di-restart.</b>\n\n" + momo_text()
    run("/etc/init.d/momo clear_logs")
    return "🧹 <b>Log Momo dibersihkan.</b>"


def act_ts_restart():
    run("/etc/init.d/tailscale restart")
    time.sleep(6)
    return "♻ <b>Tailscale di-restart.</b>\n\n" + tailscale_text()


async def execute_reboot_command(update, context):
    query = update.callback_query
    if not is_allowed(query.from_user.id):
        return
    try:
        await query.edit_message_text("🔄 <b>Reboot…</b> router mati ~1 menit, bot kembali otomatis.",
                                      parse_mode="HTML")
    except Exception as e:
        logger.error(f"Reboot confirm edit gagal: {e}")
    run(["reboot"])
    logger.info("Perintah reboot dieksekusi.")


async def reboot_prompt(update, context):
    target = update.message if update.message else update.callback_query.message
    if not await need_auth_rate(update, target, "reboot"):
        return
    kb = [[InlineKeyboardButton("✅ Ya, Reboot", callback_data="reboot_confirm"),
           InlineKeyboardButton("❌ Batal", callback_data="menu_sistem")]]
    await send(target, "⚠️ <b>Reboot router sekarang?</b> Koneksi putus ±1 menit.",
               reply_markup=InlineKeyboardMarkup(kb))

# ================= CALLBACK =================
async def button_callback(update, context):
    query = update.callback_query
    cmd = query.data or ""
    if not is_allowed(query.from_user.id):
        try:
            await query.answer("🔒 Akses ditolak.", show_alert=True)
        except Exception:
            pass
        return
    try:
        await query.answer()
    except Exception:
        pass
    if not await rate_ok(update, query.message):
        return
    logger.info(f"CALLBACK: {cmd}")
    _feat = None
    if cmd in ("act_cleanup", "act_log", "act_backup"):
        _feat = "sistem"
    elif cmd in ("act_momo_restart", "act_momo_clear"):
        _feat = "momo"
    elif cmd == "act_ts_restart":
        _feat = "tailscale"
    elif cmd.startswith("blk_") or cmd.startswith("unblk_"):
        _feat = "devices"
    elif (cmd == "menu_sched" or cmd.startswith(("sch_", "schdel_", "day_"))
          or cmd in ("days_done", "sch_save", "sch_cancel")):
        _feat = "jadwal"
    elif cmd in ("menu_docker", "menu_docker_stats", "menu_docker_images", "act_docker_prune"):
        _feat = "docker"
    elif cmd in ("act_fw_restart", "menu_firewall"):
        _feat = "firewall"
    elif cmd == "menu_jaringan" or cmd.startswith("tool_") or cmd == "act_speedtest":
        _feat = "tools"
    elif cmd in ("menu_ssh", "menu_storage", "menu_suhu"):
        _feat = "sistem"
    if _feat and not ENABLED_COMMANDS.get(_feat, True):
        try:
            await query.answer("⚙️ Fitur ini dimatikan di LuCI.", show_alert=True)
        except Exception:
            pass
        return

    m = query.message
    try:
        if m.from_user is None:
            m.from_user = query.from_user
    except Exception:
        pass
    tu = Update(update_id=update.update_id, message=m, callback_query=query)

    if cmd in ("menu_main", "start"):
        await handle_start(tu, context)
        return
    if cmd == "menu_status":
        await handle_status(tu, context, query)
        return
    if cmd == "menu_internet":
        await handle_internet(tu, context, query)
        return
    if cmd == "menu_momo":
        await handle_momo(tu, context, query)
        return
    if cmd == "menu_tailscale":
        await handle_tailscale(tu, context, query)
        return
    if cmd == "menu_klien":
        await handle_klien(tu, context, query)
        return
    if cmd == "menu_sistem":
        await handle_sistem(tu, context, query)
        return
    if cmd == "menu_docker":
        await handle_docker(tu, context, query)
        return
    if cmd == "menu_docker_stats":
        body = await asyncio.to_thread(docker_stats_text)
        await show_panel(query, "📈 Docker Stats", body,
                         [[InlineKeyboardButton("🐳 Kembali", callback_data="menu_docker")],
                          *btn_main_menu()])
        return
    if cmd == "menu_docker_images":
        body = await asyncio.to_thread(docker_images_text)
        await show_panel(query, "💿 Images", body,
                         [[InlineKeyboardButton("🐳 Kembali", callback_data="menu_docker")],
                          *btn_main_menu()])
        return
    if cmd == "act_docker_prune":
        await do_action(query, query.message, "Prune docker", docker_prune)
        return
    if cmd == "act_fw_restart":
        await do_action(query, query.message, "Restart firewall", act_fw_restart)
        return
    if cmd == "menu_firewall":
        body = firewall_text()
        await show_panel(query, "🔥 Firewall", body,
                         [[InlineKeyboardButton("♻ Restart Firewall", callback_data="act_fw_restart")],
                          *btn_main_menu()])
        return
    if cmd == "menu_jaringan":
        await show_panel(query, "📡 Tools", "Pilih Tools Yang Ingin Digunakan.",
                         [[InlineKeyboardButton("📶 Ping", callback_data="tool_ping"),
                           InlineKeyboardButton("🛰 Trace", callback_data="tool_trace")],
                          [InlineKeyboardButton("🔍 DNS", callback_data="tool_dns"),
                           InlineKeyboardButton("🚀 Speedtest", callback_data="act_speedtest")],
                          *btn_main_menu()])
        return
    if cmd in ("tool_ping", "tool_trace", "tool_dns"):
        uid = query.from_user.id
        tool = {"tool_ping": "ping", "tool_trace": "trace", "tool_dns": "dns"}[cmd]
        title = {"ping": "📶 Ping", "trace": "🛰 Trace", "dns": "🔍 DNS"}[tool]
        WIZ[uid] = {"step": "tool_host", "tool": tool}
        try:
            await query.edit_message_text(
                f"<b>{title}</b>\n{DIV}\nKirim <b>IP/Host</b>. Contoh: <code>8.8.8.8</code> atau <code>google.com</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Batal", callback_data="menu_jaringan")]]))
        except Exception:
            pass
        return
    if cmd == "act_speedtest":
        try:
            await query.edit_message_text("🚀 <b>Speedtest…</b> Tunggu Sebentar.", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Speedtest edit awal gagal: {e}")
        res = panel_text("🚀 Speedtest", await asyncio.to_thread(net_speedtest))
        try:
            await query.edit_message_text(res, parse_mode="HTML",
                                          reply_markup=InlineKeyboardMarkup(btn_main_menu()))
        except Exception as e:
            logger.error(f"Speedtest edit hasil gagal: {e}")
            try:
                await query.message.reply_text(res, parse_mode="HTML",
                                              reply_markup=InlineKeyboardMarkup(btn_main_menu()))
            except Exception as e2:
                logger.error(f"Speedtest kirim hasil gagal: {e2}")
        return
    if cmd == "menu_keamanan":
        btns = []
        if ENABLED_COMMANDS.get("firewall"):
            btns.append([InlineKeyboardButton("🧱 Firewall", callback_data="menu_firewall")])
        if ENABLED_COMMANDS.get("sistem"):
            btns.append([InlineKeyboardButton("🖥 Sesi SSH", callback_data="menu_ssh")])
        btns += btn_main_menu()
        await show_panel(query, "🔥 Keamanan", "Pilih info keamanan.", btns)
        return
    if cmd == "menu_ssh":
        await show_panel(query, "🖥 Sesi SSH", await asyncio.to_thread(ssh_sessions_text), btn_main_menu())
        return
    if cmd == "menu_layanan":
        btns = []
        if ENABLED_COMMANDS.get("momo"):
            btns.append([InlineKeyboardButton("🛡 Momo", callback_data="menu_momo")])
        if ENABLED_COMMANDS.get("tailscale"):
            btns.append([InlineKeyboardButton("🌀 Tailscale", callback_data="menu_tailscale")])
        btns += btn_main_menu()
        await show_panel(query, "🛡 Layanan", "Pilih layanan.", btns)
        return
    if cmd == "menu_storage":
        await show_panel(query, "💽 Storage", await asyncio.to_thread(storage_text), btn_main_menu())
        return
    if cmd == "menu_suhu":
        await query.edit_message_text(suhu_text(), parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup(btn_main_menu()))
        return
    if cmd == "menu_sched":
        await handle_sched(tu, context, query)
        return
    if cmd == "sch_add":
        devs = parse_dhcp_leases()
        if not devs:
            try:
                await query.edit_message_text("👥 <i>Tidak ada klien aktif.</i>", parse_mode="HTML",
                                              reply_markup=InlineKeyboardMarkup(btn_main_menu()))
            except Exception:
                pass
            return
        uid = query.from_user.id
        WIZ[uid] = {"step": "client"}
        btns = []
        for d in devs[:10]:
            mac_n = d["mac"].replace(":", "").upper()
            if len(mac_n) == 12:
                btns.append([InlineKeyboardButton(f"⏰ {d['host']} ({d['ip']})",
                                                  callback_data=f"sch_{mac_n}")])
        btns.append([InlineKeyboardButton("❌ Batal", callback_data="sch_cancel")])
        btns += btn_main_menu()
        try:
            await query.edit_message_text(f"<b>⏰ Aturan Baru (1/5)</b>\n{DIV}\nPilih klien:",
                                          parse_mode="HTML",
                                          reply_markup=InlineKeyboardMarkup(btns))
        except Exception as e:
            logger.error(f"sch_add gagal: {e}")
        return
    if cmd.startswith("sch_") and len(cmd) == 16 and cmd[4:].isalnum():
        uid = query.from_user.id
        mac = ":".join(cmd[4:][i:i + 2] for i in range(0, 12, 2))
        WIZ[uid] = {"step": "start", "mac": mac}
        try:
            await query.edit_message_text(
                f"<b>⏰ Aturan Baru (2/5)</b>\n{DIV}\nKlien: <code>{mac}</code>\n\n"
                "Ketik <b>jam mulai</b> format 24 jam.\nContoh: <code>22:00</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Batal", callback_data="sch_cancel")]]))
        except Exception as e:
            logger.error(f"sch client gagal: {e}")
        return
    if cmd.startswith("day_") and cmd[4:].isdigit():
        uid = query.from_user.id
        st = WIZ.get(uid)
        if not st or st.get("step") != "days":
            return
        n = int(cmd[4:])
        if n in st["days"]:
            st["days"].discard(n)
        else:
            st["days"].add(n)
        sel = ",".join(DAY_ID[i] for i in sorted(st["days"])) or "-"
        try:
            await query.edit_message_text(
                f"<b>⏰ Aturan Baru (4/5)</b>\n{DIV}\nPilih hari, lalu Selesai.\nPilihan: <b>{sel}</b>",
                parse_mode="HTML", reply_markup=InlineKeyboardMarkup(day_buttons(st["days"])))
        except Exception:
            pass
        return
    if cmd == "days_done":
        uid = query.from_user.id
        st = WIZ.get(uid)
        if not st or st.get("step") != "days":
            return
        if not st["days"]:
            try:
                await query.answer("Pilih minimal 1 hari!", show_alert=True)
            except Exception:
                pass
            return
        st["step"] = "down"
        try:
            await query.edit_message_text(
                f"<b>⏰ Aturan Baru (5a/6)</b>\n{DIV}\nKetik <b>batas download KB/s</b>.\n<code>0</code> = tanpa batas.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Batal", callback_data="sch_cancel")]]))
        except Exception:
            pass
        return
    if cmd == "sch_save":
        uid = query.from_user.id
        st = WIZ.get(uid)
        if not st:
            return
        ok, err = await asyncio.to_thread(
            sched_add, st["mac"], st["start"], st["end"],
            st["days"], st["down"] * 1024, st["up"] * 1024)
        WIZ.pop(uid, None)
        dn = ",".join(DAY_ID[i] for i in sorted(st["days"]))
        if ok:
            txt = (f"✅ <b>Aturan tersimpan.</b>\n\n• <code>{st['mac']}</code>\n• ⏰ {st['start']}–{st['end']} • {dn}\n"
                   f"• ↓ {st['down']}KB/s {'(♾)' if st['down'] <= 0 else ''}  ↑ {st['up']}KB/s {'(♾)' if st['up'] <= 0 else ''}")
        else:
            txt = f"❌ <b>Gagal menyimpan:</b>\n<pre>{esc(err)[:200]}</pre>"
        try:
            await query.edit_message_text(txt, parse_mode="HTML",
                                          reply_markup=InlineKeyboardMarkup(
                                              [[InlineKeyboardButton("⏰ Lihat Jadwal",
                                                                     callback_data="menu_sched")],
                                               *btn_main_menu()]))
        except Exception as e:
            logger.error(f"sch_save gagal: {e}")
        return
    if cmd == "sch_cancel":
        WIZ.pop(query.from_user.id, None)
        await handle_sched(tu, context, query)
        return
    if cmd.startswith("schdel_") and len(cmd) > len("schdel_"):
        rid = cmd[len("schdel_"):]
        ok = bool(rid) and await asyncio.to_thread(sched_del, rid)
        txt = "🗑 <b>Aturan dihapus.</b>" if ok else "❌ <b>Gagal menghapus.</b>"
        try:
            await query.edit_message_text(txt, parse_mode="HTML",
                                          reply_markup=InlineKeyboardMarkup(
                                              [[InlineKeyboardButton("⏰ Kembali",
                                                                     callback_data="menu_sched")]]))
        except Exception:
            pass
        return
    if cmd == "status":
        await handle_status(tu, context, query)
        return
    if cmd == "devices":
        await handle_klien(tu, context, query)
        return
    if cmd == "reboot_prompt":
        await reboot_prompt(tu, context)
        return
    if cmd == "reboot_confirm":
        await execute_reboot_command(tu, context)
        return
    if cmd == "act_cleanup":
        await do_action(query, query.message, "Membersihkan RAM", act_cleanup)
        return
    if cmd == "act_log":
        await do_action(query, query.message, "Mengambil log", act_log)
        return
    if cmd == "act_backup":
        try:
            await query.edit_message_text("⏳ <b>Membuat backup…</b> ±30 detik.", parse_mode="HTML")
        except Exception:
            pass
        try:
            res = await asyncio.to_thread(act_backup)
        except Exception as e:
            res = f"❌ {e}"
        if res.startswith("OK:"):
            fn = res[3:]
            try:
                await query.edit_message_text("✅ <b>Backup jadi, mengunggah…</b>", parse_mode="HTML")
                with open(fn, "rb") as f:
                    await query.message.reply_document(
                        f, filename=os.path.basename(fn),
                        caption="💾 <b>Backup konfigurasi BITS-WRT</b>",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(btn_main_menu()))
                await query.edit_message_text("✅ <b>Backup terkirim.</b>", parse_mode="HTML",
                                              reply_markup=InlineKeyboardMarkup(btn_main_menu()))
            except Exception as e:
                logger.error(f"Kirim backup gagal: {e}")
                try:
                    await query.edit_message_text(f"❌ <b>Upload gagal:</b> {esc(str(e)[:150])}",
                                                  parse_mode="HTML",
                                                  reply_markup=InlineKeyboardMarkup(btn_main_menu()))
                except Exception:
                    pass
            finally:
                try:
                    os.remove(fn)
                except Exception:
                    pass
        else:
            try:
                await query.edit_message_text(res, parse_mode="HTML",
                                              reply_markup=InlineKeyboardMarkup(btn_main_menu()))
            except Exception:
                pass
        return
    if cmd == "act_momo_restart":
        await do_action(query, query.message, "Restart Momo", act_momo, "restart")
        return
    if cmd == "act_momo_clear":
        await do_action(query, query.message, "Clear log Momo", act_momo, "clear")
        return
    if cmd == "act_ts_restart":
        await do_action(query, query.message, "Restart Tailscale", act_ts_restart)
        return
    if cmd.startswith("blk_") and len(cmd) == 16:
        mac = cmd[4:]
        await do_action(query, query.message, f"Blokir {mac}", lambda: _blk_result(mac))
        return
    if cmd.startswith("unblk_") and len(cmd) == 18:
        mac = cmd[6:]
        await do_action(query, query.message, f"Buka blokir {mac}", lambda: _unblk_result(mac))
        return
    logger.warning(f"Callback tidak dikenal: {cmd}")
    try:
        await query.message.reply_text("❓ Perintah tidak dikenal. Buka /start.",
                                       reply_markup=InlineKeyboardMarkup(btn_main_menu()))
    except Exception:
        pass

async def wizard_text(update, context):
    """Terima input teks saat wizard jadwal aktif."""
    if not update.message or not update.message.text:
        return
    uid = update.effective_user.id if update.effective_user else 0
    if not is_allowed(uid):
        return
    st = WIZ.get(uid)
    if not st:
        return
    if not await rate_ok(update, update.message):
        return
    text = update.message.text.strip()
    if text.lower() in ("batal", "cancel", "/cancel"):
        WIZ.pop(uid, None)
        await send(update.message, "❌ <i>Wizard dibatalkan.</i>")
        return
    step = st.get("step")
    if step == "tool_host":
        host = text.strip()
        if not host:
            await send(update.message, "⚠️ Kirim host/alamat, contoh <code>8.8.8.8</code>.")
            return
        WIZ.pop(uid, None)
        func = {"ping": net_ping, "trace": net_trace, "dns": net_dns}.get(st.get("tool"))
        if not func:
            return
        await send(update.message, await asyncio.to_thread(func, host))
        return
    if step == "start":
        v = valid_hhmm(text)
        if not v:
            await send(update.message, "⚠️ Format salah. Ketik jam <code>HH:MM</code>, contoh <code>22:00</code>.")
            return
        st["start"] = v
        st["step"] = "end"
        await send(update.message,
                   f"✅ Mulai: <b>{v}</b>\n\n<b>⏰ Aturan Baru (3/5)</b>\n{DIV}\nKetik <b>jam selesai</b>. Contoh: <code>06:00</code>")
        return
    if step == "end":
        v = valid_hhmm(text)
        if not v:
            await send(update.message, "⚠️ Format salah. Ketik jam <code>HH:MM</code>, contoh <code>06:00</code>.")
            return
        st["end"] = v
        st["step"] = "days"
        st["days"] = set()
        await send(update.message,
                   f"✅ {st['start']} → <b>{v}</b>\n\n<b>⏰ Aturan Baru (4/5)</b>\n{DIV}\nPilih hari:",
                   reply_markup=InlineKeyboardMarkup(day_buttons(set())))
        return
    if step == "down":
        if not text.isdigit():
            await send(update.message, "⚠️ Ketik angka KB/s, contoh <code>512</code>. <code>0</code> = tanpa batas.")
            return
        st["down"] = int(text)
        st["step"] = "up"
        await send(update.message,
                   f"✅ Download: <b>{text}KB/s</b>\n\n<b>⏰ Aturan Baru (5b/6)</b>\n{DIV}\n"
                   "Ketik <b>batas upload KB/s</b>. <code>0</code> = tanpa batas.")
        return
    if step == "up":
        if not text.isdigit():
            await send(update.message, "⚠️ Ketik angka KB/s, contoh <code>256</code>. <code>0</code> = tanpa batas.")
            return
        st["up"] = int(text)
        st["step"] = "confirm"
        dn = ",".join(DAY_ID[i] for i in sorted(st["days"]))
        kb = [[InlineKeyboardButton("✅ Simpan", callback_data="sch_save"),
               InlineKeyboardButton("❌ Batal", callback_data="sch_cancel")]]
        await send(update.message,
                   f"<b>⏰ Konfirmasi (6/6)</b>\n{DIV}\n• <code>{st['mac']}</code>\n"
                   f"• ⏰ {st['start']}–{st['end']} • {dn}\n"
                   f"• ↓ {st['down']}KB/s  ↑ {st['up']}KB/s",
                   reply_markup=InlineKeyboardMarkup(kb))
        return


# ================= POLLING & MONITOR =================
async def start_polling_task(context: ContextTypes.DEFAULT_TYPE):
    global is_polling_running
    try:
        if context.application.updater is None:
            is_polling_running = False
            return
        await context.application.updater.start_polling()
        is_polling_running = True
        logger.info("Polling dimulai.")
    except Exception as e:
        if "already running" in str(e).lower():
            is_polling_running = True
            logger.info("Polling sudah berjalan.")
        else:
            logger.error(f"Start polling gagal: {e}")
            is_polling_running = False


async def polling_management_loop(app: Application):
    global is_polling_running
    while True:
        load_config()
        try:
            running = bool(app.updater and app.updater.running)
        except Exception:
            running = False
        if not running:
            is_polling_running = False
            wan = get_wan_ip()
            ok = wan != "-" and "Unable" not in wan
            if ok and TOKEN and ALLOWED_USERS:
                logger.info("Internet OK, (re)start polling…")
                try:
                    if running:
                        await app.updater.stop()
                    app.job_queue.run_once(start_polling_task, 0, name="start_polling")
                except Exception as e:
                    logger.error(f"Trigger polling gagal: {e}")
            else:
                logger.warning("Menunggu internet/konfigurasi…")
        await asyncio.sleep(30)


async def notify_all(app: Application, text):
    for uid in ALLOWED_USERS:
        try:
            await app.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Notify {uid} gagal: {e}")


def daily_report_text():
    """Ringkasan harian (HTML) — beda dari snapshot /status."""
    _, _, rampct = get_mem()
    t = get_cpu_temp()
    tmax = MON_STATE.get("temp_max", 0) or (t or 0)
    klien = get_client_count()
    traf = daily_traffic()
    lines = [
        f"🕒 <b>Uptime :</b> {esc(get_uptime_precise())}",
        f"👥 <b>Klien :</b> {klien} Aktif",
    ]
    if traf:
        lines.append(f"📉 <b>Trafik :</b> ⬇️ {fmt_bytes(traf[0])} · ⬆️ {fmt_bytes(traf[1])}")
    devs = [d for d in bandix_devices() if str(d.get("conn", "")).lower() != "router"]
    if devs:
        top = sorted(devs, key=lambda d: float(d.get("t_rx_b", 0) or 0)
                     + float(d.get("t_tx_b", 0) or 0), reverse=True)[:3]
        tops = ", ".join(
            f"{esc(str(d.get('host') or d.get('ip4') or d.get('mac')))} "
            f"{fmt_bytes(float(d.get('t_rx_b', 0) or 0) + float(d.get('t_tx_b', 0) or 0))}"
            for d in top)
        lines.append(f"📈 <b>Top :</b> {tops}")
    lines.append(f"🌡 <b>Suhu Max :</b> {tmax:.1f}°C")
    lines.append(f"⏱ <b>WAN Putus :</b> {MON_STATE.get('wan_down', 0)}x")
    if MON_STATE.get("wan_down", 0) == 0 and tmax < TEMP_ALERT_C and rampct < RAM_ALERT_PCT:
        lines.append("✅ Semua Normal.")
    return "\n".join(lines)


async def monitor_loop(app: Application):
    """Notifikasi: WAN up/down, suhu tinggi, disk penuh, laporan harian 07:00."""
    await asyncio.sleep(60)
    while True:
        try:
            load_config()
            if not ENABLED_COMMANDS.get("monitor", True):
                await asyncio.sleep(60)
                continue
            today = time.strftime("%Y-%m-%d")
            if MON_STATE["daily_date"] != today:
                MON_STATE["daily_date"] = today
                MON_STATE["temp_max"] = 0
                MON_STATE["wan_down"] = 0
            d = ubus("network.interface.wan", "status")
            up = bool(d.get("up", False)) if d else get_wan_ip() != "-"
            if MON_STATE["wan_up"] is None:
                MON_STATE["wan_up"] = up
            elif up != MON_STATE["wan_up"]:
                MON_STATE["wan_up"] = up
                if not up:
                    MON_STATE["wan_down"] += 1
                await notify_all(app, "✅ <b>Internet tersambung kembali.</b>"
                                 if up else "🚨 <b>Internet PUTUS!</b> Cek modem Huawei & Momo.")
            t = get_cpu_temp()
            now = time.time()
            if t is not None:
                MON_STATE["temp_max"] = max(MON_STATE["temp_max"], t)
            if t and t >= TEMP_ALERT_C and now - MON_STATE["last_temp_alert"] > TEMP_COOLDOWN:
                MON_STATE["last_temp_alert"] = now
                await notify_all(app, f"🔥 <b>Suhu CPU {t:.1f}°C!</b> Pastikan ventilasi STB lancar.")
            _, _, dpct = get_disk()
            if dpct >= DISK_ALERT_PCT and now - MON_STATE["last_disk_alert"] > 86400:
                MON_STATE["last_disk_alert"] = now
                await notify_all(app, f"💽 <b>Overlay {dpct:.0f}% penuh!</b> Bersihkan log/paket.")
            _, _, rampct = get_mem()
            if rampct >= RAM_ALERT_PCT and now - MON_STATE["last_ram_alert"] > 1800:
                MON_STATE["last_ram_alert"] = now
                await notify_all(app, f"🧠 <b>RAM {rampct:.0f}% penuh!</b> Pertimbangkan cleanup/reboot.")
            cur_macs = {d["mac"].lower() for d in parse_dhcp_leases() if d["mac"]}
            if MON_STATE["macs"] and (cur_macs - MON_STATE["macs"]):
                new_macs = cur_macs - MON_STATE["macs"]
                new_devs = [f"• {d['host']} (<code>{d['ip']}</code>)" for d in parse_dhcp_leases()
                            if d["mac"].lower() in new_macs]
                if new_devs:
                    await notify_all(app, "📶 <b>Perangkat baru bergabung:</b>\n" + "\n".join(new_devs))
            MON_STATE["macs"] = cur_macs
            hm = time.strftime("%H:%M")
            if hm == "07:00" and MON_STATE["last_daily"] != today and TOKEN and ALLOWED_USERS:
                MON_STATE["last_daily"] = today
                await notify_all(app, f"🌅 <b>Laporan Harian</b>\n{DIV}\n{await asyncio.to_thread(daily_report_text)}")
        except Exception as e:
            logger.error(f"Monitor loop error: {e}")
        await asyncio.sleep(60)

# ================= MAIN =================
async def main():
    load_config()
    if not TOKEN or not ALLOWED_USERS:
        logger.warning("TOKEN/USER belum lengkap, menunggu konfigurasi…")
    if TOKEN:
        app = ApplicationBuilder().token(TOKEN).build()
        _cmds = [BotCommand("start", "🏠 Menu utama")]
        if ENABLED_COMMANDS.get("status"):
            _cmds.append(BotCommand("status", "📊 Status router"))
        if ENABLED_COMMANDS.get("internet"):
            _cmds.append(BotCommand("internet", "🌐 Internet & sinyal modem"))
        if ENABLED_COMMANDS.get("momo"):
            _cmds.append(BotCommand("momo", "🛡 Status & kontrol Momo"))
        if ENABLED_COMMANDS.get("tailscale"):
            _cmds.append(BotCommand("tailscale", "🌀 Status Tailscale"))
        if ENABLED_COMMANDS.get("devices"):
            _cmds.append(BotCommand("klien", "👥 Klien LAN"))
        if ENABLED_COMMANDS.get("sistem"):
            _cmds.append(BotCommand("sistem", "⚙ Perawatan sistem"))
        if ENABLED_COMMANDS.get("reboot"):
            _cmds.append(BotCommand("reboot", "🔄 Reboot router"))
        if ENABLED_COMMANDS.get("jadwal"):
            _cmds.append(BotCommand("jadwal", "⏰ Jadwal limit Bandix"))
        if ENABLED_COMMANDS.get("docker"):
            _cmds.append(BotCommand("docker", "🐳 Kontrol Docker"))
        if ENABLED_COMMANDS.get("tools"):
            _cmds.append(BotCommand("ping", "📶 Ping host"))
            _cmds.append(BotCommand("trace", "🛰 Traceroute host"))
            _cmds.append(BotCommand("dns", "🔍 Nslookup domain"))
            _cmds.append(BotCommand("speedtest", "🚀 Tes kecepatan"))
        if ENABLED_COMMANDS.get("sistem"):
            _cmds.append(BotCommand("storage", "💽 Disk usage"))
            _cmds.append(BotCommand("suhu", "🌡 Suhu CPU"))
            _cmds.append(BotCommand("ssh", "🖥 Sesi SSH aktif"))
        if ENABLED_COMMANDS.get("firewall"):
            _cmds.append(BotCommand("firewall", "🔥 Info firewall"))
        if ENABLED_COMMANDS.get("devices"):
            _cmds.append(BotCommand("blokir", "🚫 Blokir klien"))
            _cmds.append(BotCommand("buka", "✅ Buka blokir klien"))
        await app.bot.set_my_commands(_cmds)
        app.add_handler(CommandHandler("start", handle_start))
        app.add_handler(CommandHandler("status", handle_status))
        app.add_handler(CommandHandler("internet", handle_internet))
        app.add_handler(CommandHandler("momo", handle_momo))
        app.add_handler(CommandHandler("tailscale", handle_tailscale))
        app.add_handler(CommandHandler("klien", handle_klien))
        app.add_handler(CommandHandler("sistem", handle_sistem))
        app.add_handler(CommandHandler("reboot", reboot_prompt))
        app.add_handler(CommandHandler("jadwal", handle_sched))
        app.add_handler(CommandHandler("docker", cmd_docker))
        app.add_handler(CommandHandler("ping", cmd_ping))
        app.add_handler(CommandHandler("trace", cmd_trace))
        app.add_handler(CommandHandler("dns", cmd_dns))
        app.add_handler(CommandHandler("speedtest", cmd_speedtest))
        app.add_handler(CommandHandler("storage", cmd_storage))
        app.add_handler(CommandHandler("suhu", cmd_suhu))
        app.add_handler(CommandHandler("firewall", cmd_firewall))
        app.add_handler(CommandHandler("ssh", cmd_ssh))
        app.add_handler(CommandHandler("blokir", cmd_blokir))
        app.add_handler(CommandHandler("buka", cmd_buka))
        app.add_handler(CallbackQueryHandler(button_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_text))
        logger.info("Bot running.")
        await app.initialize()
        await app.start()
        global is_polling_running
        is_polling_running = False
        app.job_queue.run_once(start_polling_task, 0, name="initial_polling")
        asyncio.create_task(polling_management_loop(app))
        asyncio.create_task(monitor_loop(app))
        await asyncio.Event().wait()
        await app.shutdown()
    else:
        logger.warning("Tanpa TOKEN, polling management saja.")
        dummy = ApplicationBuilder().token("DUMMY").build()
        await dummy.initialize()
        asyncio.create_task(polling_management_loop(dummy))
        await asyncio.Event().wait()


if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except Exception as e:
            logger.critical(f"MAIN CRASH: {e}. Restart 10 dtk…")
            time.sleep(10)
