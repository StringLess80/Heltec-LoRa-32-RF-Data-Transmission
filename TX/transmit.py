#!/usr/bin/env python3

import glob
import socket
import sys
import time
import serial

# =====================================================
# CONFIGURATION
# =====================================================
SBS_HOST = "127.0.0.1"
SBS_PORT = 30003
BAUDRATE = 115200
CONFIG_INTERVAL = 10  # Invia la lista campi ogni 10 secondi

FIELDS_AVAILABLE = {
    "1": ("ICAO", 4, "ICA"),
    "2": ("Callsign", 10, "CAL"),
    "3": ("Altitudine", 11, "ALT"),
    "4": ("Velocita", 12, "VEL"),
    "5": ("Direzione", 13, "DIR"),
    "6": ("Latitudine", 14, "LAT"),
    "7": ("Longitudine", 15, "LON"),
    "8": ("Vertical rate", 16, "VER"),
    "9": ("Squawk", 17, "SQU"),
    "10": ("Ground state", 21, "GRO"),
    "11": ("Tipo messaggio", 1, "TIP"),
}

def select_fields():
    print("\n=== ADS-B LoRa TX CONFIGURATION ===")
    for k, v in FIELDS_AVAILABLE.items():
        print(f"{k:>2} {v[0]}")
    
    selected = input("\nInserisci i numeri separati da spazio: ").split()
    fields = [FIELDS_AVAILABLE[i] for i in selected if i in FIELDS_AVAILABLE]
    
    if not fields:
        print("Errore: Nessun campo selezionato")
        sys.exit(1)
    
    print("\nCampi attivi:", ", ".join([f[0] for f in fields]))
    return fields

def send_config(ser, selected_fields):
    """Invia il pacchetto di configurazione al ricevitore."""
    prefixes = [f[2] for f in selected_fields]
    cfg_packet = f"CFG:{','.join(prefixes)}\n"
    ser.write(cfg_packet.encode())

def parse_sbs(line, selected_fields):
    data = line.split(",")
    if len(data) < 22 or data[0] != "MSG":
        return None
    
    packet_parts = []
    for _, index, prefix in selected_fields:
        val = data[index].strip()
        if val:
            packet_parts.append(f"{prefix}={val}")
    
    return " ".join(packet_parts) if packet_parts else None

def main():
    selected_fields = select_fields()
    serial_port = "COM3"
    ser = serial.Serial(serial_port, BAUDRATE, timeout=1)
    
    print(f"Connessione a {SBS_HOST}:{SBS_PORT}...")
    sock = socket.create_connection((SBS_HOST, SBS_PORT))
    
    last_cfg_time = 0
    buffer = b""

    try:
        while True:
            # Invio periodico della configurazione
            if time.time() - last_cfg_time > CONFIG_INTERVAL:
                send_config(ser, selected_fields)
                last_cfg_time = time.time()

            raw = sock.recv(4096)
            if not raw: break
            buffer += raw

            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                msg = line.decode(errors="ignore").strip()
                packet = parse_sbs(msg, selected_fields)
                
                if packet:
                    ser.write((packet + "\n").encode())
                    print(f"TX LoRa: {packet}")

    except KeyboardInterrupt:
        print("\nChiusura...")
    finally:
        ser.close()
        sock.close()

if __name__ == "__main__":
    main()
