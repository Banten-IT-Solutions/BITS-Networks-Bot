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
  DEPENDS:=+python3-light +python3-asyncio +python3-urllib +python3-logging +curl +ca-certificates
endef

define Package/bits-networks-bot/description
  Telegram management bot for OpenWrt routers (BITS-WRT): status, internet,
  momo VPN, Tailscale, clients, schedule, Docker, firewall, storage and tools.
endef

define Package/bits-networks-bot/conffiles
/etc/config/routerbot
endef

define Build/Compile
endef

define Package/bits-networks-bot/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) ./root/usr/bin/router-bot.py $(1)/usr/bin/router-bot.py

	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./root/etc/init.d/routerbot $(1)/etc/init.d/routerbot

	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_DATA) ./root/etc/config/routerbot $(1)/etc/config/routerbot

	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/model/cbi/routerbot
	$(INSTALL_DATA) ./root/usr/lib/lua/luci/model/cbi/routerbot/config.lua \
		$(1)/usr/lib/lua/luci/model/cbi/routerbot/config.lua

	$(INSTALL_DIR) $(1)/usr/share/luci/menu.d
	$(INSTALL_DATA) ./root/usr/share/luci/menu.d/luci-app-routerbot.json \
		$(1)/usr/share/luci/menu.d/luci-app-routerbot.json
endef

$(eval $(call BuildPackage,bits-networks-bot))