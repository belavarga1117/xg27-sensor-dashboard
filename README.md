# xG27 Sensor Dashboard

Real-time IoT sensor monitor built on the Silicon Labs EFR32BG27 dev kit.
Reads temperature, humidity, ambient light, and magnetic field — displayed live in a browser over BLE → WiFi.

```
xG27 Dev Kit  ──BLE──►  MacBook  ──WiFi──►  iPhone / Browser
(Zephyr RTOS)           (Python)             (HTML dashboard)
```

## Hardware

- **Board:** Silicon Labs xG27 Dev Kit (EFR32BG27C140F768IM40)
- **Sensors:** Si7021 (temp/humidity) · VEML6035 (light) · Si7210 (magnetic field)

## Repository structure

```
firmware/        Zephyr RTOS application (west build)
host/            Mac-side BLE scanner + HTTP/SSE server + web dashboard
patches/         Upstream Zephyr driver fix for Si7210 wake sequence
```

## Firmware

**Requirements:** Zephyr SDK 0.17.x, west

```bash
west build -b xg27_dk2602a firmware/
west flash   # or use Simplicity Commander
```

The board advertises BLE manufacturer data every second:

| Offset | Type    | Field       |
|--------|---------|-------------|
| 0–1    | int16   | Temp (centi-°C) |
| 2      | uint8   | Humidity (%) |
| 3–4    | uint16  | Light (lux) |
| 5–6    | int16   | Magnetic field (µT) |

## Host (Mac bridge)

**Requirements:** Python 3.10+, Bluetooth enabled

```bash
pip install -r host/requirements.txt
python3 host/sensor_server.py
```

Opens dashboard at `http://localhost:5555` — accessible from any device on the same WiFi.

## Zephyr driver patch

The upstream Zephyr Si7210 driver (`drivers/sensor/silabs/si7210/si7210.c`) has a bug in `si7210_wakeup()`: it treats the expected NACK from a sleeping device as a fatal error. When the Si7210 is in sleep mode, the first I2C transaction wakes it up but always NACKs — the second transaction succeeds. Apply the fix before building:

```bash
cd $ZEPHYR_BASE
git apply /path/to/patches/zephyr-si7210-wakeup-fix.patch
```
