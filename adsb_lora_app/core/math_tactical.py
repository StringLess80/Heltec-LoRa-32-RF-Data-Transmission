#!/usr/bin/env python3
"""
core/math_tactical.py — Geodesia Tattica, 3D Slant Range e Cono Cieco Zenith (FIM-92 Stinger)
"""
import math
from typing import Tuple, Optional, Dict, Any
from core.state import system_state

# Raggio medio terrestre in chilometri (WGS84)
R_EARTH_KM = 6371.0
KTS_TO_MS = 0.514444  # Knots -> m/s
FT_TO_M = 0.3048      # Feet -> m


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """ Calcola la distanza geodesica orizzontale a terra in chilometri. """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R_EARTH_KM * c


# Alias per retrocompatibilità
haversine_km = haversine_distance_km


def calculate_zenith_and_slant_distance(
    ac_lat: float, ac_lon: float, ac_alt_feet: float,
    ctrl_lat: float, ctrl_lon: float, ctrl_alt_meters: float = 0.0
):
    """ Calcola la cinematica tattica 3D (Zenith angle, Slant Range 3D, Ground distance). """
    d_ground_km = haversine_distance_km(ac_lat, ac_lon, ctrl_lat, ctrl_lon)
    d_ground_m = d_ground_km * 1000.0

    ac_alt_m = (float(ac_alt_feet) if ac_alt_feet is not None else 10000.0) * FT_TO_M
    delta_h_m = max(1.0, ac_alt_m - ctrl_alt_meters)

    slant_distance_m = math.sqrt(d_ground_m**2 + delta_h_m**2)
    slant_distance_km = slant_distance_m / 1000.0

    zenith_angle_rad = math.atan2(d_ground_m, delta_h_m)
    zenith_angle_deg = math.degrees(zenith_angle_rad)

    return zenith_angle_deg, slant_distance_km, d_ground_km


def calculate_target_kinematics(
    ac_lat: float, ac_lon: float, ac_alt_ft: float,
    ac_speed_kts: float, ac_heading_deg: float,
    ctrl: Dict[str, Any]
) -> Dict[str, Any]:
    """ Calcola lo stato tattico e l'inviluppo d'ingaggio dell'aereo rispetto al controllore. """
    ctrl_lat = float(ctrl["lat"])
    ctrl_lon = float(ctrl["lon"])
    ctrl_alt_m = float(ctrl.get("alt_m", 0.0))
    
    r_max_slant_km = float(ctrl.get("radius_km", 8.0))
    h_max_ceiling_km = float(ctrl.get("cone_height_km", 3.8))
    theta_blind_deg = float(ctrl.get("zenith_blind_angle", 30.0))
    r_min_slant_km = float(ctrl.get("min_range_km", 0.2))

    d_ground_km = haversine_distance_km(ac_lat, ac_lon, ctrl_lat, ctrl_lon)
    d_ground_m = d_ground_km * 1000.0

    ac_alt_m = (float(ac_alt_ft) if ac_alt_ft is not None else 0.0) * FT_TO_M
    delta_h_m = max(0.1, ac_alt_m - ctrl_alt_m)
    delta_h_km = delta_h_m / 1000.0

    slant_distance_m = math.sqrt(d_ground_m**2 + delta_h_m**2)
    slant_distance_km = slant_distance_m / 1000.0

    zenith_rad = math.atan2(d_ground_m, delta_h_m)
    zenith_deg = math.degrees(zenith_rad)
    elevation_deg = 90.0 - zenith_deg

    speed_ms = (float(ac_speed_kts) if ac_speed_kts else 0.0) * KTS_TO_MS
    heading_rad = math.radians(float(ac_heading_deg) if ac_heading_deg else 0.0)

    v_east = speed_ms * math.sin(heading_rad)
    v_north = speed_ms * math.cos(heading_rad)

    d_lat_m = (ac_lat - ctrl_lat) * 111000.0
    d_lon_m = (ac_lon - ctrl_lon) * 111000.0 * math.cos(math.radians(ctrl_lat))

    v_sq = v_east**2 + v_north**2
    if v_sq > 0.1:
        tta_sec = max(0.0, -(d_lon_m * v_east + d_lat_m * v_north) / v_sq)
    else:
        tta_sec = 0.0

    cpa_m = math.sqrt(max(0.0, (d_lon_m + v_east * tta_sec)**2 + (d_lat_m + v_north * tta_sec)**2))
    cpa_km = cpa_m / 1000.0

    is_in_blind_cone = (zenith_deg <= theta_blind_deg)
    is_over_ceiling = (delta_h_km > h_max_ceiling_km)
    is_out_of_range = (slant_distance_km > r_max_slant_km) or is_over_ceiling
    is_too_close = (slant_distance_km < r_min_slant_km)

    if is_in_blind_cone:
        status_code = "WARNING_ZENITH_BLIND"
    elif is_out_of_range:
        status_code = "OUT_OF_RANGE"
    elif is_too_close:
        status_code = "TOO_CLOSE_UNARMED"
    else:
        status_code = "ENGAGABLE"

    return {
        "d_ground_km": round(d_ground_km, 2),
        "slant_distance_km": round(slant_distance_km, 2),
        "delta_h_km": round(delta_h_km, 2),
        "zenith_deg": round(zenith_deg, 1),
        "elevation_deg": round(elevation_deg, 1),
        "cpa_km": round(cpa_km, 2),
        "tta_sec": round(tta_sec, 0),
        "is_in_blind_cone": is_in_blind_cone,
        "status_code": status_code
    }


def is_in_vertical_blind_cone(
    ac_lat: float, ac_lon: float, ac_alt_ft: float,
    ctrl_lat: float, ctrl_lon: float, zenith_blind_angle_deg: float = 30.0
) -> bool:
    """ Verifica se un aereo si trova nel cono d'ombra Zenith. """
    zenith_deg, _, _ = calculate_zenith_and_slant_distance(
        ac_lat, ac_lon, ac_alt_ft, ctrl_lat, ctrl_lon
    )
    return zenith_deg <= zenith_blind_angle_deg


def assign_aircraft_to_controller(
    ac_lat: float, ac_lon: float, ac_alt_ft: float,
    ac_speed_kts: float = 0.0, ac_heading_deg: float = 0.0
) -> Tuple[Optional[str], bool]:
    """
    Assegna l'aereo all'unità tattica ottimale.
    RIGIDO: Se l'aereo è Fuori Inviluppo Slant Range (> 8.0km) o Tetto (> 3.8km), NON viene assegnato (None).
    """
    controllers = system_state.get("controllers", [])
    if not controllers:
        return None, False

    best_ctrl = None
    best_score = float('inf')
    in_blind = False

    for ctrl in controllers:
        kin = calculate_target_kinematics(ac_lat, ac_lon, ac_alt_ft, ac_speed_kts, ac_heading_deg, ctrl)
        
        slant_km = kin["slant_distance_km"]
        in_cone = kin["is_in_blind_cone"]
        status = kin["status_code"]

        # Se fuori dalla portata massima o sopra il tetto, passa oltre!
        if status == "OUT_OF_RANGE":
            continue

        cpa_weight = 0.7 if kin["cpa_km"] <= 2.0 else 1.0
        blind_penalty = 10.0 if in_cone else 1.0

        effective_score = slant_km * cpa_weight * blind_penalty

        if effective_score < best_score:
            best_score = effective_score
            best_ctrl = ctrl["id"]
            in_blind = in_cone

    return best_ctrl, in_blind