#!/usr/bin/env python3
"""
ADS-B LoRa Radar Dashboard
===================================================
"""

import math
import os
import struct
import sys
import time
import zlib
from datetime import datetime, timedelta

import serial
import serial.tools.list_ports
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty

# =====================================================================
# CONFIGURAZIONE
# =====================================================================
TIMEOUT = 45  # Timeout di rimozione bersaglio silente (secondi)

# Coordinate geografiche del ricevitore per il calcolo della distanza
HOME_LAT = 44.473328
HOME_LON = 11.382953

SYNC = b"\x55\xAA"
HEADER_SIZE = 7

# Strutture di decodifica fisse per eliminare l'overhead a runtime
STRUCT_HEADER = struct.Struct("<HHHB")
FIELDS_DEF = {
    0: ("ICA", "icao", struct.Struct("<I")),
    1: ("CAL", "callsign", struct.Struct("8s")),
    2: ("ALT", "alt", struct.Struct("<H")),
    3: ("VEL", "speed", struct.Struct("<H")),
    4: ("DIR", "heading", struct.Struct("<H")),
    5: ("LAT", "lat", struct.Struct("<i")),
    6: ("LON", "lon", struct.Struct("<i")),
    7: ("VER", "vertical", struct.Struct("<h")),
    8: ("SQU", "squawk", struct.Struct("<H")),
    9: ("GRO", "ground", struct.Struct("<B")),
    10: ("TIP", "type", struct.Struct("<B")),
}

aircraft = {}
console = Console()


class NonBlockingInput:
    """Gestione dell'input per terminale senza attese."""
    def __init__(self):
        self.is_windows = os.name == "nt"
        if not self.is_windows:
            self.fd = sys.stdin.fileno()
            self.old_settings = None

    def __enter__(self):
        if not self.is_windows:
            try:
                self.old_settings = termios.tcgetattr(self.fd)
                tty.setcbreak(self.fd)
            except Exception:
                pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.is_windows and self.old_settings is not None:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
            except Exception:
                pass

    def get_key(self):
        return self._get_key_windows() if self.is_windows else self._get_key_unix()

    def _get_key_windows(self):
        if not msvcrt.kbhit():
            return None
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            if ch2 == b"H": return "up"
            if ch2 == b"P": return "down"
        elif ch.lower() in (b"w", b"k"): return "up"
        elif ch.lower() in (b"s", b"j"): return "down"
        elif ch.lower() == b"q" or ch == b"\x03": return "exit"
        return None

    def _get_key_unix(self):
        r, _, _ = select.select([sys.stdin], [], [], 0)
        if not r:
            return None
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            r2, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r2:
                seq = sys.stdin.read(2)
                if seq == "[A": return "up"
                if seq == "[B": return "down"
        elif ch.lower() in ("w", "k"): return "up"
        elif ch.lower() in ("s", "j"): return "down"
        elif ch.lower() == "q" or ch == "\x03": return "exit"
        return None


def calculate_distance(lat1, lon1, lat2, lon2):
    """Calcola la distanza in km (Formula di Haversine) tra due punti."""
    rad_lat1, rad_lat2 = math.radians(lat1), math.radians(lat2)
    dlat = rad_lat2 - rad_lat1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(rad_lat1) * math.cos(rad_lat2) * math.sin(dlon / 2)**2
    return 6371.0 * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def parse_packet(header, payload):
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
    if icao not in aircraft:
        aircraft[icao] = {}

    aircraft[icao].update(data)
    aircraft[icao]["last"] = datetime.now()


def remove_old():
    """Pulisce i tracciati non più attivi via radio."""
    now = datetime.now()
    limit = timedelta(seconds=TIMEOUT)
    expired = [icao for icao, info in aircraft.items() if now - info["last"] > limit]
    for icao in expired:
        del aircraft[icao]


def build_aircraft_card(icao, data):
    """Costruisce il widget visivo dell'aeromobile."""
    age = int((datetime.now() - data["last"]).total_seconds())
    last_rx = data["last"].strftime("%H:%M:%S")

    if age < 5:
        border, age_style = "green", "bold bright_green"
    elif age < 15:
        border, age_style = "yellow", "bold bright_yellow"
    else:
        border, age_style = "red", "bold dim red"

    content = Text()
    flight_data = []
    if "alt" in data: flight_data.append(f"▲ {data['alt']}")
    if "speed" in data: flight_data.append(f"► {data['speed']}")
    if "heading" in data: flight_data.append(f"∡ {data['heading']}")

    if flight_data:
        content.append(" | ".join(flight_data) + "\n", style="cyan")

    # Mostra coordinate GPS e calcolo immediato distanza
    if "lat" in data and "lon" in data:
        dist = calculate_distance(HOME_LAT, HOME_LON, data["lat"], data["lon"])
        content.append(f"⌖ {data['lat']:.5f}, {data['lon']:.5f} ", style="bright_yellow")
        content.append(f"({dist:.1f} km)\n", style="bold white on red")
        data["_distance"] = dist  # Memorizza per ordinamento dinamico
    else:
        data["_distance"] = float("inf")  # Manda in fondo se senza coordinate

    tech_data = []
    if "vertical" in data: tech_data.append(f"↕ {data['vertical']}")
    if "squawk" in data: tech_data.append(f"SQK: {data['squawk']}")
    if "ground" in data: tech_data.append(f"[{data['ground']}]")

    if tech_data:
        content.append(" • ".join(tech_data) + "\n", style="magenta")

    if len(content) > 0:
        content.append("\n")

    content.append(f"⏱ {age}s ago", style=age_style)
    content.append(f"  (Rx: {last_rx})", style="dim white")

    ident = data.get("callsign", "NO IDENT")
    return Panel(content, title=f"✈ {icao} | {ident}", title_align="left", border_style=border, padding=(1, 2), width=44)


