"""Command line interface."""

from __future__ import annotations

import argparse
import sys
import time

from . import config
from .config import Settings
from .device import DeviceError, LampArray, detect_ids
from .effects import EffectRunner


def _open(settings: Settings) -> LampArray:
    return LampArray(
        vendor_id=settings.vendor_id,
        product_id=settings.product_id or None,
    ).open()


def _apply(settings: Settings, lamp: LampArray) -> None:
    """Apply the saved state without starting an animation."""
    if settings.autonomous:
        lamp.set_autonomous(True)
        return
    if settings.on:
        lamp.set_color(settings.rgb(), settings.brightness)
    else:
        lamp.off()


def _show(colour: tuple[int, int, int]) -> str:
    return "#" + config.to_hex(colour)


def cmd_info(args: argparse.Namespace) -> int:
    settings = config.load()
    with _open(settings) as lamp:
        info = lamp.info()
    print(f"Device:       {info.path} ({info.vendor_id}:{info.product_id})")
    print(f"Lamp count:   {info.lamp_count} (single RGB zone)")
    print(f"Kind:         {info.kind_name} ({info.kind})")
    print(f"Bounding box: {info.width_um}x{info.height_um}x{info.depth_um} um")
    print(f"Min interval: {info.min_interval_us} us")
    print(f"Config:       {config.config_path()}")
    print(
        "Saved state:  "
        f"{_show(settings.rgb())} brightness={settings.brightness} "
        f"{'on' if settings.on else 'off'} effect={settings.effect} "
        f"({'firmware' if settings.autonomous else 'host'} mode)"
    )
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    ids = detect_ids()
    if ids is None:
        print("No GIGABYTE LampArray device found", file=sys.stderr)
        return 1
    settings = config.load()
    lamp = _open(settings)
    try:
        print(f"{ids[0]} {ids[1]} {lamp.path}")
    finally:
        lamp.close()
    return 0


def cmd_color(args: argparse.Namespace) -> int:
    settings = config.load()
    try:
        rgb = config.parse_color(args.color)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.brightness is not None:
        settings.brightness = args.brightness
    settings.color = config.to_hex(rgb)
    settings.on = any(rgb) and settings.brightness > 0
    settings.effect = "static"
    settings.autonomous = args.auto
    settings.clamp()
    with _open(settings) as lamp:
        lamp.set_color(rgb, settings.brightness, autonomous=args.auto)
    config.save(settings)
    mode = "firmware/autonomous" if args.auto else "host"
    print(
        f"Set {_show(rgb)} at {settings.brightness}% brightness "
        f"({mode} mode, {lamp.info().lamp_count} zone)"
    )
    return 0


def cmd_brightness(args: argparse.Namespace) -> int:
    settings = config.load()
    settings.brightness = max(0, min(100, args.value))
    settings.on = settings.brightness > 0
    settings.clamp()
    if settings.effect == "static":
        with _open(settings) as lamp:
            lamp.set_color(settings.rgb(), settings.brightness)
    else:
        print(
            f"Brightness saved ({settings.brightness}%); it will be used the "
            f"next time the '{settings.effect}' effect starts."
        )
    config.save(settings)
    if settings.effect == "static":
        print(f"Brightness set to {settings.brightness}%")
    return 0


def cmd_on(args: argparse.Namespace) -> int:
    settings = config.load()
    settings.on = True
    settings.effect = "static"
    settings.autonomous = False
    if settings.brightness == 0:
        settings.brightness = 100
    with _open(settings) as lamp:
        lamp.set_color(settings.rgb(), settings.brightness)
    config.save(settings)
    print(f"Backlight on ({_show(settings.rgb())} at {settings.brightness}%)")
    return 0


def cmd_off(args: argparse.Namespace) -> int:
    settings = config.load()
    settings.on = False
    with _open(settings) as lamp:
        lamp.off()
    settings.autonomous = False
    config.save(settings)
    print("Backlight off")
    return 0


def cmd_toggle(args: argparse.Namespace) -> int:
    settings = config.load()
    return cmd_off(args) if settings.on else cmd_on(args)


def cmd_auto(args: argparse.Namespace) -> int:
    settings = config.load()
    enabled = args.state != "off"
    with _open(settings) as lamp:
        if enabled:
            lamp.set_autonomous(True)
        else:
            lamp.set_autonomous(False)
            if settings.on:
                lamp.set_color(settings.rgb(), settings.brightness)
    settings.autonomous = enabled
    config.save(settings)
    if enabled:
        print(
            "Firmware control enabled: Fn+Space cycles brightness using the "
            "colour stored by Gigabyte Control Center (may be off after a "
            "full power cycle)."
        )
    else:
        print("Host control enabled: the colour saved in this app is used.")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    settings = config.load()
    with _open(settings) as lamp:
        if settings.autonomous:
            lamp.set_autonomous(True)
            print("Restored firmware/autonomous mode")
        elif not settings.on:
            lamp.off()
            print("Restored saved state: off")
        else:
            # Animations need a running process, so a login restore applies
            # the base colour as a static frame.
            lamp.set_color(settings.rgb(), settings.brightness)
            suffix = (
                f" (effect '{settings.effect}' saved; run the GUI or "
                f"'gigabyte-kbd effect {settings.effect}' to animate)"
                if settings.effect != "static"
                else ""
            )
            print(
                f"Restored {_show(settings.rgb())} at "
                f"{settings.brightness}%{suffix}"
            )
    return 0


