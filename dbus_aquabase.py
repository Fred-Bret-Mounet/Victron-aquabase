#!/usr/bin/env python3
"""dbus-aquabase — bridge an Aquabase BLE watermaker onto Venus OS dbus.

Publishes com.victronenergy.watermaker.aquabase with the standard watermaker
paths plus a few Aquabase-specific extras. Reads its target MAC from
/Settings/Watermaker/Aquabase/MacAddress (configurable via dbus-spy).
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading

from gi.repository import GLib

import dbus
import dbus.mainloop.glib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(1, os.path.join(HERE, "ext", "velib_python"))
sys.path.insert(1, os.path.join(HERE, "ext"))           # vendored bleak

from vedbus import VeDbusService                     # noqa: E402
from settingsdevice import SettingsDevice            # noqa: E402

from aquabase import protocol as P                   # noqa: E402
from aquabase.ble import BleLink                     # noqa: E402

VERSION = "1.3.0"
SERVICE_NAME = "com.victronenergy.watermaker.aquabase"
SETTINGS_PREFIX = "/Settings/Watermaker/Aquabase"
ALERT_HOLD_SECONDS = 60

# Venus notification types accepted by com.victronenergy.platform/Notifications/Inject
NOTIF_WARNING      = 0
NOTIF_ALARM        = 1
NOTIF_INFORMATION  = 2

log = logging.getLogger("dbus-aquabase")


class AquabaseService:
    def __init__(self, bus: dbus.SystemBus, settings: SettingsDevice):
        self._bus = bus
        self._svc = VeDbusService(SERVICE_NAME, bus=bus, register=False)
        self._settings = settings
        self._last_state: int | None = None
        self._link: "BleLink | None" = None
        self._add_paths()
        self._svc.register()

    def attach_link(self, link: "BleLink") -> None:
        """Wire up the BLE writer used by /Mode write callbacks."""
        self._link = link

    def _add_paths(self) -> None:
        s = self._svc
        s.add_path("/Mgmt/ProcessName",    os.path.basename(__file__))
        s.add_path("/Mgmt/ProcessVersion", VERSION)
        s.add_path("/Mgmt/Connection",     "BLE")
        s.add_path("/DeviceInstance",      0)
        s.add_path("/ProductId",           0xB0B0)   # vendor-defined
        s.add_path("/ProductName",         "Aquabase Watermaker")
        s.add_path("/FirmwareVersion",     "")
        s.add_path("/HardwareVersion",     "")
        s.add_path("/Serial",              "")
        s.add_path("/Connected",           0)

        s.add_path("/State",               0)        # 0=stopped 1=running 2=washing
        # Writable command path. UI sets 0/1/2; bridge sends POWER_OFF/POWER_ON/WASH.
        # The value snaps back to /State on the next streaming frame, which is the
        # behaviour the QML ListRadioButtonGroup expects.
        s.add_path("/Mode", 0, writeable=True,
                   onchangecallback=self._on_mode_change)
        s.add_path("/CurrentFlow",         0)        # L/h
        s.add_path("/Salinity",            0)        # ppm
        s.add_path("/SalinityThreshold",   0)        # ppm
        s.add_path("/Quality",             0)        # 0=Bad 1=Good
        s.add_path("/HoursOperation",      0.0)      # h
        s.add_path("/Model",               "")
        s.add_path("/CommissionDate",      "")
        s.add_path("/LastEventCode",       0)
        s.add_path("/LastEventDescription", "")

        for name in ("StartEvent", "StopEvent", "WashEvent"):
            s.add_path(f"/Alarms/{name}/State", 0)
            s.add_path(f"/Alarms/{name}/Description", "")

    # ─── command callback (GLib thread, dispatches to BLE thread) ────────────
    def _on_mode_change(self, path: str, value) -> bool:
        try:
            mode = int(value)
        except (TypeError, ValueError):
            log.warning("/Mode rejected: non-integer value %r", value)
            return False
        cmd_map = {
            0: ("POWER_OFF", P.CMD_POWER_OFF),
            1: ("POWER_ON",  P.CMD_POWER_ON),
            2: ("WASH",      P.CMD_WASH),
        }
        if mode not in cmd_map:
            log.warning("/Mode rejected: unknown value %d", mode)
            return False
        if not self._link:
            log.warning("/Mode %d ignored: BLE link not attached yet", mode)
            return False
        if self._svc["/Connected"] != 1:
            log.warning("/Mode %d ignored: not connected to watermaker", mode)
            return False
        name, payload = cmd_map[mode]
        log.info("dispatching command %s (mode=%d) via BLE", name, mode)
        self._link.submit(self._link.write(payload))
        # Accept the dbus write so the value sticks until the next streaming
        # frame overwrites it from the device-reported /State.
        return True

    # ─── update sinks (called from GLib thread) ──────────────────────────────
    def set_connected(self, connected: bool) -> None:
        self._svc["/Connected"] = 1 if connected else 0
        if not connected:
            self._svc["/State"] = 0
            self._last_state = None

    def _raise_alarm(self, name: str, description: str) -> None:
        self._svc[f"/Alarms/{name}/State"] = 1
        self._svc[f"/Alarms/{name}/Description"] = description
        log.info("alarm raised: %s — %s", name, description)
        # Also push to the platform notification centre so it appears on
        # the GX Notifications tab. Custom alarm names like ours aren't
        # picked up by venus-platform's hardcoded /Alarms/<name> watcher,
        # but the /Notifications/Inject action accepts arbitrary text.
        self._inject_notification(NOTIF_INFORMATION, "Aquabase Watermaker", description)
        GLib.timeout_add_seconds(ALERT_HOLD_SECONDS, self._clear_alarm, name)

    def _inject_notification(self, type_: int, devicename: str, description: str) -> None:
        # See venus-platform src/notifications.hpp::VeQItemInjectNotification:
        # value is "<type>\t<devicename>\t<description>" on the
        # com.victronenergy.platform/Notifications/Inject path.
        try:
            obj = self._bus.get_object("com.victronenergy.platform", "/Notifications/Inject")
            payload = f"{type_}\t{devicename}\t{description}"
            obj.SetValue(payload, dbus_interface="com.victronenergy.BusItem")
        except dbus.DBusException as e:
            log.warning("notification inject failed: %s", e.get_dbus_name())

    def _clear_alarm(self, name: str) -> bool:
        self._svc[f"/Alarms/{name}/State"] = 0
        self._svc[f"/Alarms/{name}/Description"] = ""
        return False

    def _maybe_alert(self, new_state: int) -> None:
        prev = self._last_state
        self._last_state = new_state
        if prev is None or prev == new_state:
            return
        if new_state == 1 and prev != 1 and self._settings["AlertOnStart"]:
            self._raise_alarm("StartEvent", "Watermaker started")
        elif new_state == 0 and prev != 0 and self._settings["AlertOnStop"]:
            self._raise_alarm("StopEvent", "Watermaker stopped")
        elif new_state == 2 and prev != 2 and self._settings["AlertOnWash"]:
            self._raise_alarm("WashEvent", "Watermaker washing/flushing")

    def apply_streaming(self, f: P.StreamingFrame) -> None:
        if f.state is not None:
            if f.state & P.STATE_WASH:
                new_state = 2
            elif f.state & P.STATE_RUN:
                new_state = 1
            else:
                new_state = 0
            self._svc["/State"] = new_state
            # Keep /Mode in sync with reported /State so the radio-group
            # snaps back if the device disagrees with the last write.
            if self._svc["/Mode"] != new_state:
                self._svc["/Mode"] = new_state
            self._maybe_alert(new_state)
        if f.horameter is not None:
            self._svc["/HoursOperation"] = f.horameter
        if f.salinity is not None:
            self._svc["/Salinity"] = f.salinity
        if f.threshold is not None:
            self._svc["/SalinityThreshold"] = f.threshold
        if f.salinity is not None and f.threshold is not None:
            self._svc["/Quality"] = 0 if f.salinity > f.threshold else 1
        elif f.salinity is not None:
            thr = self._svc["/SalinityThreshold"] or 0
            self._svc["/Quality"] = 0 if f.salinity > thr else 1
        if f.flow is not None:
            self._svc["/CurrentFlow"] = f.flow

    def apply_factory(self, f: P.FactoryFrame) -> None:
        self._svc["/Model"]          = f.model_name
        self._svc["/Serial"]         = str(f.serial)
        self._svc["/CommissionDate"] = f.date_str

    def apply_history(self, e: P.HistoryEntry) -> None:
        if e.code == 0:
            return
        if e.item_id != 0:           # only mirror the most recent event
            return
        self._svc["/LastEventCode"]        = e.code
        self._svc["/LastEventDescription"] = f"{e.code_str} {e.description}".strip()


# ─── thread bridges ────────────────────────────────────────────────────────────
def make_bridge(svc: AquabaseService):
    """Wrap dbus updates so callbacks from the BLE thread land on GLib."""
    def streaming(f: P.StreamingFrame) -> None:
        GLib.idle_add(svc.apply_streaming, f)

    def factory(f: P.FactoryFrame) -> None:
        GLib.idle_add(svc.apply_factory, f)

    def history(e: P.HistoryEntry) -> None:
        GLib.idle_add(svc.apply_history, e)

    def completion(c: P.CompletionFrame) -> None:
        log.info("device completion: %s (raw=0x%02x)", "OK" if c.ok else "ERROR", c.raw_status)

    def connected(b: bool) -> None:
        GLib.idle_add(svc.set_connected, b)

    return streaming, factory, history, completion, connected


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    settings = SettingsDevice(
        bus=bus,
        supportedSettings={
            "MacAddress":   [f"{SETTINGS_PREFIX}/MacAddress",   "", 0, 0],
            "AlertOnStart": [f"{SETTINGS_PREFIX}/AlertOnStart", 0,  0, 1],
            "AlertOnStop":  [f"{SETTINGS_PREFIX}/AlertOnStop",  0,  0, 1],
            "AlertOnWash":  [f"{SETTINGS_PREFIX}/AlertOnWash",  0,  0, 1],
        },
        eventCallback=None,
    )
    mac = (settings["MacAddress"] or "").strip().strip('"').strip("'") or None
    if not mac:
        log.warning("no MAC address set at %s/MacAddress — bridge will idle until configured",
                    SETTINGS_PREFIX)

    svc = AquabaseService(bus, settings)
    streaming, factory, history, completion, connected = make_bridge(svc)
    link = BleLink(
        mac=mac,
        on_streaming=streaming,
        on_factory=factory,
        on_history=history,
        on_completion=completion,
        on_connected=connected,
    )
    svc.attach_link(link)
    worker = threading.Thread(target=link.run, name="aquabase-ble", daemon=True)
    worker.start()

    loop = GLib.MainLoop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: loop.quit())
    log.info("dbus-aquabase v%s ready", VERSION)
    try:
        loop.run()
    finally:
        link.stop()
        worker.join(timeout=3.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
