#!/usr/bin/env python3
"""Linux I2C RGB Control for PowerColor Radeon RX 7900 XTX Liquid Devil.

Reverse-engineered hardware protocol implementation for the V2 I2C RGB controller (0x22).
Supports smbus2 with a seamless stdlib ctypes fallback when smbus2 is not installed.
Includes real-time per-LED OpenRGB Effects Plugin synchronization.
"""

from __future__ import annotations

import glob
import os
import socket
import struct
import sys
import threading
import time
from typing import TYPE_CHECKING, Any, Self

import click

# Attempt smbus2 import with transparent stdlib ctypes fallback
try:
    from smbus2 import SMBus, i2c_msg

    HAS_SMBUS2 = True
except ImportError:
    import ctypes
    import fcntl

    I2C_RDWR = 0x0707
    HAS_SMBUS2 = False

    class I2CMsg(ctypes.Structure):
        _fields_ = [
            ("addr", ctypes.c_uint16),
            ("flags", ctypes.c_uint16),
            ("len", ctypes.c_uint16),
            ("buf", ctypes.c_char_p),
        ]

    class I2CRdwrIoctlData(ctypes.Structure):
        _fields_ = [
            ("msgs", ctypes.POINTER(I2CMsg)),
            ("nmsgs", ctypes.c_uint32),
        ]


if TYPE_CHECKING:
    from types import TracebackType

# I2C constants
DEFAULT_ADDR: int = 0x22
DELAY: float = 0.03  # 30ms pause for real-time ~33 FPS updates

