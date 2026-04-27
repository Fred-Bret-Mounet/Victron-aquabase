# Aquabase BLE protocol

Reverse-engineered wire protocol for **Aquabase / SLCE Watermakers**
(FIJI, ARUBA, SOROYA, BW families). Validated against an Aquabase 0.0.1
Android app and a live Aquabase FIJI Premium 65.

This is the source of truth for `aquabase/protocol.py`; values that look
like magic constants there are explained here.

## 1. Discovery and scan

The unit advertises as a peripheral with a name beginning with **`SLCE`**
(case-insensitive) — e.g. `SLCE`, `SLCE_FIJI065_…`. The Android app uses
`BluetoothLeScanner.startScan(callback)` with **no filter**, then in
`onScanResult` keeps any device whose:

- name (uppercased, ROOT locale) starts with `"SLCE"`
- advertisement contains at least one service UUID

That first advertised service-UUID is treated as the "kind" of unit but
isn't otherwise used.

| | |
|---|---|
| Advertising name prefix | `SLCE` |
| Auto-reconnect | last-connected MAC saved to `SharedPreferences("com.slcewatermakers.aquabaseapp2.prefs")` under key `pref_last_connected` |
| Bonding | every connect calls `BluetoothDevice.removeBond()` via reflection before `connectGatt(autoConnect=false, callback)`, then `device.createBond()` *after* successful service discovery |

## 2. GATT topology

Two parallel "channels". Each channel is one **service** with a notify
characteristic and a write characteristic. Subscribe (CCCD `0x2902`) to
the two notify characteristics; write everything (control + parameter
queries) to the **PARAMETERS write** characteristic.

| Channel | Service UUID | Notify char (subscribe) | Write char |
|---|---|---|---|
| `STREAMING` | `FAD76F74-3D85-404D-B873-D7426252BFBB` | `B21E5880-5EE8-48AB-858D-EEA84AFAAA9C` | `B21E5880-5EE8-48AB-858D-EEA84AFBAA9C` *(declared, unused by the app)* |
| `PARAMETERS` | `FAD76F74-3D85-404D-B873-D7426253BFBB` | `B21E5880-5EE8-48AB-858D-EEA84AFAAB9C` | `B21E5880-5EE8-48AB-858D-EEA84AFBAB9C` |

CCCD: `00002902-0000-1000-8000-00805F9B34FB`.

Notes:

- Frames on **STREAMING notify** carry live telemetry (state, horameter,
  sensors).
- Frames on **PARAMETERS notify** carry parameter blocks (auto-stop,
  history events, factory data, write-completion ACKs).
- The app writes **only** to the PARAMETERS write characteristic. The
  STREAMING-side write characteristic is enumerated but never used.

## 3. Connection sequence

1. `removeBond()` (reflection) on the target `BluetoothDevice`.
2. `device.connectGatt(ctx, autoConnect=false, callback)`.
3. On `STATE_CONNECTED` → `gatt.discoverServices()`.
4. On `onServicesDiscovered`: walk every characteristic, queue any whose
   UUID is in the notify-set above.
5. Drain the queue **one at a time**:
   - `setCharacteristicNotification(c, true)`
   - write CCCD descriptor with `ENABLE_NOTIFICATION_VALUE` (0x01 0x00)
6. After the last CCCD write: `device.createBond()`, persist MAC, signal
   `WATERMAKER_CONNECTED`.
7. The app then writes `READ_ALL` to fetch all parameter blocks.

**Reconnect-on-disconnect**: if a connect attempt is in progress, retry
up to **5 times**, then bail out with `WATERMAKER_CONNECT_FAIL`.

## 4. Frame format

Each notify and write payload is one frame:

```
[ opcode_byte ] [ payload bytes ... ]
```

The opcode is the first byte. The remaining bytes are opcode-specific.
There is **no length prefix, no checksum, no encryption**. Multi-byte
numeric fields are **big-endian unsigned**.

The Android app converts the buffer to a lowercase hex string and matches
the first 2 hex chars to dispatch — same effect as comparing the first
byte. This shows up as quirks elsewhere (large fields would overflow the
hex→int parse) but doesn't affect the wire layout.

