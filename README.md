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

* Basso utilizzo della CPU

* Framing robusto e validazione dei pacchetti

### Flusso dei dati

`Aeromobile (ADS‑B 1090 MHz) 
        ↓ 
Ricevitore RTL‑SDR
        ↓ 
readsb (TCP 127.0.0.1:30003)
        ↓
TX/transmit.py (parsing + serializzazione compatta)
        ↓ 
Seriale USB (115200 bps)
        ↓
Heltec LoRa 32 V3 (TX)
        ↓
LoRa 868 MHz
        ↓
Heltec LoRa 32 V3 (RX)
        ↓
Seriale USB (115200 bps)
        ↓
RX/recv.py (decodifica + dashboard)`

### Perché usare readsb invece di dump1090?

Sebbene il progetto funzioni anche con dump1090, è fortemente consigliato usare readsb.

### Vantaggi di readsb

* Migliore gestione dei messaggi Mode‑S e ADS‑B

* Decodifica più accurata

* Migliori prestazioni con molti aeromobili

* Output di rete più stabile

* Sviluppo e manutenzione più attivi rispetto a dump1090

In scenari reali con traffico intenso, readsb produce generalmente più messaggi validi e con minori perdite.

### Configurare readsb per l’output SBS sulla porta 30003

Avvia readsb con il seguente comando:

`sudo readsb \ --device-type rtlsdr \ --device 0 \ --gain auto \ --lat LAT_RICEVITORE \ --lon LON_RICEVITORE \ --net \ --net-bind-address 127.0.0.1 \ --net-sbs-port 30003`

Sostituisci:

* `LAT_RICEVITORE` con la latitudine del tuo ricevitore

* `LON_RICEVITORE` con la longitudine del tuo ricevitore

Esempio per Bologna:

`sudo readsb \ --device-type rtlsdr \ --device 0 \ --gain auto \ --lat 44.4733445 \ --lon 11.3803298 \ --net \ --net-bind-address 127.0.0.1 \ --net-sbs-port 30003`

Con questa configurazione il flusso SBS‑1 sarà disponibile su `127.0.0.1:30003`, che è esattamente ciò che utilizza `TX/transmit.py`.

### Utilizzo di un GPS

Le coordinate del ricevitore possono essere inserite manualmente nel comando precedente, ma è possibile anche utilizzare un modulo GPS collegato al Raspberry Pi o al PC Linux.

In quel caso le coordinate possono essere recuperate automaticamente (ad esempio tramite `gpsd`) e passate a readsb.

Questo approccio è utile per:

* stazioni riceventi mobili;

* installazioni temporanee;

* test sul campo;

* sistemi alimentati a batteria.

### Perché comprimere i dati ADS‑B?

Il formato SBS‑1 è testuale (ASCII) e contiene molta ridondanza.

Esempio di messaggio:

`MSG,3,111,11111,4CA123,111111,2026/08/02,10:15:21.123,2026/08/02,10:15:21.123,RYR8AB,37000,450,182,44.54,11.29,-64,0,0,0,0`

Dimensione tipica: 100–140 byte

Con LoRa a SF7 / BW125 kHz / CR4:5 il throughput utile è di pochi kbit/s, quindi trasmettere il testo completo sarebbe molto inefficiente.

### Strategia di compressione

* Bitmask di presenza dei campi

* Campi binari tipizzati (`struct.pack`)

* Callsign a lunghezza fissa

* Rimozione dei delimitatori CSV

* Controllo CRC16

### Risultato tipico

| Formato          | Dimensione |
| ---------------- | ---------- |
| SBS‑1 originale  | 90–140 B   |
| Binario compatto | 18–40 B    |
| Riduzione        | 65–80%     |

### Hardware

### Trasmettitore e ricevitore

* 2 × Heltec LoRa 32 V3

* Collegamento USB‑C

### Stazione ADS‑B

* Raspberry Pi o PC Linux

* Dongle RTL‑SDR

* Antenna 1090 MHz

* readsb (consigliato) o dump1090

### Configurazione LoRa

Configurazione attuale del firmware:

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

