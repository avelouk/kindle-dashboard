# CLAUDE.md: playbook for setting up a Kindle dashboard

You're helping someone turn an old Kindle into an always-on dashboard using this repo. It is a starting point, not a product: expect to write custom integrations for their devices and data. Read this whole file before touching the Kindle.

## Goals and rules

- **Stability over features.** The device sits in a living room and the owner wants to never touch it again. Follow "Stability rules" below for every change.
- **No secrets in git.** `kindle/config.json` and `kindle/integrations/*.env` are gitignored. Calendar links and device passwords are secrets.
- **Don't open network ports on the Kindle** unless the owner explicitly asks. Default maintenance access is SSH over USB only.
- **Preview before deploying.** Render with `tools/preview.py` and look at the image before pushing to the device.
- **Ask before anything irreversible** (firmware changes, jailbreak steps) and explain the risk.

## 1. Identify the Kindle

With the Kindle plugged in as a USB drive:
- Firmware: `cat /Volumes/Kindle/system/version.txt`.
- Model: the USB serial number (`ioreg -p IOUSB -l -w0 | grep -i serial` on macOS). Look up the first 4 characters in the MobileRead "Kindle Serial Numbers" wiki. Example: `B024` = Paperwhite 1 (2012), 758x1024 at 212 dpi.
- Settings → Device Info shows the firmware too (not the model).

## 2. Jailbreak (device-specific; verify on MobileRead first)

The MobileRead forums are the source of truth: the "Kindle Jailbreak Index" and NiLuJe's "Snapshots" thread (t=225030), which has all the downloads. What worked here (Paperwhite 1, firmware 5.6.1.1, Nov 2026):

1. **Airplane mode on** first, so it can't update itself.
2. **Downgrade to 5.3.3**: copy Amazon's `update_kindle_5.3.3.bin` (from Amazon's S3, linked in mobileread t=264432) to the Kindle's root, wait 2 minutes, hold power until it restarts. **Don't unplug USB until it's done.**
3. **K5 jailbreak** (`kindle-jailbreak-1.16.N-*.tar.xz` from the Snapshots thread): unzip the *contents* of `kindle-5.4-jailbreak.zip` to the root, eject, Settings → Menu → Update Your Kindle → "**** JAILBREAK ****" appears at the bottom.
4. Newer Kindles have different jailbreaks (WinterBreak, LanguageBreak, AdBreak...). Check the Jailbreak Index for the exact model and firmware.

### Things that went wrong, and the fixes

- **KUAL** (the usual launcher) crashed on 5.3.3 with "This item is not signed by an authorized developer". That error text is generic: the system log showed `isDeveloper=true` and the crash was inside KUAL itself. **KUAL isn't needed**: skip it.
- **"Update Your Kindle" greyed out / custom `.bin` packages rejected** after the jailbreak, even with the dev key installed. The workaround is the jailbreak's own trick: the file `Update_jb_$(cd mnt && cd us && sh jb.sh).bin` in the root makes the updater run `/mnt/us/jb.sh` as root when you tap Update Your Kindle. Put any script in `jb.sh` (e.g. a diagnostic dump, or a manual install of USBNetwork from its `src/` folder). This stops working once the OTA binaries are renamed (step 4), by which point you have SSH.
- **Never restart the Kindle with a custom `.bin` in the root.**
- **The Kindle's clock is reset to 2012** after a downgrade. Briefly enabling Wi-Fi fixes it (the date can't be set by hand). Turn airplane mode back on right after.

## 3. Get a shell: USBNetwork

USBNetwork (from the Snapshots thread, `kindle-usbnet-*.tar.xz`) gives SSH over USB. If the updater won't install the `.bin`, install it via the `jb.sh` trick: run its `src/install.sh` with the payload as a plain tar, after `mount -o rw,remount /`. Put the owner's public key in `/mnt/us/usbnet/etc/authorized_keys` before installing.

- Toggle USB networking by typing `;un` in the Kindle's search bar **while unplugged**, then plug in.
- macOS: the Kindle shows up as "RNDIS/Ethernet Gadget". Run `networksetup -setmanual "RNDIS/Ethernet Gadget" 192.168.15.201 255.255.255.0`, then `ssh root@192.168.15.244`. Over USB, SSH accepts any login (`-n` flag); over Wi-Fi it would need the key.
- To have USB networking on at every boot: `mv /mnt/us/usbnet/DISABLED_auto /mnt/us/usbnet/auto`. The Kindle then no longer mounts as a drive.
- If the link goes dead after replugging: unplug, `;un` (off), plug in (drive appears), unplug, `;un` (on), plug in.

## 4. Base setup on the Kindle

```
# block OTA updates (an update would undo everything)
mount -o rw,remount /
mv /usr/bin/otaupd /usr/bin/otaupd.bck; mv /usr/bin/otacheck /usr/bin/otacheck.bck
mount -o ro,remount /
mkdir -p /mnt/us/update.bin.tmp.partial
```
- **Python 3.9 + Pillow**: NiLuJe's `kindle-python-*.tar.xz` from the Snapshots thread. Copy `Update_python3_*_install_touch_pw.bin` (or `_pw2_and_up`) to the device, run `/mnt/us/usbnet/bin/kindletool extract <bin> out`, then `sh out/install.sh` after a rw remount. You get `/mnt/us/python3/bin/python3.9` (no pip).
- **Pure-Python libs** (iCal parsing, tzdata): `tools/fetch-vendor.sh` on the computer. `tools/deploy.sh` copies them over.
- Then: `cp kindle/config.example.json kindle/config.json`, fill it in, and run `tools/deploy.sh --config --service`.

