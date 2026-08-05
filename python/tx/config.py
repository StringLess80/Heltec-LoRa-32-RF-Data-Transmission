#!/usr/bin/env python3
import struct

# Network & Seriale
SBS_HOST = "127.0.0.1"
SBS_PORT = 30003
BAUDRATE = 115200

# Temporizzazioni (Modalità Alta Frequenza)
MIN_INTERVAL_PER_AIRCRAFT = 0.5   # Valuta 2 volte al sec per aereo
LORA_TX_AIRTIME_DELAY = 0.05      # 50ms min tra TX consecutive
FULL_FRAME_INTERVAL = 5.0         # Frame completo di sync ogni 5 sec

# Soglie di variazione per invio differenziale (Delta)
THRESHOLDS = {
    "ALT": 50,     # piedi
    "VEL": 5,      # nodi
    "DIR": 3,      # gradi
    "LAT": 0.002,  # gradi (~220m)
    "LON": 0.002,  # gradi
    "VER": 150,    # piedi/minuto
}

SYNC = 0xAA55

# Mappa dei campi: nome, indice SBS, codice, bit maschera, dimensione byte
FIELDS_MAP = {
    "1": ("ICAO", 4, "ICA", 0, 4),
    "2": ("Callsign", 10, "CAL", 1, 8),
    "3": ("Altitudine", 11, "ALT", 2, 2),
    "4": ("Velocita", 12, "VEL", 3, 2),
    "5": ("Direzione", 13, "DIR", 4, 2),
    "6": ("Latitudine", 14, "LAT", 5, 4),
    "7": ("Longitudine", 15, "LON", 6, 4),
    "8": ("Vertical rate", 16, "VER", 7, 2),
    "9": ("Squawk", 17, "SQU", 8, 2),
    "10": ("Ground state", 21, "GRO", 9, 1),
    "11": ("Tipo MSG", 1, "TIP", 10, 1),
}

# Precompilazione struct
STRUCT_I = struct.Struct("<I")
STRUCT_H = struct.Struct("<H")
STRUCT_h = struct.Struct("<h")
STRUCT_i = struct.Struct("<i")
STRUCT_B = struct.Struct("<B")
STRUCT_HEADER = struct.Struct("<HHHB")