<div align="center">
  <a href="#italiano">🇮🇹 Italiano</a> | <a href="docs/translations/README-EN.md">🇬🇧 English</a>
</div>

---

<a id="italiano"></a>
# IT - ADS‑B over LoRa — Heltec LoRa 32 V3 (v4.0)

![Version](https://img.shields.io/badge/Version-4.0-purple)
![Platform](https://img.shields.io/badge/ESP32-Heltec%20V3-blue)
![Radio](https://img.shields.io/badge/LoRa-SX1262-green)
![Band](https://img.shields.io/badge/868%20MHz-EU-orange)
![Python](https://img.shields.io/badge/Python-3.10+-yellow)

### Trasmissione ad alta frequenza e lunga distanza di dati ADS‑B / Mode‑S tramite LoRa con schede Heltec ESP32 e Tactical Control Center Web

---

### Panoramica

Questo progetto implementa un bridge completo **ADS‑B → LoRa → ADS‑B / Web Control Center** ottimizzato per canali radio a banda stretta e alta frequenza di aggiornamento. 

I messaggi degli aeromobili decodificati da `readsb` (o `dump1090`) vengono catturati dal flusso TCP SBS-1 sulla porta 30003, analizzati e filtrati da un **Motore Semantico** a livello software, compressi in un protocollo binario proprietario compatto, trasmessi via LoRa a 868 MHz tramite due schede Heltec LoRa 32 V3 e infine ricostruiti sul ricevitore.

La versione **4.0** introduce un **Tactical Control Center Full-Stack in Python/Flask**, un'interfaccia cartografica avanzata, l'assegnazione tattica del traffico ai controllori di terra tramite l'**Algoritmo del Cono Cieco Zenithale**, e la decodifica nativa di un **GPS Seriale NMEA 0183**.

---

### 🚀 Architettura del Motore Semantico v3.0

Il cuore del sistema è il **Motore Semantico ad Eventi** (*Semantic Engine*), sviluppato per superare i limiti di banda fisica del canale LoRa senza sacrificare la precisione della telemetria.

```text
+-------------------------------------------------------------------------+
|                         MOTORE SEMANTICO (TX)                           |
+-------------------------------------------------------------------------+
   | (SBS-1 TCP Stream)
   v
[Parser SBS-1] --------> [Database di Stato (ICAO Hex)]
                               | (Confronto Delta e Soglie)
                               v
                         [Filtro Differenziale]
                               |
                               +---> No variazioni significative? -> SCARTA
                               |
                               +---> Variazione > Soglia? ---------> GENERA DELTA
                               |
                               +---> Evento di Stato (Squawk/Gnd) -> GENERA EVENT
                               |
                               +---> Timeout 5s raggiunto? --------> GENERA FULL
                               |
                               v
                         [Dynamic Bitmasking]
                               |
                               v
                         [Pre-compiled Struct Packing]
                               | (Aggiunta Header & CRC32/CRC16)
                               v
                         [Coda TX (deque, maxlen=20)] ---> Seriale USB -> LoRa
```

#### 1. Analisi Differenziale e Macchina a Stati
Invece di operare come semplice pass-through, il trasmettitore (`python/tx/`) mantiene in memoria una macchina a stati per ogni indirizzo ICAO rilevato. Il motore semantico valuta le derivate fisiche dei seguenti parametri rispetto all'ultimo invio validato:
* **Quota (ALT):** Variazioni superiori a $\ge 50$ piedi.
* **Velocità (VEL):** Variazioni superiori a $\ge 5$ nodi.
* **Direzione (DIR):** Variazioni superiori a $\ge 3$ gradi.
* **Coordinate (LAT/LON):** Spostamenti superiori a $\ge 0.002$ gradi (circa 220 metri).
* **Rateo Verticale (VER):** Variazioni superiori a $\ge 150$ piedi/minuto.

#### 2. Dynamic Bitmasking (Mascheramento Dinamico)
Se un parametro non supera la soglia di variazione, viene omesso dalla serializzazione. Il sistema genera dinamicamente una maschera di bit a 16 bit (*Bitmask*) inserita nell'header del pacchetto. Ogni bit indica la presenza o l'assenza di uno specifico campo nel payload binario. Questo consente di ridurre la dimensione del frame dai ~130 byte del testo SBS-1 originale a soli **18-40 byte** in formato compresso (riduzione dell'overhead del 70-80%).

#### 3. Gestione dei Frame di Sincronizzazione (FULL) ed Eventi (EVENT)
* **Frame DELTA:** Contiene solo i parametri fisici che hanno superato le soglie di tolleranza.
* **Frame EVENT:** Generato istantaneamente in caso di variazione di parametri discreti e critici come il codice *Squawk* o lo stato al suolo (*Ground State*).
* **Frame FULL (Heartbeat):** Trasmesso periodicamente (ogni 5 secondi per configurazione ad alta frequenza) per inviare lo stato completo del velivolo. Questo garantisce che eventuali ricevitori sintonizzati in un secondo momento possano ricostruire la telemetria completa in pochi istanti.

---

### 🎨 Novità v4.0: Tactical Control Center

L'aggiornamento **v4.0** trasforma la stazione di ricezione in un vero e proprio **Centro di Controllo Tattico Web**:

* **Cartografia Vettoriale Leaflet.js (60 FPS):** Marker dinamici degli aerei in formato SVG che ruotano in tempo reale in base all'Heading (`DIR`). In caso di selezione, l'icona diventa **Viola Neon (`#af52de`)** aprendo l'Inspector dettagliato e tracciando il vettore di puntamento verso il controllore assegnato.
* **Integrazione GPS Seriale NMEA 0183:** Modulo di decodifica nativo per GPS seriale (`$GPGGA`, `$GPRMC`, `$GPGLL`) con rendering sulla mappa di un marker verde fluorescente ad effetto `radar pulse` animato coordinate della stazione.
* **Gestione Controllori Tattici a Terra:** Aggiunta e rimozione istantanea di controllori sulla mappa con aggiornamento dinamico delle assegnazioni del traffico aereo e diffing JSON sul DOM.
* **RF Engine Graph:** Grafico vettoriale SVG integrato che mostra la frequenza di pacchetti al secondo ricevuti via LoRa con effetto neon verde.
* **Persistenza e Scrittura:** La configurazione di sistema (`config.json`) viene salvata con percorso assoluto e `os.fsync()` per forzare la scrittura fisica su disco. Rigenerazione automatica in caso di file mancante.

---

### 📐 Algoritmo del Cono Cieco Zenithale (Zenith Blind Cone)

Un problema critico dei controllori tattici a terra è la zona d'ombra (o cieca) posizionata direttamente sopra la loro verticalità (**Zenith**).

Quando un aereo entra nel cono d'ombra del controllore assegnato (angolo di elevazione rispetto all'orizzonte tale per cui l'angolo zenithale risulta $\le \theta_{zenith}$, es. $30^\circ$):

1. L'aereo viene contrassegnato con l'avviso `⚠️ In Cono Verticale`.
2. L'algoritmo calcola la distanza ortodromica Haversine e applica una **penalizzazione x10 sulla distanza**:
   
   $$d_{tattica} = \begin{cases} d_{reale} \cdot 10 & \text{se } \theta_{zenith} \le \theta_{soglia} \text{ (In Cono Cieco)} \\ d_{reale} & \text{altrimenti} \end{cases}$$

3. La penalizzazione costringe il sistema di routing tattico a riassegnare immediatamente l'aereo al controllore adiacente ottimale.
4. Sulla mappa 2D il cono cieco è rappresentato da un cerchio tratteggiato arancione centrato sul controllore.

---

### ⚡ Ottimizzazioni Prestazionali v3.0 & v4.0

La versione 3.0/4.0 introduce interventi strutturali volti a garantire la massima fluidità e stabilità del sistema con flussi di traffico aereo intensi:

* **Architettura Modulare e Separazione delle Responsabilità:** Codice Python riorganizzato in pacchetti modulari (`core`, `protocol`, `services`, `routes`, `static`, `templates`) per massima manutenibilità e pulizia.
* **Pre-compilazione delle Strutture Binarie (`struct.Struct`):** La compilazione delle stringhe di formato di `struct.pack` e `struct.unpack` è stata spostata al di fuori dei loop critici di ricezione e trasmissione. L'uso di istanze `struct.Struct` pre-allocate evita il parsing ripetuto dei template binari, riducendo sensibilmente l'uso di CPU.
* **Coda Asincrona a Finestra Scorrevole (`deque`):** Per evitare la congestione del buffer seriale del microcontrollore Heltec durante picchi di traffico, il trasmettitore utilizza una coda asincrona `collections.deque(maxlen=20)`. Se la frequenza di generazione dei frame supera la capacità fisica di trasmissione della radio (cadenzata a 50ms di delay minimo), i pacchetti obsoleti vengono scartati automaticamente a favore di quelli più recenti.
* **Sincronizzazione e Scarto Selettivo:** In caso di corruzione di un pacchetto sulla seriale in ricezione (`python/rx/` o `serial_service.py`), il parser scarta unicamente il marcatore di sincronizzazione `0xAA55` / `0x55AA` corrente e riallinea immediatamente il puntatore del buffer ai byte successivi, minimizzando la perdita di pacchetti adiacenti.
* **Protezione RAM del Ricevitore:** Il buffer di ricezione seriale è limitato rigidamente a un massimo di 4096 byte per prevenire l'accumulo di byte di rumore (garbage) e preservare la memoria di sistema in esecuzioni prolungate.

---

### 📡 Algoritmo di Tracciamento Radar e Distanza (Haversine)

Il ricevitore include l'implementazione in virgola mobile della formula di Haversine per determinare la distanza ortodromica in tempo reale tra ciascun velivolo rilevato e le coordinate geografiche della stazione di terra (`HOME_LAT`, `HOME_LON`):

$$\Delta\sigma = 2 \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta\phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta\lambda}{2}\right)}\right)$$

$$d = R \cdot \Delta\sigma$$

#### Caratteristiche:
* **Ordinamento Dinamico per Distanza:** La griglia grafica e la lista aerei ordina costantemente i velivoli posizionando i più vicini in cima. I velivoli privi di coordinate GPS valide vengono collocati in coda alla lista in ordine alfabetico ICAO.
* **Nessun Effetto Flashing (Layout Stabile):** L'aggiornamento dinamico impedisce il riposizionamento caotico delle card sulla TUI e sulla Dashboard Web, mantenendo l'interfaccia stabile e leggibile.
* **Pacing Grafico:** L'interfaccia Web SocketIO e la TUI Rich Live si aggiornano a intervalli controllati di 100ms per la telemetria ordinaria, garantendo un framerate di 60 FPS senza rallentamenti.

---

### ⚡ Protocollo Radio Binario compatto ADS-B over LoRa

Per massimizzare il numero di aggiornamenti al secondo su canale LoRa, la struttura dei messaggi utilizza un pacchetto binario serializzato ad altissima efficienza con checksum CRC32.

#### Header e Footer del Pacchetto:
* **Header (7 Byte):** `SYNC 0xAA55` (uint16), `seq` (uint16), `mask` (uint16), `payload_len` (uint8).
* **Footer (2 Byte):** Checksum CRC32 (lower 16-bit) applicato ad Header + Payload.

#### Campi Payload ordinati per Bitmask:
* **Bit 0:** `ICAO` (4 Byte - uint32 hex)
* **Bit 1:** `Callsign` (8 Byte - ASCII string con padding `\x00`)
* **Bit 2:** `Altitudine` (2 Byte - uint16)
* **Bit 3:** `Velocità` (2 Byte - uint16)
* **Bit 4:** `Direzione/Heading` (2 Byte - uint16)
* **Bit 5:** `Latitudine` (4 Byte - int32 $deg \times 10^7$)
* **Bit 6:** `Longitudine` (4 Byte - int32 $deg \times 10^7$)
* **Bit 7:** `Vertical Rate` (2 Byte - int16)

---

### Novità Firmware v2.1: Monitoraggio OLED & Interattività

La versione **2.1** del firmware (pienamente compatibile con il backend Python v3.0/v4.0) sfrutta il display OLED integrato (SSD1306, 128x64) e il pulsante utente **PRG** (GPIO 0) di Heltec V3. È stato implementato un sistema a **3 pagine** consultabili in tempo reale.

#### Funzionalità Display sul Ricevitore (RX):
* **Pagina 0 (Live Monitor):** Mostra il numero totale di pacchetti ricevuti, l'RSSI e l'SNR dell'ultimo pacchetto, e la dimensione del payload.
* **Pagina 1 (Storico RSSI):** Un grafico cartesiano che traccia l'andamento del segnale (RSSI) degli ultimi 20 pacchetti ricevuti, con scala dinamica da -120 a -40 dBm.
* **Pagina 2 (Configurazione):** Mostra i parametri attuali della radio (Frequenza, Spreading Factor, Bandwidth, Coding Rate).

#### Funzionalità Display sul Trasmettitore (TX):
* **Pagina 0 (TX Dashboard):** Mostra la conta dei pacchetti trasmessi con successo, la dimensione dell'ultimo frame e lo stato/codice di errore del chip SX1262.
* **Pagina 1 (Stato Seriale):** Monitora lo stato del parser seriale (fase di sincronizzazione sul marcatore `0x55AA`/`0xAA55`, byte ricevuti e attesi).
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

```text
Aeromobile (ADS‑B 1090 MHz)
        ↓ 
Ricevitore RTL‑SDR
        ↓ 
readsb (TCP 127.0.0.1:30003)
        ↓
python/tx/tx.py (Motore Semantico + Serializzazione Compatta Precompilata)
        ↓ 
Seriale USB (115200 bps)
        ↓
Heltec LoRa 32 V3 (TX)  ← [OLED: Stato TX / Configurazione]
        ↓
LoRa 868 MHz (No Duty-Cycle Limit)
        ↓
Heltec LoRa 32 V3 (RX)  ← [OLED: Live Monitor / Grafico RSSI / Configurazione]
        ↓
Seriale USB (115200 bps - DTR/RTS Gestiti)
        ↓
[ Tactical Control Center Flask / SocketIO ]
        ├──> Decodifica LoRa & Parser GPS Seriale NMEA
        ├──> Calcolo Cono Cieco Zenithale & Assegnazione Controllori
        └──> Mappa Leaflet 2D e Dashboard
```

---

### Perché usare readsb invece di dump1090?

Sebbene il progetto funzioni anche con dump1090, è fortemente consigliato usare readsb.

#### Vantaggi
* Migliore gestione dei messaggi Mode‑S e ADS‑B
* Decodifica più accurata
* Migliori prestazioni con molti aeromobili
* Output di rete più stabile
* Sviluppo e manutenzione più attivi rispetto a dump1090

In scenari reali con traffico intenso, readsb produce generalmente più messaggi validi e con minori perdite.

#### Configurare readsb per l’output SBS sulla porta 30003

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

---

### Perché comprimere i dati ADS‑B?

Il formato SBS‑1 è testuale (ASCII) e contiene molta ridondanza.

Esempio di messaggio:
`MSG,3,111,11111,4CA123,111111,2026/08/02,10:15:21.123,2026/08/02,10:15:21.123,RYR8AB,37000,450,182,44.54,11.29,-64,0,0,0,0`

Dimensione tipica: 100–140 byte

Con LoRa a SF7 / BW125 kHz / CR4:5 il throughput utile è limitato, quindi trasmettere il testo completo sarebbe estremamente inefficiente.

#### Strategia di compressione
* Bitmask di presenza dei campi
* Campi binari tipizzati (`struct.pack`)
* Codifica del Callsign a lunghezza fissa
* Rimozione completa dei delimitatori CSV
* Controllo d'integrità tramite CRC32/CRC16

#### Risultato tipico

| Formato          | Dimensione |
| ---------------- | ---------- |
| SBS‑1 originale  | 90–140 B   |
| Binario compatto | 18–40 B    |
| Riduzione        | 65–80%     |

---

### Hardware

#### Trasmettitore e ricevitore
* 2 × Heltec LoRa 32 V3 (ESP32-S3 + SX1262)
* Collegamento tramite cavo USB‑C (gestione segnali DTR/RTS integrata per evitare reset USB-CDC)
* Opzionale: Modulo GPS Seriale NMEA 0183

#### Stazione ADS‑B
* Raspberry Pi o PC Linux
* Dongle USB RTL‑SDR
* Antenna omnidirezionale tarata a 1090 MHz
* readsb (consigliato) o dump1090

#### Configurazione LoRa
Configurazione predefinita nel firmware:

| Parametro        | Valore    |
| ---------------- | --------- |
| Frequenza        | 868.0 MHz |
| Spreading Factor | 7         |
| Banda            | 125 kHz   |
| Coding Rate      | 4/5       |
| Potenza TX       | 14 dBm    |

---

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

### Componenti Software (Architettura Modulare)

#### 1. Applicazione Full-Stack Web Tactical Control Center (`adsb_lora_app/`):
* **`app.py`**: Entrypoint Flask & WebSocket SocketIO (`async_mode='threading'`).
* **`config.json`**: File di configurazione persistente salvato con `os.fsync`.
* **`core/state.py`**: Gestione stato di sistema in memoria (`system_state`, `aircraft_db`).
* **`core/config_manager.py`**: Salvataggio/caricamento configurazioni e rigenerazione automatica.
* **`core/math_tactical.py`**: Geodesia Haversine, calcolo elevazione e Algoritmo Cono Cieco Zenithal.
* **`protocol/nmea_parser.py`**: Parser NMEA 0183 nativo (`$GPGGA`, `$GPRMC`, `$GPGLL`).
* **`protocol/lora_encoder.py`**: Encoder/Decoder binario (Header 0xAA55 + Bitmask + Payload + CRC32).
* **`services/serial_service.py`**: Gestione comunicazioni seriali reali con fix DTR/RTS per ESP32-S3 e GPS.
* **`services/adsb_service.py`**: Worker TCP Dump1090, timeout inattività e Loop TX/RX LoRa.
* **`routes/api.py`**: REST API per stato sistema, controllori e configurazioni.
* **`static/css/style.css`**: Design System UI.
* **`static/js/app.js`**: Gestione Mappa Leaflet.js, WebSockets, rotazione marker SVG 60fps ed eventi UI.
* **`templates/index.html`**: Layout HTML della Dashboard Web.

#### 2. Scripts CLI e Utility (`python/`):
* **`python/tx/`**: Trasmettitore CLI (`tx.py`, `evaluator.py`, `encoder.py`, `tracker.py`, `fields_selector.py`).
* **`python/rx/`**: Ricevitore CLI TUI con libreria Rich (`rx.py`, `ui.py`, `geo.py`, `tracker.py`, `input_handler.py`).

---

### Installazione

#### 1. Installare readsb
Su sistemi operativi Debian-based o Raspberry Pi OS:
```bash
sudo apt update
sudo apt install readsb
```

#### 2. Clonare la repository
```bash
git clone https://github.com/StringLess80/Heltec-LoRa-32-RF-Data-Transmission.git
cd Heltec-LoRa-32-RF-Data-Transmission
```

#### 3. Installare le dipendenze Python
Installare le librerie necessarie tramite pip (si consiglia l'utilizzo di un ambiente virtuale `venv`):
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 4. Flashare le schede Heltec
1. Apri Arduino IDE e installa i pacchetti di supporto per schede **ESP32** (Heltec) e le librerie **RadioLib** e **U8g2** dal Gestore Librerie.
2. Collega le schede e carica i rispettivi firmware:
   * Carica `firmware/tx/tx.ino` sulla scheda Heltec trasmittente.
   * Carica `firmware/rx/rx.ino` sulla scheda Heltec ricevente.

---

### Avvio del sistema

#### Opzione A: Avvio con Tactical Control Center Web

1. Avvia la Web App Flask:
   ```bash
   python3 app.py
   ```
2. Apri il browser all'indirizzo `http://localhost:5000`.
3. Dalla barra di navigazione in alto:
   * Seleziona la porta seriale della scheda **Heltec V3**.
   * Seleziona la porta seriale del **GPS**.
   * Attiva lo switch **TX** per iniziare la ritrasmissione radio.

4. **Avviare il ricevitore TUI (lato visualizzazione console):**
   ```bash
   cd python/rx
   python3 rx.py
   ```

#### Opzione B: Avvio con Interfaccia CLI / TUI (v3.0)

1. **Avviare il ricevitore TUI (lato visualizzazione console):**
   ```bash
   cd python/rx
   python3 rx.py
   ```

2. **Avviare il trasmettitore CLI (lato RTL‑SDR):**
   ```bash
   cd python/tx
   python3 tx.py
   ```