def build_ui(term_width, term_height, row_offset):
    """Genera la vista completa del radar con ordinamento per distanza."""
    # Ordina i tracciati in base alla distanza calcolata (o ICAO se non disponibile)
    sorted_icaos = sorted(aircraft.keys(), key=lambda k: (aircraft[k].get("_distance", float("inf")), k))
    cards = [build_aircraft_card(icao, aircraft[icao]) for icao in sorted_icaos]

    cols = max(1, term_width // 46)
    grid_rows = [cards[i:i + cols] for i in range(0, len(cards), cols)]
    total_rows = len(grid_rows)
    max_visible_rows = max(1, (term_height - 6) // 9)

    max_offset = max(0, total_rows - max_visible_rows)
    row_offset = max(0, min(row_offset, max_offset))
    visible_rows = grid_rows[row_offset:row_offset + max_visible_rows]

    if not cards:
        main_content = Panel(Text("\nIn attesa di tracciati radar LoRa...\n", style="yellow", justify="center"), border_style="dim")
    else:
        elements = []
        for row in visible_rows:
            elements.append(Columns(row, expand=False, equal=True))
            elements.append("")
        if elements: elements.pop()
        main_content = Group(*elements)

    scroll = f" | ROW {row_offset + 1}/{total_rows} (Frecce/WS per scorrere)" if total_rows > max_visible_rows else ""
    header = Panel(Text(f"📡 RADAR LoRa TELEMETRY | ATTIVI: {len(aircraft)}{scroll}", justify="center", style="bold white on blue"))
    return Group(header, "\n", main_content), row_offset


def main():
    ports = [p for p in serial.tools.list_ports.comports() if p.device.startswith(("/dev/ttyUSB", "/dev/ttyACM", "COM"))]
    if not ports:
        print("Nessuna porta seriale trovata.")
        sys.exit(1)

    if len(ports) == 1:
        port_name = ports[0].device
        print(f"Uso automatico: {port_name}")
    else:
        print("\nPorte disponibili:")
        for i, port in enumerate(ports):
            print(f"[{i}] {port.device} - {port.description}")

        port_name = None
        while port_name is None:
            try:
                choice = int(input("\nSeleziona porta RX: "))
                port_name = ports[choice].device
            except (ValueError, IndexError):
                print("Scelta non valida.")

    try:
        ser = serial.Serial(port_name, 115200, timeout=0)
    except Exception as exc:
        print(f"Errore connessione: {exc}")
        sys.exit(1)

    buffer = b""
    row_offset = 0
    last_ui_update = 0.0
    ui_update_interval = 0.1

    with NonBlockingInput() as key_in:
        init_ui, row_offset = build_ui(console.size.width, console.size.height, row_offset)
        with Live(init_ui, console=console, screen=True, auto_refresh=False) as live:
            while True:
                now = time.time()
                data_received, key_pressed = False, False

                raw = ser.read(2048)
                if raw:
                    buffer += raw
                    data_received = True

                    while True:
                        idx = buffer.find(SYNC)
                        if idx < 0:
                            buffer = buffer[-1:]
                            break

                        buffer = buffer[idx:]
                        if len(buffer) < HEADER_SIZE:
                            break

                        length = buffer[6]
                        total = HEADER_SIZE + length + 2

                        if len(buffer) < total:
                            break

                        packet = buffer[:total]
                        buffer = buffer[total:]

                        header = packet[:HEADER_SIZE]
                        payload = packet[HEADER_SIZE:-2]
                        crc_rx = struct.unpack("<H", packet[-2:])[0]

                        if (zlib.crc32(header + payload) & 0xFFFF) == crc_rx:
                            parse_packet(header, payload)
                        else:
                            buffer = packet[2:] + buffer

                    if len(buffer) > 4096:
                        buffer = buffer[-4096:]

                key = key_in.get_key()
                if key == "up":
                    row_offset = max(0, row_offset - 1)
                    key_pressed = True
                elif key == "down":
                    row_offset += 1
                    key_pressed = True
                elif key == "exit":
                    break

                remove_old()

                # Refresh della TUI (pacing controllato a 100ms per stabilità grafica)
                if key_pressed or (data_received and (now - last_ui_update > ui_update_interval)):
                    ui_grid, row_offset = build_ui(console.size.width, console.size.height, row_offset)
                    live.update(ui_grid)
                    live.refresh()
                    last_ui_update = now

                if not raw and not key:
                    time.sleep(0.01)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass