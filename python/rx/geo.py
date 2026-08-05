#!/usr/bin/env python3
import math

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcola la distanza in km (Formula di Haversine) tra due punti."""
    rad_lat1, rad_lat2 = math.radians(lat1), math.radians(lat2)
    dlat = rad_lat2 - rad_lat1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(rad_lat1) * math.cos(rad_lat2) * math.sin(dlon / 2)**2
    return 6371.0 * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))