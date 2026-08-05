#!/usr/bin/env python3
import select
import socket
import sys
import time
from collections import deque

import serial
import serial.tools.list_ports

from config import (
    SBS_HOST, SBS_PORT, BAUDRATE,
    MIN_INTERVAL_PER_AIRCRAFT, LORA_TX_AIRTIME_DELAY
)
from fields_selector import select_fields
from evaluator import evaluate_semantic_payload
from encoder import PacketEncoder
from tracker import AircraftTracker


def open_serial_port():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("\n[ERRORE] Nessuna porta seriale trovata.")
        sys.exit(1)

    print("\nPorte disponibili:")
    for i, p in enumerate(ports):
        print(f"[{i}] {p.device} - {p.description}")

    while True:
        try:
            choice = int(input("\nSeleziona porta TX: "))
            ser = serial.Serial(ports[choice].device, BAUDRATE, timeout=0.1)
            print(f"Seriale aperta su {ports[choice].device}")
            return ser
        except (ValueError, IndexError):
            print("Selezione non valida.")


def connect_sbs_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((SBS_HOST, SBS_PORT))
        sock.setblocking(False)
        print(f"Connesso a Dump1090 su {SBS_HOST}:{SBS_PORT}")
        return sock
    except Exception as e:
        print(f"Connessione a Dump1090 fallita: {e}")
        sys.exit(1)


def main():
    selected_fields = select_fields()
    ser = open_serial_port()
    sock = connect_sbs_socket()

    tracker = AircraftTracker()
    encoder = PacketEncoder()

    buffer = b""
    tx_queue = deque(maxlen=20)  # Evita latenze limitando la coda a max 20 pacchetti
    last_tx_time = 0.0

    try:
        while True:
            # Lettura non bloccante dei pacchetti dal socket SBS
            ready, _, _ = select.select([sock], [], [], 0.005)
            if ready:
                try:
                    raw = sock.recv(8192)
                    if raw:
                        buffer += raw
                except BlockingIOError:
                    pass

            now = time.time()

            # Estrazione righe SBS ricevute
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                tracker.update_from_sbs_line(line, now)

            # Garbage Collection aerei inattivi (> 60s)
            tracker.cleanup_stale(now, timeout_sec=60.0)

            # Analisi semantica degli aerei attivi
            for icao, ac_info in tracker.aircraft_db.items():
                if now - ac_info["last_eval"] < MIN_INTERVAL_PER_AIRCRAFT:
                    continue

                ac_info["last_eval"] = now
                fields_to_send, frame_type = evaluate_semantic_payload(ac_info, selected_fields, now)

                if not fields_to_send or frame_type == "NONE":
                    continue

                res = encoder.encode(ac_info["current_data"], fields_to_send)
                if res is None:
                    continue

                packet, mask = res
                tx_queue.append((packet, icao, frame_type, mask))

                ac_info["last_tx"] = now
                if frame_type == "FULL":
                    ac_info["last_full_tx"] = now

                # Aggiorna lo stato dei dati inviati
                for field in fields_to_send:
                    idx = field[1]
                    if idx in ac_info["current_data"]:
                        ac_info["last_sent_data"][idx] = ac_info["current_data"][idx]

            # Evasione asincrona della coda TX rispettando il delay LoRa
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