#!/usr/bin/env python3
import json
import os
from core.state import system_state, DEFAULT_REFERENCE

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

def save_config_to_file():
    cfg = {
        "reference_datum": system_state.get("reference_datum", DEFAULT_REFERENCE),
        "controllers": system_state.get("controllers", []),
        "aircraft_timeout_sec": int(system_state.get("aircraft_timeout_sec", 60)),
        "gps_serial_status": system_state.get("gps_serial_status", {}),
        "heltec_serial_status": system_state.get("serial_status", {})
    }
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        print(f"[CONFIG SUCCESS] Scritto file '{CONFIG_FILE}' | Timeout: {system_state['aircraft_timeout_sec']}s")
    except Exception as e:
        print(f"[ERR CONFIG CRITICAL] Impossibile salvare config: {e}")

def load_config_from_file():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                ref = cfg.get("reference_datum")
                if isinstance(ref, dict) and "name" in ref and "lat" in ref and "lon" in ref:
                    system_state["reference_datum"] = ref
                else:
                    system_state["reference_datum"] = DEFAULT_REFERENCE.copy()

                ctrls = cfg.get("controllers")
                system_state["controllers"] = ctrls if isinstance(ctrls, list) else []
                system_state["aircraft_timeout_sec"] = int(cfg.get("aircraft_timeout_sec", 60))
        except Exception as e:
            print(f"[ERR CONFIG READ] {e}. Rigenero default.")
            system_state["reference_datum"] = DEFAULT_REFERENCE.copy()
            system_state["controllers"] = []
            system_state["aircraft_timeout_sec"] = 60
            save_config_to_file()
    else:
        system_state["reference_datum"] = DEFAULT_REFERENCE.copy()
        system_state["controllers"] = []
        system_state["aircraft_timeout_sec"] = 60
        save_config_to_file()