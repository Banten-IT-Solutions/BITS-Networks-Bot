# SPDX-License-Identifier: MIT
#
# BITS Networks Bot — Telegram management bot for OpenWrt.
# Opsional: dibangun lewat OpenWrt build system. Letakkan folder ini di
# feeds/packages/utils/ lalu pilih di menuconfig (Utilities -> bits-networks-bot).

include $(TOPDIR)/rules.mk

PKG_NAME:=bits-networks-bot
PKG_VERSION:=1.0.0
PKG_RELEASE:=1

PKG_MAINTAINER:=Banten IT Solutions <support@bits.co.id>
PKG_LICENSE:=MIT
PKG_ARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/bits-networks-bot
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=BITS Networks Bot
  DEPENDS:=+python3-light +python3-asyncio +python3-urllib +python3-logging +python3-pip +curl +ca-certificates +speedtest-go
endef

define Package/bits-networks-bot/description
  Telegram management bot for OpenWrt routers (BITS-WRT): status, internet,
  momo VPN, Tailscale, clients, schedule, Docker, firewall, storage and tools.
endef

define Package/bits-networks-bot/conffiles
/etc/config/bitsnetworksbot
endef

define Build/Compile
endef

define Package/bits-networks-bot/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) ./root/usr/bin/bitsnetworksbot.py $(1)/usr/bin/bitsnetworksbot.py

	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./root/etc/init.d/bitsnetworksbot $(1)/etc/init.d/bitsnetworksbot

	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_DATA) ./root/etc/config/bitsnetworksbot $(1)/etc/config/bitsnetworksbot

	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/model/cbi/bitsnetworksbot
	$(INSTALL_DATA) ./root/usr/lib/lua/luci/model/cbi/bitsnetworksbot/config.lua \
		$(1)/usr/lib/lua/luci/model/cbi/bitsnetworksbot/config.lua

	$(INSTALL_DIR) $(1)/usr/share/luci/menu.d
	$(INSTALL_DATA) ./root/usr/share/luci/menu.d/luci-app-bitsnetworksbot.json \
		$(1)/usr/share/luci/menu.d/luci-app-bitsnetworksbot.json
endef

$(eval $(call BuildPackage,bits-networks-bot))