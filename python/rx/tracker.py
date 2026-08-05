#!/usr/bin/env python3
from datetime import datetime, timedelta
from config import STRUCT_HEADER, FIELDS_DEF, TIMEOUT

class AircraftTracker:
    def __init__(self):
        self.aircraft = {}

    def parse_packet(self, header: bytes, payload: bytes):
        """Decodifica il flusso binario e mappa le proprietà dell'aeromobile."""
        _sync, _seq, mask, _length = STRUCT_HEADER.unpack(header)
        offset = 0
        data = {}

        for bit in range(16):
            if not (mask & (1 << bit)) or bit not in FIELDS_DEF:
                continue

            code, key, struct_obj = FIELDS_DEF[bit]
            size = struct_obj.size

            if offset + size > len(payload):
                return

            raw = payload[offset:offset + size]
            offset += size
            value = struct_obj.unpack(raw)[0]

            if code == "ICA": data["icao"] = f"{value:06X}"
            elif code == "CAL": data["callsign"] = value.decode(errors="ignore").strip("\x00 ")
            elif code == "ALT": data["alt"] = f"{value} ft"
            elif code == "VEL": data["speed"] = f"{value} kt"
            elif code == "DIR": data["heading"] = f"{value}°"
            elif code == "LAT": data["lat"] = value / 1e7
            elif code == "LON": data["lon"] = value / 1e7
            elif code == "VER": data["vertical"] = f"{value} fpm"
            elif code == "SQU": data["squawk"] = f"{value:04o}"
            elif code == "GRO": data["ground"] = "GND" if value else "AIR"
            elif code == "TIP": data["type"] = str(value)

        if "icao" not in data:
            return

        icao = data["icao"]
        if icao not in self.aircraft:
            self.aircraft[icao] = {}

        self.aircraft[icao].update(data)
        self.aircraft[icao]["last"] = datetime.now()

    def remove_old(self):
        """Pulisce i tracciati non più attivi via radio."""
        now = datetime.now()
        limit = timedelta(seconds=TIMEOUT)
        expired = [icao for icao, info in self.aircraft.items() if now - info["last"] > limit]
        for icao in expired:
            del self.aircraft[icao]