Writes use `WRITE_TYPE_NO_RESPONSE` (`setWriteType(1)`). A successful
parameter write is acknowledged by a `COMPLETION` frame on the
PARAMETERS notify char (see §6).

## 5. App → Device commands (PARAMETERS write char)

The first byte is the opcode; some "commands" are short ASCII strings
(read requests start with `0x00 "READ "` followed by a digit).

| Name | Bytes | Payload | Notes |
|---|---|---|---|
| `POWER_OFF` | `10 00` | none | "stop" button |
| `POWER_ON` | `10 01` | none | "start" button |
| `WASH` | `10 02` | none | manual wash / rinse cycle |
| `UPDATE_AUTOMATIC_STOP` | `02` | `[enabled:1] [byVolume:1] [target:u32 BE]` | Auto-stop config: `enabled` flag, mode flag (1 = volume in L, 0 = time in min), 32-bit threshold |
| `READ_ALL` | `00 52 45 41 44 20 30` | `\x00READ 0` | Triggers the device to push back all four parameter blocks |
| `READ_LANGUAGE` | `\x00READ 1` | — | Declared, not invoked in v0.0.1 |
| `READ_AUTOMATIC_STOP` | `\x00READ 2` | — | Declared, not invoked |
| `READ_AUTOMATIC_WASHING` | `\x00READ 3` | — | Declared, not invoked |
| `READ_FACTORY_PARAMETERS` | `\x00READ 4` | — | Declared, not invoked |
| `READ_HISTORY` | `00 52 45 41 44 20 35` (`\x00READ 5`) | — | Sent from the History page; dumps the alarm/event ring |
| `UPDATE_LANGUAGE` | `01 ...` | (not implemented in v0.0.1) | Enum entry only |
| `UPDATE_AUTOMATIC_WASHING` | `03 ...` | (not implemented in v0.0.1) | Enum entry only |
| `UPDATE_FACTORY_PARAMETERS` | `04 ...` | (not implemented in v0.0.1) | Enum entry only |

The app starts a 5 s `Timer` after each parameter write and emits
`START_COMMAND` / `STOP_COMMAND` events. `DID_COMPLETION` arrives on the
PARAMETERS notify char when the device acks the write. Power on/off/wash
do **not** emit a completion frame — the 5 s timeout is harmless for
those.

## 6. Device → App notifications

### 6a. PARAMETERS notify char (`...EEA84AFAAB9C`)

Dispatch on first byte:

| Opcode | Meaning | Layout | App-side event |
|---|---|---|---|
| `01` | Language block | `[01][raw bytes]` (opaque to the BLE layer) | `LANGUAGE_UPDATE` |
| `02` | Auto-stop block | `[02][enabled:1][byVolume:1][target:u32 BE]` (7 bytes) | `AUTOMATIC_STOP_UPDATE` |
| `03` | Auto-washing block | `[03][raw bytes]` (typically 2 bytes — 1-byte enable flag) | `AUTOMATIC_WASHING_UPDATE` |
| `04` | Factory parameters | `[04][model:1][serial:u16 BE][day:1][month:1][year:u16 BE]` (8 bytes) | `FACTORY_PARAMETERS_UPDATE` |
| `05` | History entry | `[05][id:1][code:1][horameter:u32 BE]` (7 bytes) — see §6c | `HISTORY_UPDATE` |
| `ff` | Command completion | `[ff][status:1][?trailing]` — `0x53 = 'S'` (success), `0x45 = 'E'` (error) | `DID_COMPLETION` |

For opcodes `01..04` the BLE layer just stores the **whole raw frame** in
a `HashMap<g, byte[]>` and notifies the UI; per-block parsing is in the
view classes (`AutomaticStopView`, `FactoryDetailsView`, etc.).

### 6b. STREAMING notify char (`...EEA84AFAAA9C`)

Frames are pushed continuously while connected (~1 Hz). Two opcodes
populate a single shared model and emit `STREAMING_DATA_UPDATE`.

| Opcode | Meaning | Layout | Fields |
|---|---|---|---|
| `01` | Device state | `[01][state:1][horameter:u32 BE × 0.1]` (typically 6 bytes) | `state` (byte at idx 1), `horameter` in hours |
| `02` | Sensor reading | `[02][salinity:u32 BE][threshold:u32 BE][flow:u32 BE]` (13 bytes) | three uint32s — see §6c for semantics |

