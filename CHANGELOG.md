# Changelog

All notable changes to this project will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-02-23

### Added
- **Firmware:** hardware watchdog (5 s timeout) — board resets automatically if main loop stalls
- **Firmware:** `flags` byte appended to BLE manufacturer payload — receiver knows which sensors are actually reading vs. silent failures
- **Host:** BLE auto-reconnect loop — scanner restarts on any error without manual intervention
- **Host:** SSE heartbeat comment every 15 s — prevents proxy and mobile browser connection drops
- **Host:** structured `logging` with timestamps (replaces bare `print`)
- **Host:** `pathlib` for HTML file path — no longer hardcoded to a specific home directory

### Changed
- **BREAKING — BLE payload:** added 1-byte `flags` field at offset [7]; payload is now 8 bytes (was 7). Firmware and host must be updated together.
- **Host:** SSE client queue changed from `list` + `pop(0)` (O(n)) to `queue.SimpleQueue` (O(1), thread-safe)
- **Host:** `parse_mfr()` reads real `flags` from payload byte [7] instead of hardcoding `f=7`

### Fixed
- **Zephyr driver (`si7210.c`):** `si7210_wakeup()` treated the expected NACK from a sleeping Si7210 as a fatal error, causing device init to fail. Fixed by sending a wakeup pulse, waiting 5 ms, then confirming with a second read.
- **Host:** `HTTPServer` was single-threaded — an open SSE connection blocked all other requests. Fixed with `ThreadingMixIn`.

---

## [0.1.0] — 2026-02-22

### Added
- Zephyr RTOS firmware for Silicon Labs xG27 Dev Kit (EFR32BG27C140F768IM40)
- I²C sensor support: Si7021 (temperature/humidity), VEML6035 (ambient light), Si7210 (magnetic field)
- DTS overlay adding missing sensor nodes absent from the upstream board support package
- BLE advertising with manufacturer data payload (temp, humidity, lux, magnetic field)
- Python host server: BLE scan via `bleak`, HTTP + SSE dashboard on port 5555
- HTML dashboard: live sensor cards, temperature history chart, connection status indicator
- Mac-as-bridge architecture to work around iOS Safari's lack of Web Bluetooth API support
