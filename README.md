<div align="center">
  <h1>BITS Networks Bot</h1>
  <p>
    <a href="https://bits.co.id">
      <img src="https://img.shields.io/badge/Banten%20IT%20Solutions-BITS%20Networks%20Bot-00C853?style=for-the-badge&logo=telegram&logoColor=white" alt="BITS Networks Bot" />
    </a>
  </p>
  <p>
    Telegram management bot for OpenWrt routers &mdash; monitor and control your BITS-WRT device from Telegram with a clean LuCI config page.
  </p>
  <br>
  <p>
    <img src="https://img.shields.io/badge/OpenWrt-00A1E9?style=flat&logo=openwrt&logoColor=white" alt="OpenWrt" />
    <img src="https://img.shields.io/badge/LuCI-3D5780?style=flat" alt="LuCI" />
    <img src="https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/Telegram-26A5E4?style=flat&logo=telegram&logoColor=white" alt="Telegram" />
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat" alt="MIT License" />
  </p>
</div>

---

## ✨ Features

| Feature                   | Description                                                                                                      |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Status**                | CPU, load, RAM, swap, disk, uptime, WAN/VPN IP, uplink, dan klien aktif.                                         |
| **Internet**              | WAN, tethering, sinyal Huawei HiLink, dan top trafik hari ini.                                                   |
| **Momo VPN**              | Status, profil, TUN, restart & clear-log (integrasi momo/sing-box).                                              |
| **Tailscale**             | State, hostname, IP, peers online, dan restart.                                                                  |
| **Klien**                 | DHCP clients, status static/blocked, block & unblock via firewall.                                               |
| **Jadwal (Bandix)**       | Atur limit kecepatan per klien per jam & hari.                                                                   |
| **Docker**                | Daftar container, stats, images, start/stop/restart, logs, dan prune.                                            |
| **Firewall**              | Ringkasan nftables & restart.                                                                                    |
| **Sistem**                | Storage, suhu, cleanup RAM, backup, log, dan reboot.                                                              |
| **Tools**                 | Ping, traceroute, DNS, dan speedtest.                                                                             |
| **Monitor**               | Notifikasi WAN up/down, suhu, RAM, disk, perangkat baru & laporan harian 07:00.                                   |
| **Automated Release**     | semantic-release builds the `.ipk` and publishes a GitHub Release on every conventional commit.                   |

## 🛠️ Tech Stack

| Layer        | Technology                                                                        |
| ------------ | --------------------------------------------------------------------------------- |
| **Runtime**  | OpenWrt (LuCI + procd)                                                            |
| **Bot**      | `python-telegram-bot` v22 (async / `asyncio`)                                     |
| **Config**   | UCI (`/etc/config/bitsnetworksbot`)                                               |
| **Language** | Python 3 (LuCI CBI model untuk halaman konfigurasi)                               |
| **Build**    | `bash` + `tar` (no SDK), OpenWrt build system (`package.mk`)                      |
| **Release**  | semantic-release + GitHub Actions                                                 |

---

## 📁 Project Structure

```text
BITS-Networks-Bot/
├── .github/
│   └── workflows/
│       └── release.yml            # semantic-release + build .ipk + attach asset
├── bitsnetworksbot/
│   ├── Makefile                   # OpenWrt package def (package.mk)
│   └── root/
│       ├── usr/bin/bitsnetworksbot.py         # bot utama (Python)
│       ├── etc/init.d/bitsnetworksbot         # procd init script
│       ├── etc/config/bitsnetworksbot         # UCI default config
│       ├── usr/lib/lua/luci/model/cbi/bitsnetworksbot/config.lua   # LuCI CBI
│       └── usr/share/luci/menu.d/luci-app-bitsnetworksbot.json     # LuCI menu
├── scripts/
│   └── prepare.js                 # sync version + build (used by semantic-release)
├── build.sh                       # SDK-less .ipk packer
├── control                        # ipk metadata (+ Depends)
├── conffiles                      # preserve /etc/config/bitsnetworksbot
├── postinst                       # enable procd + auto pip install (best-effort)
├── package.json                   # semantic-release + plugins
├── .releaserc.json                # release plugins (git + github)
└── LICENSE
```

---

## 🚀 Quick Start

### Prerequisites

- An OpenWrt device (23.05+), with `python3` + internet access for the Telegram API.
- Bot token dari [@BotFather](https://t.me/BotFather).

### 1. Download

Grab the `.ipk` from the [Releases](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/releases) page, then copy it to your device.

### 2. Install

```sh
opkg install bitsnetworksbot_<version>_all.ipk
```

Dependencies (`python3-light`, `python3-asyncio`, `python3-urllib`, `python3-logging`, `python3-pip`, `curl`, `ca-certificates`, `speedtest-go`) are installed automatically. `python-telegram-bot` (not in the official feed) is installed best-effort via `pip` in the `postinst`.

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

> Feature flag setiap perintah bisa di-toggle satu per satu di LuCI pada konfigurasi `bitsnetworksbot`.

---

## 🏗️ Build

Choose one method. **SDK-less** for a quick `.ipk`; **OpenWrt build system** for the official feed.

### Option A — SDK-less (bash + tar)

Best for fast development and CI. Requires only `bash` + `tar` &mdash; no toolchain.

```sh
./build.sh
# output: dist/bitsnetworksbot_<version>_all.ipk
```

> The OpenWrt `.ipk` format is an outer `tar.gz` containing `./debian-binary` + `./control.tar.gz` + `./data.tar.gz`.

### Option B — OpenWrt Build System

Copy the package folder to `feeds/packages/utils/`, then:

```sh
./scripts/feeds update -a
./scripts/feeds install bitsnetworksbot
make menuconfig   # Utilities -> bitsnetworksbot
make package/bitsnetworksbot/compile
```

---

## 🚀 Release

Releases are automated with [semantic-release](https://semantic-release.gitbook.io) and [Conventional Commits](https://www.conventionalcommits.org). Write a conventional commit:

| Commit                           | Bump       |
| -------------------------------- | ---------- |
| `fix: ...`                       | patch      |
| `feat: ...`                      | minor      |
| `BREAKING CHANGE:` in body       | major      |

Push to `main` and the workflow builds the `.ipk` and publishes a GitHub Release with the asset attached.

---

## 📄 License

Distributed under the MIT License. See `LICENSE`.

---

<div align="center">
  <strong>BITS Networks Bot</strong> Developed with ❤️ by <a href="https://bits.co.id"><strong>Banten IT Solutions</strong></a>
</div>