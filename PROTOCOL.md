# PowerColor RX 7900 XTX Liquid Devil — I2C RGB Hardware Protocol

Technical specification of the reverse-engineered hardware protocol for the **PowerColor Radeon RX 7900 XTX Liquid Devil** onboard RGB controller under Linux.

---

## 1. Bus & Addressing

- **Interface**: Linux `i2c-dev` subsystem over AMDGPU Display Manager I2C driver.
- **Adapter Name**: `AMDGPU DM i2c OEM bus` (typically `/dev/i2c-7`).
- **7-Bit Address**: `0x22`
- **8-Bit Write Address**: `0x45` (ADL Offset 69)
- **8-Bit Read Address**: `0x44` (ADL Offset 68)
- **PCI Subsystem ID**: `148C:2422` (PowerColor)

---

## 2. Packet Structure

All I2C transactions are structured as **4-byte transfers**:

```
[Register_Offset, Byte_0, Byte_1, Byte_2]
```

- **Register_Offset** (1 byte): Target internal register on the microcontroller.
- **Data Payload** (3 bytes): Parameter or RGB color values.

### Read Operations
1. Write 1-byte register offset.
2. Read 3 bytes back using repeated start (I2C flags = 1).

---

## 3. Register Map

| Offset (Dec) | Offset (Hex) | Access | Purpose | Payload Format |
|---|---|---|---|---|
| `1` | `0x01` | Write | Settings / Mode | `[mode, brightness, speed]` |
| `26`–`42` | `0x1A`–`0x2A` | Write | Individual LEDs 0–16 | `[Red, Green, Blue]` |
| `48` | `0x30` | Write | **Master ALL LEDs** | `[Red, Green, Blue]` |
| `90` | `0x5A` | Read | Hardware Identification | Returns `[0x00, 0x11, 0x00]` (V2) |
| `129` | `0x81` | Read | Current Settings | `[mode, brightness, speed]` |
| `130` | `0x82` | Read | LED 0 Color | `[Red, Green, Blue]` |

---

## 4. Settings Register (Offset 1 / 0x01)

Format: `[mode, brightness, speed]`

### Hardware Effects (7900 XTX V2)
- `0`: **Off**
- `1`: **Static Color** (Uses Master Offset 48)
- `2`: **Breathing** (Uses Master Offset 48)
- `3`: **Neon** (Spectrum Cycle across color range)
- `4`: **Blink** (Single flash pulse effect)
- `5`: **Double Blink** (Double flash pulse effect)
- `7`: **Meteor** (Dynamic beam effect across face of GPU)
- `8`: **Ripple** (Dynamic wave expansion across waterblock)

### Brightness Range
- `0`: OFF
- `1` to `255`: 8-bit brightness resolution (`255` = 100% max brightness).

---

## 5. Critical Hardware Notes & Safety

- ⚠️ **DO NOT write to Register `0xCC`**: Writing to register `0xCC` causes the microcontroller to enter an unrecoverable hardware lockup state. Recovery requires a complete system shutdown and PSU power discharge.
- ⏱️ **Timing & Delays**: Always insert a **50ms pause** (`time.sleep(0.05)`) between consecutive I2C write transactions to prevent buffer overrun on the microcontroller.
- 🔒 **Bus Ownership**: Ensure no other I2C software is actively writing to `/dev/i2c-7` during transactions.
