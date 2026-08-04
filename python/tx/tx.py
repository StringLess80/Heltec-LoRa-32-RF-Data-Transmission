#!/usr/bin/env python3
"""
ADS-B LoRa Semantic TX
==============================================
"""

import select
import socket
import struct
import sys
import time
import zlib
from collections import deque

import serial
import serial.tools.list_ports

# =====================================================================
# CONFIGURAZIONE
# =====================================================================
SBS_HOST = "127.0.0.1"
SBS_PORT = 30003
BAUDRATE = 115200

# Temporizzazioni (Modalità Alta Frequenza)
MIN_INTERVAL_PER_AIRCRAFT = 0.5   # Valuta i movimenti 2 volte al secondo per aereo
LORA_TX_AIRTIME_DELAY = 0.05      # 50ms di intervallo minimo tra trasmissioni consecutive
FULL_FRAME_INTERVAL = 5.0         # Forza un invio completo ogni 5 secondi per sincronizzazione RX

# Soglie di variazione per l'invio differenziale (Delta)
THRESHOLDS = {
    "ALT": 50,     # piedi
    "VEL": 5,      # nodi
    "DIR": 3,      # gradi
    "LAT": 0.002,  # gradi (circa 220m)
    "LON": 0.002,  # gradi
    "VER": 150,    # piedi/minuto
}

SYNC = 0xAA55

# Mappa dei campi: nome, indice nel tracciato SBS, codice, bit della maschera, dimensione in byte
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

# Precompilazione delle strutture per massimizzare la velocità di struct.pack
STRUCT_I = struct.Struct("<I")
STRUCT_H = struct.Struct("<H")
STRUCT_h = struct.Struct("<h")
STRUCT_i = struct.Struct("<i")
STRUCT_B = struct.Struct("<B")
STRUCT_HEADER = struct.Struct("<HHHB")

seq = 0
aircraft_db = {}


def select_fields():
    print("\n=== ADS-B LoRa SEMANTIC TX ===")
    for key, value in FIELDS_MAP.items():
        print(f"{key:>2} - {value[0]}")

    selected = input("\nCampi da inviare (es: 1 3 4 5 6 7): ").split()

    if "1" not in selected:
        selected.insert(0, "1")

    fields = [FIELDS_MAP[key] for key in selected if key in FIELDS_MAP]
    if not fields:
        print("Nessun campo valido selezionato. Chiusura.")
        sys.exit(1)

    fields.sort(key=lambda f: f[3])
    print("\nCampi attivi (ordinati per bitmask):")
    for f in fields:
        print(f"- {f[0]}")
    return fields


def evaluate_semantic_payload(ac_info, selected_fields, now):
    """Valuta se inviare un frame completo, un delta o nulla."""
    if now - ac_info["last_full_tx"] >= FULL_FRAME_INTERVAL:
        return selected_fields, "FULL"

    fields_to_send = []
    has_changes = False
    is_event = False
    curr_data = ac_info["current_data"]
    last_sent = ac_info["last_sent_data"]

    for field in selected_fields:
        _, index, code, _, _ = field

        if code == "ICA":
            fields_to_send.append(field)
            continue

        curr_val = curr_data.get(index, "")
        if curr_val == "":
            continue

        last_val = last_sent.get(index, "")
        if last_val == "":
            fields_to_send.append(field)
            has_changes = True
            continue

        if code in ("GRO", "SQU") and curr_val != last_val:
            fields_to_send.append(field)
            has_changes = True
            is_event = True
            continue

        try:
            if code in THRESHOLDS:
                if abs(float(curr_val) - float(last_val)) >= THRESHOLDS[code]:
                    fields_to_send.append(field)
                    has_changes = True
            elif curr_val != last_val:
                fields_to_send.append(field)
                has_changes = True
        except ValueError:
            pass

    if has_changes:
        return fields_to_send, "EVENT" if is_event else "DELTA"
    return None, "NONE"


def encode_packet(cached_data, fields_to_send):
    """Codifica i campi selezionati in formato binario compresso."""
    global seq
    payload = bytearray()
    mask = 0

    for _, index, code, bit, _ in fields_to_send:
        if index not in cached_data:
            continue

        val_str = cached_data[index]
        if val_str == "":
            continue

        try:
            if code == "ICA":
                field = STRUCT_I.pack(int(val_str, 16))
            elif code == "CAL":
                field = val_str.encode()[:8].ljust(8, b"\x00")
            elif code == "ALT" or code == "VEL":
                field = STRUCT_H.pack(max(0, min(65535, int(float(val_str)))))
            elif code == "DIR":
                field = STRUCT_H.pack(int(float(val_str)) % 360)
            elif code == "LAT" or code == "LON":
                field = STRUCT_i.pack(int(float(val_str) * 1e7))
            elif code == "VER":
                field = STRUCT_h.pack(max(-32768, min(32767, int(float(val_str)))))
            elif code == "SQU":
                field = STRUCT_H.pack(int(val_str, 8))
            elif code == "GRO":
                field = STRUCT_B.pack(1 if val_str in ("1", "-1", "true", "True") else 0)
            elif code == "TIP":
                field = STRUCT_B.pack(int(val_str))
            else:
                continue

            payload += field
            mask |= (1 << bit)
        except (ValueError, struct.error):
            continue

    if not payload:
        return None

    seq = (seq + 1) & 0xFFFF
    header = STRUCT_HEADER.pack(SYNC, seq, mask, len(payload))
    crc = zlib.crc32(header + payload) & 0xFFFF
    return header + payload + STRUCT_H.pack(crc), mask


