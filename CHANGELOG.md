## [1.1.3](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/compare/v1.1.2...v1.1.3) (2026-09-09)


### Bug Fixes

* correct CBI TypedSection type so values render (was showing 'no values yet') ([df282cf](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/df282cf51aa2b455a3d9b0ec56717ac094ecdf8d))

## [1.1.2](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/compare/v1.1.1...v1.1.2) (2026-09-09)


### Bug Fixes

* ensure trailing newline in ipk control files (opkg warning) ([1e34709](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/1e3470907169b05cfff482c4ec30b71148319f1a))

## [1.1.1](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/compare/v1.1.0...v1.1.1) (2026-09-09)


### Bug Fixes

* rename package to bitsnetworksbot + fix LuCI menu (cbi) [skip release note] ([ed1b7f1](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/ed1b7f1f884e427990c56bf21593d63e29bb4f11))

# [1.1.0](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/compare/v1.0.0...v1.1.0) (2026-09-09)


### Features

* rename service/config to bitsnetworksbot + add speedtest-go & pip deps ([72c470e](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/72c470ee41eeb532d9b9b2ccebb86ccffc65e410))

# 1.0.0 (2026-09-09)


### Features

* BITS Networks Bot — Telegram management bot for OpenWrt ([a950444](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/a9504445965bc5a1732a24c929dee437081f2e87))

# 1.0.0 (2026-09-09)

### Features

- Telegram management bot for OpenWrt: status, internet, momo VPN, tailscale, clients, schedule, docker, firewall, storage, systems & tools.
- LuCI CBI config page + menu.d entry.
- procd init script with respawn.
- SDK-less `.ipk` build + semantic-release workflow.
