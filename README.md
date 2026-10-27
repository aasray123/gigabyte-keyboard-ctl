# gigabyte-keyboard-ctl

RGB backlight control for the **GIGABYTE GAMING A16 (CTH)** on Linux — full
24-bit colour, brightness, and animations, with a GUI and a scriptable CLI.

The A16 keyboard does not expose a normal `/sys/class/leds` backlight. Its
lighting lives on a USB HID interface that implements the
[Microsoft HID LampArray](https://learn.microsoft.com/en-us/windows-hardware/design/component-guidelines/hid-lamparray)
protocol (Usage Page `0x59`). On Windows, Gigabyte Control Center / GiMate
drives that interface; Linux sends nothing, which is why the backlight stays
dark after a cold boot and why OpenRGB / `opengigabyte` do not detect it.

This project talks to the LampArray interface directly through `hidraw`. No
kernel driver is required and nothing needs to be compiled.

## Features

- Any `#RRGGBB` colour (16.7 million choices), not a fixed palette
- 0–100 % brightness (software-scaled, because the firmware's intensity channel
  is on/off only)
- Effects: breathing, palette wave, and a Corsair-style rainbow
- GUI with colour picker, exact-value presets, brightness/effect controls, and
  a system-tray icon
- Scriptable CLI
- Restores the saved state at login (cold-boot fix)
- Optional `Fn+Space` firmware mode
- No root required for daily use in a normal desktop session

## Supported hardware

| Model | USB ID | Status |
|-------|--------|--------|
| GIGABYTE GAMING A16 CTH | `0414:8104` | Tested |
| GIGABYTE GAMING A16 (other revisions) | `0414:8105` | Expected to work |

The keyboard is a **single-zone RGB** device (`LampCount = 1`). Per-key and
left-to-right spatial effects are not possible on this hardware.

## Installation

### Arch Linux / CachyOS (pacman package)

The repository includes a `PKGBUILD`; build and install it with:

```bash
git clone https://github.com/aasray123/gigabyte-keyboard-ctl.git
cd gigabyte-keyboard-ctl
makepkg -si
```

Or, if you already have the built package:

```bash
sudo pacman -U gigabyte-keyboard-ctl-1.0.1-1-any.pkg.tar.zst
```

AUR publication is pending; the included `PKGBUILD` and `.SRCINFO` are ready
for it.

The package installs:

- `/usr/bin/gigabyte-kbd`
- `/usr/lib/gigabyte-keyboard-ctl/`
- `/usr/share/applications/gigabyte-kbd.desktop`
- `/usr/lib/udev/rules.d/99-gigabyte-kbd.rules`
- `/usr/lib/systemd/user/gigabyte-kbd.service`

Optional GUI dependency:

```bash
sudo pacman -S python-pyqt6
```

Enable the login restore service for your user:

```bash
systemctl --user enable --now gigabyte-kbd.service
```

If the hidraw node is not writable, log out and back in so the packaged udev
rule takes effect.

### From source (user-local install)

```bash
git clone https://github.com/aasray123/gigabyte-keyboard-ctl.git
cd gigabyte-keyboard-ctl
./install.sh
```

This installs everything under your home directory:

| Path | Purpose |
|------|---------|
| `~/.local/bin/gigabyte-kbd` | launcher |
| `~/.local/share/gigabyte-keyboard-ctl/` | Python package |
| `~/.local/share/applications/gigabyte-kbd.desktop` | desktop menu entry |
| `~/.config/autostart/gigabyte-kbd.desktop` | `gigabyte-kbd restore` at login |
| `~/.config/gigabyte-kbd/config.conf` | saved colour/brightness/effect |

The optional udev rule is the only system-wide file created by `install.sh`:

```bash
sudo ./install.sh --system
```

Uninstall the user-local install with `./install.sh --uninstall` (add
`--system` with `sudo` to remove the udev rule as well).

## Usage

### GUI

```bash
gigabyte-kbd gui
```

Choose a colour with the swatch or hex field, use a preset, adjust brightness,
and pick an effect. Closing the window keeps the app in the tray; use **Quit**
there to exit. If no tray is available, closing the window exits the app.

### CLI

```bash
gigabyte-kbd info                     # device, lamp count, saved state
gigabyte-kbd color 00aaff             # any RRGGBB colour
gigabyte-kbd color ff0000 -b 40       # red at 40 %
gigabyte-kbd brightness 70            # 0-100
gigabyte-kbd on | off | toggle
gigabyte-kbd effect breathing         # runs until Ctrl+C
gigabyte-kbd effect wave
gigabyte-kbd effect rainbow --speed 80
gigabyte-kbd effect breathing --duration 5
gigabyte-kbd restore                  # re-apply saved state
gigabyte-kbd auto on | off            # firmware mode / host mode
gigabyte-kbd detect
gigabyte-kbd config                   # print config file
```

Settings live in `~/.config/gigabyte-kbd/config.conf` (override with
`GIGABYTE_KBD_CONFIG`).

## Effects

| Effect | Description |
|--------|-------------|
| `static` | One solid colour |
| `breathing` | Smooth brightness fade of the current colour |
| `wave` | Sweeps through the 12 presets in reading order (top row left to right, then bottom row) |
| `rainbow` | Corsair CUE/ckb-next rainbow gradient: red → yellow → green → cyan → blue → magenta → red |

The presets are:

| Name | RGB | Hex |
|------|-----|-----|
| Red | 249, 56, 44 | `f9382c` |
| Orange | 255, 147, 0 | `ff9300` |
| Yellow | 255, 214, 10 | `ffd60a` |
| Green | 75, 196, 83 | `4bc453` |
| Teal | 0, 193, 182 | `00c1b6` |
| Light Blue | 50, 173, 230 | `32ade6` |
| Blue | 10, 122, 255 | `0a7aff` |
| Purple | 175, 82, 222 | `af52de` |
| Pink | 246, 49, 95 | `f6315f` |
| White | 255, 255, 255 | `ffffff` |
| Beige | 253, 237, 212 | `fdedd4` |
| Black (off) | 0, 0, 0 | `000000` |

Because the keyboard has one lighting zone, effects animate the whole keyboard
over time rather than moving between keys. `wave` follows the preset order
instead of a spatial left-to-right path.

## Host mode vs firmware mode

- **Host mode** (default): the app sends the exact RGB value. You get full
  control, but `Fn+Space` does nothing.
- **Firmware mode** (`gigabyte-kbd auto on`, or the GUI checkbox): the keyboard
  firmware drives the LEDs, so `Fn+Space` cycles brightness natively. The
  colour is the firmware's stored one — whatever GiMate last programmed in
  Windows — and may be black after a full power-off.

The GUI starts in the saved mode. Use **Let the keyboard handle Fn+Space** to
switch.

## Cold-boot behaviour

The keyboard keeps its LampArray state across reboots and USB resets, but not
across a full power-off. Windows re-sends the state through GiMate; on Linux
nothing did, so the backlight stayed off.

The login restore runs `gigabyte-kbd restore`, which re-applies the saved
colour. With the packaged install, enable it once per user:

```bash
systemctl --user enable --now gigabyte-kbd.service
```

The user-local install uses an XDG autostart entry instead, so no manual step
is needed.

Animations require a running process: the login restore applies the base
colour statically. Start the GUI or `gigabyte-kbd effect <name>` for
animations.

## Permissions

In a normal desktop session, `systemd-logind` grants the active user access to
the keyboard's hidraw node. The packaged udev rule uses the same `uaccess` tag
as a fallback:

```udev
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0414", TAG+="uaccess"
```

Check access with:

```bash
ls -l /dev/hidraw*
getfacl /dev/hidraw*
```

If your user lacks `rw`, log out and back in after installing the package.

## Limitations

- **Single zone.** The keyboard reports `LampCount = 1`; there is no per-key or
  multi-zone control. Spatial waves are impossible in hardware.
- **Brightness is software-scaled.** The firmware reports one intensity level
  (`intensity_lvls = 1`), so the LampArray intensity channel is effectively
  on/off. The app scales RGB instead.
- **Animations need a running process.** Login restore is static.
- **Firmware mode colour belongs to the firmware.** Host writes do not update
  it.
- If another program (OpenRGB, GiMate in a VM, a vendor daemon) writes to the
  same hidraw node, the last writer wins.

## Troubleshooting

**`Error: GIGABYTE LampArray device (0414:*) not found`**

```bash
lsusb | grep -i gigabyte
gigabyte-kbd detect
```

The keyboard should appear as `0414:8104` or `0414:8105`.

**`cannot open /dev/hidrawN: Permission denied`**

Install the udev rule, then log out and back in:

```bash
sudo ./install.sh --system          # source checkout
# or reinstall the package, which ships the rule
```

**GUI does not start**

```bash
sudo pacman -S python-pyqt6
```

The CLI has no GUI dependency.

**Colour changes do nothing**

Turn off firmware mode:

```bash
gigabyte-kbd auto off
```

**Tray icon missing**

Some minimal Plasma setups do not provide a tray. Closing the window then
quits the app.

## How it works

The keyboard's report descriptor exposes these feature reports:

| ID | Report | Use |
|----|--------|-----|
| `0x01` | LampArrayAttributes | read lamp count, kind, bounding box |
| `0x05` | LampRangeUpdate | set a lamp range to R, G, B, intensity |
| `0x06` | LampArrayControl | autonomous (firmware) mode on/off |

The app scans `/sys/class/hidraw/*/device/uevent` for vendor `0414`, verifies
that the report descriptor contains Usage Page `0x59`, then uses the standard
`HIDIOCSFEATURE` / `HIDIOCGFEATURE` hidraw ioctls. Nothing is patched in the
kernel, and the app does not access the network.

## Credits

LampArray protocol details for this laptop were originally documented by
[Luminous418/Gigabyte-Gaming-A16-Linux-Drivers](https://github.com/Luminous418/Gigabyte-Gaming-A16-Linux-Drivers)
(MIT). This project is an independent implementation with a GUI, animations,
and a different CLI/config model.

The rainbow gradient mirrors Corsair CUE's Rainbow / Rainbow Wave stops, as
implemented in [ckb-next](https://github.com/ckb-next/ckb-next) (GPL-2.0):
red 0 %, yellow 17 %, green 33 %, cyan 50 %, blue 67 %, magenta 83 %, red
100 %. Only the colour constants are shared; no ckb-next code is included.

## License

MIT — see [LICENSE](LICENSE).
