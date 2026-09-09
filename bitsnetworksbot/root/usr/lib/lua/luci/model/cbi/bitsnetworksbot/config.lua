-- /usr/lib/lua/luci/model/cbi/bitsnetworksbot/config.lua

local m = Map("bitsnetworksbot", translate("BITS Networks Bot"))

-- Modul yang dibutuhkan
local nixio = require("nixio")
local os = require("os")

-- ===================================================
-- Seksi Pengaturan Koneksi Bot
-- ===================================================

local s = m:section(TypedSection, "bitsnetworksbot", translate("Pengaturan Koneksi Bot"))
s.anonymous = true

-- TOKEN
local token = s:option(Value, "token", translate("Bot Token"))
token.password = true 
token.datatype = "string"
token.size = 60
token.placeholder = "123456789:AA...token"
token.description = translate("Token API yang didapat dari BotFather. Wajib diisi.")

-- ALLOWED_USERS
local users = s:option(Value, "allowed_users", translate("Allowed User IDs"))
users.datatype = "string" 
users.description = translate("Daftar ID Pengguna Telegram yang diizinkan, dipisahkan koma. Cth: 1234567,8901234")

-- ===================================================
-- Seksi Pengaturan Fitur
-- ===================================================

s = m:section(TypedSection, "bitsnetworksbot", translate("Aktifkan/Nonaktifkan Fitur"))
s.anonymous = true

local function create_checkbox(section, name, label, description)
    local option = section:option(Flag, "enable_" .. name, translate(label))
    option.default = option.enabled
    option.default = 1
    option.optional = false
    option.enabled  = "1"
    option.disabled = "0"
    option.description = translate(description)
end

create_checkbox(s, "status", "Aktifkan Perintah Status (/status)", "Menampilkan Uptime, CPU, Memori, dan IP WAN.")
create_checkbox(s, "devices", "Aktifkan Daftar Klien (/klien)", "Menampilkan daftar perangkat yang terhubung melalui DHCP.")
create_checkbox(s, "reboot", "Aktifkan Reboot Router (/reboot)", "Perintah untuk me-restart router (membutuhkan konfirmasi).")
create_checkbox(s, "internet", "Aktifkan Internet (/internet)", "Status WAN, tethering, sinyal Huawei & top trafik.")
create_checkbox(s, "momo", "Aktifkan Momo (/momo)", "Status, restart & clear-log Momo.")
create_checkbox(s, "tailscale", "Aktifkan Tailscale (/tailscale)", "Status & restart Tailscale.")
create_checkbox(s, "sistem", "Aktifkan Sistem (/sistem)", "Cleanup RAM, backup config, log & reboot.")
create_checkbox(s, "jadwal", "Aktifkan Jadwal (/jadwal)", "Atur limit Bandix per klien.")
create_checkbox(s, "monitor", "Aktifkan Notifikasi Otomatis", "WAN up/down, suhu, RAM, disk, perangkat baru & laporan harian.")
create_checkbox(s, "docker", "Aktifkan Docker (/docker)", "Daftar, start/stop/restart, log, stats, images & prune container.")
create_checkbox(s, "tools", "Aktifkan Tools Jaringan (/ping, /trace, /dns, /speedtest)", "Ping, traceroute, nslookup & tes kecepatan.")
create_checkbox(s, "firewall", "Aktifkan Firewall (/firewall)", "Ringkasan & restart firewall nftables.")


-- ===================================================
-- Penanganan Penyimpanan (Save Handler)
-- ===================================================

m.on_commit = function(map)
    os.execute("/etc/init.d/bitsnetworksbot reload >/dev/null 2>&1") 
end

return m