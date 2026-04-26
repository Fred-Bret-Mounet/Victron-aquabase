"""Asyncio BLE link for the Aquabase watermaker, with reconnect.

Designed to run in a worker thread alongside a GLib mainloop. All callbacks
fire from the asyncio thread; the caller is responsible for marshalling them
onto the dbus mainloop (e.g. via GLib.idle_add).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from . import protocol as P

log = logging.getLogger("aquabase.ble")

ScanCb       = Callable[[BLEDevice], None]
StreamingCb  = Callable[[P.StreamingFrame], None]
FactoryCb    = Callable[[P.FactoryFrame], None]
HistoryCb    = Callable[[P.HistoryEntry], None]
CompletionCb = Callable[[P.CompletionFrame], None]
ConnectedCb  = Callable[[bool], None]


class BleLink:
    def __init__(
        self,
        mac: Optional[str],
        on_streaming: StreamingCb,
        on_factory: FactoryCb,
        on_history: HistoryCb,
        on_completion: CompletionCb,
        on_connected: ConnectedCb,
        scan_timeout: float = 8.0,
        retry_delay: float = 5.0,
    ):
        self.mac = mac
        self.on_streaming = on_streaming
        self.on_factory = on_factory
        self.on_history = on_history
        self.on_completion = on_completion
        self.on_connected = on_connected
        self.scan_timeout = scan_timeout
        self.retry_delay = retry_delay

        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: BleakClient | None = None
        self._stop = asyncio.Event()
        self._main_task: asyncio.Task | None = None

    # ─── lifecycle ────────────────────────────────────────────────────────────
    def run(self) -> None:
        """Blocking entry point for a worker thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._main_task = self._loop.create_task(self._main())
            self._loop.run_until_complete(self._main_task)
        finally:
            self._loop.close()

    def stop(self) -> None:
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stop.set)

    def submit(self, coro: Awaitable) -> None:
        """Thread-safe: schedule a coroutine on the BLE loop."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ─── public BLE actions (call via submit) ────────────────────────────────
    async def write(self, payload: bytes) -> None:
        if self._client and self._client.is_connected:
            await self._client.write_gatt_char(P.CHR_WRITE_PARAMS, payload, response=False)
        else:
            log.warning("write(%s) dropped: not connected", payload.hex())

    # ─── notification handlers ────────────────────────────────────────────────
    def _on_stream(self, _c, data: bytearray) -> None:
        frame = P.decode_streaming(bytes(data))
        if frame is not None:
            try:
                self.on_streaming(frame)
            except Exception:
                log.exception("on_streaming callback failed")

    def _on_params(self, _c, data: bytearray) -> None:
        result = P.decode_parameters(bytes(data))
        try:
            if isinstance(result, P.FactoryFrame):
                self.on_factory(result)
            elif isinstance(result, P.HistoryEntry):
                self.on_history(result)
            elif isinstance(result, P.CompletionFrame):
                self.on_completion(result)
        except Exception:
            log.exception("on_params callback failed")

    # ─── main reconnect loop ─────────────────────────────────────────────────
    async def _main(self) -> None:
        while not self._stop.is_set():
            if not self.mac:
                log.info("no MAC configured; sleeping")
                await asyncio.sleep(self.retry_delay)
                continue
            try:
                await self._connect_and_serve()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("BLE session ended: %s", e)
            self.on_connected(False)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.retry_delay)
                return
            except asyncio.TimeoutError:
                pass

    async def _connect_and_serve(self) -> None:
        log.info("scanning for %s* / %s", P.NAME_PREFIX, self.mac)
        device = await self._find()
        if device is None:
            return

        log.info("connecting to %s (%s)", device.address, device.name)
        async with BleakClient(device) as client:
            self._client = client
            await client.start_notify(P.CHR_NOTIFY_STREAM, self._on_stream)
            await client.start_notify(P.CHR_NOTIFY_PARAMS, self._on_params)
            self.on_connected(True)
            log.info("connected; sending READ_ALL")
            await client.write_gatt_char(P.CHR_WRITE_PARAMS, P.CMD_READ_ALL, response=False)

            try:
                while client.is_connected and not self._stop.is_set():
                    await asyncio.sleep(1.0)
            finally:
                self._client = None

    async def _find(self) -> BLEDevice | None:
        target_mac = self.mac.lower()
        found: dict[str, BLEDevice] = {}

        def cb(dev: BLEDevice, _adv):
            if dev.address.lower() == target_mac:
                found[dev.address] = dev

        async with BleakScanner(detection_callback=cb):
            deadline = asyncio.get_event_loop().time() + self.scan_timeout
            while asyncio.get_event_loop().time() < deadline:
                if found:
                    return next(iter(found.values()))
                await asyncio.sleep(0.2)
        log.info("device %s not seen in %.1fs", self.mac, self.scan_timeout)
        return None
