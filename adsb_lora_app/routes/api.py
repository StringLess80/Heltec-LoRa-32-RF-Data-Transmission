#!/usr/bin/env python3
import time
import uuid
from flask import Blueprint, render_template, request, jsonify
from core.state import system_state
from core.config_manager import save_config_to_file
import services.serial_service as ser_srv

api_bp = Blueprint('api', __name__)

@api_bp.route('/')
def index():
    return render_template('index.html')

@api_bp.route('/api/list_serial_ports', methods=['GET'])
def list_ports_api():
    return jsonify({"ports": ser_srv.get_clean_serial_ports()})

@api_bp.route('/api/connect_gps', methods=['POST'])
def connect_gps():
    data = request.json or {}
    port = data.get("port")
    baud = int(data.get("baud", 9600))

    if not port or port == "DISCONNECT":
        if ser_srv.ser_gps_device and ser_srv.ser_gps_device.is_open:
            ser_srv.ser_gps_device.close()
        system_state["gps_serial_status"] = {"connected": False, "port": "Nessuna", "baud": baud}
        system_state["gps"]["connected"] = False
        save_config_to_file()
        return jsonify({"status": "disconnected"})

    if ser_srv.open_gps_serial(port, baud):
        save_config_to_file()
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "error", "message": f"Impossibile aprire {port}"})

@api_bp.route('/api/connect_heltec', methods=['POST'])
def connect_heltec():
    data = request.json or {}
    port = data.get("port")
    baud = int(data.get("baud", 115200))

    if not port or port == "DISCONNECT":
        if ser_srv.ser_lora_device and ser_srv.ser_lora_device.is_open:
            ser_srv.ser_lora_device.close()
        system_state["serial_status"] = {"connected": False, "port": "Nessuna", "baud": baud}
        save_config_to_file()
        return jsonify({"status": "disconnected"})

    if ser_srv.open_heltec_serial(port, baud):
        save_config_to_file()
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "error", "message": f"Impossibile aprire {port}"})

@api_bp.route('/api/toggle_tx', methods=['POST'])
def toggle_tx():
    system_state["tx_active"] = not system_state["tx_active"]
    if not system_state["tx_active"]:
        system_state["rf_stats"]["packets_sec"] = 0.0
        system_state["rf_stats"]["airtime_util"] = 0.0
        system_state["rf_stats"]["payload_bitrate"] = "0.00 KB/s"
    return jsonify({"status": "success", "tx_active": system_state["tx_active"]})

@api_bp.route('/api/set_aircraft_timeout', methods=['POST'])
def set_aircraft_timeout():
    data = request.json or {}
    try:
        timeout = int(data.get("timeout", 60))
        system_state["aircraft_timeout_sec"] = max(5, min(600, timeout))
        save_config_to_file()
        return jsonify({"status": "success", "timeout": system_state["aircraft_timeout_sec"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@api_bp.route('/api/update_reference', methods=['POST'])
def update_reference():
    data = request.json or {}
    name = str(data.get("name", "POINT_ALPHA")).strip() or "POINT_ALPHA"
    try: lat = float(data.get("lat", 45.4642))
    except (ValueError, TypeError): lat = 45.4642
    try: lon = float(data.get("lon", 9.1901))
    except (ValueError, TypeError): lon = 9.1901

    system_state["reference_datum"] = {"name": name, "lat": lat, "lon": lon}
    save_config_to_file()
    return jsonify({"status": "success", "reference": system_state["reference_datum"]})

@api_bp.route('/api/use_current_gps_ref', methods=['POST'])
def use_current_gps_ref():
    if system_state["gps"]["connected"]:
        system_state["reference_datum"]["lat"] = system_state["gps"]["lat"]
        system_state["reference_datum"]["lon"] = system_state["gps"]["lon"]
        save_config_to_file()
    return jsonify({"status": "success", "reference": system_state["reference_datum"]})

@api_bp.route('/api/add_controller', methods=['POST'])
def add_controller():
    data = request.json or {}
    name = str(data.get('name', 'STINGER_UNIT_ALPHA')).strip() or 'STINGER_UNIT_ALPHA'
    try: lat = float(data.get('lat', 45.47))
    except (ValueError, TypeError): lat = 45.47
    try: lon = float(data.get('lon', 9.20))
    except (ValueError, TypeError): lon = 9.20
    try: zenith_blind_angle = float(data.get('zenith_blind_angle', 30.0))
    except (ValueError, TypeError): zenith_blind_angle = 30.0
    try: radius_km = float(data.get('radius_km', 8.0))
    except (ValueError, TypeError): radius_km = 8.0
    try: cone_height_km = float(data.get('cone_height_km', 3.8))
    except (ValueError, TypeError): cone_height_km = 3.8
    try: min_range_km = float(data.get('min_range_km', 0.2))
    except (ValueError, TypeError): min_range_km = 0.2

    new_ctrl = {
        'id': str(uuid.uuid4())[:8],
        'name': name,
        'lat': lat,
        'lon': lon,
        'unit_type': 'MANPADS_STINGER',
        'zenith_blind_angle': zenith_blind_angle,
        'radius_km': radius_km,
        'cone_height_km': cone_height_km,
        'min_range_km': min_range_km
    }

    system_state['controllers'].append(new_ctrl)
    save_config_to_file()
    return jsonify({'status': 'success', 'controller': new_ctrl})

@api_bp.route('/api/delete_controller', methods=['POST'])
def delete_controller():
    data = request.json or {}
    target_id = str(data.get("id", "")).strip()
    system_state["controllers"] = [c for c in system_state["controllers"] if str(c.get("id")) != target_id]
    save_config_to_file()
    return jsonify({"status": "success", "controllers": system_state["controllers"]})