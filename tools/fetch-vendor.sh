#!/bin/sh
# Download the pure-Python libraries the dashboard needs into kindle/vendor/,
# in versions that run on the Kindle's Python 3.9. Needs pip on this computer.
set -e
cd "$(dirname "$0")/.."
tmp=$(mktemp -d)
python3 -m pip download -q -r kindle/requirements-vendor.txt -d "$tmp" \
  --python-version 3.9 --implementation py --abi none --only-binary=:all: --platform any
rm -rf kindle/vendor && mkdir -p kindle/vendor
for w in "$tmp"/*.whl; do unzip -q -o "$w" -d kindle/vendor; done
rm -rf kindle/vendor/*.dist-info "$tmp"
echo "kindle/vendor ready ($(du -sh kindle/vendor | cut -f1))"
