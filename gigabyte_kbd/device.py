"""Low-level HID LampArray access for the GIGABYTE GAMING A16 keyboard.

Report map used here (taken from the keyboard's HID report descriptor):

    0x01  LampArrayAttributesReport   read    lamp count, kind, bounding box
    0x02  LampAttributesRequestReport write   request details for one lamp
    0x03  LampAttributesResponseReport read   position, purposes, levels
    0x05  LampRangeUpdateReport       write   set a range of lamps to one RGBA
    0x06  LampArrayControlReport      write   AutonomousMode on/off

Only feature reports are used.  The device reports one lamp, i.e. the whole
keyboard is a single RGB zone.
"""

from __future__ import annotations

import array
import fcntl
import glob
import os
import struct
from dataclasses import dataclass

VENDOR_ID = "0414"
KNOWN_PRODUCT_IDS = ("8105", "8104")

LAMP_KINDS = {
    0: "Undefined",
    1: "Keyboard",
    2: "Mouse",
    3: "GameController",
    4: "Peripheral",
    5: "Scene",
    6: "Notification",
    7: "Chassis",
    8: "Wearable",
    9: "Furniture",
}

_ATTR_REPORT_ID = 0x01
_ATTR_REPORT_SIZE = 23
_RANGE_REPORT_ID = 0x05
_CONTROL_REPORT_ID = 0x06


class DeviceError(RuntimeError):
    """The LampArray device could not be found or used."""


class DeviceAccessError(DeviceError):
    """The hidraw node exists but this user may not open it."""


def _hidioctl(nr: int, size: int) -> int:
    # _IOWR('H', nr, size) == _IOC(_IOC_READ | _IOC_WRITE, 'H', nr, size)
    return 0xC0000000 | (size << 16) | (ord("H") << 8) | nr


def _parse_hid_id(uevent: str) -> tuple[str, str] | None:
    for line in uevent.splitlines():
        if line.startswith("HID_ID="):
            try:
                _bus, vid, pid = line.split("=", 1)[1].split(":")
            except ValueError:
                return None
            return vid.lower()[-4:], pid.lower()[-4:]
    return None


def _has_lamparray(descriptor_path: str) -> bool:
    """True when the report descriptor contains Usage Page 0x59."""
    try:
        with open(descriptor_path, "rb") as fh:
            return b"\x05\x59" in fh.read()
    except OSError:
        return False


def detect_ids() -> tuple[str, str] | None:
    """Return (vendor_id, product_id) of the LampArray interface."""
    for uevent in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        try:
            with open(uevent, encoding="ascii") as fh:
                ids = _parse_hid_id(fh.read())
        except OSError:
            continue
        if not ids or ids[0] != VENDOR_ID:
            continue
        descriptor = os.path.join(os.path.dirname(uevent), "report_descriptor")
        if _has_lamparray(descriptor):
            return ids
    return None


def find_device(
    vendor_id: str | None = None,
    product_id: str | None = None,
) -> str:
    """Return the /dev/hidraw* node of the keyboard's LampArray interface.

    ``vendor_id``/``product_id`` may be used to pin a specific revision.
    With no arguments the first GIGABYTE LampArray interface is returned.
    """
    vendor = (vendor_id or VENDOR_ID).lower()
    product = (product_id or "").lower().lstrip("#")

    for device in sorted(glob.glob("/sys/class/hidraw/hidraw*/device")):
        try:
            with open(os.path.join(device, "uevent"), encoding="ascii") as fh:
                ids = _parse_hid_id(fh.read())
        except OSError:
            continue
        if not ids or ids[0] != vendor:
            continue
        if product and ids[1] != product:
            continue
        if not _has_lamparray(os.path.join(device, "report_descriptor")):
            continue
        return "/dev/" + os.path.basename(os.path.dirname(device))

    wanted = f"{vendor}:{product or '*'}"
    raise DeviceError(f"GIGABYTE LampArray device ({wanted}) not found")


@dataclass(frozen=True)
class LampArrayInfo:
    path: str
    vendor_id: str
    product_id: str
    lamp_count: int
    kind: int
    width_um: int
    height_um: int
    depth_um: int
    min_interval_us: int

    @property
    def kind_name(self) -> str:
        return LAMP_KINDS.get(self.kind, "Unknown")


