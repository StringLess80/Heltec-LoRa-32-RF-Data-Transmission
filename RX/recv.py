#!/usr/bin/env python3

import glob
import os
import select
import shutil
import sys
import termios
from datetime import datetime, timedelta

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# =====================================================
# CONFIGURATION
# =====================================================
TIMEOUT = 300  # Aumentato a 5 minuti per evitare che l'aereo sparisca a 60s
FIELD_MAP = {
    "ICA": ("ICAO", "icao"),
    "CAL": ("CALLSIGN", "callsign"),
    "ALT": ("ALTITUDE", "alt"),
    "VEL": ("SPEED", "speed"),
    "DIR": ("HEADING", "heading"),
    "LAT": ("LATITUDE", "lat"),
    "LON": ("LONGITUDE", "lon"),
    "VER": ("VERT RATE", "vertical"),
    "SQU": ("SQUAWK", "squawk"),
    "GRO": ("GROUND", "ground"),
    "TIP": ("MSG TYPE", "type"),
}

aircraft = {}
aircraft_order = []
active_fields = [] 

def parse_lora(message):
    global active_fields
    if message.startswith("CFG:"):
        active_fields = message.replace("CFG:", "").split(",")
        return

    parts = message.split()
    temp_data = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            temp_data[k] = v

    icao = temp_data.get("ICA")
    if not icao: return

    if icao not in aircraft:
        aircraft_order.append(icao)
        aircraft[icao] = {f[1]: "-" for f in FIELD_MAP.values()}
    
    for k, v in temp_data.items():
        if k in FIELD_MAP:
            aircraft[icao][FIELD_MAP[k][1]] = v
            if k not in active_fields: active_fields.append(k)

    aircraft[icao]["last"] = datetime.now()

def remove_old_aircraft():
    now = datetime.now()
    expired = [i for i, d in aircraft.items() if now - d["last"] > timedelta(seconds=TIMEOUT)]
    for i in expired:
        del aircraft[i]
        if i in aircraft_order: aircraft_order.remove(i)

def format_age(seconds):
    """Formatta i secondi in minuti e secondi (es: 1m 15s)"""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    rem_seconds = seconds % 60
    return f"{minutes}m {rem_seconds}s"

def aircraft_box(icao, data):
    total_seconds = int((datetime.now() - data["last"]).total_seconds())
    
    # Colore basato sull'età (verde < 15s, giallo < 60s, rosso oltre)
    color = "green" if total_seconds < 15 else "yellow" if total_seconds < 60 else "red"
    
    text = Text()
    text.append(f"✈ {icao}\n", style="bold cyan")
    
    display_list = [f for f in active_fields if f in FIELD_MAP and f != "ICA"]
    
    for f_code in display_list:
        label = FIELD_MAP[f_code][0]
        val_key = FIELD_MAP[f_code][1]
        val = data.get(val_key, "-")
        text.append(f"{label:<10}: {val}\n")
    
    text.append("\n") 
    text.append(f"LAST  : {data['last'].strftime('%H:%M:%S')}\n", style="dim")
    text.append(f"AGE   : {format_age(total_seconds)}", style=color)
    
    panel_height = len(display_list) + 6
    
    return Panel(
        text, 
        width=32, 
        height=panel_height, 
        border_style=color
    )

def build_ui():
    term_w = shutil.get_terminal_size().columns
    columns = max(1, term_w // 34)
    
    header_content = f"✈ ADS-B LoRa MONITOR | TARGETS: {len(aircraft)}"
    if active_fields:
        header_content += f"\nCampi attivi: {', '.join(active_fields)}"
    
    header = Panel(Text(header_content, justify="center", style="bold green"), height=4)
    grid = Table.grid(padding=(0, 1))
    for _ in range(columns): grid.add_column(width=34)

    cards = [aircraft_box(i, aircraft[i]) for i in aircraft_order if i in aircraft]
    
    if not cards:
        grid.add_row(Panel("In attesa di dati LoRa...", border_style="yellow", expand=False))
    else:
        for i in range(0, len(cards), columns):
            row = cards[i:i+columns]
            while len(row) < columns: row.append("")
            grid.add_row(*row)
            
    return Group(header, grid)

def main():
    ports = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    if not ports: 
        print("Errore: Nessuna Heltec trovata.")
        sys.exit(1)
        
    for i, p in enumerate(ports): print(f"{i}: {p}")
    try:
        choice = int(input("\nSeleziona porta Heltec: "))
        port_name = ports[choice]
    except (ValueError, IndexError):
        print("Scelta non valida.")
        sys.exit(1)
    
    fd = os.open(port_name, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    
    buffer = b""
    with Live(build_ui(), refresh_per_second=4, screen=True) as live:
        while True:
            r, _, _ = select.select([fd], [], [], 0.1)
            if fd in r:
                new_data = os.read(fd, 2048)
                buffer += new_data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    msg = line.decode(errors="ignore").strip()
                    if msg: parse_lora(msg)
            
            remove_old_aircraft()
            live.update(build_ui())

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgramma terminato.")