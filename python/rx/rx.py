#!/usr/bin/env python3
import struct
import sys
import time
import zlib

import serial
import serial.tools.list_ports
from rich.live import Live

from config import SYNC, HEADER_SIZE
from input_handler import NonBlockingInput
from tracker import AircraftTracker
from ui import build_ui, console


def select_serial_port():
    ports = [p for p in serial.tools.list_ports.comports() if p.device.startswith(("/dev/ttyUSB", "/dev/ttyACM", "COM"))]
    if not ports:
        print("Nessuna porta seriale trovata.")
        sys.exit(1)

    if len(ports) == 1:
        port_name = ports[0].device
        print(f"Uso automatico: {port_name}")
        return port_name

    print("\nPorte disponibili:")
    for i, port in enumerate(ports):
        print(f"[{i}] {port.device} - {port.description}")

    while True:
        try:
            choice = int(input("\nSeleziona porta RX: "))
            return ports[choice].device
        except (ValueError, IndexError):
            print("Scelta non valida.")


def main():
    port_name = select_serial_port()

    try:
        ser = serial.Serial(port_name, 115200, timeout=0)
    except Exception as exc:
        print(f"Errore connessione: {exc}")
        sys.exit(1)

    tracker = AircraftTracker()
    buffer = b""
    row_offset = 0
    last_ui_update = 0.0
    ui_update_interval = 0.1

    with NonBlockingInput() as key_in:
        init_ui, row_offset = build_ui(tracker.aircraft, console.size.width, console.size.height, row_offset)
        with Live(init_ui, console=console, screen=True, auto_refresh=False) as live:
            while True:
                now = time.time()
                data_received, key_pressed = False, False

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

                        if (zlib.crc32(header + payload) & 0xFFFF) == crc_rx:
                            tracker.parse_packet(header, payload)
                        else:
                            buffer = packet[2:] + buffer

                    if len(buffer) > 4096:
                        buffer = buffer[-4096:]

                key = key_in.get_key()
                if key == "up":
                    row_offset = max(0, row_offset - 1)
                    key_pressed = True
                elif key == "down":
                    row_offset += 1
                    key_pressed = True
                elif key == "exit":
                    break

                tracker.remove_old()

                # Refresh della TUI (pacing controllato a 100ms)
                if key_pressed or (data_received and (now - last_ui_update > ui_update_interval)):
                    ui_grid, row_offset = build_ui(tracker.aircraft, console.size.width, console.size.height, row_offset)
                    live.update(ui_grid)
                    live.refresh()
                    last_ui_update = now

                if not raw and not key:
                    time.sleep(0.01)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass