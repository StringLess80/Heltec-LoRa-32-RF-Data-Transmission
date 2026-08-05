#!/usr/bin/env python3
import sys
from config import FIELDS_MAP

def select_fields():
    """Interfaccia utente per selezionare quali campi inviare via radio."""
    print("\n=== ADS-B LoRa SEMANTIC TX ===")
    for key, value in FIELDS_MAP.items():
        print(f"{key:>2} - {value[0]}")

    selected = input("\nCampi da inviare (es: 1 3 4 5 6 7): ").split()

    if "1" not in selected:
        selected.insert(0, "1")

    fields = [FIELDS_MAP[key] for key in selected if key in FIELDS_MAP]
    if not fields:
        print("Nessun campo valido selezionato. Chiusura.")
        sys.exit(1)

    fields.sort(key=lambda f: f[3])
    print("\nCampi attivi (ordinati per bitmask):")
    for f in fields:
        print(f"- {f[0]}")
    return fields