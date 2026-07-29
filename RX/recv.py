#!/usr/bin/env python3

import os
import sys
import termios
import glob
import select
from datetime import datetime


def parse_sbs(msg):
    """
    Parser formato SBS/BaseStation di dump1090/readsb
    """

    fields = msg.split(',')

    # Se non è un messaggio valido SBS
    if len(fields) < 22:
        return msg

    # Accetta solo messaggi MSG
    if fields[0] != "MSG":
        return msg

    msg_type = fields[1]
    icao = fields[4]

    result = []

    # ICAO
    result.append(f"ICAO: {icao}")

    # Tipo messaggio
    types = {
        "1": "Identificazione aereo",
        "2": "Posizione superficie",
        "3": "Posizione aria",
        "4": "Velocita'",
        "5": "Identificazione superficie",
        "6": "Trilaterazione",
        "7": "Status",
        "8": "Heartbeat"
    }

    result.append(
        f"Tipo: {types.get(msg_type, 'Sconosciuto')}"
    )


    # Messaggio posizione aria
    if msg_type == "3":

        altitude = fields[11]
        latitude = fields[14]
        longitude = fields[15]

        if altitude:
            result.append(f"Quota: {altitude} ft")

        if latitude and longitude:
            result.append(
                f"Posizione: {latitude}, {longitude}"
            )


    # Messaggio velocità
    elif msg_type == "4":

        speed = fields[12]
        heading = fields[13]
        vertical = fields[16]

        if speed:
            result.append(f"Velocita': {speed} kt")

        if heading:
            result.append(f"Direzione: {heading} deg")

        if vertical:
            result.append(
                f"Variazione verticale: {vertical} ft/min"
            )


    return "\n".join(result)



# -------------------------------------------------
# Ricerca automatica porte seriali
# -------------------------------------------------

ports = sorted(
    glob.glob('/dev/ttyACM*') +
    glob.glob('/dev/ttyUSB*')
)


if not ports:
    print("Nessuna porta seriale trovata")
    sys.exit(1)



print("Porte seriali disponibili:")

for i, port in enumerate(ports):
    print(f"  {i}: {port}")



# Scelta porta

while True:

    try:

        choice = input(
            "Seleziona il numero della porta: "
        )

        idx = int(choice)

        if 0 <= idx < len(ports):
            PORT = ports[idx]
            break

        else:
            print("Indice non valido")


    except ValueError:
        print("Inserisci un numero valido")



print(f"\nUtilizzo della porta: {PORT}")



# -------------------------------------------------
# Apertura seriale
# -------------------------------------------------

fd = os.open(
    PORT,
    os.O_RDWR |
    os.O_NOCTTY |
    os.O_NONBLOCK
)



# Configurazione seriale

attrs = termios.tcgetattr(fd)

attrs[4] = termios.B115200
attrs[5] = termios.B115200

termios.tcsetattr(
    fd,
    termios.TCSANOW,
    attrs
)



print("Ricezione da", PORT)
print("In attesa di messaggi SBS...\n")



# Buffer seriale

buf = b''



# -------------------------------------------------
# Loop principale
# -------------------------------------------------

while True:


    # Aspetta dati sulla seriale
    r, _, _ = select.select(
        [fd],
        [],
        [],
        1.0
    )


    if fd in r:


        data = os.read(fd, 256)

        buf += data



        # Cerca righe complete

        while b'\n' in buf:


            line, buf = buf.split(
                b'\n',
                1
            )


            text = line.decode(
                errors='ignore'
            ).strip()



            if text:

                ts = datetime.now().strftime(
                    '%H:%M:%S'
                )


                print("=" * 45)
                print(f"[{ts}]")

                print(
                    parse_sbs(text)
                )

                print()