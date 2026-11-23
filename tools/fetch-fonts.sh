#!/bin/sh
# Copy the Kindle's own fonts to kindle/fonts/ so tools/preview.py looks like the real thing.
# (They're Amazon's fonts: kept out of git, used for local previews only.)
set -e
cd "$(dirname "$0")/.."
KINDLE="${KINDLE:-root@192.168.15.244}"
mkdir -p kindle/fonts
for f in Futura-Bold Futura-Medium Futura-DemiBold Helvetica_LT_65_Medium Helvetica_LT_75_Bold; do
  scp -q -O "$KINDLE:/usr/java/lib/fonts/$f.ttf" kindle/fonts/
done
echo "fonts copied to kindle/fonts/"