# OpenRGB SDK Packet Types
NET_PACKET_TYPE_REQUEST_CONTROLLER_COUNT: int = 0
NET_PACKET_TYPE_REQUEST_CONTROLLER_DATA: int = 1
NET_PACKET_TYPE_SET_CLIENT_NAME: int = 50
NET_PACKET_TYPE_UPDATE_LEDS: int = 100
NET_PACKET_TYPE_UPDATE_ZONE_LEDS: int = 101
NET_PACKET_TYPE_UPDATE_SINGLE_LED: int = 102
NET_PACKET_TYPE_SET_CUSTOM_MODE: int = 110


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
        self.bus: SMBus | None = None
        self.fd: int | None = None

    def open(self) -> None:
        """Open the I2C device via SMBus or raw file descriptor."""
        if not os.path.exists(self.bus_path):
            raise FileNotFoundError(
                f"I2C bus path '{self.bus_path}' not found. "
                "Ensure i2c-dev kernel module is loaded (sudo modprobe i2c-dev)."
            )
        if HAS_SMBUS2:
            self.bus = SMBus(self.bus_path)
        else:
            self.fd = os.open(self.bus_path, os.O_RDWR)

    def close(self) -> None:
        """Close the I2C device."""
        if self.bus is not None:
            self.bus.close()
            self.bus = None
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
        if HAS_SMBUS2 and self.bus is not None:
            payload = [offset] + list(data)
            msg = i2c_msg.write(self.addr, payload)
            try:
                self.bus.i2c_rdwr(msg)
                return True
            except OSError as e:
                print(f"Error writing offset 0x{offset:02X}: {e}", file=sys.stderr)
                return False
        elif self.fd is not None:
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
        raise RuntimeError("I2C device is not open")

    def read_raw(self, offset: int, length: int = 3) -> list[int] | None:
        """Read bytes from a microcontroller offset register using repeated start.

        Args:
            offset: Target register offset.
            length: Number of bytes to read (default: 3).

        Returns:
            List of integers representing returned byte values, or None on failure.
        """
        if HAS_SMBUS2 and self.bus is not None:
            msg_w = i2c_msg.write(self.addr, [offset])
            msg_r = i2c_msg.read(self.addr, length)
            try:
                self.bus.i2c_rdwr(msg_w, msg_r)
                return list(msg_r)
            except OSError as e:
                print(f"Error reading offset 0x{offset:02X}: {e}", file=sys.stderr)
                return None
        elif self.fd is not None:
            wbuf = ctypes.create_string_buffer(bytes([offset]))
            rbuf = ctypes.create_string_buffer(length)
            msg_w = I2CMsg(
                addr=self.addr,
                flags=0,
                len=1,
                buf=ctypes.cast(wbuf, ctypes.c_char_p),
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
        raise RuntimeError("I2C device is not open")

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
        if mode in (1, 2, 4, 5, 7, 8):
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


def parse_color_args(
    r: int | None, g: int | None, b: int | None, hex_val: str | None
) -> tuple[int, int, int]:
    """Parse color from either positional R G B values or a hex string."""
    if hex_val:
        clean_val = hex_val.lstrip("#")
        if len(clean_val) == 6:
            try:
                return (
                    int(clean_val[0:2], 16),
                    int(clean_val[2:4], 16),
                    int(clean_val[4:6], 16),
                )
            except ValueError:
                pass
        raise click.BadParameter(
            f"Invalid hex color '{hex_val}'. Must be RRGGBB or #RRGGBB."
        )
    if r is not None and g is not None and b is not None:
        return r, g, b
    raise click.UsageError("Specify R G B values (0-255) or --hex color.")


# --- OpenRGB SDK Client Sync Module ---


def run_openrgb_sync_client(
    host: str = "127.0.0.1",
    port: int = 6742,
    device_idx: int = 0,
    fps: int = 30,
    bus_path: str | None = None,
) -> None:
    """Connect as a client to an OpenRGB SDK Server (port 6742) and mirror active colors to GPU."""
    interval = 1.0 / max(1, min(60, fps))
    print("PowerColor RX 7900 XTX Liquid Devil - OpenRGB Sync Client")
    print(f"Connecting to OpenRGB Server at {host}:{port}")
    print(f"Target Device Index: {device_idx}")
    print(f"Sync Rate: ~{fps} FPS ({interval * 1000:.1f}ms interval)")
    print("Press Ctrl+C to stop sync daemon.\n")

    with LiquidDevilRGB(bus_path=bus_path) as dev:
        dev.set_static(0, 0, 255)

        while True:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5.0)
                s.connect((host, port))

                name_bytes = b"Liquid Devil GPU Sync\x00"
                name_payload = struct.pack("<H", len(name_bytes)) + name_bytes
                hdr = struct.pack(
                    "<4sIII",
                    b"ORGB",
                    0,
                    NET_PACKET_TYPE_SET_CLIENT_NAME,
                    len(name_payload),
                )
                s.sendall(hdr + name_payload)

                print(f"Connected to OpenRGB Server at {host}:{port}")

                while True:
                    req_hdr = struct.pack(
                        "<4sIII",
                        b"ORGB",
                        device_idx,
                        NET_PACKET_TYPE_REQUEST_CONTROLLER_DATA,
                        4,
                    )
                    s.sendall(req_hdr + struct.pack("<I", 3))

                    resp_hdr = s.recv(16)
                    if not resp_hdr or len(resp_hdr) < 16:
                        break

                    magic, _dev_id, pkt_t, pkt_len = struct.unpack("<4sIII", resp_hdr)
                    if magic != b"ORGB" or pkt_len == 0:
                        break

                    payload = b""
                    while len(payload) < pkt_len:
                        chunk = s.recv(pkt_len - len(payload))
                        if not chunk:
                            break
                        payload += chunk

                    # Parse incoming packet (either REQUEST_CONTROLLER_DATA or UPDATE_LEDS / UPDATE_ZONE_LEDS)
                    colors_data = b""
                    stride = 3

                    if (
                        pkt_t == NET_PACKET_TYPE_REQUEST_CONTROLLER_DATA
                        and len(payload) >= 4
                    ):
                        colors_data = payload[-68:]  # Last 68 bytes
                        stride = 4

                    elif pkt_t == NET_PACKET_TYPE_UPDATE_LEDS and len(payload) >= 6:
                        colors_data = payload[6:]
                        stride = 3

                    elif (
                        pkt_t == NET_PACKET_TYPE_UPDATE_ZONE_LEDS and len(payload) >= 10
                    ):
                        colors_data = payload[10:]
                        stride = 3

                    if colors_data:
                        r_total, g_total, b_total = 0, 0, 0
                        valid_colors = 0
                        num_colors = len(colors_data) // stride

                        for i in range(min(num_colors, 17)):
                            off = i * stride
                            if off + 3 <= len(colors_data):
                                r, g, b = colors_data[off : off + 3]
                                r_total += r
                                g_total += g
                                b_total += b
                                valid_colors += 1

                        if valid_colors > 0:
                            dev.set_all_color(
                                r_total // valid_colors,
                                g_total // valid_colors,
                                b_total // valid_colors,
                            )

                    time.sleep(interval)

            except (
                TimeoutError,
                ConnectionResetError,
                BrokenPipeError,
                OSError,
            ) as e:
                print(
                    f"Disconnected from OpenRGB server ({e}). Retrying in 3 seconds...",
                    file=sys.stderr,
                )
                time.sleep(3.0)
            except KeyboardInterrupt:
                print("\nStopping OpenRGB Sync daemon.")
                break


