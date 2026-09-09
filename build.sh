#!/usr/bin/env bash
# Pack bitsnetworksbot + luci-app-bitsnetworksbot jadi .ipk tanpa OpenWrt SDK.
# Format ipk OpenWrt = tar.gz luar berisi ./debian-binary + ./control.tar.gz + ./data.tar.gz.
set -euo pipefail

PACKAGES="bitsnetworksbot luci-app-bitsnetworksbot"

rm -rf .build dist
mkdir -p dist

for pkg in $PACKAGES; do
	pkg_ver=$(awk -F': ' '/^Version:/{print $2; exit}' "$pkg/control")
	out="dist/${pkg}_${pkg_ver}_all.ipk"
	b=".build/$pkg"
	mkdir -p "$b/root" "$b/control" "$b/outer"

	# root/ -> payload ipk
	cp -a "$pkg/root/." "$b/root/"

	# control + postinst + conffiles
	cp "$pkg/control" "$b/control/control"
	if [ -f "$pkg/postinst" ]; then
		cp "$pkg/postinst" "$b/control/postinst"
		chmod 755 "$b/control/postinst"
	fi
	if [ -f "$pkg/conffiles" ]; then
		cp "$pkg/conffiles" "$b/control/conffiles"
	fi

	tar czf "$b/data.tar.gz" --owner=0 --group=0 -C "$b/root" .
	tar czf "$b/control.tar.gz" --owner=0 --group=0 -C "$b/control" .
	printf '2.0\n' > "$b/debian-binary"

	cp "$b/debian-binary" "$b/control.tar.gz" "$b/data.tar.gz" "$b/outer/"
	tar czf "$out" -C "$b/outer" .

	echo "Built: $out"
done

rm -rf .build
echo "Done: $(ls dist/*.ipk | wc -l) ipk"