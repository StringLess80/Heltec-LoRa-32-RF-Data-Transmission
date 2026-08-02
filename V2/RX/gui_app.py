#!/usr/bin/env python3
import sys
import os
import struct
import zlib
import math
from datetime import datetime, timedelta

import serial
import serial.tools.list_ports

from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt, QPointF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout,
    QHBoxLayout, QGridLayout, QLabel, QComboBox, QPushButton,
    QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath,
    QConicalGradient
)

# =====================================================
# CONFIGURAZIONE PROTOCOLLO
# =====================================================
TIMEOUT_SECONDS = 150
SYNC = b"\x55\xAA"
HEADER_SIZE = 7

FIELDS_DEF = {
    0: ("ICA", "icao", "<I", 4),
    1: ("CAL", "callsign", "8s", 8),
    2: ("ALT", "alt", "<H", 2),
    3: ("VEL", "speed", "<H", 2),
    4: ("DIR", "heading", "<H", 2),
    5: ("LAT", "lat", "<i", 4),
    6: ("LON", "lon", "<i", 4),
    7: ("VER", "vertical", "<h", 2),
    8: ("SQU", "squawk", "<H", 2),
    9: ("GRO", "ground", "<B", 1),
    10: ("TIP", "type", "<B", 1),
}

def latlon_to_xy(lat, lon, clat, clon):
    # Approssimazione Flat Earth locale (in km)
    avg_lat_rad = math.radians((lat + clat) / 2.0)
    y = (lat - clat) * 111.12
    x = (lon - clon) * 111.12 * math.cos(avg_lat_rad)
    return x, y

