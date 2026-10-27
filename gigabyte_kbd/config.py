"""Persistent settings and colour helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .device import VENDOR_ID

DEFAULT_COLOR = "00aaff"
DEFAULT_BRIGHTNESS = 100
DEFAULT_EFFECT = "static"
DEFAULT_SPEED = 50

EFFECTS = ("static", "breathing", "wave", "rainbow")

# Two rows of six, matching the GUI palette.  The "wave" effect follows this
# exact order: top row left to right, then bottom row left to right.
PRESETS = [
    ("f9382c", "Red"),
    ("ff9300", "Orange"),
    ("ffd60a", "Yellow"),
    ("4bc453", "Green"),
    ("00c1b6", "Teal"),
    ("32ade6", "Light Blue"),
    ("0a7aff", "Blue"),
    ("af52de", "Purple"),
    ("f6315f", "Pink"),
    ("ffffff", "White"),
    ("fdedd4", "Beige"),
    ("000000", "Black"),
]


def config_path() -> Path:
    override = os.environ.get("GIGABYTE_KBD_CONFIG")
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "gigabyte-kbd" / "config.conf"


def parse_color(value: str) -> tuple[int, int, int]:
    """Parse ``RRGGBB`` or ``#RRGGBB`` into an RGB tuple."""
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ValueError(f"invalid colour {value!r}; expected RRGGBB")
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError as exc:
        raise ValueError(f"invalid colour {value!r}; expected RRGGBB") from exc


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "{:02x}{:02x}{:02x}".format(*(max(0, min(255, c)) for c in rgb))


# The wave skips black: it is the "off" swatch, not a colour to fade through.
PALETTE_RGB = [
    parse_color(value) for value, _name in PRESETS if value != PRESETS[-1][0]
]


@dataclass
class Settings:
    color: str = DEFAULT_COLOR
    brightness: int = DEFAULT_BRIGHTNESS
    on: bool = True
    effect: str = DEFAULT_EFFECT
    speed: int = DEFAULT_SPEED
    autonomous: bool = False
    vendor_id: str = VENDOR_ID
    product_id: str = ""

    def rgb(self) -> tuple[int, int, int]:
        return parse_color(self.color)

    def clamp(self) -> None:
        self.brightness = max(0, min(100, int(self.brightness)))
        self.speed = max(1, min(100, int(self.speed)))
        if self.effect not in EFFECTS:
            self.effect = DEFAULT_EFFECT
        try:
            self.color = to_hex(parse_color(self.color))
        except ValueError:
            self.color = DEFAULT_COLOR


def load(path: Path | None = None) -> Settings:
    path = path or config_path()
    settings = Settings()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return settings

    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    for field in ("color", "vendor_id", "product_id", "effect"):
        if values.get(field):
            setattr(settings, field, values[field])
    for field in ("brightness", "speed"):
        if values.get(field):
            try:
                setattr(settings, field, int(values[field]))
            except ValueError:
                pass
    for field in ("on", "autonomous"):
        if values.get(field):
            setattr(settings, field, values[field].lower() in ("1", "true", "yes", "on"))

    # Environment overrides are useful for testing and multi-device setups.
    settings.vendor_id = os.environ.get("GIGABYTE_KBD_VID", settings.vendor_id)
    settings.product_id = os.environ.get("GIGABYTE_KBD_PID", settings.product_id)

    settings.clamp()
    return settings


def save(settings: Settings, path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# GIGABYTE GAMING A16 keyboard backlight",
        f"vendor_id={settings.vendor_id}",
        f"product_id={settings.product_id}",
        f"color={settings.color}",
        f"brightness={settings.brightness}",
        f"on={'true' if settings.on else 'false'}",
        f"effect={settings.effect}",
        f"speed={settings.speed}",
        f"autonomous={'true' if settings.autonomous else 'false'}",
        "",
    ]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, path)
    return path
