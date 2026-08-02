#!/usr/bin/env python3

import socket
import struct
import sys
import time
import select
import zlib

import serial
import serial.tools.list_ports

# =====================================================
# CONFIGURATION
# =====================================================

SBS_HOST = "127.0.0.1"
SBS_PORT = 30003
BAUDRATE = 115200

# Intervallo minimo tra gli invii DELLO STESSO AEREO (secondi)
MIN_INTERVAL_PER_AIRCRAFT = 2.0 

# Tempo di pausa TRA UN PACCHETTO LORA E L'ALTRO (secondi)
LORA_TX_AIRTIME_DELAY = 0.1 

SYNC = 0xAA55

# =====================================================
# FIELD MAP
# =====================================================
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

seq = 0
aircraft_db = {}


def select_fields():
    print("\n=== ADS-B LoRa CONFIGURATION ===")
    for k, v in FIELDS_MAP.items():
        print(f"{k:>2} - {v[0]}")

    prompt = "\nCampi da inviare separati da spazio (es: 1 3 4 5 6 7): "
    selected = input(prompt).split()

    fields = [FIELDS_MAP[x] for x in selected if x in FIELDS_MAP]

    if not fields:
        print("Nessun campo selezionato. Chiusura.")
        sys.exit(1)

    # FIX CRITICO: Ordina sempre i campi per BIT crescente (dal bit 0 al 15)
    # Il ricevitore legge i byte in questo identico ordine. Se non sono ordinati, i byte si mescolano.
    fields.sort(key=lambda x: x[3])

    print("\nCampi attivi (ordinati per protocollo):")
    for f in fields:
        print(f"- {f[0]}")

    return fields


def encode_packet(cached_data, selected_fields):
    global seq

    payload = bytearray()
    mask = 0

    for name, index, code, bit, size in selected_fields:
        if index not in cached_data:
            continue

        value = cached_data[index]
        if value == "":
            continue

        try:
            if code == "ICA":
                field = struct.pack("<I", int(value, 16))
            elif code == "CAL":
                field = value.encode()[:8].ljust(8, b"\x00")
            elif code == "ALT":
                # FIX: Mantiene in piedi (ft) come in aviazione
                field = struct.pack("<H", max(0, min(65535, int(float(value)))))
            elif code == "VEL":
                # FIX: Mantiene in nodi (kt)
                field = struct.pack("<H", max(0, min(65535, int(float(value)))))
            elif code == "DIR":
                heading = int(float(value)) % 360
                field = struct.pack("<H", heading)
            elif code == "LAT":
                field = struct.pack("<i", int(float(value) * 1e7))
            elif code == "LON":
                field = struct.pack("<i", int(float(value) * 1e7))
            elif code == "VER":
                field = struct.pack("<h", max(-32768, min(32767, int(float(value)))))
            elif code == "SQU":
                # FIX: Lo squawk è un numero Ottale (Base 8), non decimale!
                field = struct.pack("<H", int(value, 8))
            elif code == "GRO":
                ground = 1 if value in ("1", "-1", "true", "True") else 0
                field = struct.pack("<B", ground)
            elif code == "TIP":
                field = struct.pack("<B", int(value))
            else:
                continue

            payload += field
            mask |= (1 << bit)

        except (ValueError, struct.error):
            continue

    if len(payload) == 0:
        return None

    seq = (seq + 1) & 0xFFFF
    header = struct.pack("<HHHB", SYNC, seq, mask, len(payload))
    crc = zlib.crc32(payload) & 0xFFFF
    packet = header + payload + struct.pack("<H", crc)

    return packet, mask


def main():
    fields = select_fields()
    ports = list(serial.tools.list_ports.comports())

    if not ports:
        print("Nessuna porta seriale trovata.")
        sys.exit(1)

    print("\nPorte disponibili:")
    for i, p in enumerate(ports):
        print(f"[{i}] {p.device} - {p.description}")

    try:
        choice = int(input("\nSeleziona il numero della porta TX: "))
        port_name = ports[choice].device
    except (ValueError, IndexError):
        sys.exit(1)

    try:
        ser = serial.Serial(port_name, BAUDRATE, timeout=0.1)
    except Exception as e:
        print(f"Errore: {e}")
        sys.exit(1)

    print(f"\nSeriale aperta su {port_name}")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((SBS_HOST, SBS_PORT))
        sock.setblocking(False)
        print("Connesso. In ascolto...")
    except Exception as e:
        sys.exit(1)

    buffer = b""

    try:
        while True:
            ready_to_read, _, _ = select.select([sock], [], [], 0.05)
            if ready_to_read:
                try:
                    raw = sock.recv(8192)
                    if raw:
                        buffer += raw
                except BlockingIOError:
                    pass

            now = time.time()

            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                data = line.decode(errors="ignore").strip().split(",")

                if len(data) < 22 or data[0] != "MSG":
                    continue

                icao = data[4].strip()
                if not icao:
                    continue

                if icao not in aircraft_db:
                    aircraft_db[icao] = {"last_tx": 0, "last_seen": now, "data": {}}
                
                # FIX: Aggiorniamo l'orario di ultima ricezione correttamete qui
                aircraft_db[icao]["last_seen"] = now

                for idx in range(len(data)):
                    val = data[idx].strip()
                    if val != "":
                        aircraft_db[icao]["data"][idx] = val

            # Pulizia cache (aerei non visti da 60 sec da dump1090)
            expired = [i for i, d in aircraft_db.items() if now - d["last_seen"] > 60]
            for i in expired:
                del aircraft_db[i]

            # Trasmissione
            for icao, ac_info in aircraft_db.items():
                if now - ac_info["last_tx"] >= MIN_INTERVAL_PER_AIRCRAFT:
                    result = encode_packet(ac_info["data"], fields)
                    
                    if result:
                        packet, mask = result
                        ser.write(packet)
                        ser.flush()
                        
                        print(f"TX {icao} | MASK=0x{mask:03X} | {len(packet)} bytes")
                        
                        ac_info["last_tx"] = now
                        time.sleep(LORA_TX_AIRTIME_DELAY) 

    except KeyboardInterrupt:
        print("\nChiusura forzata...")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
        if 'sock' in locals():
            sock.close()

if __name__ == "__main__":
    main()