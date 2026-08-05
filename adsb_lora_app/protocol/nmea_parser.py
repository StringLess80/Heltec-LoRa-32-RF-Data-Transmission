#!/usr/bin/env python3
from core.state import system_state

def parse_nmea_coord(coord_str, direction):
    if not coord_str or not direction: return 0.0
    try:
        dot_idx = coord_str.find('.')
        if dot_idx < 2: return 0.0
        deg_digits = dot_idx - 2
        degrees = float(coord_str[:deg_digits])
        minutes = float(coord_str[deg_digits:])
        dec = degrees + (minutes / 60.0)
        if direction in ('S', 'W'): dec = -dec
        return dec
    except (ValueError, IndexError): return 0.0

def parse_nmea_time(time_str):
    if not time_str: return None
    try:
        clean = time_str.split('.')[0]
        if len(clean) >= 6:
            return f"{clean[0:2]}:{clean[2:4]}:{clean[4:6]} UTC"
    except Exception: pass
    return None

def parse_nmea_sentence(line):
    line = line.strip()
    if not line.startswith('$'): return
    try:
        parts = line.split('*')[0].split(',')
        sentence_type = parts[0][3:] if len(parts[0]) >= 5 else ""

        if sentence_type == "GGA" and len(parts) >= 10:
            parsed_utc = parse_nmea_time(parts[1])
            lat = parse_nmea_coord(parts[2], parts[3])
            lon = parse_nmea_coord(parts[4], parts[5])
            fix_qual = parts[6]
            num_sats = int(parts[7]) if parts[7].isdigit() else 0
            alt = float(parts[9]) if parts[9] else 0.0

            fix_desc = "No Fix"
            if fix_qual == "1": fix_desc = f"3D Fix ({num_sats} Sats)"
            elif fix_qual == "2": fix_desc = f"DGPS Fix ({num_sats} Sats)"
            elif fix_qual == "3": fix_desc = f"PPS Fix ({num_sats} Sats)"

            if lat != 0.0 and lon != 0.0:
                system_state["gps"]["lat"] = lat
                system_state["gps"]["lon"] = lon
                system_state["gps"]["alt"] = alt
                system_state["gps"]["satellites"] = num_sats
                system_state["gps"]["fix"] = fix_desc
                if parsed_utc: system_state["gps"]["utc"] = parsed_utc
                system_state["gps"]["connected"] = True

        elif sentence_type in ("RMC", "GLL") and len(parts) >= 7:
            status = parts[2] if sentence_type == "RMC" else parts[6]
            if status == "A":
                parsed_utc = parse_nmea_time(parts[1])
                lat_idx, lon_idx = (3, 5) if sentence_type == "RMC" else (1, 3)
                lat = parse_nmea_coord(parts[lat_idx], parts[lat_idx+1])
                lon = parse_nmea_coord(parts[lon_idx], parts[lon_idx+1])
                if lat != 0.0 and lon != 0.0:
                    system_state["gps"]["lat"] = lat
                    system_state["gps"]["lon"] = lon
                    if parsed_utc: system_state["gps"]["utc"] = parsed_utc
                    system_state["gps"]["connected"] = True
    except Exception: pass