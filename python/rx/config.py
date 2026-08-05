#!/usr/bin/env python3
import struct

# Timeout di rimozione bersaglio silente (secondi)
TIMEOUT = 45

# Coordinate geografiche del ricevitore (Home)
HOME_LAT = 44.473328
HOME_LON = 11.382953

# Costanti di Protocollo
SYNC = b"\x55\xAA"
HEADER_SIZE = 7

# Strutture di decodifica fisse
STRUCT_HEADER = struct.Struct("<HHHB")
FIELDS_DEF = {
    0: ("ICA", "icao", struct.Struct("<I")),
    1: ("CAL", "callsign", struct.Struct("8s")),
    2: ("ALT", "alt", struct.Struct("<H")),
    3: ("VEL", "speed", struct.Struct("<H")),
    4: ("DIR", "heading", struct.Struct("<H")),
    5: ("LAT", "lat", struct.Struct("<i")),
    6: ("LON", "lon", struct.Struct("<i")),
    7: ("VER", "vertical", struct.Struct("<h")),
    8: ("SQU", "squawk", struct.Struct("<H")),
    9: ("GRO", "ground", struct.Struct("<B")),
    10: ("TIP", "type", struct.Struct("<B")),
}