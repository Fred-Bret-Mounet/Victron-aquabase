#!/usr/bin/env python3
"""Publish a gui-v2 plugin manifest onto the local MQTT broker so the
WebAssembly build of gui-v2 (HTTP Remote Console / VRM web view) can load
it. The native GX gui-v2 reads plugins from /data/apps/enabled/*; the
WASM build looks for them on MQTT under GuiCustomizations/* (see
src/guiplugins.cpp in victronenergy/gui-v2).

Topic structure produced (all retained):
    N/<vrm-id>/GuiCustomizations/Applist                       = ["<name>"]
    N/<vrm-id>/GuiCustomizations/Apps/<name>/info              = {"sha256": .., "chunk_count": N}
    N/<vrm-id>/GuiCustomizations/Apps/<name>/Chunks/<i>        = {"base64": ".."}

The manifest bytes are split into base64-encoded chunks; the assembled
bytes (after base64 decode + concat) must hash to the published sha256.

Usage:
    publish_gui_plugin.py --manifest plugin/aquabase-watermaker.json \\
                         --name aquabase-watermaker
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys

import paho.mqtt.client as mqtt


def get_portal_id() -> str:
    import dbus  # type: ignore
    bus = dbus.SystemBus()
    obj = bus.get_object("com.victronenergy.system", "/Serial")
    return str(obj.GetValue(dbus_interface="com.victronenergy.BusItem"))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--portal-id", default=None)
    p.add_argument("--broker", default="127.0.0.1")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--chunk-size", type=int, default=32 * 1024)
    p.add_argument("--clear", action="store_true",
                   help="remove all retained topics for this plugin instead of publishing")
    args = p.parse_args()

    portal_id = args.portal_id or get_portal_id()
    base = f"N/{portal_id}/GuiCustomizations"
    print(f"portal_id={portal_id}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1,
                         client_id=f"aquabase-plugin-pub-{args.name}")
    client.connect(args.broker, args.port, keepalive=30)
    client.loop_start()

    if args.clear:
        # Empty payload + retain=True clears the retained message.
        for topic in (
            f"{base}/Applist",
            f"{base}/Apps/{args.name}/info",
        ):
            client.publish(topic, "", qos=0, retain=True).wait_for_publish(timeout=5)
            print(f"  cleared {topic}")
        client.loop_stop(); client.disconnect()
        return 0

    with open(args.manifest, "rb") as f:
        data = f.read()
    sha = hashlib.sha256(data).hexdigest()

    chunks = [
        base64.b64encode(data[i:i + args.chunk_size]).decode("ascii")
        for i in range(0, len(data), args.chunk_size)
    ]
    print(f"manifest: {len(data)} bytes  sha256={sha[:16]}…  chunks={len(chunks)}")

    topics: list[tuple[str, str]] = [
        (f"{base}/Applist",
         json.dumps({"value": [args.name]})),
        (f"{base}/Apps/{args.name}/info",
         json.dumps({"value": {"sha256": sha, "chunk_count": len(chunks)}})),
    ]
    for i, chunk in enumerate(chunks):
        topics.append((
            f"{base}/Apps/{args.name}/Chunks/{i}",
            json.dumps({"value": {"base64": chunk}}),
        ))

    for topic, payload in topics:
        client.publish(topic, payload, qos=0, retain=True).wait_for_publish(timeout=5)
        print(f"  published {topic} ({len(payload)}b)")

    client.loop_stop()
    client.disconnect()
    print(f"done — {len(topics)} topics published with retain=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
