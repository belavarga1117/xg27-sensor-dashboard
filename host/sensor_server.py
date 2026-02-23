#!/usr/bin/env python3
"""
xG27 Sensor Dashboard Server
- BLE scan-eli az xG27 Dev Kit advertising adatát (bleak)
- HTTP + SSE szerver iPhone/böngésző számára (port 5555)
"""

import asyncio
import json
import struct
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from bleak import BleakScanner

PORT        = 5555
HTML_FILE   = '/Users/vargabela/sensor.html'
DEVICE_NAME = 'xG27-Sensor'
COMPANY_ID  = 0xFFFF          # teszt company id

latest     = {}
sse_clients = []
sse_lock    = threading.Lock()


def get_wifi_ip():
    try:
        r = subprocess.run(['ipconfig', 'getifaddr', 'en0'],
                           capture_output=True, text=True)
        ip = r.stdout.strip()
        return ip if ip else 'localhost'
    except Exception:
        return 'localhost'


def push_to_clients(data_str):
    with sse_lock:
        dead = []
        for q in sse_clients:
            try:
                q.append(data_str)
            except Exception:
                dead.append(q)
        for q in dead:
            sse_clients.remove(q)


def parse_mfr(raw: bytes):
    """Parse 7-byte manufacturer payload: temp(2) hum(1) lux(2) mag(2)"""
    if len(raw) < 7:
        return None
    temp_cdeg = struct.unpack_from('<h', raw, 0)[0]
    hum       = raw[2]
    lux       = struct.unpack_from('<H', raw, 3)[0]
    mag       = struct.unpack_from('<h', raw, 5)[0]
    return {
        't': round(temp_cdeg / 100.0, 2),
        'h': int(hum),
        'l': int(lux),
        'm': float(mag),
        'f': 7,
    }


# ── BLE scanner ───────────────────────────────────────────────────────────────

async def ble_scan():
    print(f"BLE scan indul — '{DEVICE_NAME}' keresése...")

    def callback(device, adv):
        if device.name != DEVICE_NAME:
            return
        raw = adv.manufacturer_data.get(COMPANY_ID, b'')
        data = parse_mfr(raw)
        if data:
            global latest
            latest = data
            print(f"[BLE] t={data['t']}°C h={data['h']}% "
                  f"l={data['l']}lux m={data['m']}µT")
            push_to_clients(json.dumps(data))

    async with BleakScanner(callback):
        await asyncio.Future()


# ── HTTP / SSE server ─────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ('/', '/sensor.html'):
            try:
                with open(HTML_FILE, 'rb') as f:
                    body = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(body))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_error(404)

        elif self.path == '/events':
            self.send_response(200)
            self.send_header('Content-Type',  'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection',    'keep-alive')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            q = []
            with sse_lock:
                sse_clients.append(q)

            if latest:
                try:
                    self.wfile.write(f"data: {json.dumps(latest)}\n\n".encode())
                    self.wfile.flush()
                except Exception:
                    pass

            try:
                while True:
                    if q:
                        msg = q.pop(0)
                        self.wfile.write(f"data: {msg}\n\n".encode())
                        self.wfile.flush()
                    else:
                        time.sleep(0.1)
            except Exception:
                pass
            finally:
                with sse_lock:
                    if q in sse_clients:
                        sse_clients.remove(q)
        else:
            self.send_error(404)


class ReuseServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_http():
    server = ReuseServer(('', PORT), Handler)
    server.serve_forever()


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    ip = get_wifi_ip()
    print(f"Dashboard (Mac):    http://localhost:{PORT}/")
    print(f"Dashboard (iPhone): http://{ip}:{PORT}/")
    print()

    t = threading.Thread(target=start_http, daemon=True)
    t.start()

    await ble_scan()


if __name__ == '__main__':
    asyncio.run(main())
