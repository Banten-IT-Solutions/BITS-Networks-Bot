# SPDX-License-Identifier: MIT
#
# BITS Networks Bot — Telegram management bot for OpenWrt.
# Opsional: dibangun lewat OpenWrt build system. Letakkan folder ini di
# feeds/packages/utils/ lalu pilih di menuconfig (Utilities -> bitsnetworksbot).

include $(TOPDIR)/rules.mk

PKG_NAME:=bitsnetworksbot
PKG_VERSION:=1.2.0
PKG_RELEASE:=1

PKG_MAINTAINER:=Banten IT Solutions <support@bits.co.id>
PKG_LICENSE:=MIT
PKG_ARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/bitsnetworksbot
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=BITS Networks Bot
  DEPENDS:=+python3-light +python3-asyncio +python3-urllib +python3-logging +python3-pip +curl +ca-certificates +speedtest-go
endef

define Package/bitsnetworksbot/description
  Telegram management bot for OpenWrt routers (BITS-WRT): status, internet,
  momo VPN, Tailscale, clients, schedule, Docker, firewall, storage and tools.
endef

define Package/bitsnetworksbot/conffiles
/etc/config/bitsnetworksbot
endef

define Build/Compile
endef

define Package/bitsnetworksbot/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) ./root/usr/bin/bitsnetworksbot.py $(1)/usr/bin/bitsnetworksbot.py

	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./root/etc/init.d/bitsnetworksbot $(1)/etc/init.d/bitsnetworksbot

	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_DATA) ./root/etc/config/bitsnetworksbot $(1)/etc/config/bitsnetworksbot
endef

$(eval $(call BuildPackage,bitsnetworksbot))