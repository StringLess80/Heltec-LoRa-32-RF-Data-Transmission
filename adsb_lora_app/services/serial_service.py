#!/usr/bin/env python3
import time
import serial
import serial.tools.list_ports
from core.state import system_state
from protocol.nmea_parser import parse_nmea_sentence

ser_lora_device = None
ser_gps_device = None

def get_clean_serial_ports():
    ports = list(serial.tools.list_ports.comports())
    clean_ports = []
    for p in ports:
        dev = p.device
        if dev.startswith('/dev/ttyS') and (p.hwid == 'n/a' or p.vid is None):
            continue
        if any(ignored in dev for ignored in ['/dev/printk', '/dev/console', '/dev/tty0']):
            continue
        clean_ports.append({"port": dev, "desc": p.description or dev})
    return clean_ports

def open_heltec_serial(port, baud):
    global ser_lora_device
    try:
        if ser_lora_device and ser_lora_device.is_open:
            ser_lora_device.close()
        ser = serial.Serial(port, baud, timeout=0.1)
        ser.dtr = False
        ser.rts = False
        time.sleep(0.05)
        ser.dtr = True
        ser_lora_device = ser
        system_state["serial_status"] = {"connected": True, "port": port, "baud": baud}
        print(f"[SERIAL LORA] Connesso su {port}")
        return True
    except Exception as e:
        system_state["serial_status"] = {"connected": False, "port": port, "baud": baud}
        print(f"[SERIAL LORA ERR] Impossibile aprire {port}: {e}")
        return False

def open_gps_serial(port, baud):
    global ser_gps_device
    try:
        if ser_gps_device and ser_gps_device.is_open:
            ser_gps_device.close()
        ser = serial.Serial(port, baud, timeout=1.0)
        ser_gps_device = ser
        system_state["gps_serial_status"] = {"connected": True, "port": port, "baud": baud}
        print(f"[SERIAL GPS] Connesso su {port}")
        return True
    except Exception as e:
        system_state["gps_serial_status"] = {"connected": False, "port": port, "baud": baud}
        print(f"[SERIAL GPS ERR] Impossibile aprire {port}: {e}")
        return False

def gps_serial_worker():
    global ser_gps_device
    while True:
        if ser_gps_device and ser_gps_device.is_open:
            try:
                line = ser_gps_device.readline().decode('ascii', errors='ignore')
                if line: parse_nmea_sentence(line)
            except Exception:
                system_state["gps_serial_status"]["connected"] = False
                system_state["gps"]["connected"] = False
        time.sleep(0.01)