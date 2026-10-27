"""Whole-keyboard animation effects.

The keyboard has one RGB zone, so a spatial ("left to right across the keys")
wave is not possible in hardware.  The ``wave`` effect instead sweeps through
the 12-swatch palette in reading order -- top row left to right, then bottom
row left to right -- with smooth perceptual interpolation.

The ``rainbow`` effect mirrors the Corsair CUE/ckb-next rainbow gradient:
full-saturation red, yellow, green, cyan, blue, magenta and back to red, with
the stops at 0/17/33/50/67/83/100 % and linear interpolation between them.
That is the same gradient Corsair keyboards use for their Rainbow and Rainbow
Wave presets.

Frames are sent as LampArray range updates at 25 fps.
"""

from __future__ import annotations

import math
import threading
import time

from .config import PALETTE_RGB, Settings, parse_color
from .device import LampArray

FPS = 25

# Corsair's rainbow gradient, as used by CUE / ckb-next:
#   0 % red, 17 % yellow, 33 % green, 50 % cyan, 67 % blue, 83 % magenta,
#   100 % red again.  Colours are interpolated in 8-bit sRGB, matching
#   ckb-next's ckb_grad_color().
CORSAIR_RAINBOW_STOPS = (
    (0.0, (255, 0, 0)),
    (17.0, (255, 255, 0)),
    (33.0, (0, 255, 0)),
    (50.0, (0, 255, 255)),
    (67.0, (0, 0, 255)),
    (83.0, (255, 0, 255)),
    (100.0, (255, 0, 0)),
)


def period_seconds(speed: int) -> float:
    """Map the 1-100 speed setting to one full effect cycle."""
    return max(0.6, 9.0 - 0.08 * max(1, min(100, speed)))


# -- colour-space helpers --------------------------------------------------


def _srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(channel: float) -> float:
    channel = max(0.0, min(1.0, channel))
    return 12.92 * channel if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def _linear_to_oklab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    red, green, blue = rgb
    l = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    m = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    s = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    l_ = math.copysign(abs(l) ** (1 / 3), l)
    m_ = math.copysign(abs(m) ** (1 / 3), m)
    s_ = math.copysign(abs(s) ** (1 / 3), s)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _oklab_to_linear(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    lightness, a, b = lab
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    return (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def _linear_to_rgb8(rgb: tuple[float, float, float]) -> tuple[int, int, int]:
    return tuple(round(_linear_to_srgb(channel) * 255) for channel in rgb)  # type: ignore[return-value]


def _mix(
    first: tuple[float, float, float], second: tuple[float, float, float], amount: float
) -> tuple[float, float, float]:
    return tuple(a + (b - a) * amount for a, b in zip(first, second))  # type: ignore[return-value]


def _gradient_rgb(
    stops: tuple[tuple[float, tuple[int, int, int]], ...], position: float
) -> tuple[int, int, int]:
    position = max(0.0, min(100.0, position))
    for index in range(1, len(stops)):
        end_position, end_colour = stops[index]
        if position <= end_position:
            start_position, start_colour = stops[index - 1]
            span = end_position - start_position
            amount = (position - start_position) / span if span else 0.0
            return tuple(  # type: ignore[return-value]
                round(start + (end - start) * amount)
                for start, end in zip(start_colour, end_colour)
            )
    return stops[-1][1]


_PALETTE_OKLAB = tuple(
    _linear_to_oklab(tuple(_srgb_to_linear(channel / 255) for channel in rgb))
    for rgb in PALETTE_RGB
)


# -- effects ---------------------------------------------------------------


def rainbow_rgb(phase: float) -> tuple[int, int, int]:
    """Corsair-style full-saturation rainbow (red -> yellow -> ... -> red)."""
    return _gradient_rgb(CORSAIR_RAINBOW_STOPS, (phase % 1.0) * 100.0)


def palette_wave_rgb(phase: float) -> tuple[int, int, int]:
    """Sweep through the palette in reading order, interpolated in Oklab."""
    count = len(_PALETTE_OKLAB)
    position = (phase % 1.0) * count
    index = int(position) % count
    amount = position - int(position)
    lab = _mix(_PALETTE_OKLAB[index], _PALETTE_OKLAB[(index + 1) % count], amount)
    return _linear_to_rgb8(_oklab_to_linear(lab))


def frame_rgb(effect: str, phase: float, base: tuple[int, int, int]) -> tuple[int, int, int]:
    if effect == "rainbow":
        return rainbow_rgb(phase)
    if effect == "wave":
        return palette_wave_rgb(phase)
    if effect == "breathing":
        factor = 0.05 + 0.95 * (0.5 - 0.5 * math.cos(2 * math.pi * phase))
        return tuple(round(channel * factor) for channel in base)  # type: ignore[return-value]
    return base


class EffectRunner:
    """Run an effect in a background daemon thread."""

    def __init__(self, lamp: LampArray, settings: Settings) -> None:
        self._lamp = lamp
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._effect = settings.effect
        self._rgb = parse_color(settings.color)
        self._brightness = settings.brightness
        self._speed = settings.speed
        self.error: Exception | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def update(self, settings: Settings) -> None:
        with self._lock:
            self._effect = settings.effect
            self._rgb = parse_color(settings.color)
            self._brightness = settings.brightness
            self._speed = settings.speed

    def start(self) -> None:
        if self.running:
            return
        self.error = None
        self._stop.clear()
        self._lamp.set_autonomous(False)
        self._thread = threading.Thread(
            target=self._loop, name="gigabyte-kbd-effects", daemon=True
        )
        self._thread.start()

    def stop(self, *, apply_static: bool = False) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if apply_static:
            with self._lock:
                self._lamp.set_scaled_color(self._rgb, self._brightness)

    def _loop(self) -> None:
        started = time.monotonic()
        interval = 1.0 / FPS
        while not self._stop.wait(interval):
            with self._lock:
                effect = self._effect
                rgb = self._rgb
                brightness = self._brightness
                period = period_seconds(self._speed)
            if effect == "wave":
                period *= 2.0  # 11 palette segments need a little more time
            phase = ((time.monotonic() - started) / period) % 1.0
            try:
                self._lamp.set_scaled_color(frame_rgb(effect, phase, rgb), brightness)
            except Exception as exc:  # device unplugged, permission revoked, ...
                self.error = exc
                self._stop.set()
                return
