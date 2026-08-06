#!/usr/bin/env python3
"""
Linux I2C RGB Control for PowerColor Radeon RX 7900 XTX Liquid Devil

Reverse-engineered hardware protocol implementation for the V2 I2C RGB controller (0x22).
"""
import os
import sys
import time
import glob
import fcntl
import ctypes
import argparse

# I2C constants
I2C_RDWR = 0x0707
DEFAULT_ADDR = 0x22
DELAY = 0.05  # 50ms pause between writes


class i2c_msg(ctypes.Structure):
    _fields_ = [
        ('addr', ctypes.c_uint16),
        ('flags', ctypes.c_uint16),
        ('len', ctypes.c_uint16),
        ('buf', ctypes.c_char_p),
    ]


class i2c_rdwr_ioctl_data(ctypes.Structure):
    _fields_ = [
        ('msgs', ctypes.POINTER(i2c_msg)),
        ('nmsgs', ctypes.c_uint32),
    ]


def find_oem_i2c_bus():
    """Auto-detect the AMDGPU DM i2c OEM bus path from /sys/class/i2c-adapter."""
    for name_file in glob.glob("/sys/class/i2c-adapter/i2c-*/name"):
        try:
            with open(name_file, 'r') as f:
                content = f.read().strip()
                if "AMDGPU DM i2c OEM bus" in content:
                    dev_name = os.path.basename(os.path.dirname(name_file))
                    return f"/dev/{dev_name}"
        except OSError:
            continue
    # Default fallback
    return "/dev/i2c-7"


class LiquidDevilRGB:
    def __init__(self, bus_path=None, addr=DEFAULT_ADDR):
        self.bus_path = bus_path or find_oem_i2c_bus()
        self.addr = addr
        self.fd = None

    def open(self):
        if not os.path.exists(self.bus_path):
            raise FileNotFoundError(f"I2C bus path '{self.bus_path}' not found. Make sure i2c-dev module is loaded (sudo modprobe i2c-dev).")
        self.fd = os.open(self.bus_path, os.O_RDWR)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def write_raw(self, offset, data):
        payload = bytes([offset] + list(data))
        buf = ctypes.create_string_buffer(payload)
        msg = i2c_msg(addr=self.addr, flags=0, len=len(payload), buf=ctypes.cast(buf, ctypes.c_char_p))
        msgs = (i2c_msg * 1)(msg)
        ioctl_data = i2c_rdwr_ioctl_data(msgs=msgs, nmsgs=1)
        try:
            fcntl.ioctl(self.fd, I2C_RDWR, ioctl_data)
            return True
        except OSError as e:
            print(f"Error writing offset 0x{offset:02X}: {e}", file=sys.stderr)
            return False

    def read_raw(self, offset, length=3):
        wbuf = ctypes.create_string_buffer(bytes([offset]))
        rbuf = ctypes.create_string_buffer(length)
        msg_w = i2c_msg(addr=self.addr, flags=0, len=1, buf=ctypes.cast(wbuf, ctypes.c_char_p))
        msg_r = i2c_msg(addr=self.addr, flags=1, len=length, buf=ctypes.cast(rbuf, ctypes.c_char_p))
        msgs = (i2c_msg * 2)(msg_w, msg_r)
        ioctl_data = i2c_rdwr_ioctl_data(msgs=msgs, nmsgs=2)
        try:
            fcntl.ioctl(self.fd, I2C_RDWR, ioctl_data)
            return list(rbuf.raw[:length])
        except OSError as e:
            print(f"Error reading offset 0x{offset:02X}: {e}", file=sys.stderr)
            return None

    def set_settings(self, mode, brightness, speed):
        res = self.write_raw(1, [mode, brightness, speed])
        time.sleep(DELAY)
        return res

    def set_all_color(self, r, g, b):
        """Set all 17 LEDs simultaneously using Master Offset 48 (0x30)."""
        res = self.write_raw(48, [r, g, b])
        time.sleep(DELAY)
        return res

    def set_led_color(self, idx, r, g, b):
        """Set individual LED color (idx: 0..16, corresponding to offsets 26..42)."""
        if not (0 <= idx <= 16):
            raise ValueError("LED index must be between 0 and 16")
        offset = 26 + idx
        res = self.write_raw(offset, [r, g, b])
        time.sleep(DELAY)
        return res

    def turn_off(self):
        """Turn off all RGB LEDs."""
        return self.set_settings(0, 0, 0)

    def set_static(self, r, g, b, brightness=255):
        """Set static color across all LEDs."""
        self.turn_off()
        time.sleep(0.2)
        self.set_all_color(r, g, b)
        return self.set_settings(1, brightness, 255)

    def set_breathing(self, r, g, b, brightness=255, speed=50):
        """Set breathing mode with target color."""
        self.turn_off()
        time.sleep(0.2)
        self.set_all_color(r, g, b)
        return self.set_settings(2, brightness, speed)

    def get_status(self):
        settings = self.read_raw(129)
        color = self.read_raw(130)
        return settings, color


