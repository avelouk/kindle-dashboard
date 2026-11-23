#!/bin/sh
# Copy the dashboard to the Kindle and restart it.
#   KINDLE=root@192.168.15.244 tools/deploy.sh          # code only
#   tools/deploy.sh --config                            # also push kindle/config.json
#   tools/deploy.sh --service                           # also (re)install the upstart job
# Needs SSH access to the Kindle (USBNetwork over USB by default, see CLAUDE.md).
set -e
cd "$(dirname "$0")/.."
KINDLE="${KINDLE:-root@192.168.15.244}"
SSH="ssh -o ConnectTimeout=8 -o LogLevel=ERROR"
SCP="scp -q -O -o ConnectTimeout=8"

python3 -m py_compile kindle/dash.py kindle/render.py
[ -d kindle/vendor ] || { echo "kindle/vendor missing: run tools/fetch-vendor.sh first"; exit 1; }

$SSH "$KINDLE" 'mkdir -p /mnt/us/dash/integrations'
$SCP kindle/dash.py kindle/render.py "$KINDLE:/mnt/us/dash/"
if [ -d kindle/integrations ] && ls kindle/integrations/*.py >/dev/null 2>&1; then
  $SCP kindle/integrations/*.py "$KINDLE:/mnt/us/dash/integrations/"
fi
# vendor libs: only copy when missing on the device (6 MB, rarely changes)
if ! $SSH "$KINDLE" '[ -d /mnt/us/dash/vendor/icalendar ]'; then
  tar -C kindle -cf - vendor | $SSH "$KINDLE" 'cd /mnt/us/dash && tar -xf -'
fi
for arg in "$@"; do
  case "$arg" in
    --config)
      [ -f kindle/config.json ] || { echo "kindle/config.json missing"; exit 1; }
      python3 -c "import json; json.load(open('kindle/config.json'))"
      $SCP kindle/config.json "$KINDLE:/mnt/us/dash/config.json"
      $SSH "$KINDLE" 'chmod 600 /mnt/us/dash/config.json' ;;
    --service)
      $SCP kindle/dash.conf "$KINDLE:/tmp/dash.conf"
      $SSH "$KINDLE" 'mount -o rw,remount / && cp /tmp/dash.conf /etc/upstart/dash.conf && chmod 644 /etc/upstart/dash.conf; sync; mount -o ro,remount /' ;;
  esac
done

# restart: kill -9 skips the "restore Kindle UI" cleanup, upstart respawns us in ~20 s
$SSH "$KINDLE" 'p=$(/sbin/status dash 2>/dev/null | sed -n "s/.*process //p"); if [ -n "$p" ]; then kill -9 $p; else /sbin/start dash; fi; /sbin/status dash'
echo "deployed; new screen in ~30-60 s. Log: ssh $KINDLE tail -f /mnt/us/dash/dash.log"
