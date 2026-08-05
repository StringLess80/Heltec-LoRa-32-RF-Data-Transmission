<div align="center">
  <a href="../../README.md">🇮🇹 Italiano</a> | <b>🇬🇧 English</b>
</div>

<a id="english"></a>
# EN - ADS‑B over LoRa — Heltec LoRa 32 V3 (v3.0)

![Version](https://img.shields.io/badge/Version-3.0-red)
![Platform](https://img.shields.io/badge/ESP32-Heltec%20V3-blue)
![Radio](https://img.shields.io/badge/LoRa-SX1262-green)
![Band](https://img.shields.io/badge/868%20MHz-EU-orange)
![Python](https://img.shields.io/badge/Python-3.10+-yellow)

### High-frequency and long-range transmission of ADS-B / Mode-S data via LoRa with Heltec ESP32 boards

---

### Overview

This project implements a complete ADS‑B → LoRa → ADS‑B bridge optimized for narrow-bandwidth radio channels with high update rates.

Aircraft messages decoded by `readsb` (or `dump1090`) are captured from the TCP SBS-1 stream on port 30003, analyzed and filtered by a software-level **Semantic Engine**, compressed into a compact proprietary binary protocol, transmitted over an 868 MHz LoRa link using two Heltec LoRa 32 V3 boards, and finally reconstructed on the receiver side to populate an interactive text-based radar TUI ordered by distance.

---

### 🚀 Semantic Engine v3.0 Architecture

At the core of the system is the **Event-Driven Semantic Engine**, designed to bypass the physical bandwidth constraints of LoRa channels without sacrificing telemetry precision.

```
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
                               +---> No meaningful change? -> DISCARD
                               |
                               +---> Change > Threshold? ----> GENERATE DELTA
                               |
                               +---> State Event (Squawk/Gnd)-> GENERATE EVENT
                               |
                               +---> 5s Timeout reached? -----> GENERATE FULL
                               |
                               v
                         [Dynamic Bitmasking]
                               |
                               v
                         [Pre-compiled Struct Packing]
                               | (Header & CRC16 generation)
                               v
                         [TX Queue (deque, maxlen=20)] ---> USB Serial -> LoRa
```

#### 1. Differential Analysis and State Machine
Instead of acting as a simple passthrough, the `python/tx/` transmitter maintains a state machine for each detected ICAO hex address. The semantic engine evaluates the physical derivatives of the following parameters compared to the last validated transmission:
* **Altitude (ALT):** Variations greater than $\ge 50$ feet.
* **Speed (VEL):** Variations greater than $\ge 5$ knots.
* **Heading (DIR):** Variations greater than $\ge 3$ degrees.
* **Coordinates (LAT/LON):** Displacements greater than $\ge 0.002$ degrees (approx. 220 meters).
* **Vertical Rate (VER):** Variations greater than $\ge 150$ feet/minute.

#### 2. Dynamic Bitmasking
If a parameter does not exceed its delta threshold, it is omitted from the serialization process entirely. The system dynamically generates a 16-bit field presence mask (*Bitmask*) embedded in the packet header. Each bit indicates the presence or absence of a specific field in the binary payload. This technique shrinks the typical frame size from the ~130 bytes of the original ASCII SBS-1 text down to only **18-40 bytes** in compressed format (reducing data overhead by 70-80%).

#### 3. Sync Frame (FULL) and Event Frame (EVENT) Management
* **DELTA Frame:** Contains only the physical parameters that have exceeded their delta threshold.
* **EVENT Frame:** Generated instantaneously when discrete, critical parameters change (e.g., *Squawk* code or *Ground State*).
* **FULL Frame (Heartbeat):** Transmitted periodically (every 5 seconds in high-frequency configuration) to send the complete aircraft status. This ensures that any receivers powered on at a later time can reconstruct full aircraft telemetries within moments.

---

### ⚡ Performance Optimizations v3.0

Version 3.0 introduces structural code updates aimed at maximizing system stability and throughput under heavy air-traffic scenarios:

* **Clean Modular Architecture & Separation of Concerns:** Python codebase split into specialized modules (`config`, `geo`, `tracker`, `ui`, `evaluator`, `encoder`, `fields_selector`) for improved maintainability.
* **Pre-compiled Binary Structures (`struct.Struct`):** Formatting strings for `struct.pack` and `struct.unpack` have been pre-compiled outside critical loops. Using pre-allocated `struct.Struct` instances avoids repeated parsing of binary templates, drastically reducing CPU usage.
* **Asynchronous Sliding Window Queue (`deque`):** To prevent Heltec microcontroller serial buffer congestion during traffic spikes, the transmitter uses a sliding window queue `collections.deque(maxlen=20)`. If the frame generation rate exceeds the physical LoRa transmission capacity (paced at a minimum 50ms delay), obsolete packets are automatically dropped in favor of the newest ones.
* **Sync and Selective Discarding:** In case of packet corruption over the receiving serial line (`python/rx/`), the parser discards only the current `0x55AA` sync marker and immediately realigns the buffer pointer to subsequent bytes, minimizing adjacent packet loss.
* **Receiver RAM Protection:** The serial receive buffer is rigidly capped at a maximum of 4096 bytes to prevent garbage accumulation and preserve system memory during long-term operations.

---

### 📡 Radar Tracking and Distance Algorithm (Haversine)

The `python/rx/` receiver features a floating-point implementation of the Haversine formula to compute real-time great-circle distances between each tracked aircraft and the ground receiver coordinates (`HOME_LAT`, `HOME_LON`):

$$\Delta\sigma = 2 \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta\phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta\lambda}{2}\right)}\right)$$

$$d = R \cdot \Delta\sigma$$

#### Features:
* **Dynamic Sorting by Distance:** The UI grid constantly sorts aircraft, placing the nearest ones at the top. Aircraft lacking valid GPS coordinates are placed at the bottom of the list in alphabetical ICAO order.
* **No Flashing Effects (Stable Layout):** Sorting prevents chaotic card rearranging on the TUI, keeping the interface stable and highly readable.
* **Graphical Pacing:** The Rich Live interface updates at 100ms intervals for regular telemetry updates, responding instantly (<10ms latency) to keyboard inputs for vertical scrolling.

---

### Firmware Update v2.1: OLED Monitoring & Interactivity

Version **2.1** of the firmware (fully compatible with the Python v3.0 backend) takes advantage of the built-in OLED display (SSD1306, 128x64) and the user **PRG** button (GPIO 0) on the Heltec V3. A real-time **3-page** system has been implemented.

#### Display Features on Receiver (RX):
* **Page 0 (Live Monitor):** Shows the total number of received packets, RSSI and SNR of the last packet, and payload size.
* **Page 1 (RSSI History):** A Cartesian graph plotting the signal strength (RSSI) of the last 20 received packets, with a dynamic scale from -120 to -40 dBm.
* **Page 2 (Configuration):** Displays current radio parameters (Frequency, Spreading Factor, Bandwidth, Coding Rate).

#### Display Features on Transmitter (TX):
* **Page 0 (TX Dashboard):** Shows the successful transmission count, the size of the last frame, and the status/error code of the SX1262 chip.
* **Page 1 (Serial Status):** Monitors the serial parser state (syncing phase on the `0x55AA` marker, bytes received vs expected).
* **Page 2 (Configuration):** Summary of radio parameters and transmission power (14 dBm).

#### Hardware Screenshot Capture:
By holding down the **PRG** button for more than 2 seconds, the ESP32 performs a dump of the screen memory (1024 bytes of frame buffer) and sends it over serial, protected by `---START_SCREENSHOT---` and `---END_SCREENSHOT---` tags. This allows you to save the exact Heltec screen directly to your PC as a `.png` file.

---

### OLED Screenshot Gallery (Heltec V3)

Below are the three monitoring screens available on the receiver's (RX) OLED, captured directly using the built-in screenshot feature.

<p align="center">
  <img src="screenshots/page0_monitor.png" width="30%" alt="Page 0 - Live Monitor" />
  <img src="screenshots/page1_graph.png" width="30%" alt="Page 1 - RSSI History Graph" />
  <img src="screenshots/page2_config.png" width="30%" alt="Page 2 - Radio Configuration" />
</p>

---

### Data Flow

```
Aircraft (ADS‑B 1090 MHz)
        ↓ 
RTL‑SDR Receiver
        ↓ 
readsb (TCP 127.0.0.1:30003)
        ↓
python/tx/tx.py (Semantic Engine + Compact Pre-compiled Serialization)
        ↓ 
USB Serial (115200 bps)
        ↓
Heltec LoRa 32 V3 (TX)  ← [OLED: TX Status / Configuration]
        ↓
LoRa 868 MHz (No Duty-Cycle Limit)
        ↓
Heltec LoRa 32 V3 (RX)  ← [OLED: Live Monitor / RSSI Graph / Configuration]
        ↓
USB Serial (115200 bps)
        ↓
python/rx/rx.py (Fast Decode + Distance Calculation + Sorted Dashboard)
```

---

### Why use readsb instead of dump1090?

Although the project works with dump1090, using readsb is highly recommended.

### Advantages

* Better handling of Mode‑S and ADS‑B messages
* More accurate decoding
* Better performance with a high number of aircraft
* More stable network output
* More active development and maintenance compared to dump1090

In real-world scenarios with heavy traffic, readsb generally produces more valid messages with fewer losses.

### Configuring readsb for SBS output on port 30003

Start readsb with the following command:

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

With this setup, the SBS-1 stream will be available on `127.0.0.1:30003`, which is the exact port used by the Python script.

---

### Why compress ADS-B data?

The SBS-1 format is text-based (ASCII) and contains a lot of redundancy.

Example message:

`MSG,3,111,11111,4CA123,111111,2026/08/02,10:15:21.123,2026/08/02,10:15:21.123,RYR8AB,37000,450,182,44.54,11.29,-64,0,0,0,0`

Typical size: 100–140 bytes

With LoRa set to SF7 / BW125 kHz / CR4:5, the useful throughput is limited, making the transmission of raw text extremely inefficient.

### Compression Strategy

* Field presence bitmask
* Typed binary fields (`struct.pack`)
* Fixed-length Callsign encoding
* Complete removal of CSV delimiters
* Integrity check via CRC16

### Typical Results

| Format           | Size       |
| ---------------- | ---------- |
| Original SBS‑1   | 90–140 B   |
| Compact Binary   | 18–40 B    |
| Size Reduction   | 65–80%     |

---

### Hardware

### Transmitter and Receiver

* 2 × Heltec LoRa 32 V3 (ESP32-S3 + SX1262)
* USB‑C cable connection

### ADS‑B Station

* Raspberry Pi or Linux PC
* RTL‑SDR USB Dongle
* Omnidirectional antenna tuned to 1090 MHz
* readsb (recommended) or dump1090

### LoRa Configuration

Default configuration in the firmware:

| Parameter        | Value     |
| ---------------- | --------- |
| Frequency        | 868.0 MHz |
| Spreading Factor | 7         |
| Bandwidth        | 125 kHz   |
| Coding Rate      | 4/5       |
| TX Power         | 14 dBm    |

---

### Heltec V3 Pin Mapping

The pin configuration includes the SX1262 LoRa module, OLED management, and hardware controls:

| Signal  | GPIO | Description |
| ------- | ---- | ----------- |
| **CS**  | 8    | SPI Chip Select (LoRa) |
| **DIO1**| 14   | Interrupt Pin (LoRa) |
| **RST** | 12   | Reset Pin (LoRa) |
| **BUSY**| 13   | Busy Status Pin (LoRa) |
| **SDA** | 17   | I2C Data (OLED) |
| **SCL** | 18   | I2C Clock (OLED) |
| **OLED RST** | 21| Reset (OLED) |
| **Vext**| 36   | Display Power (LOW = ON) |
| **PRG** | 0    | User / Boot Button (LOW = Pressed) |

---

### Software Components (Modular Python Architecture)

#### `python/tx/` (Transmitter Module)
* **`config.py`**: Constants, delta thresholds, timing parameters, pre-compiled binary structs, and SBS field mappings.
* **`fields_selector.py`**: Interactive CLI menu to select telemetry fields to transmit.
* **`evaluator.py`**: Semantic Engine evaluating deltas and frame generation logic (FULL/DELTA/EVENT).
* **`encoder.py`**: Binary payload serializer with sequence number tracking and CRC32 checksums.
* **`tracker.py`**: Aircraft state tracker, fast SBS line parser, and garbage collector for inactive targets.
* **`tx.py`**: Transmitter entry point: Dump1090/readsb socket management, serial connection, and TX queuing.

#### `python/rx/` (Receiver Module)
* **`config.py`**: Home station location parameters, timeouts, and binary protocol definitions.
* **`geo.py`**: Great-circle distance calculations via Haversine formula.
* **`input_handler.py`**: Cross-platform non-blocking keyboard input listener (Windows/Linux/macOS).
* **`tracker.py`**: LoRa binary packet parser and active aircraft state management.
* **`ui.py`**: Interactive Rich Live TUI layout rendering (aircraft cards, responsive grid, scrolling).
* **`rx.py`**: Receiver entry point: Serial stream reader, parser loop, and UI refresh loop.

---

### Installation

### 1. Install readsb

On Debian-based systems or Raspberry Pi OS:

```bash
sudo apt update
sudo apt install readsb
```

### 2. Clone the repository

```bash
git clone https://github.com/StringLess80/Heltec-LoRa-32-RF-Data-Transmission.git
cd Heltec-LoRa-32-RF-Data-Transmission
```

### 3. Install Python dependencies

Install the required libraries via pip (using a virtual environment `venv` is recommended):

```bash
pip install -r requirements.txt
```

### 4. Flash the Heltec boards

1. Open the Arduino IDE and install the board support packages for **ESP32** (Heltec) along with the **RadioLib** and **U8g2** libraries from the Library Manager.
2. Connect the boards and upload the respective firmware:
   * Upload `firmware/tx/tx.ino` to the transmitting Heltec board.
   * Upload `firmware/rx/rx.ino` to the receiving Heltec board.

---

### System Startup

### 1. Start the receiver (Display side)

Navigate to the receiver directory and run the main entry point:

```bash
cd python/rx
python3 rx.py
```

### 2. Start the transmitter (RTL-SDR side)

Open another terminal on the machine connected to the SDR, navigate to the transmitter directory, and run the main entry point:

```bash
cd python/tx
python3 tx.py
```