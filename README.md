# Liquid Devil RGB Control for Linux

A standalone CLI tool, Python library, and **OpenRGB Real-Time Sync Client** for controlling the RGB lighting on the **PowerColor Radeon RX 7900 XTX Liquid Devil** graphics card under Linux via I2C.

Reverse-engineered hardware protocol implementation for the V2 I2C RGB microcontroller at address `0x22`.

---

## Features

- 🔄 **OpenRGB Sync Client Mode**: Connects as an SDK client to an active OpenRGB Server (`127.0.0.1:6742`) and **syncs your Liquid Devil GPU to match your motherboard, RAM, or PC theme in real-time at 30 FPS!**
- 🌐 **OpenRGB SDK Server Mode**: Optional built-in SDK Server (port `6742`) for third-party tools (Artemis, SignalRGB).
- 🟢 **Auto-Detection**: Automatically locates the `AMDGPU DM i2c OEM bus` across systems and reboots.
- 🎨 **Full Color Control**: Set any static RGB color or hex color (`#FF00FF`, `#00FFFF`, etc.).
- 💡 **Full Brightness**: Supports the full `0–255` brightness range.
- 🌊 **8 Built-in Hardware Effects**:
  - `static`: Solid continuous color.
  - `breathing`: Gentle pulse fade in/out.
  - `neon`: Smooth spectrum cycle across the full color range.
  - `blink`: Single flashing pulse effect.
  - `double-blink`: Double flashing pulse effect.
  - `meteor`: Dynamic light beam shooting across the face of the GPU.
  - `ripple`: Dynamic wave expansion across the waterblock.
  - `off`: Turn off all LEDs.
- 🎯 **Individual LED Addressing**: Address any of the **17 individual LEDs** (0 to 16) on the EKWB waterblock.
- ⚙️ **Master Offset Support**: Uses Master Offset 48 (`0x30`) for simultaneous, flicker-free updates up to **33 FPS**.
- 🔒 **Safe Execution**: Includes guardrails to prevent writing to hazardous registers (such as `0xCC`).
- ⚡ **Zero Dependencies**: Standard Python 3 library (`ctypes`, `fcntl`, `sys`, `socket`) — no third-party packages required!

---

## Installation

### Prerequisites

Make sure the Linux `i2c-dev` module is loaded:

```bash
sudo modprobe i2c-dev
```

To make `i2c-dev` load automatically on boot:

```bash
echo "i2c-dev" | sudo tee /etc/modules-load.d/i2c-dev.conf
```

Ensure your user is in the `i2c` group for non-root access:

```bash
sudo usermod -aG i2c $USER
```

### Install Package

Clone the repository and install:

```bash
git clone https://github.com/shanefagan/liquid_devil_linux_rgb.git
cd liquid_devil_linux_rgb
pip install .
```

Or rebuild the Arch Linux package:

```bash
makepkg -si
```

---

## OpenRGB Real-Time Sync (Recommended)

When you run OpenRGB to control your motherboard, RAM, or PC lighting:

1. Enable **SDK Server** in OpenRGB (OpenRGB GUI -> Settings -> Start Server on port `6742`).
2. Run `liquid-devil-rgb openrgb-sync`:

```bash
liquid-devil-rgb openrgb-sync
```

Your Liquid Devil GPU will connect to OpenRGB, read the active color theme, and **mirror OpenRGB in real-time at 30 FPS!**

---

## Systemd Service (Auto-Sync to OpenRGB at Boot)

To automatically sync your Liquid Devil GPU to OpenRGB whenever your system boots, create `/etc/systemd/system/liquid-devil-sync.service`:

```ini
[Unit]
Description=PowerColor Liquid Devil 7900 XTX OpenRGB Sync Daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/liquid-devil-rgb openrgb-sync
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now liquid-devil-sync.service
```

---

## Command Line Interface Usage

```bash
# Sync GPU to running OpenRGB server in real-time (30 FPS)
liquid-devil-rgb openrgb-sync

# Read RGB status and mode
liquid-devil-rgb status

# Turn off all RGB LEDs
liquid-devil-rgb off

# Set static color (R G B or --hex)
liquid-devil-rgb static 0 0 255          # Pure Blue
liquid-devil-rgb static --hex #FF00FF    # Purple / Magenta

# Set breathing effect
liquid-devil-rgb breathing 255 0 0 --speed 50

# Set spectrum cycle / neon effect
liquid-devil-rgb neon --speed 50

# Set flashing blink / double-blink
liquid-devil-rgb blink 0 255 0 --speed 50
liquid-devil-rgb double-blink 0 255 255 --speed 50

# Set dynamic meteor beam effect
liquid-devil-rgb meteor 255 0 255 --speed 20

# Set dynamic ripple wave effect
liquid-devil-rgb ripple 255 255 0 --speed 30

# Control individual LED (0 to 16)
liquid-devil-rgb led 0 255 0 0           # Set LED 0 (front right) to Red
```

---

## Hardware Protocol Summary

| Parameter | Register / Value | Notes |
| :--- | :--- | :--- |
| **I2C Bus** | Auto-detected (`AMDGPU DM i2c OEM bus`) | Usually `/dev/i2c-7` |
| **I2C Target Address** | `0x22` | 7-bit address |
| **Identification (Reg `0x90`)** | `0x00 0x11 0x00` | 7900 XTX V2 Controller |
| **Settings Offset** | `1` (`0x01`) | `[mode, brightness, speed]` |
| **Master All-LED Offset** | `48` (`0x30`) | Sets entire card simultaneously |
| **Individual LED Offsets** | `26` to `42` (`0x1A`–`0x2A`) | 17 LEDs (0 to 16) |

*See `PROTOCOL.md` for full technical specification.*

---

## License

[MIT License](LICENSE)