def main():
    fields = select_fields()

    # Seleziona porta seriale
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("\n[ERRORE] Nessuna porta seriale trovata.")
        sys.exit(1)

    print("\nPorte disponibili:")
    for i, p in enumerate(ports):
        print(f"[{i}] {p.device} - {p.description}")

    ser = None
    while ser is None:
        try:
            choice = int(input("\nSeleziona porta TX: "))
            ser = serial.Serial(ports[choice].device, BAUDRATE, timeout=0.1)
            print(f"Seriale aperta su {ports[choice].device}")
        except (ValueError, IndexError):
            print("Selezione non valida.")

    # Connessione a Dump1090
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((SBS_HOST, SBS_PORT))
        sock.setblocking(False)
        print(f"Connesso a Dump1090 su {SBS_HOST}:{SBS_PORT}")
    except Exception as e:
        print(f"Connessione a Dump1090 fallita: {e}")
        sys.exit(1)

    buffer = b""
    tx_queue = deque(maxlen=20)  # Evita ritardi limitando la coda a 20 elementi (max 1s di telemetria)
    last_tx_time = 0

    try:
        while True:
            # Lettura non bloccante dei pacchetti dal socket
            ready, _, _ = select.select([sock], [], [], 0.005)
            if ready:
                try:
                    raw = sock.recv(8192)
                    if raw:
                        buffer += raw
                except BlockingIOError:
                    pass

            now = time.time()

            # Parsing veloce delle righe SBS ricevute
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                data = line.decode(errors="ignore").strip().split(",")

                if len(data) < 22 or data[0] != "MSG":
                    continue

                icao = data[4].strip()
                if not icao:
                    continue

                if icao not in aircraft_db:
                    aircraft_db[icao] = {
                        "last_eval": 0,
                        "last_tx": 0,
                        "last_full_tx": 0,
                        "last_seen": now,
                        "current_data": {},
                        "last_sent_data": {},
                    }

                aircraft_db[icao]["last_seen"] = now

                # Aggiorna i campi valorizzati
                for idx in range(len(data)):
                    val = data[idx].strip()
                    if val:
                        aircraft_db[icao]["current_data"][idx] = val

            # Garbage Collection degli aeromobili persi (> 60s)
            expired = [icao for icao, info in aircraft_db.items() if now - info["last_seen"] > 60]
            for icao in expired:
                del aircraft_db[icao]

            # Analisi semantica dei dati degli aerei attivi
            for icao, ac_info in aircraft_db.items():
                if now - ac_info["last_eval"] < MIN_INTERVAL_PER_AIRCRAFT:
                    continue

                ac_info["last_eval"] = now
                fields_to_send, frame_type = evaluate_semantic_payload(ac_info, fields, now)

                if not fields_to_send or frame_type == "NONE":
                    continue

                res = encode_packet(ac_info["current_data"], fields_to_send)
                if res is None:
                    continue

                packet, mask = res
                tx_queue.append((packet, icao, frame_type, mask))

                ac_info["last_tx"] = now
                if frame_type == "FULL":
                    ac_info["last_full_tx"] = now

                # Allinea i dati correntemente inviati
                for field in fields_to_send:
                    idx = field[1]
                    if idx in ac_info["current_data"]:
                        ac_info["last_sent_data"][idx] = ac_info["current_data"][idx]

            # Evasione asincrona della coda TX rispettando il minimo delay radio
            if tx_queue and (now - last_tx_time >= LORA_TX_AIRTIME_DELAY):
                packet, p_icao, p_type, p_mask = tx_queue.popleft()
                try:
                    ser.write(packet)
                    ser.flush()
                    last_tx_time = now
                    print(f"TX [{p_type:^5}] {p_icao} | MASK 0x{p_mask:03X} | SIZE {len(packet):>2} B | Q: {len(tx_queue)}")
                except Exception as e:
                    print(f"Errore scrittura seriale: {e}")

    except KeyboardInterrupt:
        print("\nArresto...")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
        if 'sock' in locals():
            sock.close()


if __name__ == "__main__":
    main()