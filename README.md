# gigabyte-keyboard-ctl

RGB backlight control for the **GIGABYTE GAMING A16 (CTH)** on Linux.

The A16 keyboard does not expose a normal `/sys/class/leds` backlight. Its
lighting lives on a USB HID interface that implements the
**[Microsoft HID LampArray](https://learn.microsoft.com/en-us/windows-hardware/design/component-guidelines/hid-lamparray)**
protocol (Usage Page `0x59`). On Windows, Gigabyte Control Center / GiMate
drives it through that protocol; Linux sends nothing, which is why the
backlight stays dark after a cold boot and why OpenRGB / `opengigabyte` do not
find it (as of 2026 OpenRGB still has no LampArray support).

This project is a small userspace app that talks to the LampArray interface
directly through `hidraw`. **No kernel driver is required**, there is nothing
to compile, and it works with any 24-bit colour — not just the handful GiMate
offers.

## Features

- Any `#RRGGBB` colour (16.7 million choices), not a fixed palette
- 0–100 % brightness (emulated by scaling RGB, because the firmware's
  intensity channel is on/off only)
- Software animations: breathing, palette wave and a perceptually smooth
  rainbow
- GUI with colour picker, presets, brightness slider, effect controls and a
  system-tray icon
- Scriptable CLI
- Restores the backlight automatically at login (cold boot fix)
- Optional `Fn+Space` firmware mode
- No root needed for daily use in a normal desktop session

## Requirements

- Linux with `hidraw` (any modern kernel)
- Python 3.10+
- **Optional:** PyQt6 for the GUI (`python-pyqt6` on CachyOS/Arch)
- Read/write access to the keyboard's hidraw node. In a normal desktop
  session, `systemd-logind` normally grants this to the active user already.
  If not, install the udev rule (see below).

## Install

```bash
cd gigabyte-keyboard-ctl
./install.sh
```

This installs everything under your home directory:

- `~/.local/bin/gigabyte-kbd` — launcher
- `~/.local/share/gigabyte-keyboard-ctl/` — Python package
- `~/.local/share/applications/gigabyte-kbd.desktop` — menu entry
- `~/.config/autostart/gigabyte-kbd.desktop` — applies the saved colour at
  login, which fixes the dark-keyboard-on-cold-boot problem

If the CLI reports that it cannot open `/dev/hidraw*`, install the udev rule:

```bash
sudo ./install.sh --system
```

Then log out and back in. You can also add yourself to the `input` group
instead, but the rule uses logind's `uaccess` tag, so no group change is
needed.

Uninstall with `./install.sh --uninstall` (and
`sudo ./install.sh --system --uninstall` for the udev rule).

### What gets written

Everything is user-local. The app never installs a kernel module and never
changes `/etc`, the bootloader or system packages. These files are created:

| Path | Purpose |
|------|---------|
| `~/.local/bin/gigabyte-kbd` | launcher |
| `~/.local/share/gigabyte-keyboard-ctl/` | Python package |
| `~/.local/share/applications/gigabyte-kbd.desktop` | desktop menu entry |
| `~/.config/autostart/gigabyte-kbd.desktop` | runs `gigabyte-kbd restore` at login |
| `~/.config/gigabyte-kbd/config.conf` | your colour/brightness/effect settings |

At runtime the app only rewrites `config.conf` (when you change a setting).
The optional udev rule is the only system-wide file, and only if you run
`sudo ./install.sh --system`.

## GUI

```bash
gigabyte-kbd gui
```

Pick a colour with the large swatch or the hex field, use the presets, adjust
brightness, or choose an effect. Closing the window keeps the app in the tray;
use **Quit** there to exit. The saved state is reapplied on the next launch.

If the tray icon is not available, closing the window exits the app.

## CLI

```bash
gigabyte-kbd info                     # device, lamp count, saved state
gigabyte-kbd color 00aaff             # any RRGGBB colour
gigabyte-kbd color ff0000 -b 40       # red at 40 %
gigabyte-kbd brightness 70            # 0-100
gigabyte-kbd on
gigabyte-kbd off
gigabyte-kbd toggle
gigabyte-kbd effect breathing         # runs until Ctrl+C
gigabyte-kbd effect wave              # sweep through the 12 palette swatches
gigabyte-kbd effect rainbow --speed 80
gigabyte-kbd effect breathing --duration 5
gigabyte-kbd restore                  # re-apply saved state (login hook)
gigabyte-kbd auto on | off            # firmware mode / host mode
gigabyte-kbd detect
gigabyte-kbd config                   # print config file
```

Settings are stored in `~/.config/gigabyte-kbd/config.conf` (override with
`GIGABYTE_KBD_CONFIG`).

## Host mode vs. firmware mode

The keyboard has two ways of driving the backlight:

- **Host mode** (default, and what the colour/effect commands use): the app
  sends the exact RGB value. Total control, but `Fn+Space` does nothing while
  host mode is active.
- **Firmware mode** (`gigabyte-kbd auto on`, or the checkbox in the GUI): the
  keyboard firmware drives the LEDs, so **`Fn+Space` cycles brightness
  natively**. The downside is that the firmware uses *its own* stored colour,
  which is whatever GiMate last programmed in Windows. After a full shutdown
  that stored colour can be black, so `Fn+Space` may show nothing until you
  set a colour in Windows once. The app's colour writes do not update the
  firmware's stored colour.

The GUI starts in the mode saved in the config. Use **Let the keyboard handle
Fn+Space** to switch.

## Why the backlight is dark on a cold boot

The keyboard keeps its last LampArray state across reboots and USB resets, but
not across a full power-off. On Windows, GiMate re-sends the state at startup;
on Linux nothing did. The autostart entry installed by `./install.sh` runs
`gigabyte-kbd restore` at login, so the backlight comes up in your saved
colour. If you prefer a different colour at login, set it with
`gigabyte-kbd color ...` — the last saved state is what gets restored.

## Limitations

- **One zone.** The keyboard reports `LampCount = 1`; there is no per-key or
  multi-zone control on this model. A spatial left-to-right wave across the
  keys is therefore impossible in hardware. The `wave` effect is the closest
  equivalent: it sweeps smoothly through the palette in reading order (top row
  left to right, then bottom row left to right) on the single zone.
  Effects are whole-keyboard fades/cycles.
- **Rainbow is perceptual.** It rotates hue in Oklch at constant lightness and
  moderate chroma, instead of the HSV rainbow that produces harsh
  green/yellow/blue peaks.
- **Brightness is software-scaled.** The firmware reports one intensity level
  (`intensity_lvls = 1`), so the LampArray intensity channel is effectively
  on/off. The app scales the RGB values instead.
- **Animations need a running process.** The login hook applies the base
  colour statically; start the GUI or `gigabyte-kbd effect <name>` for
  animations.
- **Firmware mode colour is not ours.** See above.
- If another program (OpenRGB, GiMate in a VM, a vendor daemon) is writing to
  the same hidraw node, the last writer wins.

## Troubleshooting

**`Error: GIGABYTE LampArray device (0414:*) not found`**

The keyboard's LampArray interface was not detected. Check:

```bash
lsusb | grep -i gigabyte
grep -l . /sys/class/hidraw/hidraw*/device/report_descriptor
gigabyte-kbd detect
```

The keyboard should appear as `0414:8104` or `0414:8105`.

**`cannot open /dev/hidrawN: Permission denied`**

Install the udev rule: `sudo ./install.sh --system`, then log out/in. Verify
with `getfacl /dev/hidraw*` — your user should have `rw`.

**The GUI does not start**

Install PyQt6: `sudo pacman -S python-pyqt6` (CachyOS/Arch). The CLI has no
GUI dependency.

**Colour changes do nothing**

Make sure firmware mode is off (`gigabyte-kbd auto off`). In firmware mode the
keyboard ignores host colour updates by design.

**Tray icon is missing on KDE**

Some minimal Plasma setups do not provide a tray. Closing the window then
quits the app.

## How it works

The report descriptor exposes these feature reports:

| ID | Report | Use |
|----|--------|-----|
| `0x01` | LampArrayAttributes | read lamp count, kind, bounding box |
| `0x05` | LampRangeUpdate | set lamp range to R, G, B, intensity |
| `0x06` | LampArrayControl | autonomous (firmware) mode on/off |

The app scans `/sys/class/hidraw/*/device/uevent` for vendor `0414`, checks
that the report descriptor contains Usage Page `0x59`, then uses the standard
`HIDIOCSFEATURE` / `HIDIOCGFEATURE` hidraw ioctls. Nothing is patched in the
kernel.

## Credits

The LampArray protocol details for this exact laptop were originally
documented by
[Luminous418/Gigabyte-Gaming-A16-Linux-Drivers](https://github.com/Luminous418/Gigabyte-Gaming-A16-Linux-Drivers)
(MIT). This project is an independent implementation with a GUI, animations,
and a slightly different CLI/config model.

## License

MIT — see [LICENSE](LICENSE).
