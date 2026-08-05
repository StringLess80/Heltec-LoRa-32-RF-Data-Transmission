#!/usr/bin/env python3
import struct
import zlib

SYNC = 0xAA55

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

ACTIVE_FIELDS = [FIELDS_MAP[k] for k in ["1", "2", "3", "4", "5", "6", "7", "8"]]
ACTIVE_FIELDS.sort(key=lambda f: f[3])

STRUCT_I = struct.Struct("<I")
STRUCT_H = struct.Struct("<H")
STRUCT_h = struct.Struct("<h")
STRUCT_i = struct.Struct("<i")
STRUCT_B = struct.Struct("<B")
STRUCT_HEADER = struct.Struct("<HHHB")

seq = 0

def encode_packet(cached_data, fields_to_send):
    global seq
    payload = bytearray()
    mask = 0

    sorted_fields = sorted(fields_to_send, key=lambda f: f[3])

    for _, index, code, bit, _ in sorted_fields:
        if index not in cached_data or cached_data[index] == "": continue
        val_str = str(cached_data[index]).strip()
        if not val_str: continue

        try:
            if code == "ICA": field = STRUCT_I.pack(int(val_str, 16))
            elif code == "CAL": field = val_str.encode('ascii', errors='ignore')[:8].ljust(8, b"\x00")
            elif code in ("ALT", "VEL"): field = STRUCT_H.pack(max(0, min(65535, int(float(val_str)))))
            elif code == "DIR": field = STRUCT_H.pack(int(float(val_str)) % 360)
            elif code in ("LAT", "LON"): field = STRUCT_i.pack(int(float(val_str) * 1e7))
            elif code == "VER": field = STRUCT_h.pack(max(-32768, min(32767, int(float(val_str)))))
            elif code == "SQU": field = STRUCT_H.pack(int(val_str, 8) if val_str.isdigit() else int(val_str))
            elif code == "GRO": field = STRUCT_B.pack(1 if val_str in ("1", "-1", "true", "True") else 0)
            elif code == "TIP": field = STRUCT_B.pack(int(val_str))
            else: continue

            payload += field
            mask |= (1 << bit)
        except (ValueError, struct.error): continue

    if not payload: return None
    seq = (seq + 1) & 0xFFFF
    header = STRUCT_HEADER.pack(SYNC, seq, mask, len(payload))
    crc = zlib.crc32(header + payload) & 0xFFFF
    return header + payload + STRUCT_H.pack(crc), mask