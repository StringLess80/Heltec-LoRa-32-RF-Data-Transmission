#!/usr/bin/env python3
import struct
import zlib
from config import (
    SYNC, STRUCT_I, STRUCT_H, STRUCT_h, STRUCT_i, STRUCT_B, STRUCT_HEADER
)

class PacketEncoder:
    def __init__(self):
        self.seq = 0

    def encode(self, cached_data: dict, fields_to_send: list):
        """Codifica i campi selezionati in formato binario compresso."""
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
                elif code in ("ALT", "VEL"):
                    field = STRUCT_H.pack(max(0, min(65535, int(float(val_str)))))
                elif code == "DIR":
                    field = STRUCT_H.pack(int(float(val_str)) % 360)
                elif code in ("LAT", "LON"):
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

        self.seq = (self.seq + 1) & 0xFFFF
        header = STRUCT_HEADER.pack(SYNC, self.seq, mask, len(payload))
        crc = zlib.crc32(header + payload) & 0xFFFF
        return header + payload + STRUCT_H.pack(crc), mask