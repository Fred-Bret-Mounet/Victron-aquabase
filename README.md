# Aquabase-watermaker

Venus OS dbus bridge for **Aquabase / SLCE Watermakers** (FIJI, ARUBA, SOROYA, BW
families) over BLE. Publishes `com.victronenergy.watermaker.aquabase` so the
unit shows up on the GX touchscreen and on VRM.

Reverse-engineered from the official Aquabase 0.0.1 Android app and validated
against a live FIJI Premium 65.

## Status

- ✅ Read-only telemetry: state, operating hours, salinity, salinity threshold,
      flow rate, water-quality (OK/NOK), model, serial, commission date,
      most-recent event.
- ✅ Auto-reconnect with configurable retry interval.
- ⏳ Writable controls (`/State` start/stop/wash, auto-stop config) — wired in
      the BLE layer but not exposed on dbus until reconnect behavior is fully
      proven on Venus.

## Requirements

- Raspberry Pi running Venus OS 3.x (with working BLE — built-in radio works).
- `python3-pip` (`opkg install python3-pip` if missing).
- Internet access at install time (the setup script `pip install`s `bleak`
  and `git clone`s Victron's `velib_python`).

A Cerbo GX is **not supported** — its BLE stack does not present the bluez
interfaces `bleak` needs. Run the bridge on a separate Pi and the Cerbo will
pick up the watermaker over MQTT/dbus once both are on the same network.

## Install

On the Pi (as root):

```sh
mkdir -p /data && cd /data
git clone https://github.com/<you>/Aquabase-watermaker
cd Aquabase-watermaker
./setup install AA:BB:CC:DD:EE:FF      # MAC of your watermaker
```

`./setup install` (no MAC) is fine too — it just leaves the setting blank;
write the MAC later with:

```sh
dbus -y com.victronenergy.settings /Settings/Watermaker/Aquabase/MacAddress \
    SetValue '"AA:BB:CC:DD:EE:FF"'
svc -t /service/dbus-aquabase
```

## Verify

```sh
tail -F /var/log/dbus-aquabase/current
dbus -y com.victronenergy.watermaker.aquabase / GetValue
```

You should see, within ~10 seconds of boot, a connected device and the live
salinity/flow/horameter updating once per second.

## Uninstall

```sh
./setup uninstall    # removes the service link, keeps files
./setup purge        # also deletes /data/Aquabase-watermaker
```

## Layout

```
Aquabase-watermaker/
├── dbus_aquabase.py        # main service
├── aquabase/
│   ├── protocol.py         # UUIDs, opcodes, frame decoders
│   └── ble.py              # asyncio bleak link + reconnect
├── service/                # runit service template (linked into /service/)
│   ├── run
│   └── log/run
├── ext/velib_python/       # cloned by setup
├── setup                   # install / uninstall / purge / status
├── version
└── requirements.txt
```

## Published dbus paths

`com.victronenergy.watermaker.aquabase`:

| Path | Type | Notes |
|---|---|---|
| `/Connected` | int 0/1 | BLE link up |
| `/State` | int | 0 stopped, 1 running, 2 washing |
| `/CurrentFlow` | int | L/h, current produced-water flow |
| `/Salinity` | int | ppm, raw membrane reading |
| `/SalinityThreshold` | int | ppm, "good" if salinity ≤ this |
| `/Quality` | int 0/1 | derived: 1=OK, 0=NOK |
| `/HoursOperation` | float | total operating hours |
| `/Model` | str | resolved from the model byte |
| `/Serial` | str | numeric serial |
| `/CommissionDate` | str | DD/MM/YYYY |
| `/LastEventCode` | int | last non-zero history code |
| `/LastEventDescription` | str | "Cnnn-x DESCRIPTION" if known |

## Caveats

- Salinity and threshold are reported **as-the-firmware-sees-them**. On the
  panel, "NOK" is shown until salinity drops below the threshold; the bridge
  exposes both numbers and an OK/NOK derived flag, but the on-panel
  production valve (V64) state is **not** in the BLE protocol.
- Pressures (PSn03/PSn31/PSn33), low-pressure pump state and valve position
  are visible on the touchscreen but **not exposed by BLE**. Don't expect
  them on dbus — that's a firmware limit, not a bridge limit.
- The `STATE_WASH` and `STATE_ALARM` bit positions in `protocol.py` are
  provisional. Trigger a wash cycle and watch `/var/log/dbus-aquabase/current`
  to confirm before relying on `/State == 2`.