# =====================================================
# WORKER SERIALE (QTHREAD)
# =====================================================
class SerialWorker(QThread):
    packet_parsed = pyqtSignal(dict)
    status_changed = pyqtSignal(str, bool)

    def __init__(self, port, baudrate=115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.running = True

    def run(self):
        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
            self.status_changed.emit(f"Connesso a {self.port}", True)
        except Exception as e:
            self.status_changed.emit(f"Errore di connessione: {str(e)}", False)
            return

        buffer = b""
        while self.running:
            try:
                raw = ser.read(1024)
                if raw:
                    buffer += raw
                    while True:
                        idx = buffer.find(SYNC)
                        if idx < 0:
                            buffer = buffer[-1:]
                            break

                        buffer = buffer[idx:]
                        if len(buffer) < HEADER_SIZE:
                            break

                        length = buffer[6]
                        total = HEADER_SIZE + length + 2

                        if len(buffer) < total:
                            break

                        packet = buffer[:total]
                        buffer = buffer[total:]

                        header = packet[:HEADER_SIZE]
                        payload = packet[HEADER_SIZE:-2]
                        crc_rx = struct.unpack("<H", packet[-2:])[0]

                        if (zlib.crc32(payload) & 0xFFFF) == crc_rx:
                            self.parse_and_emit(header, payload)
            except Exception as e:
                self.status_changed.emit(f"Errore di lettura seriale: {str(e)}", False)
                break

        try:
            ser.close()
        except:
            pass
        self.status_changed.emit("Disconnesso", False)

    def parse_and_emit(self, header, payload):
        _sync, _seq, mask, _length = struct.unpack("<HHHB", header)
        offset = 0
        data = {}

        for bit in range(16):
            if not (mask & (1 << bit)):
                continue
            if bit not in FIELDS_DEF:
                continue

            code, key, fmt, size = FIELDS_DEF[bit]
            if offset + size > len(payload):
                return

            raw = payload[offset:offset + size]
            offset += size

            value = struct.unpack(fmt, raw)[0]

            if code == "ICA":
                data["icao"] = f"{value:06X}"
            elif code == "CAL":
                data["callsign"] = value.decode(errors="ignore").strip("\x00 ")
            elif code == "ALT":
                data["alt"] = int(value)
            elif code == "VEL":
                data["speed"] = int(value)
            elif code == "DIR":
                data["heading"] = float(value)
            elif code == "LAT":
                data["lat"] = value / 1e7
            elif code == "LON":
                data["lon"] = value / 1e7
            elif code == "VER":
                data["vertical"] = int(value)
            elif code == "SQU":
                data["squawk"] = f"{value:04o}"
            elif code == "GRO":
                data["ground"] = "GND" if value else "AIR"
            elif code == "TIP":
                data["type"] = int(value)

        if "icao" in data:
            self.packet_parsed.emit(data)

    def stop(self):
        self.running = False
        self.wait()

# =====================================================
# COMPONENTE VISUALE RADAR
# =====================================================
class RadarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.aircraft_dict = {}
        self.home_lat = 44.473328
        self.home_lon = 11.382953
        self.auto_center = True
        self.fixed_range_km = 0.0

        self.sweep_angle = 0.0
        self.sweep_timer = QTimer(self)
        self.sweep_timer.timeout.connect(self.update_sweep)
        self.sweep_timer.start(33)  # ~30 FPS

    def update_sweep(self):
        self.sweep_angle = (self.sweep_angle + 1.5) % 360
        self.update()

    def setData(self, aircraft_dict, home_lat, home_lon, auto_center, fixed_range):
        self.aircraft_dict = aircraft_dict
        self.home_lat = home_lat
        self.home_lon = home_lon
        self.auto_center = auto_center
        self.fixed_range_km = fixed_range

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Sfondo scuro radar
        painter.fillRect(self.rect(), QColor(10, 11, 14))

        width = self.width()
        height = self.height()
        radius = min(width, height) // 2 - 25
        center = QPointF(width / 2, height / 2)

        if radius <= 10:
            return

        # 1. Trova i velivoli con coordinate GPS attive
        active_gps = [
            d for d in self.aircraft_dict.values()
            if "lat" in d and "lon" in d
        ]

        # 2. Definisci il centro dinamico del radar
        if self.auto_center and active_gps:
            clat = sum(d["lat"] for d in active_gps) / len(active_gps)
            clon = sum(d["lon"] for d in active_gps) / len(active_gps)
        else:
            clat, clon = self.home_lat, self.home_lon

        # 3. Calcola il raggio limite di visualizzazione
        max_dist = 5.0  # Raggio minimo predefinito a 5 km
        if clat is not None and clon is not None and active_gps:
            for d in active_gps:
                x, y = latlon_to_xy(d["lat"], d["lon"], clat, clon)
                dist = math.sqrt(x*x + y*y)
                if dist > max_dist:
                    max_dist = dist

        if self.fixed_range_km > 0.0:
            radar_range_km = self.fixed_range_km
        else:
            radar_range_km = max_dist * 1.25  # Margine del 25% per evitare bordi netti

        scale_px_per_km = radius / radar_range_km

        # 4. Disegno degli anelli e linee di griglia (non soggetti a maschera di ritaglio)
        pen_grid = QPen(QColor(0, 180, 80, 60), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen_grid)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        num_rings = 4
        for idx in range(1, num_rings + 1):
            r = radius * (idx / num_rings)
            painter.drawEllipse(center, r, r)

        pen_axes = QPen(QColor(0, 180, 80, 90), 1)
        painter.setPen(pen_axes)
        painter.drawLine(QPointF(center.x() - radius, center.y()), QPointF(center.x() + radius, center.y()))
        painter.drawLine(QPointF(center.x(), center.y() - radius), QPointF(center.x(), center.y() + radius))

        # 5. Attivazione Maschera di ritaglio vettoriale circolare
        painter.save()
        clip_path = QPainterPath()
        clip_path.addEllipse(center, radius, radius)
        painter.setClipPath(clip_path)

        # Disegno del fascio radar rotante
        sweep_gradient = QConicalGradient(center, -self.sweep_angle)
        sweep_gradient.setColorAt(0.0, QColor(0, 255, 100, 100))
        sweep_gradient.setColorAt(0.08, QColor(0, 255, 100, 35))
        sweep_gradient.setColorAt(0.4, QColor(0, 255, 100, 0))
        sweep_gradient.setColorAt(1.0, QColor(0, 255, 100, 0))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(sweep_gradient))
        painter.drawEllipse(center, radius, radius)

        # Disegno delle rotte (trails) e delle icone aerei
        now = datetime.now()
        for icao, data in self.aircraft_dict.items():
            if "lat" not in data or "lon" not in data:
                continue

            # Coordinate correnti proiettate
            ax, ay = latlon_to_xy(data["lat"], data["lon"], clat, clon)
            px = center.x() + ax * scale_px_per_km
            py = center.y() - ay * scale_px_per_km

            age_sec = (now - data["last"]).total_seconds()
            
            if age_sec < 15:
                color_target = QColor(0, 255, 120)
                color_trail = QColor(0, 255, 120, 75)
            elif age_sec < 60:
                color_target = QColor(255, 200, 0)
                color_trail = QColor(255, 200, 0, 50)
            else:
                color_target = QColor(255, 50, 50)
                color_trail = QColor(255, 50, 50, 25)

            # A. Disegno della rotta storica (Trail)
            if "history" in data:
                history_points = data["history"]
                if len(history_points) > 1:
                    trail_path = QPainterPath()
                    # Inizializza il tracciato dal primo punto salvato
                    hx_init, hy_init = latlon_to_xy(history_points[0][0], history_points[0][1], clat, clon)
                    trail_path.moveTo(center.x() + hx_init * scale_px_per_km, center.y() - hy_init * scale_px_per_km)

                    for hlat, hlon in history_points[1:]:
                        hx, hy = latlon_to_xy(hlat, hlon, clat, clon)
                        trail_path.lineTo(center.x() + hx * scale_px_per_km, center.y() - hy * scale_px_per_km)
                    
                    # Trascina l'ultimo frammento fino all'attuale posizione geometrica dell'icona
                    trail_path.lineTo(px, py)

                    painter.setPen(QPen(color_trail, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(trail_path)

            # B. Disegno dell'aereo vettoriale (Icona)
            painter.save()
            painter.translate(px, py)
            heading = data.get("heading", 0.0)
            painter.rotate(heading)

            aircraft_path = QPainterPath()
            aircraft_path.moveTo(0, -9)
            aircraft_path.lineTo(7, 6)
            aircraft_path.lineTo(2, 4)
            aircraft_path.lineTo(0, 6)
            aircraft_path.lineTo(-2, 4)
            aircraft_path.lineTo(-7, 6)
            aircraft_path.closeSubpath()

            painter.setPen(QPen(QColor(10, 11, 14), 1))
            painter.setBrush(QBrush(color_target))
            painter.drawPath(aircraft_path)
            painter.restore()

            # C. Etichette di identificazione
            painter.setPen(QPen(color_target))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            ident = data.get("callsign", icao)
            alt_text = f"{data['alt']}ft" if "alt" in data else ""
            painter.drawText(int(px + 12), int(py - 2), ident)
            if alt_text:
                painter.setFont(QFont("Segoe UI", 7))
                painter.setPen(QPen(color_target.darker(115)))
                painter.drawText(int(px + 12), int(py + 8), alt_text)

        # Ripristina lo stato del pittore rimuovendo il clip circolare
        painter.restore()

        # 6. Testo dei punti cardinali
        painter.setPen(QPen(QColor(0, 255, 100, 180)))
        painter.setFont(QFont("Monospace", 9))
        painter.drawText(int(center.x() - 5), int(center.y() - radius - 5), "N")
        painter.drawText(int(center.x() - 5), int(center.y() + radius + 15), "S")
        painter.drawText(int(center.x() + radius + 5), int(center.y() + 5), "E")
        painter.drawText(int(center.x() - radius - 15), int(center.y() + 5), "W")

        # Info testuali scala
        painter.drawText(15, height - 15, f"Raggio Max: {radar_range_km:.2f} km")
        painter.drawText(15, height - 30, f"Spaziatura Anelli: {radar_range_km/num_rings:.2f} km")

# =====================================================
# INTERFACCIA PRINCIPALE (MAIN WINDOW)
# =====================================================
class RadarMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SDR/LoRa Telemetry Radar Display")
        self.resize(1100, 700)

        self.aircraft_data = {}
        self.serial_thread = None

        self.setStyleSheet("""
            QMainWindow {
                background-color: #12131a;
            }
            QWidget {
                color: #e2e4f0;
                font-family: "Segoe UI", "Helvetica Neue", sans-serif;
                font-size: 13px;
            }
            QGroupBox {
                border: 1px solid #232533;
                border-radius: 6px;
                margin-top: 15px;
                font-weight: bold;
                background-color: #181921;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 5px;
                color: #00ff7f;
            }
            QPushButton {
                background-color: #2a2d3e;
                border: 1px solid #3f445f;
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #35394f;
                border-color: #00ff7f;
            }
            QPushButton:pressed {
                background-color: #1c1d29;
            }
            QLineEdit {
                background-color: #1f212c;
                border: 1px solid #2d3042;
                border-radius: 4px;
                padding: 4px 6px;
                color: #ffffff;
            }
            QComboBox {
                background-color: #1f212c;
                border: 1px solid #2d3042;
                border-radius: 4px;
                padding: 4px 20px 4px 6px;
                color: #ffffff;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: #2d3042;
                border-left-style: solid;
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1b24;
                border: 1px solid #2d3042;
                color: #e2e4f0;
                selection-background-color: #223c30;
                selection-color: #00ff7f;
                outline: none;
            }
            QTableWidget {
                background-color: #181921;
                gridline-color: #232533;
                border: 1px solid #232533;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #1a1c24;
                color: #00ff7f;
                padding: 5px;
                font-weight: bold;
                border: 1px solid #232533;
            }
            QTableWidget::item:selected {
                background-color: #223c30;
                color: #00ff7f;
            }
        """)

        self.initUI()

        self.gui_timer = QTimer(self)
        self.gui_timer.timeout.connect(self.update_gui_and_prune)
        self.gui_timer.start(1000)

    def initUI(self):
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(main_splitter)

        self.radar_widget = RadarWidget(self)
        main_splitter.addWidget(self.radar_widget)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(10)

        # 1. Connessione seriale
        group_serial = QGroupBox("CONNESSIONE SERIALE")
        layout_serial = QGridLayout(group_serial)
        layout_serial.setContentsMargins(12, 15, 12, 12)
        layout_serial.setSpacing(8)

        layout_serial.addWidget(QLabel("Porta:"), 0, 0)
        self.combo_port = QComboBox()
        layout_serial.addWidget(self.combo_port, 0, 1)

        btn_refresh = QPushButton("Aggiorna")
        btn_refresh.clicked.connect(self.scan_ports)
        layout_serial.addWidget(btn_refresh, 0, 2)

        self.btn_connect = QPushButton("CONNETTI")
        self.btn_connect.clicked.connect(self.toggle_connection)
        layout_serial.addWidget(self.btn_connect, 1, 0, 1, 3)

        self.label_status = QLabel("Stato: Disconnesso")
        self.label_status.setStyleSheet("color: #ff5555; font-weight: bold;")
        layout_serial.addWidget(self.label_status, 2, 0, 1, 3)

        right_layout.addWidget(group_serial)

        # 2. Configurazione coordinate e parametri radar
        group_geo = QGroupBox("PROIEZIONE GEOMETRICA")
        layout_geo = QGridLayout(group_geo)
        layout_geo.setContentsMargins(12, 15, 12, 12)
        layout_geo.setSpacing(8)

        layout_geo.addWidget(QLabel("Home Lat:"), 0, 0)
        self.edit_lat = QLineEdit(str(self.radar_widget.home_lat))
        layout_geo.addWidget(self.edit_lat, 0, 1)

        layout_geo.addWidget(QLabel("Home Lon:"), 1, 0)
        self.edit_lon = QLineEdit(str(self.radar_widget.home_lon))
        layout_geo.addWidget(self.edit_lon, 1, 1)

        self.check_auto_center = QCheckBox("Auto-centra sui target attivi")
        self.check_auto_center.setChecked(self.radar_widget.auto_center)
        layout_geo.addWidget(self.check_auto_center, 2, 0, 1, 2)

        layout_geo.addWidget(QLabel("Scala radar:"), 3, 0)
        self.combo_scale = QComboBox()
        self.combo_scale.addItems(["Auto-scale", "5 km", "15 km", "50 km", "100 km"])
        layout_geo.addWidget(self.combo_scale, 3, 1)

        right_layout.addWidget(group_geo)

        # 3. Tabella dei target
        group_targets = QGroupBox("AEREI TRACCIATI IN TEMPO REALE")
        layout_targets = QVBoxLayout(group_targets)
        layout_targets.setContentsMargins(6, 15, 6, 6)

        self.table_aircraft = QTableWidget(0, 6)
        self.table_aircraft.setHorizontalHeaderLabels(["ICAO", "Callsign", "Alt (ft)", "Vel (kt)", "Rotta", "Ultimo Rx"])
        self.table_aircraft.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_aircraft.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_aircraft.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout_targets.addWidget(self.table_aircraft)

        right_layout.addWidget(group_targets)

        main_splitter.addWidget(right_panel)
        main_splitter.setStretchFactor(0, 7)
        main_splitter.setStretchFactor(1, 3)

        self.scan_ports()

    def scan_ports(self):
        previous_selection = self.combo_port.currentText()
        self.combo_port.clear()

        smart_keywords = ["usb", "uart", "bridge", "cp21", "ftdi", "ch34", "arduino", "esp32", "silicon labs", "acm", "prolific"]
        ports = serial.tools.list_ports.comports()
        smart_ports = []

        for p in ports:
            dev_lower = p.device.lower()
            desc_lower = p.description.lower()
            hwid_lower = p.hwid.lower()

            if "bluetooth" in desc_lower or "bthenum" in hwid_lower:
                continue

            is_usb_chip = any(k in desc_lower or k in hwid_lower for k in smart_keywords)
            is_usb_path = p.device.startswith(("/dev/ttyUSB", "/dev/ttyACM", "/dev/cu.usb", "COM"))

            if is_usb_chip or is_usb_path:
                smart_ports.append(p)

        if not smart_ports:
            smart_ports = [p for p in ports if "bluetooth" not in p.description.lower()]

        for p in smart_ports:
            self.combo_port.addItem(p.device)

        index = self.combo_port.findText(previous_selection)
        if index >= 0:
            self.combo_port.setCurrentIndex(index)
        elif self.combo_port.count() > 0:
            self.combo_port.setCurrentIndex(0)

    def toggle_connection(self):
        if self.serial_thread and self.serial_thread.isRunning():
            self.serial_thread.stop()
            self.serial_thread = None
        else:
            port = self.combo_port.currentText()
            if not port:
                self.label_status.setText("Errore: Seleziona una porta seriale")
                return

            self.serial_thread = SerialWorker(port)
            self.serial_thread.packet_parsed.connect(self.handle_packet)
            self.serial_thread.status_changed.connect(self.handle_status_change)
            self.serial_thread.start()

    def handle_status_change(self, msg, connected):
        self.label_status.setText(f"Stato: {msg}")
        if connected:
            self.label_status.setStyleSheet("color: #00ff7f; font-weight: bold;")
            self.btn_connect.setText("DISCONNETTI")
        else:
            self.label_status.setStyleSheet("color: #ff5555; font-weight: bold;")
            self.btn_connect.setText("CONNETTI")

    def handle_packet(self, data):
        icao = data["icao"]
        now = datetime.now()

        if icao not in self.aircraft_data:
            self.aircraft_data[icao] = {}

        self.aircraft_data[icao].update(data)
        self.aircraft_data[icao]["last"] = now

        # Salva solo le coordinate grezze nello storico (lat, lon) per eliminare gli sfasamenti
        if "lat" in data and "lon" in data:
            history = self.aircraft_data[icao].get("history", [])
            pos = (data["lat"], data["lon"])
            if not history or history[-1] != pos:
                history.append(pos)
                if len(history) > 40:
                    history.pop(0)
                self.aircraft_data[icao]["history"] = history

    def update_gui_and_prune(self):
        now = datetime.now()
        expired = [
            icao for icao, d in self.aircraft_data.items()
            if (now - d["last"]).total_seconds() > TIMEOUT_SECONDS
        ]
        for icao in expired:
            del self.aircraft_data[icao]

        try:
            h_lat = float(self.edit_lat.text())
            h_lon = float(self.edit_lon.text())
        except ValueError:
            h_lat = 44.473328
            h_lon = 11.382953

        auto_ctr = self.check_auto_center.isChecked()

        scale_txt = self.combo_scale.currentText()
        if scale_txt == "Auto-scale":
            fixed_scale = 0.0
        else:
            fixed_scale = float(scale_txt.split(" ")[0])

        self.radar_widget.setData(self.aircraft_data, h_lat, h_lon, auto_ctr, fixed_scale)

        self.table_aircraft.setRowCount(0)
        for icao, d in self.aircraft_data.items():
            row = self.table_aircraft.rowCount()
            self.table_aircraft.insertRow(row)

            age = int((now - d["last"]).total_seconds())
            callsign = d.get("callsign", "N/A")
            alt = str(d.get("alt", "N/A"))
            speed = str(d.get("speed", "N/A"))
            heading = f"{d['heading']}°" if "heading" in d else "N/A"

            self.table_aircraft.setItem(row, 0, QTableWidgetItem(icao))
            self.table_aircraft.setItem(row, 1, QTableWidgetItem(callsign))
            self.table_aircraft.setItem(row, 2, QTableWidgetItem(alt))
            self.table_aircraft.setItem(row, 3, QTableWidgetItem(speed))
            self.table_aircraft.setItem(row, 4, QTableWidgetItem(heading))
            self.table_aircraft.setItem(row, 5, QTableWidgetItem(f"{age}s fa"))

            color = QColor(255, 255, 255)
            if age > 60:
                color = QColor(255, 100, 100)
            elif age > 15:
                color = QColor(255, 220, 100)

            for col in range(6):
                self.table_aircraft.item(row, col).setForeground(color)

    def closeEvent(self, event):
        if self.serial_thread and self.serial_thread.isRunning():
            self.serial_thread.stop()
        event.accept()

# =====================================================
# METODO DI AVVIO
# =====================================================
def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = RadarMainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()