# --- OpenRGB SDK Server Helpers ---


class PacketWriter:
    """Fluent binary packet writer helper for OpenRGB SDK serialization."""

    def __init__(self) -> None:
        self.buf = bytearray()

    def pack(self, fmt: str, *args: Any) -> PacketWriter:
        self.buf += struct.pack(fmt, *args)
        return self

    def write_string(self, s: str) -> PacketWriter:
        encoded = s.encode("utf-8") + b"\x00"
        self.pack("<H", len(encoded))
        self.buf += encoded
        return self

    def to_bytes(self) -> bytes:
        return bytes(self.buf)


def build_controller_data_packet(protocol_version: int = 3) -> bytes:
    """Build serialized OpenRGB controller data payload for the 7900 XTX Liquid Devil."""
    p = PacketWriter()
    p.pack("<I", 3)  # DEVICE_TYPE_GPU = 3
    p.write_string("PowerColor RX 7900 XTX Liquid Devil")
    p.write_string("PowerColor")
    p.write_string("Liquid Devil 7900 XTX I2C RGB Controller")
    p.write_string("v2.0")
    p.write_string("AMDGPU DM i2c OEM bus (0x22)")
    p.write_string("0x22")

    # Modes Count = 1, Active Mode = 0
    p.pack("<Hi", 1, 0)
    p.write_string("Direct")
    p.pack("<iIIIIIIII", 0, 1, 0, 0, 0, 0, 0, 0, 0)

    # Mode Colors (17 LEDs)
    color_bytes = b"\x00\x00\xff\x00" if protocol_version >= 4 else b"\x00\x00\xff"
    p.pack("<H", 17)
    p.buf += color_bytes * 17

    # Zone (1 zone: Liquid Devil Block)
    p.write_string("Liquid Devil Block")
    p.pack("<iIIIH", 0, 17, 17, 17, 0)

    # LEDs Array (17 LEDs)
    p.pack("<H", 17)
    for i in range(17):
        p.write_string(f"LED {i}")
        p.pack("<I", 0)

    # Colors Array (17 LEDs)
    p.pack("<H", 17)
    p.buf += color_bytes * 17

    return p.to_bytes()