def cmd_effect(args: argparse.Namespace) -> int:
    if args.name not in config.EFFECTS:
        print(
            f"Error: unknown effect {args.name!r}; choose from "
            + ", ".join(config.EFFECTS),
            file=sys.stderr,
        )
        return 2
    settings = config.load()
    settings.effect = args.name
    if args.speed is not None:
        settings.speed = args.speed
    if args.brightness is not None:
        settings.brightness = args.brightness
    settings.on = True
    settings.autonomous = False
    settings.clamp()

    with _open(settings) as lamp:
        if args.duration or args.name == "static":
            if args.name == "static":
                lamp.set_color(settings.rgb(), settings.brightness)
                config.save(settings)
                print(f"Static {_show(settings.rgb())} at {settings.brightness}%")
                return 0
            runner = EffectRunner(lamp, settings)
            runner.start()
            try:
                time.sleep(args.duration)
            except KeyboardInterrupt:
                pass
            finally:
                runner.stop(apply_static=True)
            config.save(settings)
            print("Effect stopped")
            return 0

        print(
            f"Effect '{args.name}' at speed {settings.speed} "
            f"(Ctrl+C to stop)"
        )
        runner = EffectRunner(lamp, settings)
        runner.start()
        try:
            while runner.running:
                time.sleep(0.2)
                if runner.error is not None:
                    raise runner.error
        except KeyboardInterrupt:
            print()
        finally:
            runner.stop(apply_static=True)
            config.save(settings)
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    settings = config.load()
    print(f"# {config.config_path()}")
    for line in config.save(settings).read_text(encoding="utf-8").splitlines():
        print(line)
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    try:
        from .gui import main as gui_main
    except ImportError as exc:
        print(f"Error: GUI dependencies are missing: {exc}", file=sys.stderr)
        print("Install PyQt6 (e.g. sudo pacman -S python-pyqt6).", file=sys.stderr)
        return 1
    return gui_main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gigabyte-kbd",
        description=(
            "Control the RGB backlight of the GIGABYTE GAMING A16 (CTH) "
            "keyboard over its HID LampArray interface."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="show device details and saved state").set_defaults(
        func=cmd_info
    )
    sub.add_parser("detect", help="print the detected device IDs").set_defaults(
        func=cmd_detect
    )
    sub.add_parser("gui", help="open the graphical control panel").set_defaults(
        func=cmd_gui
    )
    sub.add_parser("config", help="print the configuration").set_defaults(
        func=cmd_config
    )

    p = sub.add_parser("color", help="set a solid colour (16.7 million choices)")
    p.add_argument("color", help="hex colour, e.g. ff0000 or #00aaff")
    p.add_argument("-b", "--brightness", type=int, metavar="0-100")
    p.add_argument(
        "--auto",
        action="store_true",
        help="hand control back to the firmware afterwards (Fn+Space works)",
    )
    p.set_defaults(func=cmd_color)

    p = sub.add_parser("brightness", help="set brightness 0-100")
    p.add_argument("value", type=int)
    p.set_defaults(func=cmd_brightness)

    sub.add_parser("on", help="turn the backlight on").set_defaults(func=cmd_on)
    sub.add_parser("off", help="turn the backlight off").set_defaults(func=cmd_off)
    sub.add_parser("toggle", help="toggle on/off").set_defaults(func=cmd_toggle)
    sub.add_parser(
        "restore", help="re-apply the saved state (used at login)"
    ).set_defaults(func=cmd_restore)

    p = sub.add_parser("auto", help="enable or disable firmware (Fn+Space) mode")
    p.add_argument("state", nargs="?", choices=("on", "off"), default="on")
    p.set_defaults(func=cmd_auto)

    p = sub.add_parser("effect", help="run an animation until Ctrl+C")
    p.add_argument("name", choices=config.EFFECTS)
    p.add_argument("--speed", type=int, metavar="1-100")
    p.add_argument("-b", "--brightness", type=int, metavar="0-100")
    p.add_argument(
        "--duration",
        type=float,
        metavar="SECONDS",
        help="stop automatically (useful for scripts and tests)",
    )
    p.set_defaults(func=cmd_effect)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except BrokenPipeError:
        return 0
    except DeviceError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
