#!/usr/bin/env python3

import os
import struct
import sys
import zlib
from datetime import datetime, timedelta

import serial
import serial.tools.list_ports
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.align import Align

# =====================================================
# CONFIGURATION
# =====================================================

TIMEOUT = 150

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

    # Colori diagnostici
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

    # RIGA 1: Dati di volo (Altitudine, Velocità, Direzione)
    flight_data = []
    if "alt" in data: flight_data.append(f"▲ {data['alt']}")
    if "speed" in data: flight_data.append(f"► {data['speed']}")
    if "heading" in data: flight_data.append(f"∡ {data['heading']}")
    
    if flight_data:
        content.append(" | ".join(flight_data) + "\n", style="cyan")

    # RIGA 2: Posizione
    if "lat" in data and "lon" in data:
        content.append(f"⌖ {data['lat']:.5f}, {data['lon']:.5f}\n", style="bright_yellow")

    # RIGA 3: Dati tecnici (V/S, Squawk, Stato)
    tech_data = []
    if "vertical" in data: tech_data.append(f"↕ {data['vertical']}")
    if "squawk" in data: tech_data.append(f"SQK: {data['squawk']}")
    if "ground" in data: tech_data.append(f"[{data['ground']}]")
    
    if tech_data:
        content.append(" • ".join(tech_data) + "\n", style="magenta")

    # SPAZIATURA E TIMING
    # Aggiunge uno spazio vuoto solo se ci sono dati sopra, per staccare il timer
    if len(content) > 0:
        content.append("\n")
        
    content.append(f"⏱ {age}s ago", style=age_color)
    content.append(f"  (Rx: {last_rx})", style="dim white")

    # TITOLO DELLA SCHEDA (ICAO + IDENT)
    ident = data.get("callsign", "NO IDENT")
    card_title = f"✈ {icao} | {ident}"

    return Panel(
        content,
        title=card_title,
        title_align="left",
        border_style=border_color,
        padding=(1, 2), # Respiro interno alla scheda
        width=42 # Larghezza fissa per impaginazione ordinata, ma altezza fluida
    )

def build_ui():
    # Raccoglie le card solo degli aerei attivi
    cards = [
        build_aircraft_card(icao, aircraft[icao])
        for icao in aircraft_order
        if icao in aircraft
    ]

    # Layout principale
    if not cards:
        main_content = Panel(
            Text("\nIn attesa di pacchetti LoRa...\n", style="yellow", justify="center"), 
            border_style="dim"
        )
    else:
        # Usa Columns per distribuire automaticamente le schede nello schermo
        main_content = Columns(cards, expand=False, equal=True)

    # Header in alto
    header = Panel(
        Text(
            f"📡 RADAR LoRa TELEMETRY | TARGETS: {len(aircraft)}",
            justify="center",
            style="bold white on blue"
        )
    )
    
    return Group(header, "\n", main_content)

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
        ser = serial.Serial(port_name, 115200, timeout=0.1)
    except Exception as e:
        print(f"Errore: {e}")
        sys.exit(1)

    buffer = b""

    # Refresh screen 4 times a second
    with Live(build_ui(), refresh_per_second=4, screen=True) as live:
        while True:
            raw = ser.read(1024)

            if raw:
                buffer += raw

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

            remove_old()
            live.update(build_ui())

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTerminato.")