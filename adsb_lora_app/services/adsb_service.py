#!/usr/bin/env python3
import select
import socket
import time
from collections import deque
from core.state import system_state, aircraft_db
from core.math_tactical import assign_aircraft_to_controller
from protocol.lora_encoder import ACTIVE_FIELDS, encode_packet
import services.serial_service as ser_srv

SBS_HOST = "127.0.0.1"
SBS_PORT = 30003
MIN_INTERVAL_PER_AIRCRAFT = 0.5
LORA_TX_AIRTIME_DELAY = 0.05
FULL_FRAME_INTERVAL = 5.0
THRESHOLDS = {"ALT": 50, "VEL": 5, "DIR": 3, "LAT": 0.002, "LON": 0.002, "VER": 150}

def evaluate_semantic_payload(ac_info, now):
    if now - ac_info["last_full_tx"] >= FULL_FRAME_INTERVAL:
        return ACTIVE_FIELDS, "FULL"
    fields_to_send = []
    has_changes = False
    curr_data = ac_info["current_data"]
    last_sent = ac_info["last_sent_data"]

    for field in ACTIVE_FIELDS:
        _, index, code, _, _ = field
        if code == "ICA":
            fields_to_send.append(field)
            continue
        curr_val = curr_data.get(index, "")
        if curr_val == "": continue
        last_val = last_sent.get(index, "")
        if last_val == "":
            fields_to_send.append(field)
            has_changes = True
            continue
        try:
            if code in THRESHOLDS:
                if abs(float(curr_val) - float(last_val)) >= THRESHOLDS[code]:
                    fields_to_send.append(field)
                    has_changes = True
            elif curr_val != last_val:
                fields_to_send.append(field)
                has_changes = True
        except ValueError: pass

    if has_changes: return fields_to_send, "DELTA"
    return None, "NONE"

def adsb_worker(socketio):
    buffer = b""
    tx_queue = deque(maxlen=30)
    last_tx_time = 0
    pkt_count = 0
    total_bytes_sent = 0
    last_stats = time.time()
    last_reconnect_dump = 0
    sock = None

    while True:
        now = time.time()
        
        if not system_state["gps"]["connected"]:
            system_state["gps"]["utc"] = time.strftime("%H:%M:%S UTC", time.gmtime())

        if sock is None and (now - last_reconnect_dump > 3.0):
            last_reconnect_dump = now
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((SBS_HOST, SBS_PORT))
                sock.setblocking(False)
                system_state["dump1090_connected"] = True
            except Exception:
                sock = None
                system_state["dump1090_connected"] = False

        if sock:
            try:
                ready, _, _ = select.select([sock], [], [], 0.005)
                if ready:
                    raw = sock.recv(8192)
                    if raw: buffer += raw
                    else:
                        sock.close()
                        sock = None
                        system_state["dump1090_connected"] = False
            except Exception:
                sock = None
                system_state["dump1090_connected"] = False

        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            data = line.decode(errors="ignore").strip().split(",")
            if len(data) < 22 or data[0] != "MSG": continue
            icao = data[4].strip()
            if not icao: continue

            if icao not in aircraft_db:
                aircraft_db[icao] = {
                    "icao": icao, "last_eval": 0, "last_tx": 0, "last_full_tx": 0,
                    "last_seen": now, "current_data": {}, "last_sent_data": {},
                    "assigned_ctrl": None, "in_blind_cone": False
                }
            ac = aircraft_db[icao]
            ac["last_seen"] = now
            for idx in range(len(data)):
                val = data[idx].strip()
                if val: ac["current_data"][idx] = val

        timeout_sec = system_state.get("aircraft_timeout_sec", 60)
        expired = [k for k, v in aircraft_db.items() if now - v["last_seen"] > timeout_sec]
        for k in expired: del aircraft_db[k]

        for icao, ac in aircraft_db.items():
            try:
                lat = float(ac["current_data"].get(14, 0))
                lon = float(ac["current_data"].get(15, 0))
                alt = float(ac["current_data"].get(11, 10000))
                if lat != 0 and lon != 0:
                    ctrl_id, in_cone = assign_aircraft_to_controller(lat, lon, alt)
                    ac["assigned_ctrl"] = ctrl_id
                    ac["in_blind_cone"] = in_cone
            except ValueError: pass

            if now - ac["last_eval"] >= MIN_INTERVAL_PER_AIRCRAFT:
                ac["last_eval"] = now
                fields_to_send, frame_type = evaluate_semantic_payload(ac, now)
                if fields_to_send and frame_type != "NONE":
                    res = encode_packet(ac["current_data"], fields_to_send)
                    if res:
                        packet, mask = res
                        tx_queue.append((packet, icao, frame_type, mask))
                        if frame_type == "FULL": ac["last_full_tx"] = now

        if system_state["tx_active"] and tx_queue and (now - last_tx_time >= LORA_TX_AIRTIME_DELAY):
            packet, p_icao, p_type, p_mask = tx_queue.popleft()
            
            if ser_srv.ser_lora_device and ser_srv.ser_lora_device.is_open:
                try:
                    ser_srv.ser_lora_device.write(packet)
                    ser_srv.ser_lora_device.flush()
                except Exception: pass
            
            last_tx_time = now
            pkt_count += 1
            total_bytes_sent += len(packet)

        elapsed_stats = now - last_stats
        if elapsed_stats >= 1.0:
            pps = round(pkt_count / elapsed_stats, 1) if system_state["tx_active"] else 0.0
            airtime = round((pps * 0.042) * 100, 1) if system_state["tx_active"] else 0.0
            bitrate_kb = round((total_bytes_sent / elapsed_stats) / 1024.0, 2) if system_state["tx_active"] else 0.0
            
            system_state["rf_stats"]["packets_sec"] = pps
            system_state["rf_stats"]["airtime_util"] = min(100.0, airtime)
            system_state["rf_stats"]["payload_bitrate"] = f"{bitrate_kb} KB/s"
            
            pkt_count = 0
            total_bytes_sent = 0
            last_stats = now

        for c in system_state["controllers"]:
            c["active_assigned"] = sum(1 for a in aircraft_db.values() if a.get("assigned_ctrl") == c["id"])

        socketio.emit('telemetry_update', {
            "system": system_state,
            "aircraft": list(aircraft_db.values())
        })
        time.sleep(0.08)