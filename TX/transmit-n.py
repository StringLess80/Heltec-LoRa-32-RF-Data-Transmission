#!/usr/bin/env python3

import glob
import socket
import sys

import serial


# =====================================================
# CONFIGURATION
# =====================================================

SBS_HOST = "127.0.0.1"
SBS_PORT = 30003

BAUDRATE = 115200


# =====================================================
# AVAILABLE SBS FIELDS
# =====================================================

FIELDS_AVAILABLE = {
    "1": ("ICAO", 4),
    "2": ("Callsign", 10),
    "3": ("Altitudine", 11),
    "4": ("Velocita", 12),
    "5": ("Direzione", 13),
    "6": ("Latitudine", 14),
    "7": ("Longitudine", 15),
    "8": ("Vertical rate", 16),
    "9": ("Squawk", 17),
    "10": ("Ground state", 21),
    "11": ("Tipo messaggio", 1),
}


# =====================================================
# FIELD SELECTION
# =====================================================

def select_fields():
    print(
        """
=================================
 ADS-B LoRa TX CONFIGURATION
=================================

Scegli quali dati inviare:

1  ICAO
2  Callsign
3  Altitudine
4  Velocita
5  Direzione
6  Latitudine
7  Longitudine
8  Vertical rate
9  Squawk
10 Ground state
11 Tipo messaggio


Inserisci più numeri separati da spazio

Esempio:
1 2 3 6 7

"""
    )

    selected = input("Campi: ").split()

    fields = []

    for item in selected:
        if item in FIELDS_AVAILABLE:
            fields.append(FIELDS_AVAILABLE[item])

    if not fields:
        print("Nessun campo selezionato")
        sys.exit(1)

    print("\nInvierò:")

    for name, _ in fields:
        print(f"- {name}")

    return fields



# =====================================================
# SERIAL PORT SELECTION
# =====================================================

def select_serial_port():

    ports = sorted(
        glob.glob("COM*")
        + glob.glob("/dev/ttyACM*")
        + glob.glob("/dev/ttyUSB*")
    )

    if not ports:
        print("Nessuna Heltec trovata")
        sys.exit(1)

    print("\nPorte disponibili:")

    for index, port in enumerate(ports):
        print(f"{index}: {port}")

    while True:

        try:
            choice = int(
                input("\nPorta Heltec: ")
            )

            return ports[choice]

        except (ValueError, IndexError):
            print("Scelta errata")



# =====================================================
# SBS PARSER
# =====================================================

def parse_sbs(line, selected_fields):

    data = line.split(",")

    if len(data) < 22:
        return None

    if data[0] != "MSG":
        return None

    packet = []

    for name, index in selected_fields:

        value = data[index]

        if value:

            short_name = name[:3].upper()

            packet.append(
                f"{short_name}={value}"
            )

    if packet:
        return " ".join(packet)

    return None



# =====================================================
# MAIN LOOP
# =====================================================

def main():

    selected_fields = select_fields()

    serial_port = select_serial_port()

    print(
        f"\nConnessione Heltec: {serial_port}"
    )

    ser = serial.Serial(
        serial_port,
        BAUDRATE,
        timeout=1,
    )

    print(
        "Connessione readsb/dump1090..."
    )

    sock = socket.create_connection(
        (
            SBS_HOST,
            SBS_PORT,
        )
    )

    print(
        "\nTrasmissione attiva\n"
    )

    buffer = b""


    while True:

        raw = sock.recv(4096)

        if not raw:
            break

        buffer += raw


        while b"\n" in buffer:

            line, buffer = buffer.split(
                b"\n",
                1,
            )


            message = line.decode(
                errors="ignore"
            ).strip()


            packet = parse_sbs(
                message,
                selected_fields,
            )


            if packet:

                ser.write(
                    (
                        packet + "\n"
                    ).encode()
                )


                print(
                    "TX:",
                    packet,
                )



# =====================================================
# ENTRY POINT
# =====================================================

if __name__ == "__main__":
    main()