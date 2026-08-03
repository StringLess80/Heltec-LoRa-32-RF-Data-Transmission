#!/usr/bin/env python3
"""
ADS-B LoRa Radar Dashboard
============================

Riceve via porta seriale i pacchetti binari inviati dal trasmettitore
LoRa (vedi tx.py), li decodifica e mostra una
dashboard testuale interattiva (basata su "rich") con lo stato di
tutti gli aeromobili attualmente tracciati.

La UI si aggiorna in modo "intelligente": in modo istantaneo quando
l'utente scorre la lista con i tasti, e a intervalli regolari quando
arrivano nuovi dati via radio, per evitare sfarfallii e consumo di
CPU inutile.
"""

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

# Import specifici per l'input non bloccante, diversi per piattaforma
if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty

# =====================================================================
# CONFIGURAZIONE
# =====================================================================

TIMEOUT = 60  # secondi dopo i quali un aeromobile senza aggiornamenti scade

SYNC = b"\x55\xAA"
HEADER_SIZE = 7

# =====================================================================
# MAPPA DEI CAMPI
# =====================================================================

# bit -> (codice campo, chiave dizionario, formato struct, dimensione byte)
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

# Stato globale: dati per ICAO e ordine di prima apparizione (per la UI)
aircraft = {}
aircraft_order = []

console = Console()


class NonBlockingInput:
    """
    Gestisce la cattura dei tasti in modo non bloccante e immediato,
    in modo compatibile sia con Windows (msvcrt) che con Unix
    (termios/tty in modalita' cbreak).
    """

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
        """
        Legge un singolo tasto senza bloccare l'esecuzione.

        Ritorna:
            str | None: "up", "down", "exit" oppure None se non e'
            stato premuto (o riconosciuto) nessun tasto utile.
        """
        if self.is_windows:
            return self._get_key_windows()
        return self._get_key_unix()

    def _get_key_windows(self):
        if not msvcrt.kbhit():
            return None

        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):  # Prefisso tasti freccia
            ch2 = msvcrt.getch()
            if ch2 == b"H":
                return "up"
            if ch2 == b"P":
                return "down"
        elif ch.lower() in (b"w", b"k"):
            return "up"
        elif ch.lower() in (b"s", b"j"):
            return "down"
        elif ch.lower() == b"q" or ch == b"\x03":
            return "exit"
        return None

    def _get_key_unix(self):
        rlist, _, _ = select.select([sys.stdin], [], [], 0)
        if not rlist:
            return None

        ch = sys.stdin.read(1)
        if ch == "\x1b":  # Inizio sequenza di escape (es. tasti freccia)
            r2, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r2:
                seq = sys.stdin.read(2)
                if seq == "[A":
                    return "up"
                if seq == "[B":
                    return "down"
        elif ch.lower() in ("w", "k"):
            return "up"
        elif ch.lower() in ("s", "j"):
            return "down"
        elif ch.lower() == "q" or ch == "\x03":
            return "exit"
        return None


def parse_packet(header, payload):
    """
    Decodifica un pacchetto (header + payload) gia' validato dal CRC
    e aggiorna il database globale degli aeromobili.

    Argomenti:
        header (bytes): 7 byte di header (SYNC, seq, mask, length).
        payload (bytes): byte del payload, secondo la bitmask.
    """
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
            return  # payload troncato/corrotto: scarta il pacchetto

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
        return  # senza ICAO non possiamo identificare l'aeromobile

    icao = data["icao"]

    if icao not in aircraft:
        aircraft_order.append(icao)
        aircraft[icao] = {}

    aircraft[icao].update(data)
    aircraft[icao]["last"] = datetime.now()


def remove_old():
    """Rimuove dal database gli aeromobili non aggiornati da troppo tempo."""
    now = datetime.now()
    expired = [
        icao for icao, info in aircraft.items()
        if now - info["last"] > timedelta(seconds=TIMEOUT)
    ]
    for icao in expired:
        del aircraft[icao]
        if icao in aircraft_order:
            aircraft_order.remove(icao)


# =====================================================================
# UI - COSTRUZIONE DELLA DASHBOARD
# =====================================================================

def build_aircraft_card(icao, data):
    """
    Costruisce il pannello (Panel) "rich" che rappresenta un singolo
    aeromobile, con colore del bordo dipendente dall'eta' del dato.

    Argomenti:
        icao (str): identificativo ICAO dell'aeromobile.
        data (dict): dati correnti dell'aeromobile.

    Ritorna:
        rich.panel.Panel: il pannello pronto per essere mostrato.
    """
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

    # Riga con i dati di volo principali (quota, velocita', direzione)
    flight_data = []
    if "alt" in data:
        flight_data.append(f"▲ {data['alt']}")
    if "speed" in data:
        flight_data.append(f"► {data['speed']}")
    if "heading" in data:
        flight_data.append(f"∡ {data['heading']}")

    if flight_data:
        content.append(" | ".join(flight_data) + "\n", style="cyan")

    # Riga con la posizione geografica
    if "lat" in data and "lon" in data:
        content.append(
            f"⌖ {data['lat']:.5f}, {data['lon']:.5f}\n", style="bright_yellow"
        )

    # Riga con i dati tecnici (rateo verticale, squawk, stato al suolo)
    tech_data = []
    if "vertical" in data:
        tech_data.append(f"↕ {data['vertical']}")
    if "squawk" in data:
        tech_data.append(f"SQK: {data['squawk']}")
    if "ground" in data:
        tech_data.append(f"[{data['ground']}]")

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
        width=42,
    )


