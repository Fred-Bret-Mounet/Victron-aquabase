"""Aquabase BLE wire protocol — UUIDs, opcodes, decoders.

Reverse-engineered from the Aquabase 0.0.1 Android app and a live FIJI
Premium 65. The firmware exposes five live values: a state
byte, the operating-hour counter, a salinity reading, a salinity
threshold, and the produced-water flow rate.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

# ─── GATT topology ────────────────────────────────────────────────────────────
SVC_STREAMING     = "fad76f74-3d85-404d-b873-d7426252bfbb"
SVC_PARAMETERS    = "fad76f74-3d85-404d-b873-d7426253bfbb"
CHR_NOTIFY_STREAM = "b21e5880-5ee8-48ab-858d-eea84afaaa9c"
CHR_NOTIFY_PARAMS = "b21e5880-5ee8-48ab-858d-eea84afaab9c"
CHR_WRITE_PARAMS  = "b21e5880-5ee8-48ab-858d-eea84afbab9c"
NAME_PREFIX       = "SLCE"

# ─── Outbound opcodes (x1.f) ──────────────────────────────────────────────────
CMD_POWER_OFF     = bytes.fromhex("1000")
CMD_POWER_ON      = bytes.fromhex("1001")
CMD_WASH          = bytes.fromhex("1002")
CMD_READ_ALL      = bytes.fromhex("00524541442030")  # b"\x00READ 0"
CMD_READ_HISTORY  = bytes.fromhex("00524541442035")  # b"\x00READ 5"
OP_UPDATE_STOP    = 0x02

# ─── State-byte bits (only RUN is confirmed against the panel) ────────────────
STATE_RUN   = 0x01
STATE_WASH  = 0x02   # provisional — refine when a wash cycle is observed
STATE_ALARM = 0x04   # provisional

# ─── Lookup tables ────────────────────────────────────────────────────────────
MODEL_NAMES = [
    "Aquabase ARUBA Comfort", "Aquabase ARUBA Premium 60",
    "Aquabase ARUBA Premium 120", "Aquabase ARUBA Premium 180",
    "Aquabase ARUBA Premium 240", "Aquabase ARUBA Premium 300",
    "Aquabase ARUBA XL Comfort", "Aquabase ARUBA XL Premium 450",
    "Aquabase ARUBA XL Premium 600", "Aquabase ARUBA XL Premium 750",
    "SOROYA Comfort", "SOROYA Premium 625", "SOROYA Premium 800",
    "SOROYA Premium 1000", "SOROYA Premium 1250", "SOROYA Premium 1600",
    "BW", "FIJI Comfort 35", "FIJI Premium 35", "FIJI Comfort 65",
    "FIJI Premium 65", "FIJI Comfort 105", "FIJI Premium 105",
]

HISTORY_CODES = {
    23: ("C214-0", "ACCES AU MODE MAINTENANCE"),
    24: ("C200-0", "REMPLACEMENT DE D004"),
    49: ("C001-1", "ERREUR DEPRESSION PSn03"),
}


# ─── Decoded frames ───────────────────────────────────────────────────────────
@dataclass
class StreamingFrame:
    state: int | None = None
    horameter: float | None = None      # hours
    salinity: int | None = None         # ppm (raw)
    threshold: int | None = None        # ppm
    flow: int | None = None             # L/h


@dataclass
class FactoryFrame:
    model_id: int
    serial: int
    day: int
    month: int
    year: int

    @property
    def model_name(self) -> str:
        return (MODEL_NAMES[self.model_id]
                if self.model_id < len(MODEL_NAMES)
                else f"unknown(0x{self.model_id:02x})")

    @property
    def date_str(self) -> str:
        return f"{self.day:02d}/{self.month:02d}/{self.year}"


@dataclass
class HistoryEntry:
    item_id: int
    code: int
    horameter: float

    @property
    def code_str(self) -> str:
        return HISTORY_CODES.get(self.code, (f"0x{self.code:02x}", "?"))[0]

    @property
    def description(self) -> str:
        return HISTORY_CODES.get(self.code, ("", "?"))[1]


@dataclass
class CompletionFrame:
    ok: bool
    raw_status: int


# ─── Decoders ─────────────────────────────────────────────────────────────────
def decode_streaming(buf: bytes) -> StreamingFrame | None:
    if not buf:
        return None
    op = buf[0]
    if op == 0x01 and len(buf) >= 6:
        return StreamingFrame(
            state=buf[1],
            horameter=int.from_bytes(buf[2:6], "big") * 0.1,
        )
    if op == 0x02 and len(buf) >= 13:
        sal, thr, flow = struct.unpack(">III", buf[1:13])
        return StreamingFrame(salinity=sal, threshold=thr, flow=flow)
    return None


def decode_parameters(buf: bytes):
    """Return one of: FactoryFrame, HistoryEntry, CompletionFrame, ('raw', op, payload)."""
    if not buf:
        return None
    op = buf[0]
    if op == 0x04 and len(buf) >= 8:
        return FactoryFrame(
            model_id=buf[1],
            serial=int.from_bytes(buf[2:4], "big"),
            day=buf[4],
            month=buf[5],
            year=int.from_bytes(buf[6:8], "big"),
        )
    if op == 0x05 and len(buf) >= 7:
        return HistoryEntry(
            item_id=buf[1],
            code=buf[2],
            horameter=int.from_bytes(buf[3:7], "big") * 0.1,
        )
    if op == 0xff and len(buf) >= 2:
        return CompletionFrame(ok=(buf[1] == 0x53), raw_status=buf[1])
    return ("raw", op, buf[1:])


def encode_update_stop(enabled: bool, by_volume: bool, target: int) -> bytes:
    return (bytes([OP_UPDATE_STOP, int(bool(enabled)), int(bool(by_volume))])
            + (target & 0xffffffff).to_bytes(4, "big"))
