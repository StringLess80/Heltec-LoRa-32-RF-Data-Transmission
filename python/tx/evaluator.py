#!/usr/bin/env python3
from config import FULL_FRAME_INTERVAL, THRESHOLDS

def evaluate_semantic_payload(ac_info: dict, selected_fields: list, now: float):
    """Valuta se inviare un frame completo, un delta o nulla."""
    if now - ac_info["last_full_tx"] >= FULL_FRAME_INTERVAL:
        return selected_fields, "FULL"

    fields_to_send = []
    has_changes = False
    is_event = False
    curr_data = ac_info["current_data"]
    last_sent = ac_info["last_sent_data"]

    for field in selected_fields:
        _, index, code, _, _ = field

        if code == "ICA":
            fields_to_send.append(field)
            continue

        curr_val = curr_data.get(index, "")
        if curr_val == "":
            continue

        last_val = last_sent.get(index, "")
        if last_val == "":
            fields_to_send.append(field)
            has_changes = True
            continue

        if code in ("GRO", "SQU") and curr_val != last_val:
            fields_to_send.append(field)
            has_changes = True
            is_event = True
            continue

        try:
            if code in THRESHOLDS:
                if abs(float(curr_val) - float(last_val)) >= THRESHOLDS[code]:
                    fields_to_send.append(field)
                    has_changes = True
            elif curr_val != last_val:
                fields_to_send.append(field)
                has_changes = True
        except ValueError:
            pass

    if has_changes:
        return fields_to_send, "EVENT" if is_event else "DELTA"
    return None, "NONE"