Usata dal firmware basato su RadioLib:

| Segnale | GPIO |
| ------- | ---- |
| CS      | 8    |
| DIO1    | 14   |
| RST     | 12   |
| BUSY    | 13   |

### Protocollo binario compatto

### Struttura del frame

`+--------+--------+--------+------+---------+-------+ | SYNC | SEQ | MASK | LEN | PAYLOAD | CRC16 | | 2 B | 2 B | 2 B | 1 B | N B | 2 B | +--------+--------+--------+------+---------+-------+`

### Mappa dei campi

| Bit | Campo            | Tipo    |
| --- | ---------------- | ------- |
| 0   | ICAO             | uint32  |
| 1   | Callsign         | 8s      |
| 2   | Quota            | uint16  |
| 3   | Velocità         | uint16  |
| 4   | Rotta            | uint16  |
| 5   | Latitudine       | float32 |
| 6   | Longitudine      | float32 |
| 7   | Rateo verticale  | int16   |
| 8   | RSSI (opzionale) | int8    |

Vengono serializzati solo i campi realmente presenti nel messaggio SBS originale.

### Componenti software

### `TX/transmit.py`

Responsabilità:

* Connessione a `127.0.0.1:30003`

* Parsing dei messaggi SBS‑1

* Selezione dei campi validi

* Serializzazione binaria compatta

* Calcolo CRC16

* Invio dei frame alla scheda trasmittente

### `RX/recv.py`

Responsabilità:

* Sincronizzazione sul marker `0x55AA`

* Validazione CRC16

* Decodifica del payload binario

* Mantenimento della tabella aeromobili

* Rimozione degli aeromobili inattivi

* Rendering della dashboard con Rich

### Dashboard in tempo reale

![Decoding raw data - ADS-B Flight Tracking - FlightAware Discussions](screenshots/Screenshot%20From%202026-08-02%2013-56-24.png)

Dashboard del terminale con una scheda per ogni aeromobile

Funzionalità:

* Una scheda per ogni aeromobile

* Layout automatico a griglia

* Adattamento dinamico alla larghezza del terminale

* Timer “last seen”

* Refresh pulito e senza sfarfallii

### Installazione

### 1. Installare readsb

Su Debian / Raspberry Pi OS:

`sudo apt update sudo apt install readsb`

### 2. Clonare il repository

`git clone https://github.com/StringLess80/Heltec-LoRa-32-RF-Data-Transmission.git cd Heltec-LoRa-32-RF-Data-Transmission`

### 3. Installare le dipendenze Python

`pip install pyserial rich`

### 4. Flashare le schede Heltec

Apri i file `.ino` con Arduino IDE e installa:

* ESP32 board package

* RadioLib

Carica:

* `TX/transmitter.ino` sulla scheda trasmittente

* `RX/receiver.ino` sulla scheda ricevente

### Avvio del sistema

### Prima il ricevitore

`cd RX python3 recv.py`

### Poi il trasmettitore

`cd TX python3 transmit.py`

### Prestazioni

Valori indicativi con payload da 24 byte:

| Metrica            | Valore tipico |
| ------------------ | ------------- |
| Airtime            | ~55 ms        |
| Pacchetti/s        | ~18           |
| Throughput utile   | ~3–5 kbit/s   |
| Latenza end‑to‑end | 100–300 ms    |

Le prestazioni dipendono da:

* numero di aeromobili;

* configurazione LoRa;

* ambiente RF;

* latenza della seriale USB.

### Limitazioni attuali

### Nessuna consegna garantita

Il collegamento LoRa funziona in modalità broadcast senza ACK.

Possibili effetti:

* perdita di pacchetti;

* ricezione fuori ordine;

* nessuna ritrasmissione.

### Disponibilità dei dati SBS

Non tutti i messaggi contengono tutti i campi. Posizione, quota e velocità possono arrivare in frame ADS‑B separati.

### Duty cycle

L’utilizzo della banda ISM 868 MHz deve rispettare le normative ETSI applicabili al duty‑cycle.

## Author 
**Alessandro Iglina** 

GitHub: https://github.com/StringLess80