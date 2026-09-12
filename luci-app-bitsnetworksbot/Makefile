# SPDX-License-Identifier: MIT
#
# LuCI app untuk BITS Networks Bot — halaman konfigurasi (CBI) saja.
# Dibangun lewat OpenWrt build system (feeds/luci). Letakkan folder ini di
# feeds/luci/applications/luci-app-bitsnetworksbot lalu pilih di menuconfig
# (LuCI -> Applications -> luci-app-bitsnetworksbot).

include $(TOPDIR)/rules.mk

LUCI_TITLE:=BITS Networks Bot
LUCI_DEPENDS:=+bitsnetworksbot
LUCI_PKGARCH:=all

PKG_LICENSE:=MIT
PKG_MAINTAINER:=Banten IT Solutions <support@bits.co.id>
PKG_VERSION:=1.2.5
PKG_RELEASE:=1

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature file