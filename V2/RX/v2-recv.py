#!/usr/bin/env python3

import os
import struct
import sys
import time
import zlib
from datetime import datetime, timedelta

import serial
import serial.tools.list_ports
from rich.console import Group, Console
from rich.live import Live
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text

# Import specifici per l'input non bloccante su diverse piattaforme
if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty

# =====================================================
# CONFIGURATION
# =====================================================

TIMEOUT = 60

SYNC = b"\x55\xAA"
HEADER_SIZE = 7

# =====================================================
# FIELD MAP
# =====================================================

FIELDS_DEF = {
    0: ("ICA", "icao", "<I", 4),
    1: ("CAL", "callsign", "8s", 8),
    2: ("ALT", "alt", "<H", 2),
    3: ("VEL", "speed", "<H", 2),
    4: ("DIR", "heading", "<H", 2),
    5: ("LAT", "lat", "<i", 4),
    6: ("LON", "lon", "<i", 4),
    7: ("VER", "vertical", "<h", 2),
    8: ("SQU", "squawk", "<H", 2),
    9: ("GRO", "ground", "<B", 1),
    10: ("TIP", "type", "<B", 1),
}

aircraft = {}
aircraft_order = []

console = Console()


class NonBlockingInput:
    """Gestisce la cattura dei tasti in modo non bloccante e immediato."""
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
        if self.is_windows:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch in (b"\x00", b"\xe0"):  # Tasti freccia
                    ch2 = msvcrt.getch()
                    if ch2 == b"H":
                        return "up"
                    elif ch2 == b"P":
                        return "down"
                elif ch.lower() in (b"w", b"k"):
                    return "up"
                elif ch.lower() in (b"s", b"j"):
                    return "down"
                elif ch.lower() == b"q" or ch == b"\x03":
                    return "exit"
        else:
            rlist, _, _ = select.select([sys.stdin], [], [], 0)
            if rlist:
                ch = sys.stdin.read(1)
                if ch == "\x1b":  # Sequenze di escape (es. frecce)
                    r2, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if r2:
                        seq = sys.stdin.read(2)
                        if seq == "[A":
                            return "up"
                        elif seq == "[B":
                            return "down"
                elif ch.lower() in ("w", "k"):
                    return "up"
                elif ch.lower() in ("s", "j"):
                    return "down"
                elif ch.lower() == "q" or ch == "\x03":
                    return "exit"
        return None


def parse_packet(header, payload):
    _sync, _seq, mask, _length = struct.unpack("<HHHB", header)

    offset = 0
    data = {}

    for bit in range(16):
        if not (mask & (1 << bit)):
            continue

        if bit not in FIELDS_DEF:
            continue

        code, key, fmt, size = FIELDS_DEF[bit]

        if offset + size > len(payload):
            return

        raw = payload[offset:offset + size]
        offset += size

        value = struct.unpack(fmt, raw)[0]

        if code == "ICA":
            data["icao"] = f"{value:06X}"

        elif code == "CAL":
            data["callsign"] = value.decode(errors="ignore").strip("\x00 ")

        elif code == "ALT":
            data["alt"] = f"{value} ft"

        elif code == "VEL":
            data["speed"] = f"{value} kt"

        elif code == "DIR":
            data["heading"] = f"{value}°"

        elif code == "LAT":
            data["lat"] = value / 1e7

        elif code == "LON":
            data["lon"] = value / 1e7

        elif code == "VER":
            data["vertical"] = f"{value} fpm"

        elif code == "SQU":
            data["squawk"] = f"{value:04o}"

        elif code == "GRO":
            data["ground"] = "GND" if value else "AIR"

        elif code == "TIP":
            data["type"] = str(value)

    if "icao" not in data:
        return

    icao = data["icao"]

    if icao not in aircraft:
        aircraft_order.append(icao)
        aircraft[icao] = {}

    aircraft[icao].update(data)
    aircraft[icao]["last"] = datetime.now()


def remove_old():
    now = datetime.now()
    expired = [
        icao for icao, d in aircraft.items()
        if now - d["last"] > timedelta(seconds=TIMEOUT)
    ]
    for icao in expired:
        del aircraft[icao]
        if icao in aircraft_order:
            aircraft_order.remove(icao)

# =====================================================
# UI - DESIGN RINNOVATO
# =====================================================

def build_aircraft_card(icao, data):
    age = int((datetime.now() - data["last"]).total_seconds())
    last_rx = data["last"].strftime("%H:%M:%S")

    if age < 15:
        border_color = "green"
        age_color = "bold bright_green"
    elif age < 60:
        border_color = "yellow"
        age_color = "bold bright_yellow"
    else:
        border_color = "red"
        age_color = "bold dim red"

    content = Text()

    flight_data = []
    if "alt" in data: flight_data.append(f"▲ {data['alt']}")
    if "speed" in data: flight_data.append(f"► {data['speed']}")
    if "heading" in data: flight_data.append(f"∡ {data['heading']}")
    
    if flight_data:
        content.append(" | ".join(flight_data) + "\n", style="cyan")

    if "lat" in data and "lon" in data:
        content.append(f"⌖ {data['lat']:.5f}, {data['lon']:.5f}\n", style="bright_yellow")

    tech_data = []
    if "vertical" in data: tech_data.append(f"↕ {data['vertical']}")
    if "squawk" in data: tech_data.append(f"SQK: {data['squawk']}")
    if "ground" in data: tech_data.append(f"[{data['ground']}]")
    
    if tech_data:
        content.append(" • ".join(tech_data) + "\n", style="magenta")

    if len(content) > 0:
        content.append("\n")
        
    content.append(f"⏱ {age}s ago", style=age_color)
    content.append(f"  (Rx: {last_rx})", style="dim white")

    ident = data.get("callsign", "NO IDENT")
    card_title = f"✈ {icao} | {ident}"

    return Panel(
        content,
        title=card_title,
        title_align="left",
        border_style=border_color,
        padding=(1, 2),
        width=42
    )


def build_ui(term_width, term_height, row_offset):
    cards = [
        build_aircraft_card(icao, aircraft[icao])
        for icao in aircraft_order
        if icao in aircraft
    ]

    card_width = 42
    col_spacing = 2
    cols = max(1, term_width // (card_width + col_spacing))

    grid_rows = [cards[i : i + cols] for i in range(0, len(cards), cols)]
    total_rows = len(grid_rows)

    row_height = 9
    usable_height = max(1, term_height - 6)
    max_visible_rows = max(1, usable_height // row_height)

    max_offset = max(0, total_rows - max_visible_rows)
    row_offset = min(row_offset, max_offset)
    row_offset = max(0, row_offset)

    visible_rows = grid_rows[row_offset : row_offset + max_visible_rows]

    if not cards:
        main_content = Panel(
            Text("\nIn attesa di pacchetti LoRa...\n", style="yellow", justify="center"), 
            border_style="dim"
        )
    else:
        row_elements = []
        for r in visible_rows:
            row_elements.append(Columns(r, expand=False, equal=True))
            row_elements.append("")
        
        if row_elements:
            row_elements.pop()
        main_content = Group(*row_elements)

    scroll_status = ""
    if total_rows > max_visible_rows:
        scroll_status = f" | ROW {row_offset + 1}/{total_rows} (Frecce o W/S per scorrere)"

    header = Panel(
        Text(
            f"📡 RADAR LoRa TELEMETRY | TARGETS: {len(aircraft)}{scroll_status}",
            justify="center",
            style="bold white on blue"
        )
    )
    
    return Group(header, "\n", main_content), row_offset

# =====================================================
# MAIN LOOP
# =====================================================

def main():
    ports = [
        p for p in serial.tools.list_ports.comports()
        if p.device.startswith(("/dev/ttyUSB", "/dev/ttyACM", "COM"))
    ]

    if not ports:
        print("Nessuna porta seriale trovata.")
        sys.exit(1)

    if len(ports) == 1:
        port_name = ports[0].device
        print(f"Uso automaticamente {port_name}")
    else:
        print("\nPorte disponibili:")
        for i, p in enumerate(ports):
            print(f"[{i}] {p.device} - {p.description}")

        try:
            choice = int(input("\nSeleziona il numero della porta RX: "))
            port_name = ports[choice].device
        except (ValueError, IndexError):
            sys.exit(1)

    try:
        # timeout=0 rende la lettura seriale completamente non-bloccante
        ser = serial.Serial(port_name, 115200, timeout=0)
    except Exception as e:
        print(f"Errore: {e}")
        sys.exit(1)

    buffer = b""
    row_offset = 0
    last_ui_update = 0.0
    ui_update_interval = 0.1  # Aggiorna i dati sulla UI massimo ogni 100ms per evitare sfarfallii

    with NonBlockingInput() as key_in:
        initial_ui, row_offset = build_ui(console.size.width, console.size.height, row_offset)
        with Live(initial_ui, console=console, screen=True, auto_refresh=False) as live:
            while True:
                now = time.time()
                data_received = False
                key_pressed = False

                # 1. Lettura seriale immediata (non bloccante)
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

                        if (zlib.crc32(payload) & 0xFFFF) == crc_rx:
                            parse_packet(header, payload)

                # 2. Controllo tastiera immediato
                key = key_in.get_key()
                if key == "up":
                    row_offset = max(0, row_offset - 1)
                    key_pressed = True
                elif key == "down":
                    row_offset += 1
                    key_pressed = True
                elif key == "exit":
                    break

                # Periodico controllo scadenze (es. ogni secondo)
                remove_old()

                # 3. Rendering dinamico e intelligente
                # Se l'utente preme un tasto l'aggiornamento è ISTANTANEO (reattività massima).
                # Se arrivano nuovi dati, aggiorna l'interfaccia a intervalli regolari.
                if key_pressed or (data_received and (now - last_ui_update > ui_update_interval)):
                    ui_grid, row_offset = build_ui(console.size.width, console.size.height, row_offset)
                    live.update(ui_grid)
                    live.refresh()
                    last_ui_update = now

                # 4. Sleep minimo per evitare di consumare il 100% della CPU se inattivo
                if not raw and not key:
                    time.sleep(0.01)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTerminato.")