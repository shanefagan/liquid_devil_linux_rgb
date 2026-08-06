#!/usr/bin/env python3
"""Linux I2C RGB Control for PowerColor Radeon RX 7900 XTX Liquid Devil.

Reverse-engineered hardware protocol implementation for the V2 I2C RGB controller (0x22).
"""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import glob
import os
import sys
import time
from typing import TYPE_CHECKING

from typing_extensions import Self

if TYPE_CHECKING:
    from types import TracebackType

# I2C constants
I2C_RDWR: int = 0x0707
DEFAULT_ADDR: int = 0x22
DELAY: float = 0.03  # 30ms pause for real-time ~33 FPS updates


class I2CMsg(ctypes.Structure):
    """Linux i2c_msg structure for raw ioctl communication."""

    _fields_ = [
        ("addr", ctypes.c_uint16),
        ("flags", ctypes.c_uint16),
        ("len", ctypes.c_uint16),
        ("buf", ctypes.c_char_p),
    ]


class I2CRdwrIoctlData(ctypes.Structure):
    """Linux i2c_rdwr_ioctl_data structure for I2C_RDWR ioctl calls."""

    _fields_ = [
        ("msgs", ctypes.POINTER(I2CMsg)),
        ("nmsgs", ctypes.c_uint32),
    ]


def find_oem_i2c_bus() -> str:
    """Auto-detect the AMDGPU DM i2c OEM bus path from /sys/class/i2c-adapter.

    Returns:
        Device path for the OEM bus (e.g. '/dev/i2c-7').
    """
    for name_file in glob.glob("/sys/class/i2c-adapter/i2c-*/name"):
        try:
            with open(name_file, encoding="utf-8") as f:
                content = f.read().strip()
                if "AMDGPU DM i2c OEM bus" in content:
                    dev_name = os.path.basename(os.path.dirname(name_file))
                    return f"/dev/{dev_name}"
        except OSError:
            continue
    return "/dev/i2c-7"


