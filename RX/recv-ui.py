#!/usr/bin/env python3

import glob
import os
import select
import shutil
import sys
import termios
from datetime import datetime, timedelta

# Librerie per l'interfaccia
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# =====================================================
# CONFIGURATION
# =====================================================

TIMEOUT = 60

# Mappatura tra i prefissi inviati dal TX e le chiavi del database interno
# TX invia: ICA, CAL, ALT, VEL, DIR, LAT, LON, VER, SQU, GRO, TIP
FIELD_MAP = {
    "ICA": "icao",
    "CAL": "callsign",
    "ALT": "alt",
    "VEL": "speed",
    "DIR": "heading",
    "LAT": "lat",
    "LON": "lon",
    "VER": "vertical",
    "SQU": "squawk",
}

# =====================================================
# AIRCRAFT DATABASE
# =====================================================

aircraft = {}
aircraft_order = []


# =====================================================
# CUSTOM LORA PARSER
# =====================================================

def parse_custom_lora(message):
    """
    Parsa i messaggi ricevuti via LoRa nel formato:
    ICA=406A3D CAL=AZA123 ALT=30000 ...
    """
    parts = message.split()
    temp_data = {}

    # Estrae le coppie Chiave=Valore
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            temp_data[key] = value

    # L'ICAO è indispensabile per identificare l'aereo
    icao = temp_data.get("ICA")
    if not icao:
        return

    # Se è un nuovo aereo, inizializza il database
    if icao not in aircraft:
        aircraft_order.append(icao)
        aircraft[icao] = {
            "callsign": "-",
            "alt": "-",
            "speed": "-",
            "heading": "-",
            "lat": "-",
            "lon": "-",
            "vertical": "-",
            "squawk": "-",
            "last": datetime.now(),
        }

    plane = aircraft[icao]

    # Aggiorna i campi presenti nel messaggio ricevuto
    for short_key, dict_key in FIELD_MAP.items():
        if short_key in temp_data:
            plane[dict_key] = temp_data[short_key]

    # Aggiorna timestamp ultimo avvistamento
    plane["last"] = datetime.now()


# =====================================================
# REMOVE LOST AIRCRAFT
# =====================================================

def remove_old_aircraft():
    """Rimuove aerei non aggiornati da oltre TIMEOUT secondi."""
    now = datetime.now()
    expired = [
        icao for icao, data in aircraft.items()
        if now - data["last"] > timedelta(seconds=TIMEOUT)
    ]

    for icao in expired:
        del aircraft[icao]
        if icao in aircraft_order:
            aircraft_order.remove(icao)


# =====================================================
# AIRCRAFT CARD
# =====================================================

def aircraft_box(icao, data):
    """Crea un pannello grafico per ogni aereo."""
    age = int((datetime.now() - data["last"]).total_seconds())
    
    # Determina il colore in base all'anzianità del dato
    color = "green" if age < 10 else "yellow" if age < 30 else "red"

    text = Text()
    text.append(f"✈ {icao}\n", style="bold cyan")
    
    # Chiamata di volo o linea vuota
    callsign = data['callsign'] if data['callsign'] != "-" else "---"
    text.append(f"{callsign}\n", style="bold white")
    text.append("-" * 20 + "\n", style="dim")

    # Dati volo
    text.append(f"ALT   : {data['alt']} ft\n")
    text.append(f"SPEED : {data['speed']} kt\n")
    text.append(f"HEAD  : {data['heading']}°\n")
    text.append(f"V/R   : {data['vertical']}\n")
    text.append(f"POS   : {data['lat']}, {data['lon']}\n")
    text.append(f"SQUAWK: {data['squawk']}\n")
    
    text.append("\n")
    text.append(f"LAST  : {data['last'].strftime('%H:%M:%S')}\n", style="dim")
    text.append(f"AGE   : {age}s", style=color)

    return Panel(
        text,
        width=32,
        height=14,
        border_style=color,
    )


# =====================================================
# USER INTERFACE
# =====================================================

def build_ui():
    """Costruisce la UI dinamica per il terminale."""
    terminal_width = shutil.get_terminal_size().columns
    card_width = 34
    columns = max(1, terminal_width // card_width)

    header = Panel(
        Text(
            f"✈ ADS-B LoRa MONITOR | TARGETS: {len(aircraft)}",
            justify="center",
            style="bold green",
        ),
        height=3,
    )

    grid = Table.grid(padding=(0, 1))
    for _ in range(columns):
        grid.add_column(width=card_width)

    cards = [aircraft_box(icao, aircraft[icao]) for icao in aircraft_order if icao in aircraft]

    if not cards:
        return Group(
            header,
            Panel("In attesa di dati LoRa ADS-B...", border_style="yellow", expand=False)
        )

    for i in range(0, len(cards), columns):
        row = cards[i:i + columns]
        while len(row) < columns:
            row.append("")
        grid.add_row(*row)

    return Group(header, grid)


# =====================================================
# SERIAL PORT HANDLING
# =====================================================

def select_port():
    """Trova e seleziona la porta seriale corretta."""
    ports = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    if not ports:
        print("Errore: Nessuna porta seriale trovata (Heltec scollegata?)")
        sys.exit(1)

    print("\nPorte disponibili:")
    for i, port in enumerate(ports):
        print(f"{i}: {port}")

    while True:
        try:
            choice = int(input("\nSeleziona porta (0, 1...): "))
            return ports[choice]
        except (ValueError, IndexError):
            print("Scelta non valida.")


def open_serial(port):
    """Inizializza la porta seriale in modalità non-blocking."""
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    attrs[4] = termios.B115200 # ispeed
    attrs[5] = termios.B115200 # ospeed
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return fd


# =====================================================
# MAIN LOOP
# =====================================================

def main():
    port_name = select_port()
    fd = open_serial(port_name)
    
    print(f"Ricezione attiva su {port_name}...")
    buffer = b""

    with Live(build_ui(), refresh_per_second=4, screen=True) as live:
        while True:
            # Monitora la seriale per nuovi dati
            r, _, _ = select.select([fd], [], [], 0.5)
            
            if fd in r:
                new_data = os.read(fd, 2048)
                buffer += new_data
                
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    message = line.decode(errors="ignore").strip()
                    if message:
                        parse_custom_lora(message)

            remove_old_aircraft()
            live.update(build_ui())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nChiusura...")
        sys.exit(0)