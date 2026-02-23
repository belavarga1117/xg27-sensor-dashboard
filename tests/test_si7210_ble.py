#!/usr/bin/env python3
"""
Regression test: Si7210 magnetic sensor reporting over BLE.

Scans for xG27-Sensor advertisements and verifies:
  1. At least one packet is received (BLE advertising works)
  2. The Si7210 flag (bit 2 of the flags byte) is set in every packet
  3. The reported magnetic field is non-zero (sensor actually measuring)

Exit code: 0 = PASS, 1 = FAIL
"""

import asyncio
import struct
import sys
from dataclasses import dataclass

from bleak import BleakScanner

DEVICE_NAME  = "xG27-Sensor"
COMPANY_ID   = 0xFFFF
SCAN_SECONDS = 15


@dataclass
class Packet:
    flags: int
    mag_ut: int

    @property
    def si7210_ok(self) -> bool:
        return bool(self.flags & 4)


def _parse(raw: bytes) -> Packet | None:
    if len(raw) < 8:
        return None
    mag   = struct.unpack_from("<h", raw, 5)[0]
    flags = raw[7]
    return Packet(flags=flags, mag_ut=mag)


async def _collect() -> list[Packet]:
    packets: list[Packet] = []

    def on_adv(device, adv):
        if device.name != DEVICE_NAME:
            return
        raw = adv.manufacturer_data.get(COMPANY_ID, b"")
        pkt = _parse(raw)
        if pkt:
            packets.append(pkt)

    print(f"Scanning for '{DEVICE_NAME}' ({SCAN_SECONDS} s)…")
    async with BleakScanner(on_adv):
        await asyncio.sleep(SCAN_SECONDS)

    return packets


def _run_tests(packets: list[Packet]) -> bool:
    passed = True

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passed
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            passed = False

    total = len(packets)
    si7210_ready = [p for p in packets if p.si7210_ok]
    nonzero      = [p for p in si7210_ready if p.mag_ut != 0]

    print(f"\nReceived {total} packet(s) in {SCAN_SECONDS} s\n")

    check(
        "BLE advertising active",
        total > 0,
        f"{total} packets" if total else "no packets received",
    )
    check(
        "Si7210 flag set (f & 4) in all packets",
        total > 0 and len(si7210_ready) == total,
        f"{len(si7210_ready)}/{total}",
    )
    check(
        "Magnetic field non-zero",
        len(nonzero) > 0,
        (
            f"avg {sum(p.mag_ut for p in nonzero)/len(nonzero):.1f} µT"
            if nonzero else "all readings zero"
        ),
    )

    return passed


def main() -> int:
    packets = asyncio.run(_collect())
    ok = _run_tests(packets)
    print(f"\n{'PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