class LiquidDevilRGB:
    """Hardware controller interface for PowerColor RX 7900 XTX Liquid Devil RGB lighting."""

    def __init__(self, bus_path: str | None = None, addr: int = DEFAULT_ADDR) -> None:
        """Initialize the RGB controller instance.

        Args:
            bus_path: Optional path to the i2c device (auto-detected if None).
            addr: 7-bit I2C device address (default: 0x22).
        """
        self.bus_path: str = bus_path or find_oem_i2c_bus()
        self.addr: int = addr
        self.fd: int | None = None

    def open(self) -> None:
        """Open the I2C device file descriptor."""
        if not os.path.exists(self.bus_path):
            raise FileNotFoundError(
                f"I2C bus path '{self.bus_path}' not found. "
                "Ensure i2c-dev kernel module is loaded (sudo modprobe i2c-dev)."
            )
        self.fd = os.open(self.bus_path, os.O_RDWR)

    def close(self) -> None:
        """Close the I2C device file descriptor."""
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def write_raw(self, offset: int, data: list[int]) -> bool:
        """Write raw 3-byte payload to a specific microcontroller offset register.

        Args:
            offset: Microcontroller offset register index.
            data: List of 3 byte values [b0, b1, b2].

        Returns:
            True if write transaction succeeded, False otherwise.
        """
        if self.fd is None:
            raise RuntimeError("I2C device is not open")

        payload = bytes([offset] + list(data))
        buf = ctypes.create_string_buffer(payload)
        msg = I2CMsg(
            addr=self.addr,
            flags=0,
            len=len(payload),
            buf=ctypes.cast(buf, ctypes.c_char_p),
        )
        msgs = (I2CMsg * 1)(msg)
        ioctl_data = I2CRdwrIoctlData(msgs=msgs, nmsgs=1)
        try:
            fcntl.ioctl(self.fd, I2C_RDWR, ioctl_data)
            return True
        except OSError as e:
            print(f"Error writing offset 0x{offset:02X}: {e}", file=sys.stderr)
            return False

    def read_raw(self, offset: int, length: int = 3) -> list[int] | None:
        """Read bytes from a microcontroller offset register using repeated start.

        Args:
            offset: Target register offset.
            length: Number of bytes to read (default: 3).

        Returns:
            List of integers representing returned byte values, or None on failure.
        """
        if self.fd is None:
            raise RuntimeError("I2C device is not open")

        wbuf = ctypes.create_string_buffer(bytes([offset]))
        rbuf = ctypes.create_string_buffer(length)
        msg_w = I2CMsg(
            addr=self.addr, flags=0, len=1, buf=ctypes.cast(wbuf, ctypes.c_char_p)
        )
        msg_r = I2CMsg(
            addr=self.addr,
            flags=1,
            len=length,
            buf=ctypes.cast(rbuf, ctypes.c_char_p),
        )
        msgs = (I2CMsg * 2)(msg_w, msg_r)
        ioctl_data = I2CRdwrIoctlData(msgs=msgs, nmsgs=2)
        try:
            fcntl.ioctl(self.fd, I2C_RDWR, ioctl_data)
            return list(rbuf.raw[:length])
        except OSError as e:
            print(f"Error reading offset 0x{offset:02X}: {e}", file=sys.stderr)
            return None

    def set_settings(self, mode: int, brightness: int, speed: int) -> bool:
        """Set controller settings register (offset 1)."""
        res = self.write_raw(1, [mode, brightness, speed])
        time.sleep(DELAY)
        return res

    def set_all_color(self, r: int, g: int, b: int) -> bool:
        """Set all 17 LEDs simultaneously using Master Offset 48 (0x30)."""
        res = self.write_raw(48, [r, g, b])
        time.sleep(DELAY)
        return res

    def set_led_color(self, idx: int, r: int, g: int, b: int) -> bool:
        """Set individual LED color (idx: 0..16, corresponding to offsets 26..42)."""
        if not (0 <= idx <= 16):
            raise ValueError("LED index must be between 0 and 16")
        offset = 26 + idx
        res = self.write_raw(offset, [r, g, b])
        time.sleep(DELAY)
        return res

    def turn_off(self) -> bool:
        """Turn off all RGB LEDs."""
        return self.set_settings(0, 0, 0)

    def set_mode(
        self,
        mode: int,
        r: int = 0,
        g: int = 0,
        b: int = 0,
        brightness: int = 255,
        speed: int = 255,
    ) -> bool:
        """Apply a hardware lighting mode (1-9) seamlessly without turning off."""
        if mode in (1, 2, 4, 5, 7, 8):  # Modes requiring color setup
            self.set_all_color(r, g, b)
        return self.set_settings(mode, brightness, speed)

    def set_static(self, r: int, g: int, b: int, brightness: int = 255) -> bool:
        """Set static color instantly across all LEDs (Mode 1)."""
        return self.set_mode(1, r, g, b, brightness=brightness, speed=255)

    def set_breathing(
        self, r: int, g: int, b: int, brightness: int = 255, speed: int = 50
    ) -> bool:
        """Set breathing effect with target color (Mode 2)."""
        return self.set_mode(2, r, g, b, brightness=brightness, speed=speed)

    def set_neon(self, brightness: int = 255, speed: int = 50) -> bool:
        """Set spectrum cycle / neon effect across color range (Mode 3)."""
        return self.set_mode(3, brightness=brightness, speed=speed)

    def set_blink(
        self, r: int, g: int, b: int, brightness: int = 255, speed: int = 50
    ) -> bool:
        """Set single flash pulse effect with target color (Mode 4)."""
        return self.set_mode(4, r, g, b, brightness=brightness, speed=speed)

    def set_double_blink(
        self, r: int, g: int, b: int, brightness: int = 255, speed: int = 50
    ) -> bool:
        """Set double flash pulse effect with target color (Mode 5)."""
        return self.set_mode(5, r, g, b, brightness=brightness, speed=speed)

    def set_meteor(
        self, r: int, g: int, b: int, brightness: int = 255, speed: int = 20
    ) -> bool:
        """Set meteor beam effect across face of GPU (Mode 7)."""
        return self.set_mode(7, r, g, b, brightness=brightness, speed=speed)

    def set_ripple(
        self, r: int, g: int, b: int, brightness: int = 255, speed: int = 30
    ) -> bool:
        """Set ripple wave expansion effect across waterblock (Mode 8)."""
        return self.set_mode(8, r, g, b, brightness=brightness, speed=speed)

    def get_status(
        self,
    ) -> tuple[list[int] | None, list[int] | None]:
        """Read controller mode settings and LED 0 color state."""
        settings = self.read_raw(129)
        color = self.read_raw(130)
        return settings, color


