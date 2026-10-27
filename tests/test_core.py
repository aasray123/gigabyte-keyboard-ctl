#!/usr/bin/env python3
"""Unit tests for the parts that do not need the keyboard."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gigabyte_kbd import config
from gigabyte_kbd.device import LampArray, LampArrayInfo
from gigabyte_kbd.effects import _linear_to_oklab, _oklab_to_linear, frame_rgb, period_seconds


class ColourTests(unittest.TestCase):
    def test_parse_and_format(self) -> None:
        self.assertEqual(config.parse_color("00aaff"), (0, 170, 255))
        self.assertEqual(config.parse_color("#FF0000"), (255, 0, 0))
        self.assertEqual(config.parse_color("f00"), (255, 0, 0))
        self.assertEqual(config.to_hex((0, 170, 255)), "00aaff")

    def test_invalid(self) -> None:
        with self.assertRaises(ValueError):
            config.parse_color("12345")
        with self.assertRaises(ValueError):
            config.parse_color("gggggg")


class SettingsTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.conf"
            settings = config.Settings(
                color="ff0000",
                brightness=42,
                on=True,
                effect="rainbow",
                speed=70,
                autonomous=False,
                product_id="8104",
            )
            config.save(settings, path)
            loaded = config.load(path)
            self.assertEqual(loaded.color, "ff0000")
            self.assertEqual(loaded.brightness, 42)
            self.assertEqual(loaded.effect, "rainbow")
            self.assertEqual(loaded.speed, 70)
            self.assertEqual(loaded.product_id, "8104")

    def test_clamping(self) -> None:
        settings = config.Settings(brightness=500, speed=-4, effect="nope", color="xx")
        settings.clamp()
        self.assertEqual(settings.brightness, 100)
        self.assertEqual(settings.speed, 1)
        self.assertEqual(settings.effect, "static")
        self.assertEqual(settings.color, config.DEFAULT_COLOR)


class EffectTests(unittest.TestCase):
    def test_period_decreases_with_speed(self) -> None:
        self.assertGreater(period_seconds(1), period_seconds(100))
        self.assertGreaterEqual(period_seconds(100), 0.6)

    def test_frames(self) -> None:
        base = (10, 20, 30)
        self.assertEqual(frame_rgb("static", 0.5, base), base)
        self.assertEqual(frame_rgb("breathing", 0.0, base), (0, 1, 2))
        for effect in ("rainbow", "wave"):
            for phase in (0.0, 0.13, 0.25, 0.5, 0.75, 0.99):
                frame = frame_rgb(effect, phase, base)
                self.assertTrue(all(0 <= c <= 255 for c in frame), (effect, phase, frame))
        self.assertEqual(frame_rgb("wave", 0.0, base), config.PALETTE_RGB[0])

    def test_oklab_roundtrip(self) -> None:
        for colour in ((0, 0, 0), (255, 255, 255), (249, 56, 44), (50, 173, 230)):
            linear = tuple(c / 255 for c in colour)
            roundtrip = _oklab_to_linear(_linear_to_oklab(linear))
            for before, after in zip(linear, roundtrip):
                self.assertAlmostEqual(before, after, places=5)


class PaletteTests(unittest.TestCase):
    def test_exact_preset_values(self) -> None:
        expected = [
            "f9382c", "ff9300", "ffd60a", "4bc453", "00c1b6", "32ade6",
            "0a7aff", "af52de", "f6315f", "ffffff", "fdedd4", "000000",
        ]
        self.assertEqual([value for value, _name in config.PRESETS], expected)
        self.assertEqual(
            config.PALETTE_RGB,
            [config.parse_color(value) for value in expected[:-1]],
        )


class FakeLamp(LampArray):
    def __init__(self) -> None:
        super().__init__(path="/dev/fake")
        self._fd = 1
        self._info = LampArrayInfo(
            path="/dev/fake",
            vendor_id="0414",
            product_id="8104",
            lamp_count=1,
            kind=1,
            width_um=12000,
            height_um=16000,
            depth_um=2000,
            min_interval_us=100,
        )

    def close(self) -> None:
        self._fd = None


class ReportTests(unittest.TestCase):
    def test_scaled_colour_report(self) -> None:
        lamp = FakeLamp()
        with mock.patch("gigabyte_kbd.device.fcntl.ioctl") as ioctl:
            lamp.set_scaled_color((255, 128, 0), 50)
        args = ioctl.call_args.args
        self.assertEqual(args[1], 0xC0000000 | (10 << 16) | (ord("H") << 8) | 0x06)
        # array('B', ...) is the ioctl argument
        self.assertEqual(list(args[2]), [0x05, 0x01, 0, 0, 0, 0, 128, 64, 0, 255])

    def test_off(self) -> None:
        lamp = FakeLamp()
        with mock.patch("gigabyte_kbd.device.fcntl.ioctl") as ioctl:
            lamp.off()
        reports = [list(call.args[2]) for call in ioctl.call_args_list]
        self.assertEqual(reports[0], [0x06, 0x00])
        self.assertEqual(reports[1], [0x05, 0x01, 0, 0, 0, 0, 0, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
