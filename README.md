# Liquid Devil RGB Control for Linux

A standalone CLI tool, Python library, and **OpenRGB SDK Server** for controlling the RGB lighting on the **PowerColor Radeon RX 7900 XTX Liquid Devil** graphics card under Linux via I2C.

Reverse-engineered hardware protocol implementation for the V2 I2C RGB microcontroller at address `0x22`.

---

## Features

- 🌐 **OpenRGB SDK Server Mode**: Emulates an OpenRGB SDK Server (port `6742`) so OpenRGB-compatible apps (**Artemis**, **SignalRGB**, **Audio Visualizers**, **OpenRGB GUI**) can control the GPU in real-time!
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

## OpenRGB SDK Server Mode (Real-Time Apps Integration)

`liquid-devil-rgb` includes an **OpenRGB SDK Server daemon**. Running this daemon opens port `6742` and exposes your Liquid Devil GPU to any software that supports OpenRGB SDK (e.g. OpenRGB GUI, Artemis, SignalRGB, Audio Visualizers).

To start the SDK Server:

```bash
liquid-devil-rgb sdk-server
```

Once running, open **OpenRGB GUI** (or Artemis / SignalRGB), connect to `127.0.0.1:6742` under the **SDK Client** tab, and your **PowerColor RX 7900 XTX Liquid Devil** will appear as an active GPU device!

---

## Systemd Service (Automated SDK Server or Startup Color)

### Option A: Run OpenRGB SDK Server at Boot (Recommended)

`/etc/systemd/system/liquid-devil-sdk-server.service`:

```ini
[Unit]
Description=PowerColor Liquid Devil 7900 XTX OpenRGB SDK Server Daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/liquid-devil-rgb sdk-server
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now liquid-devil-sdk-server.service
```

---

### Option B: Set a Fixed Color at Boot

`/etc/systemd/system/liquid-devil-rgb.service`:

```ini
[Unit]
Description=Set PowerColor Liquid Devil 7900 XTX RGB Color
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/liquid-devil-rgb static 0 0 255
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

---

## Command Line Interface Usage

```bash
# Read RGB status and mode
liquid-devil-rgb status

# Run OpenRGB SDK Server (port 6742)
liquid-devil-rgb sdk-server

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