def hex_color(val):
    val = val.lstrip('#')
    if len(val) == 6:
        return tuple(int(val[i:i+2], 16) for i in (0, 2, 4))
    raise argparse.ArgumentTypeError("Hex color must be in format RRGGBB or #RRGGBB")


def main():
    parser = argparse.ArgumentParser(
        description="Linux I2C RGB Control for PowerColor RX 7900 XTX Liquid Devil"
    )
    parser.add_argument("--bus", type=str, default=None, help="I2C bus path (default: auto-detect)")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: off
    subparsers.add_parser("off", help="Turn all LEDs off")

    # Command: static
    p_static = subparsers.add_parser("static", help="Set static color")
    p_static.add_argument("r", type=int, nargs="?", help="Red (0-255)")
    p_static.add_argument("g", type=int, nargs="?", help="Green (0-255)")
    p_static.add_argument("b", type=int, nargs="?", help="Blue (0-255)")
    p_static.add_argument("--hex", type=hex_color, help="Hex color (e.g. #00FF00)")
    p_static.add_argument("--brightness", type=int, default=255, help="Brightness (0-255, default: 255)")

    # Command: breathing
    p_breath = subparsers.add_parser("breathing", help="Set breathing mode color")
    p_breath.add_argument("r", type=int, nargs="?", help="Red (0-255)")
    p_breath.add_argument("g", type=int, nargs="?", help="Green (0-255)")
    p_breath.add_argument("b", type=int, nargs="?", help="Blue (0-255)")
    p_breath.add_argument("--hex", type=hex_color, help="Hex color (e.g. #FF00FF)")
    p_breath.add_argument("--brightness", type=int, default=255, help="Brightness (0-255)")
    p_breath.add_argument("--speed", type=int, default=50, help="Animation speed (0-255)")

    # Command: led
    p_led = subparsers.add_parser("led", help="Set individual LED color")
    p_led.add_argument("idx", type=int, help="LED index (0 to 16)")
    p_led.add_argument("r", type=int, help="Red (0-255)")
    p_led.add_argument("g", type=int, help="Green (0-255)")
    p_led.add_argument("b", type=int, help="Blue (0-255)")

    # Command: status
    subparsers.add_parser("status", help="Read current RGB controller status")

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
                modes = {0:'off', 1:'static', 2:'breathing', 3:'neon', 4:'blink', 
                         5:'double_blink', 6:'color_shift', 7:'meteor', 8:'ripple', 9:'seven_colors'}
                mode_str = modes.get(settings[0], f'unknown({settings[0]})')
                print(f"  Settings: Mode={mode_str}, Brightness={settings[1]}, Speed={settings[2]}")
            if color:
                print(f"  LED 0 Color: R={color[0]}, G={color[1]}, B={color[2]}")

        elif args.command in ("static", "breathing"):
            if args.hex:
                r, g, b = args.hex
            elif args.r is not None and args.g is not None and args.b is not None:
                r, g, b = args.r, args.g, args.b
            else:
                print("Error: Specify R G B or --hex color", file=sys.stderr)
                sys.exit(1)

            if args.command == "static":
                print(f"[*] Setting static color: R={r} G={g} B={b} (Brightness={args.brightness})")
                dev.set_static(r, g, b, brightness=args.brightness)
            else:
                print(f"[*] Setting breathing color: R={r} G={g} B={b} (Speed={args.speed})")
                dev.set_breathing(r, g, b, brightness=args.brightness, speed=args.speed)

        elif args.command == "led":
            print(f"[*] Setting LED {args.idx} color: R={args.r} G={args.g} B={args.b}")
            dev.set_led_color(args.idx, args.r, args.g, args.b)
            dev.set_settings(1, 255, 255)


if __name__ == '__main__':
    main()
