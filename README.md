### ADS‑B over LoRa — Heltec LoRa 32 V3

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

### Novità Firmware: Monitoraggio OLED & Interattività

Il firmware è stato esteso per sfruttare il display OLED integrato (SSD1306, 128x64) e il pulsante utente **PRG** (GPIO 0) di Heltec V3. È stato implementato un sistema a **3 pagine** consultabili in tempo reale.

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
Versione (V1 o V2)/TX/transmit.py (parsing + serializzazione compatta)
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
Versione (V1 o V2)/RX/recv.py (decodifica + dashboard)
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

Le coordinate del ricevitore possono essere inserite manualmente nel comando precedente, ma è possibile anche utilizzare un modulo GPS collegato al Raspberry Pi o al PC Linux.

In quel caso le coordinate possono essere recuperate automaticamente e passate a readsb.

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

### Protocollo binario compatto

### Struttura del frame
| Campo | Byte | Descrizione |
|------|------|-------------|
| `SYNC` | 2 | Byte di sincronizzazione (`0x55AA`) |
| `SEQ` | 2 | Numero di sequenza progressivo del pacchetto |
| `MASK` | 2 | Bitmask di presenza dei campi |
| `LEN` | 1 | Lunghezza del payload |
| `PAYLOAD` | N | Dati serializzati |
| `CRC16` | 2 | Controllo di integrità | 

### Mappa dei campi (MASK)

I dati vengono trasmessi in modo dinamico: solo i campi realmente popolati nel messaggio SBS originale vengono inseriti nel payload binario, attivando il relativo bit nella maschera.

| Bit | Campo | Formato | Tipo | Descrizione / Unità di misura |
| :---: | --- | :---: | :---: | --- |
| **0** | ICAO | `<I` | `uint32` | Identificativo univoco del transponder (Hex) |
| **1** | Callsign | `8s` | `char[8]` | Identificativo del volo (8 caratteri ASCII) |
| **2** | Quota (Altitude) | `<H` | `uint16` | Altitudine in piedi (ft) |
| **3** | Velocità (Speed) | `<H` | `uint16` | Velocità al suolo in nodi (kt) |
| **4** | Rotta (Heading) | `<H` | `uint16` | Prua/Rotta in gradi (0–359°) |
| **5** | Latitudine | `<i` | `int32` | Coordinata geografica scalata (valore $\times 10^7$) |
| **6** | Longitudine | `<i` | `int32` | Coordinata geografica scalata (valore $\times 10^7$) |
| **7** | Rateo verticale | `<h` | `int16` | Vertical Speed in piedi al minuto (fpm) |
| **8** | Squawk | `<H` | `uint16` | Codice transponder a 4 cifre ottali (es. `7700`) |
| **9** | Ground | `<B` | `uint8` | Stato al suolo: `1` (GND), `0` (AIR) |
| **10** | Type | `<B` | `uint8` | Categoria/tipo del velivolo |

---

### Componenti software

Il progetto è suddiviso in due versioni principali (`V1` e `V2`). Si consiglia di utilizzare la cartella **`V2`** che contiene le ottimizzazioni di performance più recenti e la gestione fluida dei pacchetti.

### `TX/transmit.py`

Responsabilità:
* Connessione socket a `127.0.0.1:30003` (flusso readsb)
* Parsing dei messaggi SBS-1 testuali
* Selezione ed estrazione dei campi validi
* Serializzazione binaria compatta tramite `struct.pack`
* Calcolo del CRC16 di verifica
* Invio dei frame tramite connessione seriale alla scheda Heltec TX

### `RX/recv.py`

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

Funcionalità incluse:
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
pip install pyserial rich
```

### 4. Flashare le schede Heltec

1. Apri l'Arduino IDE e installa i pacchetti di supporto per schede **ESP32** (Heltec) e le librerie **RadioLib** e **U8g2** dal Gestore Librerie.
2. Collega le schede e carica i rispettivi firmware:
   * Carica `V2/TX/transmitter/transmitter.ino` sulla scheda Heltec trasmittente.
   * Carica `V2/RX/receiver/receiver.ino` sulla scheda Heltec ricevente.

### Avvio del sistema

### 1. Avviare il ricevitore (lato visualizzazione)

Spostati nella directory della versione scelta ed esegui lo script di ricezione:

```bash
cd V2/RX
python3 recv.py
```

### 2. Avviare il trasmettitore (lato RTL‑SDR)

Apri un altro terminale sulla macchina connessa all'SDR e avvia lo script di trasmissione:

```bash
cd V2/TX
python3 transmit.py
```

Le prestazioni generali possono variare in base al rumore elettromagnetico circostante, alla vicinanza tra i nodi, alla potenza impostata e alla velocità di elaborazione della porta seriale USB.