def hex_color(val: str) -> tuple[int, int, int]:
    """Parse hex color string into (R, G, B) tuple."""
    clean_val = val.lstrip("#")
    if len(clean_val) == 6:
        try:
            return (
                int(clean_val[0:2], 16),
                int(clean_val[2:4], 16),
                int(clean_val[4:6], 16),
            )
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(
        f"Invalid hex color '{val}'. Must be in RRGGBB or #RRGGBB format."
    )


def add_color_args(subparser: argparse.ArgumentParser) -> None:
    """Helper to add standard R, G, B, and --hex arguments to a command subparser."""
    subparser.add_argument("r", type=int, nargs="?", help="Red (0-255)")
    subparser.add_argument("g", type=int, nargs="?", help="Green (0-255)")
    subparser.add_argument("b", type=int, nargs="?", help="Blue (0-255)")
    subparser.add_argument("--hex", type=hex_color, help="Hex color (e.g. #00FF00)")
    subparser.add_argument(
        "--brightness",
        type=int,
        default=255,
        help="Brightness (0-255, default: 255)",
    )


def parse_rgb(args: argparse.Namespace) -> tuple[int, int, int]:
    """Extract (R, G, B) from CLI arguments."""
    if getattr(args, "hex", None):
        return args.hex
    r, g, b = (
        getattr(args, "r", None),
        getattr(args, "g", None),
        getattr(args, "b", None),
    )
    if r is not None and g is not None and b is not None:
        return r, g, b
    print("Error: Specify R G B values (0-255) or --hex color", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    """CLI entry point for liquid-devil-rgb."""
    parser = argparse.ArgumentParser(
        description="Linux I2C RGB Control for PowerColor RX 7900 XTX Liquid Devil"
    )
    parser.add_argument(
        "--bus",
        type=str,
        default=None,
        help="I2C bus path (default: auto-detect)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: off
    subparsers.add_parser("off", help="Turn all LEDs off")

    # Command: status
    subparsers.add_parser("status", help="Read current RGB controller status")

    # Command: static
    p_static = subparsers.add_parser("static", help="Set solid static color (Mode 1)")
    add_color_args(p_static)

    # Command: breathing
    p_breath = subparsers.add_parser("breathing", help="Set breathing effect (Mode 2)")
    add_color_args(p_breath)
    p_breath.add_argument(
        "--speed", type=int, default=50, help="Animation speed (0-255)"
    )

    # Command: neon
    p_neon = subparsers.add_parser(
        "neon", help="Set spectrum cycle / neon effect (Mode 3)"
    )
    p_neon.add_argument(
        "--brightness", type=int, default=255, help="Brightness (0-255)"
    )
    p_neon.add_argument("--speed", type=int, default=50, help="Speed (0-255)")

    # Command: blink
    p_blink = subparsers.add_parser(
        "blink", help="Set single flash pulse effect (Mode 4)"
    )
    add_color_args(p_blink)
    p_blink.add_argument(
        "--speed", type=int, default=50, help="Animation speed (0-255)"
    )

    # Command: double-blink
    p_dblink = subparsers.add_parser(
        "double-blink", help="Set double flash pulse effect (Mode 5)"
    )
    add_color_args(p_dblink)
    p_dblink.add_argument(
        "--speed", type=int, default=50, help="Animation speed (0-255)"
    )

    # Command: meteor
    p_meteor = subparsers.add_parser(
        "meteor", help="Set meteor beam effect across face (Mode 7)"
    )
    add_color_args(p_meteor)
    p_meteor.add_argument(
        "--speed", type=int, default=20, help="Animation speed (0-255)"
    )

    # Command: ripple
    p_ripple = subparsers.add_parser(
        "ripple", help="Set ripple wave expansion effect (Mode 8)"
    )
    add_color_args(p_ripple)
    p_ripple.add_argument(
        "--speed", type=int, default=30, help="Animation speed (0-255)"
    )

    # Command: led
    p_led = subparsers.add_parser("led", help="Set individual LED color (0 to 16)")
    p_led.add_argument("idx", type=int, help="LED index (0 to 16)")
    p_led.add_argument("r", type=int, help="Red (0-255)")
    p_led.add_argument("g", type=int, help="Green (0-255)")
    p_led.add_argument("b", type=int, help="Blue (0-255)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    with LiquidDevilRGB(bus_path=args.bus) as dev:
        if args.command == "off":
            print("[*] Turning LEDs off...")
            dev.turn_off()

        elif args.command == "status":
            print(f"[*] Bus: {dev.bus_path}")
            settings, color = dev.get_status()
            if settings:
                modes = {
                    0: "off",
                    1: "static",
                    2: "breathing",
                    3: "neon",
                    4: "blink",
                    5: "double_blink",
                    7: "meteor",
                    8: "ripple",
                }
                mode_str = modes.get(settings[0], f"unknown({settings[0]})")
                print(
                    f"  Settings: Mode={mode_str}, Brightness={settings[1]}, Speed={settings[2]}"
                )
            if color:
                print(f"  LED 0 Color: R={color[0]}, G={color[1]}, B={color[2]}")

        elif args.command == "static":
            r, g, b = parse_rgb(args)
            print(
                f"[*] Setting static color: R={r} G={g} B={b} (Brightness={args.brightness})"
            )
            dev.set_static(r, g, b, brightness=args.brightness)

        elif args.command == "breathing":
            r, g, b = parse_rgb(args)
            print(
                f"[*] Setting breathing color: R={r} G={g} B={b} (Speed={args.speed})"
            )
            dev.set_breathing(r, g, b, brightness=args.brightness, speed=args.speed)

        elif args.command == "neon":
            print(f"[*] Setting spectrum cycle / neon effect (Speed={args.speed})")
            dev.set_neon(brightness=args.brightness, speed=args.speed)

        elif args.command == "blink":
            r, g, b = parse_rgb(args)
            print(f"[*] Setting blink effect: R={r} G={g} B={b} (Speed={args.speed})")
            dev.set_blink(r, g, b, brightness=args.brightness, speed=args.speed)

        elif args.command == "double-blink":
            r, g, b = parse_rgb(args)
            print(
                f"[*] Setting double-blink effect: R={r} G={g} B={b} (Speed={args.speed})"
            )
            dev.set_double_blink(r, g, b, brightness=args.brightness, speed=args.speed)

        elif args.command == "meteor":
            r, g, b = parse_rgb(args)
            print(f"[*] Setting meteor effect: R={r} G={g} B={b} (Speed={args.speed})")
            dev.set_meteor(r, g, b, brightness=args.brightness, speed=args.speed)

        elif args.command == "ripple":
            r, g, b = parse_rgb(args)
            print(f"[*] Setting ripple effect: R={r} G={g} B={b} (Speed={args.speed})")
            dev.set_ripple(r, g, b, brightness=args.brightness, speed=args.speed)

        elif args.command == "led":
            print(f"[*] Setting LED {args.idx} color: R={args.r} G={args.g} B={args.b}")
            dev.set_led_color(args.idx, args.r, args.g, args.b)
            dev.set_settings(1, 255, 255)


if __name__ == "__main__":
    main()
