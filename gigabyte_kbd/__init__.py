"""Userspace lighting control for the GIGABYTE GAMING A16 (CTH) keyboard.

The keyboard exposes a single-zone Microsoft HID LampArray interface
(Usage Page 0x59).  This package talks to it directly through hidraw, so it
works without a vendor driver, without root (when the hidraw node is
accessible), and without the Gigabyte Control Center.
"""

__version__ = "1.0.1"
__all__ = ["__version__"]
