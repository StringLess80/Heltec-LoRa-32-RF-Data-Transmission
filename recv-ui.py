#!/usr/bin/env python3

import os
import sys
import termios
import glob
import select
import shutil

from datetime import datetime, timedelta

from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import Group


# =====================================================
# DATABASE AEREI
# =====================================================

aircraft = {}

# ordine di comparsa degli aerei
aircraft_order = []

TIMEOUT = 60



# =====================================================
# PARSER SBS dump1090/readsb
# =====================================================

def parse_sbs(msg):

    fields = msg.split(',')

    if len(fields) < 22:
        return


    if fields[0] != "MSG":
        return


    icao = fields[4]

    if not icao:
        return



    # nuovo aereo

    if icao not in aircraft:

        aircraft_order.append(icao)

        aircraft[icao] = {

            "type": "",
            "alt": "",
            "speed": "",
            "heading": "",
            "lat": "",
            "lon": "",
            "last": datetime.now()

        }



    plane = aircraft[icao]


    msg_type = fields[1]



    # identificazione

    if msg_type == "1":

        if fields[10]:

            plane["type"] = fields[10].strip()



    # posizione

    elif msg_type == "3":

        if fields[11]:
            plane["alt"] = fields[11]

        if fields[14]:
            plane["lat"] = fields[14]

        if fields[15]:
            plane["lon"] = fields[15]



    # velocità

    elif msg_type == "4":

        if fields[12]:
            plane["speed"] = fields[12]

        if fields[13]:
            plane["heading"] = fields[13]



    plane["last"] = datetime.now()



# =====================================================
# RIMOZIONE AEREI PERSI
# =====================================================

def remove_old_aircraft():

    now = datetime.now()

    expired = []


    for icao, data in aircraft.items():

        if now - data["last"] > timedelta(seconds=TIMEOUT):

            expired.append(icao)



    for icao in expired:

        del aircraft[icao]

        aircraft_order.remove(icao)



# =====================================================
# CARD AEREO
# =====================================================

def aircraft_box(icao, data):


    age = int(
        (datetime.now() - data["last"]).total_seconds()
    )


    text = Text()


    text.append(
        f"✈ {icao}\n",
        style="bold cyan"
    )

    text.append("\n")


    text.append(
        f"TYPE  : {data['type'] or '-'}\n"
    )

    text.append(
        f"ALT   : {data['alt'] or '-'} ft\n"
    )

    text.append(
        f"SPEED : {data['speed'] or '-'} kt\n"
    )

    text.append(
        f"HEAD  : {data['heading'] or '-'}°\n"
    )


    text.append(
        f"LAT   : {data['lat'] or '-'}\n"
    )

    text.append(
        f"LON   : {data['lon'] or '-'}\n"
    )


    text.append("\n")


    text.append(
        f"LAST  : {data['last'].strftime('%H:%M:%S')}\n"
    )

    text.append(
        f"AGE   : {age}s"
    )


    return Panel(

        text,

        width=32,

        height=13,

        border_style="cyan"

    )



# =====================================================
# CREAZIONE UI
# =====================================================

def build_ui():


    terminal_width = shutil.get_terminal_size().columns


    card_width = 34


    columns = max(
        1,
        terminal_width // card_width
    )



    header = Panel(

        Text(
            f"✈ ADS-B LoRa MONITOR   |   TARGETS: {len(aircraft)}",
            justify="center",
            style="bold green"
        ),

        height=3

    )



    grid = Table.grid(
        padding=(0,1)
    )



    for _ in range(columns):

        grid.add_column(
            width=card_width
        )



    cards = []


    # mantiene ordine di comparsa

    for icao in aircraft_order:

        if icao in aircraft:

            cards.append(

                aircraft_box(
                    icao,
                    aircraft[icao]
                )

            )



    if not cards:

        return Group(

            header,

            Panel(
                "Waiting for ADS-B data...",
                border_style="yellow"
            )

        )



    # costruzione righe

    for i in range(0, len(cards), columns):

        row = cards[i:i+columns]


        while len(row) < columns:

            row.append("")



        grid.add_row(
            *row
        )



    return Group(

        header,

        grid

    )



# =====================================================
# SCELTA PORTA SERIALE
# =====================================================

ports = sorted(

    glob.glob('/dev/ttyACM*') +

    glob.glob('/dev/ttyUSB*')

)



if not ports:

    print(
        "Nessuna porta seriale trovata"
    )

    sys.exit(1)



print("Porte disponibili:")


for i, port in enumerate(ports):

    print(
        f"{i}: {port}"
    )



while True:

    try:

        idx = int(
            input("\nSeleziona porta: ")
        )

        PORT = ports[idx]

        break


    except:

        print(
            "Scelta non valida"
        )



print(
    f"\nUso porta: {PORT}"
)



# =====================================================
# CONFIGURAZIONE SERIAL
# =====================================================

fd = os.open(

    PORT,

    os.O_RDWR |

    os.O_NOCTTY |

    os.O_NONBLOCK

)



attrs = termios.tcgetattr(fd)


attrs[4] = termios.B115200
attrs[5] = termios.B115200


termios.tcsetattr(

    fd,

    termios.TCSANOW,

    attrs

)



print(
    "Ricezione ADS-B..."
)



# =====================================================
# LOOP PRINCIPALE
# =====================================================

buf = b''



with Live(

    build_ui(),

    refresh_per_second=5

) as live:


    while True:


        r, _, _ = select.select(

            [fd],

            [],

            [],

            1

        )



        if fd in r:


            data = os.read(

                fd,

                1024

            )


            buf += data



            while b'\n' in buf:


                line, buf = buf.split(

                    b'\n',

                    1

                )


                msg = line.decode(

                    errors="ignore"

                ).strip()



                if msg:

                    parse_sbs(msg)



        remove_old_aircraft()



        live.update(

            build_ui()

        )