def handle_sdk_client(
    client_sock: socket.socket, client_addr: tuple[str, int], dev: LiquidDevilRGB
) -> None:
    """Handle an incoming OpenRGB SDK client connection."""
    print(f"OpenRGB SDK Client connected from {client_addr[0]}:{client_addr[1]}")
    client_sock.settimeout(5.0)
    protocol_version = 3

    try:
        dev.set_static(0, 0, 255)

        while True:
            header = client_sock.recv(16)
            if not header or len(header) < 16:
                break

            magic, _dev_idx, pkt_type, pkt_len = struct.unpack("<4sIII", header)
            if magic != b"ORGB":
                print(f"Invalid SDK magic bytes: {magic!r}", file=sys.stderr)
                break

            payload = b""
            if pkt_len > 0:
                while len(payload) < pkt_len:
                    chunk = client_sock.recv(pkt_len - len(payload))
                    if not chunk:
                        break
                    payload += chunk

            if pkt_type == NET_PACKET_TYPE_REQUEST_CONTROLLER_COUNT:
                resp_header = struct.pack(
                    "<4sIII",
                    b"ORGB",
                    0,
                    NET_PACKET_TYPE_REQUEST_CONTROLLER_COUNT,
                    4,
                )
                resp_payload = struct.pack("<I", 1)
                client_sock.sendall(resp_header + resp_payload)

            elif pkt_type == NET_PACKET_TYPE_REQUEST_CONTROLLER_DATA:
                if len(payload) >= 4:
                    protocol_version = struct.unpack("<I", payload[:4])[0]
                data = build_controller_data_packet(protocol_version)
                resp_header = struct.pack(
                    "<4sIII",
                    b"ORGB",
                    0,
                    NET_PACKET_TYPE_REQUEST_CONTROLLER_DATA,
                    len(data),
                )
                client_sock.sendall(resp_header + data)

            elif pkt_type == NET_PACKET_TYPE_SET_CLIENT_NAME:
                if len(payload) >= 2:
                    try:
                        name_len = struct.unpack("<H", payload[:2])[0]
                        client_name = (
                            payload[2 : 2 + name_len]
                            .decode("utf-8", errors="ignore")
                            .rstrip("\x00")
                        )
                        print(f"OpenRGB SDK Client Name set to: '{client_name}'")
                    except (struct.error, UnicodeDecodeError):
                        pass

            elif pkt_type == NET_PACKET_TYPE_UPDATE_LEDS:
                # Payload: [buffer_size (4B)][num_colors (2B)][color_structs...]
                if len(payload) >= 6:
                    num_colors = struct.unpack("<H", payload[4:6])[0]
                    colors_data = payload[6:]
                    stride = 4 if protocol_version >= 4 else 3

                    # Stream individual LED colors or calculate master color
                    if num_colors >= 17:
                        for i in range(17):
                            off = i * stride
                            if off + 3 <= len(colors_data):
                                r, g, b = colors_data[off : off + 3]
                                dev.write_raw(26 + i, [r, g, b])
                        dev.set_settings(1, 255, 255)
                    else:
                        r_t, g_t, b_t, valid = 0, 0, 0, 0
                        for i in range(num_colors):
                            off = i * stride
                            if off + 3 <= len(colors_data):
                                r, g, b = colors_data[off : off + 3]
                                r_t += r
                                g_t += g
                                b_t += b
                                valid += 1
                        if valid > 0:
                            dev.set_all_color(r_t // valid, g_t // valid, b_t // valid)

            elif pkt_type == NET_PACKET_TYPE_UPDATE_ZONE_LEDS:
                # Payload: [buffer_size (4B)][zone_index (4B)][num_colors (2B)][color_structs...]
                if len(payload) >= 10:
                    num_colors = struct.unpack("<H", payload[8:10])[0]
                    colors_data = payload[10:]
                    stride = 4 if protocol_version >= 4 else 3

                    if num_colors >= 17:
                        for i in range(17):
                            off = i * stride
                            if off + 3 <= len(colors_data):
                                r, g, b = colors_data[off : off + 3]
                                dev.write_raw(26 + i, [r, g, b])
                        dev.set_settings(1, 255, 255)
                    else:
                        r_t, g_t, b_t, valid = 0, 0, 0, 0
                        for i in range(num_colors):
                            off = i * stride
                            if off + 3 <= len(colors_data):
                                r, g, b = colors_data[off : off + 3]
                                r_t += r
                                g_t += g
                                b_t += b
                                valid += 1
                        if valid > 0:
                            dev.set_all_color(r_t // valid, g_t // valid, b_t // valid)

            elif pkt_type == NET_PACKET_TYPE_UPDATE_SINGLE_LED:
                # Payload: [buffer_size (4B)][led_index (4B)][r (1B)][g (1B)][b (1B)]
                if len(payload) >= 11:
                    led_idx = struct.unpack("<I", payload[4:8])[0]
                    r, g, b = payload[8:11]
                    if 0 <= led_idx <= 16:
                        dev.set_led_color(led_idx, r, g, b)

    except (TimeoutError, ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        client_sock.close()
        print(f"OpenRGB SDK Client disconnected: {client_addr[0]}:{client_addr[1]}")


def run_sdk_server(
    host: str = "0.0.0.0", port: int = 6742, bus_path: str | None = None
) -> None:
    """Run OpenRGB SDK Server daemon listening on specified host/port."""
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_sock.bind((host, port))
        server_sock.listen(5)
        print("PowerColor RX 7900 XTX Liquid Devil - OpenRGB SDK Server")
        print(f"Listening on {host}:{port} (OpenRGB SDK Protocol)")
        print(f"I2C Bus: {bus_path or find_oem_i2c_bus()}")
        print("Press Ctrl+C to stop server.\n")

        with LiquidDevilRGB(bus_path=bus_path) as dev:
            dev.set_static(0, 0, 255)
            while True:
                client_sock, client_addr = server_sock.accept()
                t = threading.Thread(
                    target=handle_sdk_client,
                    args=(client_sock, client_addr, dev),
                    daemon=True,
                )
                t.start()

    except KeyboardInterrupt:
        print("\nStopping OpenRGB SDK Server.")
    finally:
        server_sock.close()


# --- Click CLI Group & Commands ---


@click.group()
@click.option(
    "--bus", type=str, default=None, help="I2C bus path (default: auto-detect)"
)
@click.pass_context
def cli(ctx: click.Context, bus: str | None) -> None:
    """Linux I2C RGB Control for PowerColor RX 7900 XTX Liquid Devil."""
    ctx.ensure_object(dict)
    ctx.obj["bus"] = bus


@cli.command("openrgb-sync")
@click.option(
    "--host",
    type=str,
    default="127.0.0.1",
    help="OpenRGB server IP (default: 127.0.0.1)",
)
@click.option(
    "--port",
    type=int,
    default=6742,
    help="OpenRGB server port (default: 6742)",
)
@click.option(
    "--device-idx",
    type=int,
    default=0,
    help="Target OpenRGB device index to mirror (default: 0)",
)
@click.option(
    "--fps", type=int, default=30, help="Sync update frame rate (default: 30)"
)
@click.pass_context
def openrgb_sync_cmd(
    ctx: click.Context, host: str, port: int, device_idx: int, fps: int
) -> None:
    """Sync GPU colors in real-time by connecting as a client to an OpenRGB Server."""
    run_openrgb_sync_client(
        host=host,
        port=port,
        device_idx=device_idx,
        fps=fps,
        bus_path=ctx.obj["bus"],
    )


@cli.command("sdk-server")
@click.option(
    "--host",
    type=str,
    default="0.0.0.0",
    help="Host IP to bind (default: 0.0.0.0)",
)
@click.option(
    "--port",
    type=int,
    default=6742,
    help="Port to listen (default: 6742)",
)
@click.pass_context
def sdk_server_cmd(ctx: click.Context, host: str, port: int) -> None:
    """Run OpenRGB SDK Server daemon (port 6742)."""
    run_sdk_server(host=host, port=port, bus_path=ctx.obj["bus"])


@cli.command("off")
@click.pass_context
def off_cmd(ctx: click.Context) -> None:
    """Turn all LEDs off."""
    with LiquidDevilRGB(bus_path=ctx.obj["bus"]) as dev:
        print("Turning LEDs off...")
        dev.turn_off()


@cli.command("status")
@click.pass_context
def status_cmd(ctx: click.Context) -> None:
    """Read current RGB controller status."""
    with LiquidDevilRGB(bus_path=ctx.obj["bus"]) as dev:
        print(f"Bus: {dev.bus_path}")
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


@cli.command("static")
@click.argument("r", type=int, required=False)
@click.argument("g", type=int, required=False)
@click.argument("b", type=int, required=False)
@click.option(
    "--hex",
    "hex_val",
    type=str,
    default=None,
    help="Hex color (e.g. #00FF00)",
)
@click.option("--brightness", type=int, default=255, help="Brightness (0-255)")
@click.pass_context
def static_cmd(
    ctx: click.Context,
    r: int | None,
    g: int | None,
    b: int | None,
    hex_val: str | None,
    brightness: int,
) -> None:
    """Set solid static color (Mode 1)."""
    red, green, blue = parse_color_args(r, g, b, hex_val)
    with LiquidDevilRGB(bus_path=ctx.obj["bus"]) as dev:
        print(
            f"Setting static color: R={red} G={green} B={blue} (Brightness={brightness})"
        )
        dev.set_static(red, green, blue, brightness=brightness)


@cli.command("breathing")
@click.argument("r", type=int, required=False)
@click.argument("g", type=int, required=False)
@click.argument("b", type=int, required=False)
@click.option(
    "--hex",
    "hex_val",
    type=str,
    default=None,
    help="Hex color (e.g. #00FF00)",
)
@click.option("--brightness", type=int, default=255, help="Brightness (0-255)")
@click.option("--speed", type=int, default=50, help="Animation speed (0-255)")
@click.pass_context
def breathing_cmd(
    ctx: click.Context,
    r: int | None,
    g: int | None,
    b: int | None,
    hex_val: str | None,
    brightness: int,
    speed: int,
) -> None:
    """Set breathing effect (Mode 2)."""
    red, green, blue = parse_color_args(r, g, b, hex_val)
    with LiquidDevilRGB(bus_path=ctx.obj["bus"]) as dev:
        print(f"Setting breathing color: R={red} G={green} B={blue} (Speed={speed})")
        dev.set_breathing(red, green, blue, brightness=brightness, speed=speed)


@cli.command("neon")
@click.option("--brightness", type=int, default=255, help="Brightness (0-255)")
@click.option("--speed", type=int, default=50, help="Speed (0-255)")
@click.pass_context
def neon_cmd(ctx: click.Context, brightness: int, speed: int) -> None:
    """Set spectrum cycle / neon effect (Mode 3)."""
    with LiquidDevilRGB(bus_path=ctx.obj["bus"]) as dev:
        print(f"Setting spectrum cycle / neon effect (Speed={speed})")
        dev.set_neon(brightness=brightness, speed=speed)


@cli.command("blink")
@click.argument("r", type=int, required=False)
@click.argument("g", type=int, required=False)
@click.argument("b", type=int, required=False)
@click.option(
    "--hex",
    "hex_val",
    type=str,
    default=None,
    help="Hex color (e.g. #00FF00)",
)
@click.option("--brightness", type=int, default=255, help="Brightness (0-255)")
@click.option("--speed", type=int, default=50, help="Animation speed (0-255)")
@click.pass_context
def blink_cmd(
    ctx: click.Context,
    r: int | None,
    g: int | None,
    b: int | None,
    hex_val: str | None,
    brightness: int,
    speed: int,
) -> None:
    """Set single flash pulse effect (Mode 4)."""
    red, green, blue = parse_color_args(r, g, b, hex_val)
    with LiquidDevilRGB(bus_path=ctx.obj["bus"]) as dev:
        print(f"Setting blink effect: R={red} G={green} B={blue} (Speed={speed})")
        dev.set_blink(red, green, blue, brightness=brightness, speed=speed)


@cli.command("double-blink")
@click.argument("r", type=int, required=False)
@click.argument("g", type=int, required=False)
@click.argument("b", type=int, required=False)
@click.option(
    "--hex",
    "hex_val",
    type=str,
    default=None,
    help="Hex color (e.g. #00FF00)",
)
@click.option("--brightness", type=int, default=255, help="Brightness (0-255)")
@click.option("--speed", type=int, default=50, help="Animation speed (0-255)")
@click.pass_context
def double_blink_cmd(
    ctx: click.Context,
    r: int | None,
    g: int | None,
    b: int | None,
    hex_val: str | None,
    brightness: int,
    speed: int,
) -> None:
    """Set double flash pulse effect (Mode 5)."""
    red, green, blue = parse_color_args(r, g, b, hex_val)
    with LiquidDevilRGB(bus_path=ctx.obj["bus"]) as dev:
        print(
            f"Setting double-blink effect: R={red} G={green} B={blue} (Speed={speed})"
        )
        dev.set_double_blink(red, green, blue, brightness=brightness, speed=speed)


@cli.command("meteor")
@click.argument("r", type=int, required=False)
@click.argument("g", type=int, required=False)
@click.argument("b", type=int, required=False)
@click.option(
    "--hex",
    "hex_val",
    type=str,
    default=None,
    help="Hex color (e.g. #00FF00)",
)
@click.option("--brightness", type=int, default=255, help="Brightness (0-255)")
@click.option("--speed", type=int, default=20, help="Animation speed (0-255)")
@click.pass_context
def meteor_cmd(
    ctx: click.Context,
    r: int | None,
    g: int | None,
    b: int | None,
    hex_val: str | None,
    brightness: int,
    speed: int,
) -> None:
    """Set meteor beam effect across face (Mode 7)."""
    red, green, blue = parse_color_args(r, g, b, hex_val)
    with LiquidDevilRGB(bus_path=ctx.obj["bus"]) as dev:
        print(f"Setting meteor effect: R={red} G={green} B={blue} (Speed={speed})")
        dev.set_meteor(red, green, blue, brightness=brightness, speed=speed)


@cli.command("ripple")
@click.argument("r", type=int, required=False)
@click.argument("g", type=int, required=False)
@click.argument("b", type=int, required=False)
@click.option(
    "--hex",
    "hex_val",
    type=str,
    default=None,
    help="Hex color (e.g. #00FF00)",
)
@click.option("--brightness", type=int, default=255, help="Brightness (0-255)")
@click.option("--speed", type=int, default=30, help="Animation speed (0-255)")
@click.pass_context
def ripple_cmd(
    ctx: click.Context,
    r: int | None,
    g: int | None,
    b: int | None,
    hex_val: str | None,
    brightness: int,
    speed: int,
) -> None:
    """Set ripple wave expansion effect (Mode 8)."""
    red, green, blue = parse_color_args(r, g, b, hex_val)
    with LiquidDevilRGB(bus_path=ctx.obj["bus"]) as dev:
        print(f"Setting ripple effect: R={red} G={green} B={blue} (Speed={speed})")
        dev.set_ripple(red, green, blue, brightness=brightness, speed=speed)


@cli.command("led")
@click.argument("idx", type=int)
@click.argument("r", type=int)
@click.argument("g", type=int)
@click.argument("b", type=int)
@click.pass_context
def led_cmd(ctx: click.Context, idx: int, r: int, g: int, b: int) -> None:
    """Set individual LED color (0 to 16)."""
    with LiquidDevilRGB(bus_path=ctx.obj["bus"]) as dev:
        print(f"Setting LED {idx} color: R={r} G={g} B={b}")
        dev.set_led_color(idx, r, g, b)
        dev.set_settings(1, 255, 255)


def main() -> None:
    """CLI entry point for liquid-devil-rgb."""
    cli(obj={})


if __name__ == "__main__":
    main()