## 5. Kindle quirks to know (all bit us)

- **BusyBox 1.17**: `grep -E` doesn't exist (use `grep -e a -e b`). No `nohup`; use `(setsid cmd > log 2>&1 < /dev/null &)`. `ps` doesn't show script arguments, so look for `python3.9`. `stop`/`start` are in `/sbin` (not on SSH's PATH). `mntroot` isn't on PATH; use `mount -o rw,remount /`.
- **`/mnt/us` is FAT**: no symlinks, no permissions. `chmod` silently does little.
- **IPv6 DNS hangs** on some home routers: always `curl -4`. Use `/mnt/us/usbnet/bin/curl` (modern OpenSSL), not the system curl.
- **The stock UI must be stopped**: `stop lab126_gui` (not just `framework`, which leaves the status bar and keyboard drawing over you). Starting it again resets USB networking.
- **Keep it awake**: `lipc-set-prop com.lab126.powerd preventScreenSaver 1`. With the UI stopped, the dashboard re-asserts it on every refresh.
- **Firewall**: iptables blocks incoming connections and UDP broadcast replies. Prefer designs that only make outgoing connections.
- **Screen**: FBInk at `/mnt/us/usbnet/bin/fbink`. `fbink -f -g file=x.png` does a full refresh (black flash, clears ghosting). Without `-f` it's a quiet update. For a partial update: `-g file=x.png,x=..,y=..`.
- **Front light**: `lipc-set-prop com.lab126.powerd flIntensity 0..24`. On the PW1, 0 still leaves a faint glow; writing `0` to `/sys/devices/system/fl_tps6116x/fl_tps6116x0/fl_intensity` turns it fully off (other models have a different path). `set_light()` in dash.py does both.
- **Touch**: `/dev/input/event0`, coordinates 1:1 with screen pixels on the PW1 (check with `evtest` on other models).
- **The e-ink screen keeps the last image when nothing is running.** A frozen dashboard looks alive. The ticking clock is the health indicator.
- **Kindle Python 3.9**: no 3.10+ syntax (no `match`, no `X | Y` types). Vendored libs must support 3.9.

## 6. How the code works

- `kindle/dash.py` runs on the Kindle. On start: `stop lab126_gui`, keep awake, draw cached data. Loop every 5 s:
  - every `refresh_minutes`: fetch weather + each calendar, then a full flashing redraw
  - on the hour: a quiet redraw
  - every minute: redraw only the clock box
  - at `restart_hour`: `os.execv` itself (a fresh process, the UI stays stopped)
  - a separate thread reads taps. 5 taps in the top-left corner within 5 s: exit and restore the stock UI until reboot.
- `kindle/render.py` takes `(now, weather, events, buttons, button_state, legend, errors)` and returns a PIL image. Each screen section draws inside its own try/except.
- `kindle/dash.conf` is the upstart job: `start on started framework`, respawn, 20 s delay. Kill switch: create `/mnt/us/dash/DISABLE`. Installed to `/etc/upstart/dash.conf`.
- Config (`kindle/config.json`): location, `calendars` (`name`, `url`, `marker`: circle/square/ring/diamond), `buttons`, `light` (`mode`: tap/on/off/keep, `level` 0-24, `seconds`), `refresh_minutes`, `restart_hour`. See `config.example.json`.

### Adding a button

Write a script in `kindle/integrations/` that does one thing and exits 0 on success. Add it to `config.json`:
```json
{"id": "lights_off", "label": "Lights off", "command": ["{python}", "integrations/hue.py", "off"],
 "style": "primary", "weight": 1, "busy_label": "Sending…", "ok_label": "Off", "timeout": 60}
```
`{python}` is the Kindle's Python, and commands run with cwd `/mnt/us/dash`. The script must:
- never hang: use socket timeouts and keep under `timeout` seconds
- retry briefly on its own, and print something useful to stdout (it's logged)
- keep credentials in a gitignored `.env` next to it, `chmod 600`
- only use the standard library or what's vendored. Test it over SSH on the device before wiring it to a button.

### Adding a data source

Fetch it in `Dashboard.fetch()` with its own try/except, keep its last good value with a timestamp, and drop it when it's too old. Draw it in its own `section(...)` in `render.render`. Add a case to `tests/test_render.py` with garbage data.

## 7. Stability rules (apply to every change)

1. Nothing may stop the main loop. Every network call, draw, tap and button runs in its own try/except and logs to `dash.log`.
2. Bad data degrades one section with a small note in the footer. It never blanks the screen and never freezes it.
3. Keep last good data. Validate replies; error JSON is not data (Open-Meteo returns `{"error": true, "reason": "The service is overloaded"}`).
4. Every subprocess and socket has a timeout.
5. Nothing grows without bound: the log rotates at 512 KB, and caches are rewritten whole with atomic writes.
6. A broken `config.json` keeps the previous config.
7. After changes, run `python3 tests/test_render.py && python3 tests/test_dash.py` and preview. Deploy, then watch `dash.log` through one full refresh and one minute tick.

## 8. Debugging on the device

```
ssh root@192.168.15.244
tail -f /mnt/us/dash/dash.log            # our log
/sbin/status dash                        # service state
grep -i <thing> /var/log/messages        # system log (framework, powerd, wifi)
lipc-get-prop com.lab126.powerd status   # "Remaining time: Unknown" = won't sleep
```
Restart without bringing back the stock UI: `kill -9 $(/sbin/status dash | sed -n 's/.*process //p')` (upstart respawns it in ~20 s). `tools/deploy.sh` does this.
