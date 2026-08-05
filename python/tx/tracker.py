#!/usr/bin/env python3

class AircraftTracker:
    def __init__(self):
        self.aircraft_db = {}

    def update_from_sbs_line(self, line: bytes, now: float):
        """Parsing veloce della singola riga SBS ricevuta dal socket."""
        data = line.decode(errors="ignore").strip().split(",")

        if len(data) < 22 or data[0] != "MSG":
            return

        icao = data[4].strip()
        if not icao:
            return

        if icao not in self.aircraft_db:
            self.aircraft_db[icao] = {
                "last_eval": 0,
                "last_tx": 0,
                "last_full_tx": 0,
                "last_seen": now,
                "current_data": {},
                "last_sent_data": {},
            }

        self.aircraft_db[icao]["last_seen"] = now

        # Aggiorna i campi valorizzati
        for idx in range(len(data)):
            val = data[idx].strip()
            if val:
                self.aircraft_db[icao]["current_data"][idx] = val

    def cleanup_stale(self, now: float, timeout_sec: float = 60.0):
        """Rimuove dal DB gli aeromobili non più visti."""
        expired = [icao for icao, info in self.aircraft_db.items() if now - info["last_seen"] > timeout_sec]
        for icao in expired:
            del self.aircraft_db[icao]