class LampArray:
    """Open hidraw node and send LampArray feature reports."""

    def __init__(
        self,
        path: str | None = None,
        vendor_id: str | None = None,
        product_id: str | None = None,
    ) -> None:
        self.path = path or find_device(vendor_id, product_id)
        self._fd: int | None = None
        self._info: LampArrayInfo | None = None

    # -- lifecycle ---------------------------------------------------------

    def open(self) -> "LampArray":
        if self._fd is not None:
            return self
        try:
            self._fd = os.open(self.path, os.O_RDWR)
        except OSError as exc:
            if exc.errno in (1, 13):  # EPERM, EACCES
                raise DeviceAccessError(
                    f"cannot open {self.path}: {exc.strerror}. "
                    "Install the udev rule from this project (sudo ./install.sh "
                    "--system) or add your user to the 'input' group, then log "
                    "out and back in."
                ) from exc
            raise DeviceError(f"cannot open {self.path}: {exc}") from exc
        return self

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "LampArray":
        return self.open()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def fd(self) -> int:
        if self._fd is None:
            raise DeviceError("device is not open")
        return self._fd

    # -- feature reports ---------------------------------------------------

    def _get_feature(self, report_id: int, size: int) -> bytes:
        buf = array.array("B", [report_id] + [0] * (size - 1))
        fcntl.ioctl(self.fd, _hidioctl(0x07, size), buf)
        return bytes(buf)

    def _set_feature(self, data: list[int]) -> None:
        buf = array.array("B", data)
        fcntl.ioctl(self.fd, _hidioctl(0x06, len(data)), buf)

    # -- public protocol ---------------------------------------------------

    def info(self) -> LampArrayInfo:
        if self._info is not None:
            return self._info
        report = self._get_feature(_ATTR_REPORT_ID, _ATTR_REPORT_SIZE)
        lamp_count = struct.unpack_from("<H", report, 1)[0]
        width, height, depth, kind, interval = struct.unpack_from("<IIIII", report, 3)
        vendor, product = detect_ids() or (VENDOR_ID, "")
        self._info = LampArrayInfo(
            path=self.path,
            vendor_id=vendor,
            product_id=product,
            lamp_count=lamp_count,
            kind=kind,
            width_um=width,
            height_um=height,
            depth_um=depth,
            min_interval_us=interval,
        )
        return self._info

    def set_autonomous(self, enabled: bool) -> None:
        """Hand control to the keyboard firmware (Fn+Space works)."""
        self._set_feature([_CONTROL_REPORT_ID, 1 if enabled else 0])

    def set_range(
        self,
        red: int,
        green: int,
        blue: int,
        intensity: int = 255,
        *,
        start: int = 0,
        end: int | None = None,
        flags: int = 0x01,
    ) -> None:
        """Set a lamp range to one colour.  Defaults to every lamp."""
        if end is None:
            end = max(self.info().lamp_count - 1, 0)
        data = [_RANGE_REPORT_ID, flags]
        data += [start & 0xFF, (start >> 8) & 0xFF]
        data += [end & 0xFF, (end >> 8) & 0xFF]
        data += [
            max(0, min(255, red)),
            max(0, min(255, green)),
            max(0, min(255, blue)),
            max(0, min(255, intensity)),
        ]
        self._set_feature(data)

    def set_scaled_color(
        self,
        rgb: tuple[int, int, int],
        brightness: int = 100,
    ) -> None:
        """Send one RGB value, scaling it for 0-100 brightness.

        The firmware reports a single intensity level (on/off only), so
        brightness is emulated by scaling the RGB values.
        """
        scale = max(0, min(100, brightness)) / 100.0
        red, green, blue = (round(channel * scale) for channel in rgb)
        self.set_range(red, green, blue, 255)

    def set_color(
        self,
        rgb: tuple[int, int, int],
        brightness: int = 100,
        *,
        autonomous: bool = False,
    ) -> None:
        """Apply a colour with 0-100 brightness in host mode."""
        self.set_autonomous(False)
        self.set_scaled_color(rgb, brightness)
        if autonomous:
            self.set_autonomous(True)

    def off(self) -> None:
        self.set_autonomous(False)
        self.set_range(0, 0, 0, 0)
