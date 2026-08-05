#!/usr/bin/env python3
from datetime import datetime
from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from config import HOME_LAT, HOME_LON
from geo import calculate_distance

console = Console()

def build_aircraft_card(icao: str, data: dict) -> Panel:
    """Costruisce il widget visivo del singolo aeromobile."""
    age = int((datetime.now() - data["last"]).total_seconds())
    last_rx = data["last"].strftime("%H:%M:%S")

    if age < 5:
        border, age_style = "green", "bold bright_green"
    elif age < 15:
        border, age_style = "yellow", "bold bright_yellow"
    else:
        border, age_style = "red", "bold dim red"

    content = Text()
    flight_data = []
    if "alt" in data: flight_data.append(f"▲ {data['alt']}")
    if "speed" in data: flight_data.append(f"► {data['speed']}")
    if "heading" in data: flight_data.append(f"∡ {data['heading']}")

    if flight_data:
        content.append(" | ".join(flight_data) + "\n", style="cyan")

    # Mostra coordinate GPS e calcolo distanza
    if "lat" in data and "lon" in data:
        dist = calculate_distance(HOME_LAT, HOME_LON, data["lat"], data["lon"])
        content.append(f"⌖ {data['lat']:.5f}, {data['lon']:.5f} ", style="bright_yellow")
        content.append(f"({dist:.1f} km)\n", style="bold white on red")
        data["_distance"] = dist
    else:
        data["_distance"] = float("inf")

    tech_data = []
    if "vertical" in data: tech_data.append(f"↕ {data['vertical']}")
    if "squawk" in data: tech_data.append(f"SQK: {data['squawk']}")
    if "ground" in data: tech_data.append(f"[{data['ground']}]")

    if tech_data:
        content.append(" • ".join(tech_data) + "\n", style="magenta")

    if len(content) > 0:
        content.append("\n")

    content.append(f"⏱ {age}s ago", style=age_style)
    content.append(f"  (Rx: {last_rx})", style="dim white")

    ident = data.get("callsign", "NO IDENT")
    return Panel(content, title=f"✈ {icao} | {ident}", title_align="left", border_style=border, padding=(1, 2), width=44)


def build_ui(aircraft_dict: dict, term_width: int, term_height: int, row_offset: int):
    """Genera la vista completa del radar con ordinamento per distanza."""
    sorted_icaos = sorted(aircraft_dict.keys(), key=lambda k: (aircraft_dict[k].get("_distance", float("inf")), k))
    cards = [build_aircraft_card(icao, aircraft_dict[icao]) for icao in sorted_icaos]

    cols = max(1, term_width // 46)
    grid_rows = [cards[i:i + cols] for i in range(0, len(cards), cols)]
    total_rows = len(grid_rows)
    max_visible_rows = max(1, (term_height - 6) // 9)

    max_offset = max(0, total_rows - max_visible_rows)
    row_offset = max(0, min(row_offset, max_offset))
    visible_rows = grid_rows[row_offset:row_offset + max_visible_rows]

    if not cards:
        main_content = Panel(Text("\nIn attesa di tracciati radar LoRa...\n", style="yellow", justify="center"), border_style="dim")
    else:
        elements = []
        for row in visible_rows:
            elements.append(Columns(row, expand=False, equal=True))
            elements.append("")
        if elements: elements.pop()
        main_content = Group(*elements)

    scroll = f" | ROW {row_offset + 1}/{total_rows} (Frecce/WS per scorrere)" if total_rows > max_visible_rows else ""
    header = Panel(Text(f"📡 RADAR LoRa TELEMETRY | ATTIVI: {len(aircraft_dict)}{scroll}", justify="center", style="bold white on blue"))
    return Group(header, "\n", main_content), row_offset