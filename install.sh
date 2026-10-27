#!/usr/bin/env bash
# Install the GIGABYTE A16 keyboard backlight app for the current user.
#
#   ./install.sh                 user install (~/.local, autostart at login)
#   ./install.sh --no-autostart  user install without the login restore entry
#   sudo ./install.sh --system   install the optional udev rule
#   ./install.sh --uninstall     remove the user install
#   sudo ./install.sh --system --uninstall
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
SHARE_DIR="$DATA_HOME/gigabyte-keyboard-ctl"
BIN_DIR="$HOME/.local/bin"
BIN="$BIN_DIR/gigabyte-kbd"
AUTOSTART="$CONFIG_HOME/autostart/gigabyte-kbd.desktop"
DESKTOP_FILE="$DATA_HOME/applications/gigabyte-kbd.desktop"
UDEV_RULE="/etc/udev/rules.d/99-gigabyte-kbd.rules"

SYSTEM=0
UNINSTALL=0
AUTOSTART_ENABLED=1
for arg in "$@"; do
    case "$arg" in
        --system) SYSTEM=1 ;;
        --uninstall|--remove) UNINSTALL=1 ;;
        --no-autostart) AUTOSTART_ENABLED=0 ;;
        -h|--help)
            sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            exit 2
            ;;
    esac
done

if [[ $SYSTEM -eq 1 ]]; then
    if [[ $EUID -ne 0 ]]; then
        echo "System install needs root: sudo $0 --system" >&2
        exit 1
    fi
    if [[ $UNINSTALL -eq 1 ]]; then
        rm -f "$UDEV_RULE"
        udevadm control --reload-rules
        udevadm trigger --subsystem-match=hidraw
        echo "Removed $UDEV_RULE"
    else
        install -Dm644 "$ROOT_DIR/udev/99-gigabyte-kbd.rules" "$UDEV_RULE"
        udevadm control --reload-rules
        udevadm trigger --subsystem-match=hidraw
        echo "Installed $UDEV_RULE"
        echo "Log out and back in if the hidraw nodes are still not writable."
    fi
    exit 0
fi

if [[ $EUID -eq 0 ]]; then
    echo "Run the user install as your normal account, not as root." >&2
    echo "For the optional udev rule use: sudo $0 --system" >&2
    exit 1
fi

if [[ $UNINSTALL -eq 1 ]]; then
    rm -rf "$SHARE_DIR"
    rm -f "$BIN" "$AUTOSTART" "$DESKTOP_FILE"
    echo "Removed the user install."
    echo "Settings are still in $CONFIG_HOME/gigabyte-kbd/ (delete manually if wanted)."
    exit 0
fi

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

install -d "$SHARE_DIR" "$BIN_DIR"
rm -rf "$SHARE_DIR/gigabyte_kbd"
cp -r "$ROOT_DIR/gigabyte_kbd" "$SHARE_DIR/"
find "$SHARE_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} +
install -Dm755 "$ROOT_DIR/bin/gigabyte-kbd" "$BIN"
install -Dm644 "$ROOT_DIR/data/gigabyte-kbd.desktop" "$DESKTOP_FILE"

if [[ $AUTOSTART_ENABLED -eq 1 ]]; then
    install -d "$(dirname "$AUTOSTART")"
    cat > "$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=GIGABYTE A16 Keyboard Backlight
Comment=Restore the keyboard backlight colour at login
Exec="$BIN" restore
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
    echo "Installed login restore: $AUTOSTART"
fi

if ! python3 -c 'import PyQt6' 2>/dev/null; then
    echo "Note: PyQt6 is not installed; the CLI works, but the GUI needs it."
    echo "      On CachyOS/Arch: sudo pacman -S python-pyqt6"
fi

echo
echo "Installed: $BIN"
echo "Try:"
echo "  gigabyte-kbd info"
echo "  gigabyte-kbd color 00aaff"
echo "  gigabyte-kbd effect rainbow"
echo "  gigabyte-kbd gui"
echo
if ! "$BIN" info >/dev/null 2>&1; then
    echo "The keyboard could not be opened yet. Check permissions with:"
    echo "  ls -l /dev/hidraw*"
    echo "If needed, install the udev rule:  sudo $0 --system"
fi