### 6c. Field semantics

Validated against the Aquabase FIJI Premium 65 control panel.

#### `01` device-state frame

- **`state` byte** (offset 1) — bit-packed flags. The only bit
  empirically confirmed is **bit 0 = RUN** (LP pump active, panel shows
  `Pompe BP P04: MARCHE`). The `STATE_WASH` (`0x02`) and `STATE_ALARM`
  (`0x04`) bits in `aquabase/protocol.py` are **provisional**: they
  follow the app's enum ordering but haven't been observed firing on a
  real unit yet. Trigger a wash cycle and watch
  `/var/log/dbus-aquabase/current` to confirm the WASH bit position
  before relying on `/State == 2`.
- **`horameter`** (offsets 2–5) — operating-hour counter as a big-endian
  uint32 scaled by `× 0.1`. Resolution is therefore 0.1 h (= 6 minutes).
  The panel's `00235.5 h` matched a frame `01 00 00 00 09 32` →
  `0x932 = 2354`, scaled to 235.4 — within one tick of the panel's
  reading.

#### `02` sensors frame

The three uint32s are, in order:

1. **`s1` = salinity reading**, ppm-ish raw value. Steady around ~1700
   on an idle membrane, dipped slightly under flow. The panel shows
   `Salinité` as a status (OK/NOK), not a number.
2. **`s2` = salinity threshold**, ppm. Static `1000` on the test unit;
   the panel's NOK / OK indicator flips when `s1 ≤ s2`.
3. **`s3` = produced-water flow**, **L/h**. `0` while idle. Climbs once
   the unit is running and the FI61 flow sensor sees water — confirmed
   by matching the panel's `Débit FI61: 4 L/h` exactly with `s3 = 4`.

The panel also displays pressures (PSn03, PSn31, PSn33), the LP pump
state (P04), and the production-valve state (V64) — none of those are
exposed via BLE. That's a firmware limit on the watermaker side.

#### `04` factory-parameters frame

Layout: `[04] [model:1] [serial:u16 BE] [day:1] [month:1] [year:u16 BE]`.

- **`model` byte** indexes into a 23-entry table from the dex (see the
  `MODEL_NAMES` list in `aquabase/protocol.py`):

    ```
    0  Aquabase ARUBA Comfort      6  Aquabase ARUBA XL Comfort
    1  Aquabase ARUBA Premium 60   7  Aquabase ARUBA XL Premium 450
    …                              …
    20 FIJI Premium 65            22 FIJI Premium 105
    ```

  Validated: byte `0x14 = 20` → `FIJI Premium 65`, matching the panel.

- **`serial`** (bytes 2-3) — uint16 BE. `0x2AE1 = 10977`, matching the
  panel's `SN: 10977` exactly.

- **`day month year`** (bytes 4-7) — `[DD] [MM] [YEAR_BE]`. Bytes
  `07 0A 07 E9` decoded to `7 / 10 / 2025` (October 7, 2025) on the test
  unit; that date isn't shown anywhere on the panel, so the inference is
  purely structural — likely commissioning date.

#### `05` history-entry frame

Layout: `[05] [id:1] [code:1] [horameter:u32 BE × 0.1]` (7 bytes).

The unit holds a **fixed 50-slot ring** of events (`id` 0..49). The app
silently drops entries with `code == 0` (empty slots). On the test unit
ids 0..8 contained real events at horameter 224.1 h, ids 9..49 were
empty.

The byte-`code` is a firmware lookup index into the panel's
`Cnnn-suffix` codes — there is no formula. From the test panel:

| code byte | panel code | description |
|---|---|---|
| `0x17` (23) | `C214-0` | `ACCES AU MODE MAINTENANCE` |
| `0x18` (24) | `C200-0` | `REMPLACEMENT DE D004` |
| `0x31` (49) | `C001-1` | `ERREUR DEPRESSION PSn03` |

These three are seeded in `HISTORY_CODES`. The mapping for other codes
will fill in as new events get observed.

#### `ff` completion frame

Layout: `[ff] [status:1] [?trailing]`. Observed `ff 53 00` → status
`'S'` (success) with one trailing zero byte. The trailing byte's purpose
isn't clear from the dex; the app only reads `[1]`.

## 7. Quirks & gotchas

