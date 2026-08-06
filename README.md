# Liquid Devil RGB Control for Linux

A standalone CLI tool and Python library for controlling the RGB lighting on the **PowerColor Radeon RX 7900 XTX Liquid Devil** graphics card under Linux via I2C.

Reverse-engineered hardware protocol implementation for the V2 I2C RGB microcontroller at address `0x22`.

---

## Features

- 🟢 **Auto-Detection**: Automatically locates the `AMDGPU DM i2c OEM bus` across systems and reboots.
- 🎨 **Full Color Control**: Set any static RGB color or hex color (`#FF00FF`, `#00FFFF`, etc.).
- 💡 **Full Brightness**: Supports the full `0–255` brightness range.
- 🌊 **Effects Support**: Static and Breathing lighting modes.
- 🎯 **Individual LED Addressing**: Address any of the **17 individual LEDs** (0 to 16) on the EKWB waterblock.
- ⚙️ **Master Offset Support**: Uses Master Offset 48 (`0x30`) for simultaneous, flicker-free updates.
- 🔒 **Safe Execution**: Includes guardrails to prevent writing to hazardous registers (such as `0xCC`).
- ⚡ **Zero Dependencies**: Standard Python 3 library (`ctypes`, `fcntl`, `sys`) — no third-party packages required!

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

Or run directly without installation:

```bash
python3 liquid_devil_rgb.py --help
```

---

## Usage

### Command Line Interface

```bash
# Read RGB status and mode
liquid-devil-rgb status

# Turn off all RGB LEDs
liquid-devil-rgb off

# Set static color (R G B)
liquid-devil-rgb static 0 0 255          # Pure Blue
liquid-devil-rgb static 255 0 0          # Pure Red
liquid-devil-rgb static 0 255 0          # Pure Green
liquid-devil-rgb static 255 255 255      # Bright White

# Set static color using Hex code
liquid-devil-rgb static --hex #FF00FF    # Purple / Magenta
liquid-devil-rgb static --hex #00FFFF    # Cyan

# Set breathing mode
liquid-devil-rgb breathing 255 0 255 --speed 50

# Control individual LED (0 to 16)
liquid-devil-rgb led 0 255 0 0           # Set LED 0 (front right) to Red
```

---

## Systemd Service (Optional Startup Color)

To set your GPU RGB color automatically at boot, create a systemd service:

`/etc/systemd/system/liquid-devil-rgb.service`:

```ini
[Unit]
Description=Set PowerColor Liquid Devil 7900 XTX RGB Color
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/liquid-devil-rgb static 0 0 255
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

Enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now liquid-devil-rgb.service
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

## OpenRGB Coexistence

OpenRGB does not currently support the 7900 XTX Liquid Devil V2 controller. Because OpenRGB skips the unrecognized controller at address `0x22` after its initial startup scan, `liquid-devil-rgb` and OpenRGB can run side-by-side without issues (e.g., OpenRGB managing your RAM/motherboard while `liquid-devil-rgb` controls your GPU).

---

## License

[MIT License](LICENSE)
