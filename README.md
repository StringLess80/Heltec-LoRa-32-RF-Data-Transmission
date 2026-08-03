***

<div align="center">
  <a href="#italiano">🇮🇹 Italiano</a> | <a href="#english">🇬🇧 English</a>
</div>

---

<a id="italiano"></a>
# 🇮🇹 ADS‑B over LoRa — Heltec LoRa 32 V3 (v2.1)

![Version](https://img.shields.io/badge/Version-2.1-red)
![Platform](https://img.shields.io/badge/ESP32-Heltec%20V3-blue)
![Radio](https://img.shields.io/badge/LoRa-SX1262-green)
![Band](https://img.shields.io/badge/868%20MHz-EU-orange)
![Python](https://img.shields.io/badge/Python-3.10+-yellow)

### Trasmissione a lunga distanza di dati ADS‑B / Mode‑S tramite LoRa con schede Heltec ESP32

### Panoramica

Questo progetto implementa un bridge completo ADS‑B → LoRa → ADS‑B pensato per collegamenti radio a lunga distanza e bassa larghezza di banda.

I messaggi degli aeromobili decodificati da readsb (o dump1090) vengono acquisiti dal flusso SBS‑1 / BaseStation TCP sulla porta 30003, compressi in un protocollo binario compatto, trasmessi tramite un collegamento LoRa 868 MHz usando due schede Heltec LoRa 32 V3 (ESP32 + SX1262) e ricostruiti sul lato ricevente per una visualizzazione in tempo reale.

Il sistema è ottimizzato per:

* Efficienza di banda
* Lunga portata
* Bassa latenza
* Monitoraggio visivo locale tramite display OLED integrato
* Framing robusto e validazione dei pacchetti

---

### Novità Firmware v2.1: Monitoraggio OLED & Interattività

La versione **2.1** del firmware sfrutta il display OLED integrato (SSD1306, 128x64) e il pulsante utente **PRG** (GPIO 0) di Heltec V3. È stato implementato un sistema a **3 pagine** consultabili in tempo reale.

#### Funzionalità Display sul Ricevitore (RX):
* **Pagina 0 (Live Monitor):** Mostra il numero totale di pacchetti ricevuti, l'RSSI e l'SNR dell'ultimo pacchetto, e la dimensione del payload.
* **Pagina 1 (Storico RSSI):** Un grafico cartesiano che traccia l'andamento del segnale (RSSI) degli ultimi 20 pacchetti ricevuti, con scala dinamica da -120 a -40 dBm.
* **Pagina 2 (Configurazione):** Mostra i parametri attuali della radio (Frequenza, Spreading Factor, Bandwidth, Coding Rate).

#### Funzionalità Display sul Trasmettitore (TX):
* **Pagina 0 (TX Dashboard):** Mostra la conta dei pacchetti trasmessi con successo, la dimensione dell'ultimo frame e lo stato/codice di errore del chip SX1262.
* **Pagina 1 (Stato Seriale):** Monitora lo stato del parser seriale (fase di sincronizzazione sul marcatore `0x55AA`, byte ricevuti e attesi).
* **Pagina 2 (Configurazione):** Riepilogo dei parametri radio e potenza di trasmissione (14 dBm).

#### Cattura Screenshot Hardware (OLED Capture):
Tenendo premuto il pulsante **PRG** per più di 2 secondi, l'ESP32 esegue un dump della memoria dello schermo (1024 byte di frame buffer) e lo invia via seriale protetto dai tag `---START_SCREENSHOT---` e `---END_SCREENSHOT---`, consentendo di salvare l'esatta schermata dell'Heltec direttamente sul PC in formato `.png`.

---

### Galleria Schermate OLED (Heltec V3)

Di seguito sono mostrate le tre schermate di monitoraggio disponibili sull'OLED del ricevitore (RX), catturate direttamente tramite la funzione di screenshot integrata.

<p align="center">
  <img src="screenshots/page0_monitor.png" width="30%" alt="Pagina 0 - Live Monitor" />
  <img src="screenshots/page1_graph.png" width="30%" alt="Pagina 1 - Grafico Storico RSSI" />
  <img src="screenshots/page2_config.png" width="30%" alt="Pagina 2 - Configurazione Radio" />
</p>

---

### Flusso dei dati

```
Aeromobile (ADS‑B 1090 MHz)
        ↓ 
Ricevitore RTL‑SDR
        ↓ 
readsb (TCP 127.0.0.1:30003)
        ↓
python/tx/tx.py (parsing + serializzazione compatta)
        ↓ 
Seriale USB (115200 bps)
        ↓
Heltec LoRa 32 V3 (TX)  ← [OLED: Stato TX / Configurazione]
        ↓
LoRa 868 MHz
        ↓
Heltec LoRa 32 V3 (RX)  ← [OLED: Live Monitor / Grafico RSSI / Configurazione]
        ↓
Seriale USB (115200 bps)
        ↓
python/rx/rx.py (decodifica + dashboard)
```

---

### Perché usare readsb invece di dump1090?

Sebbene il progetto funzioni anche con dump1090, è fortemente consigliato usare readsb.

### Vantaggi

* Migliore gestione dei messaggi Mode‑S e ADS‑B
* Decodifica più accurata
* Migliori prestazioni con molti aeromobili
* Output di rete più stabile
* Sviluppo e manutenzione più attivi rispetto a dump1090

In scenari reali con traffico intenso, readsb produce generalmente più messaggi validi e con minori perdite.

### Configurare readsb per l’output SBS sulla porta 30003

Avvia readsb con il seguente comando:

```bash
sudo readsb \
  --device-type rtlsdr \
  --device 0 \
  --gain auto \
  --lat <LAT_RICEVITORE> \
  --lon <LON_RICEVITORE> \
  --net \
  --net-bind-address 127.0.0.1 \
  --net-sbs-port 30003
```

Sostituisci:

* `<LAT_RICEVITORE>` con la latitudine del tuo ricevitore (es. `41.130000`)
* `<LON_RICEVITORE>` con la longitudine del tuo ricevitore (es. `13.022000`)

Con questa configurazione il flusso SBS‑1 sarà disponibile su `127.0.0.1:30003`, che è esattamente la porta utilizzata dallo script python.

### Utilizzo di un GPS

Le coordinate del ricevitore possono essere inserite manualmente nel comando precedente, ma è possibile anche utilizzare un modulo GPS collegato al Raspberry Pi o al PC Linux. In quel caso le coordinate possono essere recuperate automaticamente e passate a readsb.

---

### Perché comprimere i dati ADS‑B?

Il formato SBS‑1 è testuale (ASCII) e contiene molta ridondanza.

Esempio di messaggio:

`MSG,3,111,11111,4CA123,111111,2026/08/02,10:15:21.123,2026/08/02,10:15:21.123,RYR8AB,37000,450,182,44.54,11.29,-64,0,0,0,0`

Dimensione tipica: 100–140 byte

Con LoRa a SF7 / BW125 kHz / CR4:5 il throughput utile è di pochi kbit/s, quindi trasmettere il testo completo sarebbe estremamente inefficiente.

### Strategia di compressione

* Bitmask di presenza dei campi
* Campi binari tipizzati (`struct.pack`)
* Codifica del Callsign a lunghezza fissa
* Rimozione completa dei delimitatori CSV
* Controllo d'integrità tramite CRC16

### Risultato tipico

| Formato          | Dimensione |
| ---------------- | ---------- |
| SBS‑1 originale  | 90–140 B   |
| Binario compatto | 18–40 B    |
| Riduzione        | 65–80%     |

---

### Hardware

### Trasmettitore e ricevitore

* 2 × Heltec LoRa 32 V3 (ESP32-S3 + SX1262)
* Collegamento tramite cavo USB‑C

### Stazione ADS‑B

* Raspberry Pi o PC Linux
* Dongle USB RTL‑SDR
* Antenna omnidirezionale tarata a 1090 MHz
* readsb (consigliato) o dump1090

### Configurazione LoRa

Configurazione predefinita nel firmware:

| Parametro        | Valore    |
| ---------------- | --------- |
| Frequenza        | 868.0 MHz |
| Spreading Factor | 7         |
| Banda            | 125 kHz   |
| Coding Rate      | 4/5       |
| Potenza TX       | 14 dBm    |


### Compromessi

| Modifica | Effetto                                 |
| -------- | --------------------------------------- |
| SF ↑     | Maggiore portata, minore throughput     |
| BW ↑     | Maggiore throughput, minore sensibilità |
| CR ↑     | Maggiore robustezza, maggiore airtime   |


### Mappatura pin Heltec V3

La configurazione dei pin include sia il modulo LoRa SX1262, sia la gestione dell'OLED e dei controlli hardware:

| Segnale | GPIO | Descrizione |
| ------- | ---- | ----------- |
| **CS**  | 8    | SPI Chip Select (LoRa) |
| **DIO1**| 14   | Interrupt Pin (LoRa) |
| **RST** | 12   | Reset Pin (LoRa) |
| **BUSY**| 13   | Busy Status Pin (LoRa) |
| **SDA** | 17   | I2C Data (OLED) |
| **SCL** | 18   | I2C Clock (OLED) |
| **OLED RST** | 21| Reset (OLED) |
| **Vext**| 36   | Alimentazione Display (LOW = ON) |
| **PRG** | 0    | Pulsante Utente / Boot (LOW = Premuto) |

---

### Componenti software

### `python/tx/tx.py`

Responsabilità:
* Connessione socket a `127.0.0.1:30003` (flusso readsb)
* Parsing dei messaggi SBS-1 testuali
* Selezione ed estrazione dei campi validi
* Serializzazione binaria compatta tramite `struct.pack`
* Calcolo del CRC16 di verifica
* Invio dei frame tramite connessione seriale alla scheda Heltec TX

### `python/rx/rx.py`

Responsabilità:
* Lettura non bloccante della seriale della scheda Heltec RX
* Sincronizzazione sul marker di inizio frame `0x55AA`
* Validazione del checksum CRC16
* Decodifica del payload binario compatto
* Mantenimento e aggiornamento in tempo reale del database interno degli aeromobili
* Rimozione automatica dei velivoli non più attivi (timeout di 150 secondi)
* Rendering grafico della dashboard nel terminale con aggiornamento reattivo (libreria Rich)


### Dashboard in tempo reale

La dashboard è disegnata per adattarsi in tempo reale al vostro terminale, disponendo le informazioni in una comoda vista a griglia auto-impaginata.

Funzionalità incluse:
* Una scheda informativa compatta per ogni velivolo tracciato
* Layout a griglia auto-adattivo alla larghezza della finestra
* Timer "last seen" aggiornato costantemente
* Gestione dello scorrimento verticale (tramite tasti Freccia o tasti `W`/`S`) per visualizzare decine di aerei contemporaneamente
* Refresh intelligente ed estremamente reattivo per evitare sfarfallii dello schermo

---

### Installazione

### 1. Installare readsb

Su sistemi operativi Debian-based o Raspberry Pi OS:

```bash
sudo apt update
sudo apt install readsb
```

### 2. Clonare la repository

```bash
git clone https://github.com/StringLess80/Heltec-LoRa-32-RF-Data-Transmission.git
cd Heltec-LoRa-32-RF-Data-Transmission
```

### 3. Installare le dipendenze Python

Installare le librerie necessarie tramite pip (si consiglia l'utilizzo di un ambiente virtuale `venv`):

```bash
pip install -r requirements.txt
```

### 4. Flashare le schede Heltec

1. Apri l'Arduino IDE e installa i pacchetti di supporto per schede **ESP32** (Heltec) e le librerie **RadioLib** e **U8g2** dal Gestore Librerie.
2. Collega le schede e carica i rispettivi firmware:
   * Carica `firmware/tx/tx.ino` sulla scheda Heltec trasmittente.
   * Carica `firmware/rx/rx.ino` sulla scheda Heltec ricevente.

### Avvio del sistema

### 1. Avviare il ricevitore (lato visualizzazione)

Spostati nella directory degli script ed esegui lo script di ricezione:

```bash
cd python/rx
python3 rx.py
```

### 2. Avviare il trasmettitore (lato RTL‑SDR)

Apri un altro terminale sulla macchina connessa all'SDR e avvia lo script di trasmissione:

```bash
cd python/tx
python3 tx.py
```

Le prestazioni generali possono variare in base al rumore elettromagnetico circostante, alla vicinanza tra i nodi, alla potenza impostata e alla velocità di elaborazione della porta seriale USB.

<br><br>

---

<a id="english"></a>
# 🇬🇧 ADS‑B over LoRa — Heltec LoRa 32 V3 (v2.1)

![Version](https://img.shields.io/badge/Version-2.1-red)
![Platform](https://img.shields.io/badge/ESP32-Heltec%20V3-blue)
![Radio](https://img.shields.io/badge/LoRa-SX1262-green)
![Band](https://img.shields.io/badge/868%20MHz-EU-orange)
![Python](https://img.shields.io/badge/Python-3.10+-yellow)

<div align="center">
  <a href="#italiano">↑ Back to Italian</a>
</div>

### Long-range transmission of ADS-B / Mode-S data via LoRa with Heltec ESP32 boards

### Overview

This project implements a complete ADS‑B → LoRa → ADS‑B bridge designed for long-range, low-bandwidth radio links.

Aircraft messages decoded by readsb (or dump1090) are acquired from the SBS‑1 / BaseStation TCP stream on port 30003, compressed into a compact binary protocol, transmitted over an 868 MHz LoRa link using two Heltec LoRa 32 V3 boards (ESP32 + SX1262), and reconstructed on the receiving side for real-time visualization.

The system is optimized for:

* Bandwidth efficiency
* Long range
* Low latency
* Local visual monitoring via integrated OLED display
* Robust framing and packet validation

---

### Firmware Update v2.1: OLED Monitoring & Interactivity

Version **2.1** of the firmware takes full advantage of the built-in OLED display (SSD1306, 128x64) and the user **PRG** button (GPIO 0) on the Heltec V3. A real-time **3-page** system has been implemented.

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
python/tx/tx.py (parsing + compact serialization)
        ↓ 
USB Serial (115200 bps)
        ↓
Heltec LoRa 32 V3 (TX)  ← [OLED: TX Status / Configuration]
        ↓
LoRa 868 MHz
        ↓
Heltec LoRa 32 V3 (RX)  ← [OLED: Live Monitor / RSSI Graph / Configuration]
        ↓
USB Serial (115200 bps)
        ↓
python/rx/rx.py (decoding + dashboard)
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

### Using a GPS

Receiver coordinates can be manually entered into the previous command, but you can also use a GPS module connected to your Raspberry Pi or Linux PC. In that case, coordinates can be retrieved automatically and passed to readsb.

---

### Why compress ADS-B data?

The SBS-1 format is text-based (ASCII) and contains a lot of redundancy.

Example message:

`MSG,3,111,11111,4CA123,111111,2026/08/02,10:15:21.123,2026/08/02,10:15:21.123,RYR8AB,37000,450,182,44.54,11.29,-64,0,0,0,0`

Typical size: 100–140 bytes

With LoRa set to SF7 / BW125 kHz / CR4:5, the useful throughput is only a few kbit/s, making the transmission of raw text extremely inefficient.

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


### Trade-offs

| Change   | Effect                                     |
| -------- | ------------------------------------------ |
| SF ↑     | Longer range, lower throughput             |
| BW ↑     | Higher throughput, lower sensitivity       |
| CR ↑     | Greater robustness, longer airtime         |


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

### Software Components

### `python/tx/tx.py`

Responsibilities:
* Socket connection to `127.0.0.1:30003` (readsb stream)
* Parsing of text-based SBS-1 messages
* Selection and extraction of valid fields
* Compact binary serialization via `struct.pack`
* CRC16 checksum calculation
* Sending frames via serial connection to the Heltec TX board

### `python/rx/rx.py`

Responsibilities:
* Non-blocking reading of the Heltec RX board serial port
* Synchronization on the `0x55AA` start frame marker
* CRC16 checksum validation
* Decoding of the compact binary payload
* Maintenance and real-time updating of the internal aircraft database
* Automatic removal of inactive aircraft (150-second timeout)
* Graphical dashboard rendering in the terminal with reactive updates (Rich library)


### Real-time Dashboard

The dashboard is designed to adapt in real-time to your terminal, displaying information in a convenient auto-paginated grid view.

Features include:
* A compact information card for every tracked aircraft
* Grid layout that auto-adapts to window width
* Constantly updated "last seen" timer
* Vertical scroll handling (via Arrow keys or `W`/`S` keys) to view dozens of aircraft simultaneously
* Smart and highly reactive refresh to prevent screen flickering

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

### System Startup

### 1. Start the receiver (Display side)

Navigate to the python scripts directory and run the receiving script:

```bash
cd python/rx
python3 rx.py
```

### 2. Start the transmitter (RTL-SDR side)

Open another terminal on the machine connected to the SDR and start the transmission script:

```bash
cd python/tx
python3 tx.py
```

Overall performance may vary depending on surrounding electromagnetic noise, node proximity, set transmission power, and the processing speed of the USB serial port.