- **Hex round-tripping in the parser**: every decoder converts bytes →
  lowercase hex string → integer. Functionally equivalent to byte ops
  but means a frame longer than 4 bytes in a single field would overflow
  the int parse.
- **Writes are no-response** (`WRITE_TYPE_NO_RESPONSE`). For
  `UPDATE_AUTOMATIC_STOP` and similar parameter writes, the device sends
  an `ff` completion frame. For `POWER_ON`/`POWER_OFF`/`WASH` it does
  not — the app's 5 s timeout is benign for those.
- **Forced unbond every connect**: `removeBond()` runs every time. If
  the unit was paired with another phone, expect to re-pair on the next
  reconnect.
- **Single-device assumption**: globals (`f4465d`, `f4466e`, `f4468h`)
  hold one adapter / one gatt / one model. Only one watermaker may be
  driven at a time per app process.
- **PARAMETERS-only writes**: the app's write path always targets the
  PARAMETERS write characteristic. The matching write characteristic on
  the STREAMING service (enumerated in `f4538d`) is never touched. A
  device-side firmware likely accepts on it too but it's untested.
- **Status byte mapping**: `0x53 = 'S'`, `0x45 = 'E'`. The app's
  `COMPLETION_SUCCESS` (`ff53`) and `COMPLETION_ERROR` (`ff45`) enum
  entries are declared but the dispatcher only matches the first byte
  (`ff`) — the status differentiation happens in listener code that
  reads `[1]`.
- **State bits are partially confirmed**. `RUN` (bit 0) is solid;
  `WASH` (bit 1) and `ALARM` (bit 2) are educated guesses based on the
  dex's enum values. Real-world traces of a wash cycle and an alarm
  condition would let you nail those down.

## 8. Minimal viable client

Pseudo-flow for a fresh implementation:

```
scan with no filter
filter: device.name.upper().startswith("SLCE")
connect → discoverServices
for each char in {NOTIFY_STREAM, NOTIFY_PARAMS}:
    enable notifications via CCCD 0x2902 = ENABLE_NOTIFICATION_VALUE
write `\x00READ 0` to PARAMETERS write char
    → expect 4 PARAMETERS notify frames (op 0x01-0x04) + history entries + 0xff completion
loop:
    receive STREAMING frames (op 0x01 device-state, 0x02 sensors) at ~1 Hz
    parse per §6
on user action:
    write 0x10 0x01 / 0x10 0x00 / 0x10 0x02 to PARAMETERS write char
    write 0x02 enabled byVolume target_u32_be for auto-stop config
```

A working reference implementation in Python (asyncio + bleak) is in
[`aquabase/ble.py`](aquabase/ble.py); a CLI probe that drops to a REPL
is in [the package's tooling](aquabase_probe.py) (also referenced as the
single-file probe in the README).

## 9. What's NOT exposed over BLE

For completeness — these fields appear on the watermaker's own
touchscreen but are **not** in any BLE frame:

- `Pression PSn03` — low-pressure sensor (bar)
- `Pression PSn31` — HP pump output pressure (bar)
- `Pression PSn33` — membrane pressure (bar)
- `Pompe BP P04` — LP pump state (MARCHE / ARRET)
- `Vanne production V64` — production-valve position (REJET / PRODUCTION)
- `Soft CM v X.X`, `Soft EV v X.X` — firmware versions

You'll find the bridge exposes the five fields the firmware *does* send
(state, horameter, salinity, salinity threshold, flow) and derives a
quality flag (`OK` if `salinity ≤ threshold`).

## 10. Scope of this document

Reverse-engineered from:

- `Aquabase 0.0.1` (apkpure download) — decompiled with **jadx 1.5.5**
  to read the BLE handlers in `v1.C0372b`, `v1.C0375e`, the protocol
  enums in `x1.f`, `x1.j`, `x1.g`, `x1.i`, and the GATT topology in
  `x1.AbstractC0391b`.
- A live Aquabase FIJI Premium 65 (commissioned 7 Oct 2025) used to
  validate field semantics against the on-board panel.

If you reproduce this against a different model or trigger an event
type not listed in §6c (any code byte not in `{23, 24, 49}`), please
open an issue or PR with the byte and the matching panel description so
the lookup table can be extended.
