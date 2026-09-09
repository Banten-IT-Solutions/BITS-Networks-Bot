# BITS Networks Bot

[![Banten IT Solutions](https://img.shields.io/badge/Banten%20IT%20Solutions-BITS%20Networks%20Bot-00C853?style=for-the-badge&logo=telegram&logoColor=white)](https://bits.co.id)
[![OpenWrt](https://img.shields.io/badge/OpenWrt-00A1E9?style=flat&logo=openwrt&logoColor=white)](https://openwrt.org)
[![LuCI](https://img.shields.io/badge/LuCI-3D5780?style=flat)](https://github.com/openwrt/luci)
[![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![MIT License](https://img.shields.io/badge/license-MIT-green?style=flat)](LICENSE)

Telegram management bot for OpenWrt routers — monitor and control your BITS-WRT device from Telegram with a clean LuCI config page.

---

## ✨ Features

| Feature | Description |
|---|---|
| **Status** | CPU, load, RAM, swap, disk, uptime, WAN/VPN IP, uplink, clients. |
| **Internet** | WAN, tethering, Huawei HiLink signal, top trafik hari ini. |
| **Momo VPN** | Status, profil, TUN, restart & clear-log (integrasi momo/sing-box). |
| **Tailscale** | State, hostname, IP, peers online, restart. |
| **Klien** | DHCP clients, static/blocked state, block/unblock via firewall. |
| **Jadwal (Bandix)** | Atur limit kecepatan per klien per jam & hari. |
| **Docker** | Daftar container, stats, images, start/stop/restart, logs, prune. |
| **Firewall** | Ringkasan nftables + restart. |
| **Sistem** | Storage, suhu, cleanup RAM, backup, log, reboot. |
| **Tools** | Ping, traceroute, DNS, speedtest. |
| **Monitor** | Notifikasi WAN up/down, suhu, RAM, disk, perangkat baru & laporan harian 07:00. |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Runtime** | OpenWrt + Python 3 (`python-telegram-bot`) |
| **Bot** | `python-telegram-bot` v22 (async / `asyncio`) |
| **Config** | UCI (`/etc/config/bitsnetworksbot`) |
| **LuCI** | CBI model (`bitsnetworksbot/config`) + `menu.d` |
| **Service** | procd (`/etc/init.d/bitsnetworksbot`) |
| **Build** | `bash` + `tar` (SDK-less) + OpenWrt build system (`package.mk`) |
| **Release** | semantic-release + GitHub Actions |

---

## 📁 Project Structure

```
BITS-Networks-Bot/
├── .github/workflows/release.yml            # semantic-release + build .ipk + attach asset
├── bits-networks-bot/
│   ├── Makefile                             # OpenWrt build system (package.mk)
│   └── root/
│       ├── usr/bin/bitsnetworksbot.py            # bot utama (Python)
│       ├── etc/init.d/bitsnetworksbot             # procd init script
│       ├── etc/config/bitsnetworksbot             # UCI default config
│       ├── usr/lib/lua/luci/model/cbi/bitsnetworksbot/config.lua   # LuCI CBI
│       └── usr/share/luci/menu.d/luci-app-bitsnetworksbot.json     # LuCI menu
├── scripts/prepare.js                       # sync versi + build (dipakai semantic-release)
├── build.sh                                 # SDK-less .ipk packer
├── control / conffiles / postinst           # metadata ipk
├── package.json / .releaserc.json           # semantic-release
├── CHANGELOG.md
└── LICENSE
```

---

## 🚀 Quick Start

### Prerequisites

- OpenWrt device (23.05+) with `python3` + `python3-pip`.
- Internet access for the Telegram API.
- Bot token from [@BotFather](https://t.me/BotFather).

### 1. Install

Download the `.ipk` from [Releases](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/releases), copy to device, then:

```sh
opkg install bits-networks-bot_<version>_all.ipk
```

Dependencies (`python3-light`, `python3-asyncio`, `python3-urllib`, `python3-logging`, `curl`, `ca-certificates`) are pulled automatically.

### 2. Install python-telegram-bot (pip)

`python-telegram-bot` is not in the official OpenWrt feed; install it via pip (the `postinst` also attempts this automatically, best-effort):

```sh
opkg install python3-pip
pip3 install python-telegram-bot
```

### 3. Configure

Set the bot token and allowed user IDs in LuCI (`Services → BITS Networks Bot`) or via CLI:

```sh
uci set bitsnetworksbot.config.token='123456789:BOT_TOKEN'
uci set bitsnetworksbot.config.allowed_users='123456789'
uci commit bitsnetworksbot
/etc/init.d/bitsnetworksbot restart
```

### 4. Use

Open Telegram and send `/start` to your bot.

---

## ⚙️ Commands

`/start` `/status` `/internet` `/momo` `/tailscale` `/klien` `/jadwal` `/sistem` `/docker` `/ping` `/trace` `/dns` `/speedtest` `/storage` `/suhu` `/ssh` `/firewall` `/blokir` `/buka` `/reboot`

> Feature flags (per command) can be toggled individually in LuCI under the `bitsnetworksbot` config.

---

## 🏗️ Build

### Option A — SDK-less (bash + tar)

```sh
./build.sh
# output: dist/bits-networks-bot_<version>_all.ipk
```

> The OpenWrt `.ipk` format is an outer `tar.gz` containing `./debian-binary` + `./control.tar.gz` + `./data.tar.gz`.

### Option B — OpenWrt Build System

Copy `bits-networks-bot/` to `feeds/packages/utils/`, then:

```sh
./scripts/feeds update -a
./scripts/feeds install bits-networks-bot
make menuconfig   # Utilities -> bits-networks-bot
make package/bits-networks-bot/compile
```

---

## 🚀 Release

Releases are automated with [semantic-release](https://semantic-release.gitbook.io) + [Conventional Commits](https://www.conventionalcommits.org):

| Commit | Bump |
|---|---|
| `fix: ...` | patch |
| `feat: ...` | minor |
| `BREAKING CHANGE:` in body | major |

Push to `main` and the workflow builds the `.ipk` and publishes a GitHub Release with the asset attached.

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

**BITS Networks Bot** Developed with ❤️ by [**Banten IT Solutions**](https://bits.co.id)