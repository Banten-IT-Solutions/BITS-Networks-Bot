// prepare.js — dipanggil semantic-release pada fase "prepare".
// Menyelaraskan versi package.json + control + Makefile (kedua paket),
// lalu membangun .ipk (bitsnetworksbot + luci-app-bitsnetworksbot).
const fs = require('fs');
const { execSync } = require('child_process');

const version = process.argv[2];

if (!version) {
  console.error('usage: node scripts/prepare.js <version>');
  process.exit(1);
}

const packages = ['bitsnetworksbot', 'luci-app-bitsnetworksbot'];

// package.json
const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));
pkg.version = version;
fs.writeFileSync('package.json', JSON.stringify(pkg, null, 2) + '\n');

for (const name of packages) {
  // control (opkg)
  let control = fs.readFileSync(`${name}/control`, 'utf8');
  control = control.replace(/^Version: .*$/m, `Version: ${version}`);
  fs.writeFileSync(`${name}/control`, control);

  // Makefile (OpenWrt build system PKG_VERSION)
  let makefile = fs.readFileSync(`${name}/Makefile`, 'utf8');
  makefile = makefile.replace(/^PKG_VERSION:=.*$/m, `PKG_VERSION:=${version}`);
  fs.writeFileSync(`${name}/Makefile`, makefile);
}

// build ipk (build.sh membaca Version dari masing-masing control)
execSync('bash build.sh', { stdio: 'inherit' });

console.log(`prepared version ${version}`);