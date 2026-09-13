#!/usr/bin/env bash
# Pack bitsnetworksbot + luci-app-bitsnetworksbot: .ipk (opkg) + .apk (apk) tanpa SDK.
# .ipk = tar.gz luar (debian-binary + control.tar.gz + data.tar.gz)
# .apk = apk-tools v3 `mkpkg` (butuh binary `apk` di PATH / env APK_BIN)
set -euo pipefail

PACKAGES="bitsnetworksbot luci-app-bitsnetworksbot"

rm -rf .build dist
mkdir -p dist

for pkg in $PACKAGES; do
	ctrl="$pkg/control"
	pkg_ver=$(awk -F': ' '/^Version:/{print $2; exit}' "$ctrl")
	pkg_desc=$(awk -F': ' '/^Description:/{print $2; exit}' "$ctrl")
	pkg_depends=$(awk -F': ' '/^Depends:/{print $2; exit}' "$ctrl" | tr ',' ' ')
	out_ipk="dist/${pkg}_${pkg_ver}_all.ipk"
	out_apk="dist/${pkg}-${pkg_ver}-r0.apk"
	b=".build/$pkg"
	mkdir -p "$b/root" "$b/control" "$b/outer"

	# root/ -> payload
	cp -a "$pkg/root/." "$b/root/"

	# ===== .ipk (opkg) =====
	cp "$ctrl" "$b/control/control"
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
	tar czf "$out_ipk" -C "$b/outer" .

	# ===== .apk (apk-tools v3) =====
	APK_BIN="${APK_BIN:-apk}"
	if command -v "$APK_BIN" >/dev/null 2>&1; then
		APK_ARGS=(
			mkpkg
			--info "name:${pkg}"
			--info "version:${pkg_ver}-r0"
			--info "arch:noarch"
			--info "description:${pkg_desc}"
			--info "license:MIT"
			--info "depends:${pkg_depends}"
		)
		if [ -f "$pkg/postinst" ]; then
			APK_ARGS+=(--script "post-install:$pkg/postinst")
		fi
		APK_ARGS+=(--files "$b/root" --output "$out_apk")
		"$APK_BIN" "${APK_ARGS[@]}"
		echo "Built: $out_apk"
	fi

	echo "Built: $out_ipk"
done

rm -rf .build
echo "Done: $(ls dist/*.ipk 2>/dev/null | wc -l) ipk, $(ls dist/*.apk 2>/dev/null | wc -l) apk"