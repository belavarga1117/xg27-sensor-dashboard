#!/usr/bin/env python3
"""
xG27 Sensor Dashboard Server

- Scans for xG27-Sensor BLE advertisements (bleak)
- Serves a real-time HTML dashboard over HTTP/SSE on port 5555
- Auto-reconnects BLE on failure
"""

import asyncio
import json
import logging
import pathlib
import queue
import struct
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Any

from bleak import BleakScanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

PORT             = 5555
HTML_FILE        = pathlib.Path(__file__).parent / "sensor.html"
DEVICE_NAME      = "xG27-Sensor"
COMPANY_ID       = 0xFFFF
BLE_RETRY_DELAY  = 5    # seconds between reconnect attempts
SSE_HEARTBEAT    = 15   # seconds between keep-alive comments

latest: dict[str, Any] = {}
_clients: list[queue.SimpleQueue[str]] = []
_clients_lock = threading.Lock()


def _wifi_ip() -> str:
    try:
        r = subprocess.run(
            ["ipconfig", "getifaddr", "en0"], capture_output=True, text=True
        )
        return r.stdout.strip() or "localhost"
    except Exception:
        return "localhost"


def _broadcast(payload: str) -> None:
    with _clients_lock:
        for q in _clients:
            q.put_nowait(payload)


def _parse(raw: bytes) -> dict[str, Any] | None:
    """Parse the 8-byte BLE manufacturer payload (company ID already stripped).

    Layout:
      [0–1]  int16 LE   temperature (centi-°C)
      [2]    uint8      humidity (%RH)
      [3–4]  uint16 LE  ambient light (lux)
      [5–6]  int16 LE   magnetic field (µT)
      [7]    uint8      sensor flags  bit0=temp/hum  bit1=lux  bit2=mag
    """
    if len(raw) < 8:
        return None
    temp_cdeg = struct.unpack_from("<h", raw, 0)[0]
    hum       = raw[2]
    lux       = struct.unpack_from("<H", raw, 3)[0]
    mag       = struct.unpack_from("<h", raw, 5)[0]
    flags     = raw[7]
    return {
        "t": round(temp_cdeg / 100.0, 2),
        "h": int(hum),
        "l": int(lux),
        "m": float(mag),
        "f": int(flags),
    }


# ── BLE ───────────────────────────────────────────────────────────────────────

async def _ble_scan() -> None:
    log.info("BLE scan started — looking for '%s'", DEVICE_NAME)

    def on_adv(device, adv):
        if device.name != DEVICE_NAME:
            return
        raw = adv.manufacturer_data.get(COMPANY_ID, b"")
        data = _parse(raw)
        if data is None:
            return
        global latest
        latest = data
        log.info(
            "t=%.2f°C  h=%d%%  l=%d lux  m=%.1f µT  f=%d",
            data["t"], data["h"], data["l"], data["m"], data["f"],
        )
        _broadcast(json.dumps(data))

    async with BleakScanner(on_adv):
        await asyncio.Future()


async def ble_loop() -> None:
    while True:
        try:
            await _ble_scan()
        except Exception as exc:
            log.error("BLE error: %s — retry in %ds", exc, BLE_RETRY_DELAY)
            await asyncio.sleep(BLE_RETRY_DELAY)


# ── HTTP / SSE ────────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence per-request access log

    def do_GET(self):
        if self.path in ("/", "/sensor.html"):
            self._serve_html()
        elif self.path == "/events":
            self._serve_sse()
        else:
            self.send_error(404)

    def _serve_html(self):
        try:
            body = HTML_FILE.read_bytes()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_sse(self):
        self.send_response(200)
        self.send_header("Content-Type",  "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection",    "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q: queue.SimpleQueue[str] = queue.SimpleQueue()
        with _clients_lock:
            _clients.append(q)

        if latest:
            try:
                self.wfile.write(f"data: {json.dumps(latest)}\n\n".encode())
                self.wfile.flush()
            except Exception:
                pass

        try:
            while True:
                try:
                    msg = q.get(timeout=SSE_HEARTBEAT)
                    line = f"data: {msg}\n\n"
                except queue.Empty:
                    line = ": heartbeat\n\n"  # prevent proxy / browser timeout
                self.wfile.write(line.encode())
                self.wfile.flush()
        except Exception:
            pass
        finally:
            with _clients_lock:
                try:
                    _clients.remove(q)
                except ValueError:
                    pass


class _Server(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    ip = _wifi_ip()
    log.info("Dashboard (Mac):    http://localhost:%d/", PORT)
    log.info("Dashboard (iPhone): http://%s:%d/", ip, PORT)

    threading.Thread(target=lambda: _Server(("", PORT), _Handler).serve_forever(),
                     daemon=True).start()
    await ble_loop()


if __name__ == "__main__":
    asyncio.run(main())
