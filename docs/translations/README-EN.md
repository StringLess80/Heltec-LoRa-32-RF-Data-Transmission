<div align="center">
  <a href="../../README.md">🇮🇹 Italiano</a> | <b>🇬🇧 English</b>
</div>

<a id="english"></a>
# EN - ADS‑B over LoRa — Heltec LoRa 32 V3 (v4.0)

![Version](https://img.shields.io/badge/Version-4.0-purple)
![Platform](https://img.shields.io/badge/ESP32-Heltec%20V3-blue)
![Radio](https://img.shields.io/badge/LoRa-SX1262-green)
![Band](https://img.shields.io/badge/868%20MHz-EU-orange)
![Python](https://img.shields.io/badge/Python-3.10+-yellow)

### High-frequency, long-range transmission of ADS‑B / Mode‑S data via LoRa using Heltec ESP32 boards and Tactical Control Center Web

---

### Overview

This project implements a complete **ADS‑B → LoRa → ADS‑B / Web Control Center** bridge optimized for narrow-band radio channels and high refresh rates.

Aircraft messages decoded by `readsb` (or `dump1090`) are captured from the SBS-1 TCP stream on port 30003, parsed and filtered by a software-level **Semantic Engine**, compressed into a compact proprietary binary protocol, transmitted via LoRa at 868 MHz using two Heltec LoRa 32 V3 boards, and finally reconstructed at the receiver.

Version **4.0** introduces a **Full-Stack Tactical Control Center in Python/Flask**, an advanced vector mapping interface, tactical traffic assignment to ground controllers via the **Zenith Blind Cone Algorithm**, and native decoding for an **NMEA 0183 Serial GPS**.

---

### 🚀 Semantic Engine v3.0 Architecture

The core of the system is the event-driven **Semantic Engine**, developed to overcome the physical bandwidth limits of the LoRa channel without sacrificing telemetry precision.

```text
+-------------------------------------------------------------------------+
|                         SEMANTIC ENGINE (TX)                            |
+-------------------------------------------------------------------------+
   | (SBS-1 TCP Stream)
   v
[SBS-1 Parser] --------> [State Database (ICAO Hex)]
                               | (Delta & Threshold Comparison)
                               v
                         [Differential Filter]
                               |
                               +---> No significant changes? -> DISCARD
                               |
                               +---> Change > Threshold? ------> GENERATE DELTA
                               |
                               +---> State Event (Squawk/Gnd) -> GENERATE EVENT
                               |
                               +---> 5s Timeout reached? -------> GENERATE FULL
                               |
                               v
                         [Dynamic Bitmasking]
                               |
                               v
                         [Pre-compiled Struct Packing]
                               | (Append Header & CRC32/CRC16)
                               v
                         [TX Queue (deque, maxlen=20)] ---> USB Serial -> LoRa
```

#### 1. Differential Analysis and State Machine
Instead of operating as a simple pass-through, the transmitter (`python/tx/`) maintains an in-memory state machine for every detected ICAO address. The semantic engine evaluates the physical derivatives of the following parameters compared to the last validated transmission:
* **Altitude (ALT):** Changes greater than or equal to $\ge 50$ feet.
* **Speed (VEL):** Changes greater than or equal to $\ge 5$ knots.
* **Heading (DIR):** Changes greater than or equal to $\ge 3$ degrees.
* **Coordinates (LAT/LON):** Displacement greater than $\ge 0.002$ degrees (~220 meters).
* **Vertical Rate (VER):** Changes greater than or equal to $\ge 150$ feet/minute.

#### 2. Dynamic Bitmasking
If a parameter does not exceed its variance threshold, it is omitted from serialization. The system dynamically generates a 16-bit Bitmask included in the packet header. Each bit indicates the presence or absence of a specific field in the binary payload. This reduces frame sizes from ~130 bytes (original SBS-1 text) down to **18–40 bytes** in compressed format (70–80% overhead reduction).

#### 3. Handling Synchronization (FULL) and Event (EVENT) Frames
* **DELTA Frames:** Contain only physical parameters that have crossed tolerance thresholds.
* **EVENT Frames:** Instantly generated when critical discrete parameters change, such as *Squawk* codes or ground state (*Ground State*).
* **FULL Frames (Heartbeat):** Periodically transmitted (every 5 seconds under high-frequency configuration) to send the complete aircraft status. This ensures that any receivers tuning in later can reconstruct full telemetry within moments.

---

### 🎨 What's New in v4.0: Tactical Control Center

The **v4.0** update transforms the receiver station into a full-fledged **Web Tactical Control Center**:

* **Leaflet.js Vector Mapping (60 FPS):** Dynamic SVG aircraft markers rotating in real time based on Heading (`DIR`). When selected, the icon turns **Neon Purple (`#af52de`)**, opening the detailed Inspector and drawing the line vector towards the assigned controller.
* **NMEA 0183 Serial GPS Integration:** Native decoding module for serial GPS (`$GPGGA`, `$GPRMC`, `$GPGLL`) displaying a bright fluorescent green marker with an animated radar pulse effect at the station's coordinates.
* **Ground Tactical Controller Management:** Instant addition and removal of controllers on the map with dynamic updating of air traffic assignments and JSON diffing on the DOM.
* **RF Engine Graph:** Integrated SVG vector graph displaying real-time received LoRa packet frequency per second with a green neon styling.
* **Persistence:** System configuration (`config.json`) is saved using absolute paths and `os.fsync()` to force physical disk writes. Automatic configuration file regeneration if missing.

---

### ⚡ Performance Optimizations v3.0 & v4.0

Versions 3.0 and 4.0 introduce key structural optimizations to ensure maximum system fluidity and stability under dense air traffic flows:

* **Modular Architecture and Separation of Concerns:** Python codebase reorganized into modular packages (`core`, `protocol`, `services`, `routes`, `static`, `templates`) for maintainability and clean structure.
* **Pre-compilation of Binary Structures (`struct.Struct`):** Compilation of `struct.pack` and `struct.unpack` format strings is executed outside critical RX/TX loops. Pre-allocated `struct.Struct` instances eliminate repeated binary template parsing, significantly lowering CPU utilization.
* **Sliding-Window Asynchronous Queue (`deque`):** To prevent buffer congestion on the Heltec microcontroller serial port during traffic spikes, the transmitter uses an asynchronous queue (`collections.deque(maxlen=20)`). If frame generation rate exceeds the physical radio output capacity (paced with a minimum 50ms delay), stale packets are dropped automatically in favor of newer telemetry.
* **Sync Recovery and Selective Discarding:** Upon serial packet corruption at the receiver (`python/rx/` or `serial_service.py`), the parser drops only the current `0xAA55` / `0x55AA` sync marker and immediately realigns the buffer pointer to subsequent bytes, minimizing frame loss.
* **Receiver RAM Protection:** Serial RX buffer is strictly capped at 4096 bytes to prevent noise/garbage accumulation and preserve memory stability over long continuous runtimes.

---

### 📡 Radar Tracking Algorithm & Haversine Distance

The receiver implements a floating-point version of the Haversine formula to compute real-time orthodromic distance between each detected aircraft and ground station coordinates (`HOME_LAT`, `HOME_LON`):

$$\Delta\sigma = 2 \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta\phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta\lambda}{2}\right)}\right)$$

$$d = R \cdot \Delta\sigma$$

#### Key Features:
* **Dynamic Distance Sorting:** Aircraft lists and grid displays are continuously sorted, putting the nearest aircraft at the top. Vehicles lacking valid GPS coordinates are placed at the bottom sorted alphabetically by ICAO.
* **Flicker-Free Layout:** Dynamic updates avoid chaotic UI re-rendering on both the TUI and Web Dashboard, ensuring a stable, readable layout.
* **Graphical Pacing:** SocketIO Web Interface and Rich Live TUI refresh at controlled 100ms intervals for regular telemetry, guaranteeing smooth 60 FPS performance without system lag.

---

### ⚡ Compact ADS-B over LoRa Binary Radio Protocol

To maximize updates per second over LoRa, message structures use an ultra-compact serialized binary format protected by a CRC32 checksum.

#### Packet Header & Footer:
* **Header (7 Bytes):** `SYNC 0xAA55` (uint16), `seq` (uint16), `mask` (uint16), `payload_len` (uint8).
* **Footer (2 Bytes):** CRC32 Checksum (lower 16-bit) calculated over Header + Payload.

#### Payload Fields ordered by Bitmask:
* **Bit 0:** `ICAO` (4 Bytes - uint32 hex)
* **Bit 1:** `Callsign` (8 Bytes - ASCII string padded with `\x00`)
* **Bit 2:** `Altitude` (2 Bytes - uint16)
* **Bit 3:** `Speed` (2 Bytes - uint16)
* **Bit 4:** `Heading` (2 Bytes - uint16)
* **Bit 5:** `Latitude` (4 Bytes - int32 $deg \times 10^7$)
* **Bit 6:** `Longitude` (4 Bytes - int32 $deg \times 10^7$)
* **Bit 7:** `Vertical Rate` (2 Bytes - int16)

---

### Firmware v2.1 Highlights: OLED Monitoring & Interactivity

Firmware version **2.1** (fully compatible with Python backend v3.0/v4.0) takes advantage of Heltec V3's onboard OLED screen (SSD1306, 128x64) and the user button **PRG** (GPIO 0). It introduces a **3-page real-time status monitor**.

#### Receiver (RX) Display Pages:
* **Page 0 (Live Monitor):** Displays total received packets, RSSI and SNR of the latest frame, and payload size.
* **Page 1 (RSSI History):** Cartesian line graph displaying RSSI trends across the last 20 received packets, scaled dynamically from -120 to -40 dBm.
* **Page 2 (Configuration):** Displays current radio parameters (Frequency, Spreading Factor, Bandwidth, Coding Rate).

#### Transmitter (TX) Display Pages:
* **Page 0 (TX Dashboard):** Displays successful transmission counts, payload size of the last frame, and SX1262 status/error codes.
* **Page 1 (Serial Status):** Monitors serial parser status (sync state on `0x55AA`/`0xAA55` markers, received and expected byte counts).
* **Page 2 (Configuration):** Radio setup summary and output power setting (14 dBm).

#### Hardware OLED Screen Capture:
Holding down the **PRG** button for more than 2 seconds triggers an onboard frame buffer dump (1024 bytes). The ESP32 outputs the raw data over serial enclosed in `---START_SCREENSHOT---` and `---END_SCREENSHOT---` tags, allowing exact OLED screens to be saved on the host PC in `.png` format.

---

### OLED Screen Gallery (Heltec V3)

Below are the three real-time monitoring screens on the receiver OLED display, captured directly via the built-in screenshot utility.

<p align="center">
  <img src="../../screenshots/page0_monitor.png" width="30%" alt="Page 0 - Live Monitor" />
  <img src="../../screenshots/page1_graph.png" width="30%" alt="Page 1 - RSSI History Graph" />
  <img src="../../screenshots/page2_config.png" width="30%" alt="Page 2 - Radio Setup" />
</p>

---

### Data Flow

```text
Aircraft (ADS‑B 1090 MHz)
        ↓ 
RTL‑SDR Receiver
        ↓ 
readsb (TCP 127.0.0.1:30003)
        ↓
python/tx/tx.py (Semantic Engine + Compact Binary Precompiled Serialization)
        ↓ 
USB Serial (115200 bps)
        ↓
Heltec LoRa 32 V3 (TX)  ← [OLED: TX Status / Configuration]
        ↓
LoRa 868 MHz (No Duty-Cycle Limit)
        ↓
Heltec LoRa 32 V3 (RX)  ← [OLED: Live Monitor / RSSI Graph / Configuration]
        ↓
USB Serial (115200 bps - DTR/RTS Handled)
        ↓
[ Tactical Control Center Flask / SocketIO ]
        ├──> LoRa Decoding & NMEA Serial GPS Parser
        ├──> Zenith Blind Cone Calculation & Controller Routing
        └──> 2D Leaflet Map & Web Dashboard
```

---

### Why use readsb instead of dump1090?

While the project works with `dump1090`, using `readsb` is highly recommended.

#### Key Advantages
* Better handling of Mode‑S and ADS‑B messages
* More accurate message decoding
* Superior performance under high aircraft density
* Stable network output implementation
* Active ongoing development compared to legacy dump1090

Under heavy real-world traffic, readsb consistently yields more valid frames with lower packet loss.

#### Configuring readsb for SBS Output on Port 30003

Start `readsb` using the following command:

```bash
sudo readsb \
  --device-type rtlsdr \
  --device 0 \
  --gain auto \
  --lat <RECEIVER_LAT> \
  --lon <RECEIVER_LON> \
  --net \
  --net-bind-address 127.0.0.1 \
  --net-sbs-port 30003
```

Replace:
* `<RECEIVER_LAT>` with your receiver's latitude (e.g., `41.130000`)
* `<RECEIVER_LON>` with your receiver's longitude (e.g., `13.022000`)

This configuration streams SBS-1 formatted data on `127.0.0.1:30003`, matching the default TCP input expected by the Python script.

---

### Why compress ADS‑B data?

The SBS-1 message structure is text-based (ASCII) and highly redundant.

Example message:
`MSG,3,111,11111,4CA123,111111,2026/08/02,10:15:21.123,2026/08/02,10:15:21.123,RYR8AB,37000,450,182,44.54,11.29,-64,0,0,0,0`

Typical size: 100–140 bytes.

On LoRa channels using SF7 / BW125 kHz / CR4:5, channel throughput is strictly constrained. Transmitting raw ASCII strings would cause severe congestion.

#### Compression Strategy
* Bitmask field presence indicators
* Typed binary packing (`struct.pack`)
* Fixed-length Callsign encoding
* Stripping of CSV string delimiters
* Integrity checks via CRC32/CRC16

#### Compression Results

| Format           | Size     |
| ---------------- | -------- |
| Original SBS‑1   | 90–140 B |
| Compact Binary   | 18–40 B  |
| Reduction        | 65–80%   |

---

### Hardware Requirements

#### Transmitter & Receiver
* 2 × Heltec LoRa 32 V3 (ESP32-S3 + SX1262)
* Connection via USB‑C cable (DTR/RTS signal handling implemented to prevent auto-resets on USB-CDC serial connection)
* Optional: Serial NMEA 0183 GPS Module

#### ADS-B Ground Station
* Raspberry Pi or Linux PC
* RTL‑SDR USB Dongle
* Omnidirectional antenna tuned to 1090 MHz
* readsb (recommended) or dump1090

#### Default LoRa Configuration
Default settings configured in firmware:

| Parameter        | Value     |
| ---------------- | --------- |
| Frequency        | 868.0 MHz |
| Spreading Factor | 7         |
| Bandwidth        | 125 kHz   |
| Coding Rate      | 4/5       |
| TX Power         | 14 dBm    |

---

### Heltec V3 Pinout Mapping

Hardware mapping for the SX1262 LoRa module, OLED display, and system controls:

| Signal  | GPIO | Description |
| ------- | ---- | ----------- |
| **CS**  | 8    | SPI Chip Select (LoRa) |
| **DIO1**| 14   | Interrupt Pin (LoRa) |
| **RST** | 12   | Reset Pin (LoRa) |
| **BUSY**| 13   | Busy Status Pin (LoRa) |
| **SDA** | 17   | I2C Data (OLED) |
| **SCL** | 18   | I2C Clock (OLED) |
| **OLED RST** | 21| Reset (OLED) |
| **Vext**| 36   | Display Power Control (LOW = ON) |
| **PRG** | 0    | User Button / Boot (LOW = Pressed) |

---

### Software Architecture

#### 1. Full-Stack Web Tactical Control Center (`adsb_lora_app/`):
* **`app.py`**: Flask entry point & SocketIO WebSockets (`async_mode='threading'`).
* **`config.json`**: Persistent storage configuration flushed using `os.fsync`.
* **`core/state.py`**: In-memory system state engine (`system_state`, `aircraft_db`).
* **`core/config_manager.py`**: Config loader/saver with automatic file regeneration fallback.
* **`core/math_tactical.py`**: Haversine geodesy, elevation angles, and Zenith Blind Cone math.
* **`protocol/nmea_parser.py`**: Native NMEA 0183 parser (`$GPGGA`, `$GPRMC`, `$GPGLL`).
* **`protocol/lora_encoder.py`**: Binary encoder/decoder (Header 0xAA55 + Bitmask + Payload + CRC32).
* **`services/serial_service.py`**: Physical serial management with DTR/RTS fixes for ESP32-S3 and GPS input.
* **`services/adsb_service.py`**: Dump1090 TCP worker, inactivity timeouts, and LoRa RX/TX Loops.
* **`routes/api.py`**: REST API endpoints for system state, controller list, and dynamic configuration.
* **`static/css/style.css`**: Dark Tactical UI design system styling.
* **`static/js/app.js`**: Leaflet.js map controller, WebSockets handler, 60fps SVG marker rotation, and UI events.
* **`templates/index.html`**: Web Dashboard HTML layout.

#### 2. CLI Tools & Utilities (`python/`):
* **`python/tx/`**: CLI Transmitter (`tx.py`, `evaluator.py`, `encoder.py`, `tracker.py`, `fields_selector.py`).
* **`python/rx/`**: CLI Receiver with Rich TUI interface (`rx.py`, `ui.py`, `geo.py`, `tracker.py`, `input_handler.py`).

---

### Installation

#### 1. Install readsb
On Debian-based Linux or Raspberry Pi OS:
```bash
sudo apt update
sudo apt install readsb
```

#### 2. Clone the repository
```bash
git clone https://github.com/StringLess80/Heltec-LoRa-32-RF-Data-Transmission.git
cd Heltec-LoRa-32-RF-Data-Transmission
```

#### 3. Install Python dependencies
Set up dependencies using pip (a virtual environment is recommended):
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 4. Flash Heltec Microcontrollers
1. Open Arduino IDE and install **ESP32** platform support along with the **RadioLib** and **U8g2** libraries via the Library Manager.
2. Connect boards and flash their target code:
   * Upload `firmware/tx/tx.ino` to the transmitting Heltec board.
   * Upload `firmware/rx/rx.ino` to the receiving Heltec board.

---

### System Execution

#### Option A: Running with Tactical Control Center Web Interface (Recommended v4.0)

1. Launch the Flask Web Application:
   ```bash
   python3 app.py
   ```
2. Open your browser and navigate to `http://localhost:5000`.
3. In the top navigation bar:
   * Select the serial port connected to the **Heltec V3** board.
   * Select the serial port for your **GPS** module (if available).
   * Toggle the **TX** switch to enable RF retransmission.
4. **Start the TUI Receiver (Display console):**
   ```bash
   cd python/rx
   python3 rx.py
   ```

#### Option B: Running via CLI / TUI Interface (v3.0)

1. **Start the TUI Receiver (Display console):**
   ```bash
   cd python/rx
   python3 rx.py
   ```

2. **Start the CLI Transmitter (RTL‑SDR feeder):**
   ```bash
   cd python/tx
   python3 tx.py
   ```