#!/usr/bin/env python3

DEFAULT_BAUDRATE = 115200

DEFAULT_REFERENCE = {
    "name": "POINT_ALPHA",
    "lat": 45.4642,
    "lon": 9.1901
}

system_state = {
    "tx_active": False,
    "dump1090_connected": False,
    "aircraft_timeout_sec": 60,
    "serial_status": {
        "connected": False,
        "port": "Nessuna",
        "baud": DEFAULT_BAUDRATE
    },
    "gps_serial_status": {
        "connected": False,
        "port": "Nessuna",
        "baud": 9600
    },
    "gps": {
        "connected": False,
        "fix": "No Fix / Disconnesso",
        "lat": 0.0,
        "lon": 0.0,
        "alt": 0.0,
        "satellites": 0,
        "utc": "--:--:-- UTC"
    },
    "reference_datum": DEFAULT_REFERENCE.copy(),
    "controllers": [],
    "rf_stats": {
        "packets_sec": 0.0,
        "airtime_util": 0.0,
        "payload_bitrate": "0.00 KB/s",
        "rf_config": "868MHz | SF7 | BW125",
        "tx_power": "+14 dBm (25 mW)"
    }
}

aircraft_db = {}