## [1.1.11](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/compare/v1.1.10...v1.1.11) (2026-09-09)


### Bug Fixes

* reorder LuCI menu (bot above tailscale in Services) ([c58dede](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/c58dededfe4c50401222905c306029cecc24ab04))

## [1.1.10](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/compare/v1.1.9...v1.1.10) (2026-09-09)


### Bug Fixes

* **docker:** drop capture_output+stderr conflict so '/docker logs' and '/docker ps' work ([a47d2fd](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/a47d2fd22e15bd30ed9e5432e365981675e465bd))

## [1.1.9](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/compare/v1.1.8...v1.1.9) (2026-09-09)


### Bug Fixes

* remove dead menu.d css field + orphan style.css (dispatcher.uc ignores 'css') ([fe83b10](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/fe83b10a11fb25d20d92ac1d66d3b81795a11450))

## [1.1.8](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/compare/v1.1.7...v1.1.8) (2026-09-09)


### Bug Fixes

* responsive password field via theme custom.css (menu.d css tidak didukung CBI) ([01c0f47](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/01c0f47f67d16a26772645c901196b995c048822))

## [1.1.7](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/compare/v1.1.6...v1.1.7) (2026-09-09)


### Bug Fixes

* **reliability:** prevent 'Timed out' crash — timeouts + graceful startup retry + loop exc handler ([3c79bf3](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/3c79bf3cdbfb0da402ee39c53f38ff5063b60606))

## [1.1.6](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/compare/v1.1.5...v1.1.6) (2026-09-09)


### Bug Fixes

* responsive LuCI form for mobile (token field full-width) + token placeholder ([49d0448](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/49d0448c50b4f4b835ec8e890155a6767e8e15cc))
* **security:** docker commands via list args (no shell injection) + esc name/output ([e7a26fa](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/e7a26faa0a59aade3a9500d38a60d80a9b843bc9))

## [1.1.5](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/compare/v1.1.4...v1.1.5) (2026-09-09)


### Bug Fixes

* stop auto-adding bot ID to allowed users (breaks notify / misleading count) ([d9f1acc](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/d9f1acc002ca543be89c27b4f20f8045963aee81))

## [1.1.4](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/compare/v1.1.3...v1.1.4) (2026-09-09)


### Bug Fixes

* correct /devices label to /klien in LuCI config ([9039efb](https://github.com/Banten-IT-Solutions/BITS-Networks-Bot/commit/9039efb2331d35eae861305649db99b9c4d1e713))

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
