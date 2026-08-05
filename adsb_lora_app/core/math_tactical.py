#!/usr/bin/env python3
import math
from core.state import system_state

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def is_in_vertical_blind_cone(ac_lat, ac_lon, ac_alt_ft, ctrl_lat, ctrl_lon, zenith_blind_angle_deg=30.0):
    dist_m = haversine_km(ctrl_lat, ctrl_lon, ac_lat, ac_lon) * 1000.0
    ac_alt_m = (float(ac_alt_ft) if ac_alt_ft else 10000.0) * 0.3048
    if dist_m <= 1.0: return True
    elevation_deg = math.degrees(math.atan2(ac_alt_m, dist_m))
    return (90.0 - elevation_deg) <= zenith_blind_angle_deg

def assign_aircraft_to_controller(ac_lat, ac_lon, ac_alt_ft):
    if not system_state["controllers"]:
        return None, False

    best_ctrl = None
    best_score = float('inf')
    in_blind = False

    for ctrl in system_state["controllers"]:
        dist = haversine_km(ctrl["lat"], ctrl["lon"], ac_lat, ac_lon)
        zenith_angle = ctrl.get("zenith_blind_angle", 30.0)
        in_cone = is_in_vertical_blind_cone(ac_lat, ac_lon, ac_alt_ft, ctrl["lat"], ctrl["lon"], zenith_angle)
        
        score = dist * (10.0 if in_cone else 1.0)
        if score < best_score:
            best_score = score
            best_ctrl = ctrl["id"]
            in_blind = in_cone

    return best_ctrl, in_blind