def build_ui(term_width, term_height, row_offset):
    """
    Costruisce l'intera dashboard: header, griglia di card degli
    aeromobili (con scroll verticale) oppure un messaggio di attesa
    se non ci sono ancora dati.

    Argomenti:
        term_width (int): larghezza corrente del terminale.
        term_height (int): altezza corrente del terminale.
        row_offset (int): riga della griglia da cui iniziare a
            mostrare i contenuti (per lo scroll).

    Ritorna:
        tuple: (rich.console.Group, row_offset) dove row_offset e'
        stato "clampato" ai limiti validi.
    """
    cards = [
        build_aircraft_card(icao, aircraft[icao])
        for icao in aircraft_order
        if icao in aircraft
    ]

    card_width = 42
    col_spacing = 2
    cols = max(1, term_width // (card_width + col_spacing))

    grid_rows = [cards[i:i + cols] for i in range(0, len(cards), cols)]
    total_rows = len(grid_rows)

    row_height = 9
    usable_height = max(1, term_height - 6)
    max_visible_rows = max(1, usable_height // row_height)

    # Mantiene lo scroll entro i limiti validi
    max_offset = max(0, total_rows - max_visible_rows)
    row_offset = min(row_offset, max_offset)
    row_offset = max(0, row_offset)

    visible_rows = grid_rows[row_offset:row_offset + max_visible_rows]

    if not cards:
        main_content = Panel(
            Text(
                "\nIn attesa di pacchetti LoRa...\n",
                style="yellow",
                justify="center",
            ),
            border_style="dim",
        )
    else:
        row_elements = []
        for row in visible_rows:
            row_elements.append(Columns(row, expand=False, equal=True))
            row_elements.append("")  # spaziatura tra le righe

        if row_elements:
            row_elements.pop()  # rimuove la spaziatura finale superflua

        main_content = Group(*row_elements)

    scroll_status = ""
    if total_rows > max_visible_rows:
        scroll_status = (
            f" | ROW {row_offset + 1}/{total_rows} (Frecce o W/S per scorrere)"
        )

    header = Panel(
        Text(
            f"📡 RADAR LoRa TELEMETRY | TARGETS: {len(aircraft)}{scroll_status}",
            justify="center",
            style="bold white on blue",
        )
    )

    return Group(header, "\n", main_content), row_offset


# =====================================================================
# MAIN LOOP
# =====================================================================

def main():
    """Individua la porta seriale, avvia la ricezione e la UI live."""
    ports = [
        port for port in serial.tools.list_ports.comports()
        if port.device.startswith(("/dev/ttyUSB", "/dev/ttyACM", "COM"))
    ]

    if not ports:
        print("Nessuna porta seriale trovata.")
        sys.exit(1)

    if len(ports) == 1:
        port_name = ports[0].device
        print(f"Uso automaticamente {port_name}")
    else:
        print("\nPorte disponibili:")
        for i, port in enumerate(ports):
            print(f"[{i}] {port.device} - {port.description}")

        try:
            choice = int(input("\nSeleziona il numero della porta RX: "))
            port_name = ports[choice].device
        except (ValueError, IndexError):
            sys.exit(1)

    try:
        # timeout=0 rende la lettura seriale completamente non bloccante
        ser = serial.Serial(port_name, 115200, timeout=0)
    except Exception as exc:
        print(f"Errore: {exc}")
        sys.exit(1)

    buffer = b""
    row_offset = 0
    last_ui_update = 0.0
    # Aggiorna i dati sulla UI al massimo ogni 100ms per evitare sfarfallii
    ui_update_interval = 0.1

    with NonBlockingInput() as key_in:
        initial_ui, row_offset = build_ui(
            console.size.width, console.size.height, row_offset
        )
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

                # Controllo periodico delle scadenze (aeromobili non piu' visti)
                remove_old()

                # 3. Rendering dinamico e intelligente:
                #    - se l'utente preme un tasto, aggiornamento ISTANTANEO
                #      (massima reattivita');
                #    - se arrivano nuovi dati, aggiornamento a intervalli
                #      regolari (evita sfarfallii).
                should_update = key_pressed or (
                    data_received and (now - last_ui_update > ui_update_interval)
                )
                if should_update:
                    ui_grid, row_offset = build_ui(
                        console.size.width, console.size.height, row_offset
                    )
                    live.update(ui_grid)
                    live.refresh()
                    last_ui_update = now

                # 4. Sleep minimo per non consumare il 100% della CPU se inattivo
                if not raw and not key:
                    time.sleep(0.01)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTerminato.")