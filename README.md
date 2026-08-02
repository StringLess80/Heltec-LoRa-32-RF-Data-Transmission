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
Heltec LoRa 32 V3 (TX)
        ↓
LoRa 868 MHz
        ↓
Heltec LoRa 32 V3 (RX)
        ↓
Seriale USB (115200 bps)
        ↓
Versione (V1 o V2)/RX/recv.py (decodifica + dashboard)
```

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

Con questa configurazione il flusso SBS‑1 sarà disponibile su `127.0.0.1:30003`, che è esattamente la porta utilizzata dallo script `transmit.py`.

### Utilizzo di un GPS

Le coordinate del ricevitore possono essere inserite manualmente nel comando precedente, ma è possibile anche utilizzare un modulo GPS collegato al Raspberry Pi o al PC Linux.

In quel caso le coordinate possono essere recuperate automaticamente (ad esempio tramite `gpsd`) e passate a readsb.

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

### Hardware

### Trasmettitore e ricevitore

* 2 × Heltec LoRa 32 V3
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

Utilizzata dal firmware basato sulla libreria RadioLib per il modulo LoRa SX1262 integrato:

| Segnale | GPIO | Descrizione |
| ------- | ---- | ----------- |
| CS      | 8    | SPI Chip Select |
| DIO1    | 14   | Interrupt Pin |
| RST     | 12   | Reset Pin |
| BUSY    | 13   | Busy Status Pin |
| SCK     | 9    | SPI Clock |
| MISO    | 11   | SPI MISO |
| MOSI    | 10   | SPI MOSI |

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

*Nota: L'RSSI non è trasmesso nel payload ma viene opzionalmente calcolato e aggiunto a livello locale dalla scheda ricevente durante l'elaborazione del pacchetto.*

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

Installare le librerie necessarie (si consiglia l'utilizzo di un ambiente virtuale `venv` se si lavora su distribuzioni Linux moderne):

```bash
pip install pyserial rich
```

### 4. Flashare le schede Heltec

1. Apri l'Arduino IDE e installa i pacchetti di supporto per schede **ESP32** (Heltec) e la libreria **RadioLib** dal Gestore Librerie.
2. Collega le schede e carica i rispettivi firmware (l'esempio fa riferimento alla versione più recente `V2`):
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

### Prestazioni

Valori indicativi misurati sul campo con payload medi da 24 byte:

| Metrica            | Valore tipico |
| ------------------ | ------------- |
| Airtime del pacchetto | ~55 ms        |
| Pacchetti al secondo | ~18 pkt/s     |
| Throughput utile   | ~3–5 kbit/s   |
| Latenza end‑to‑end | 100–300 ms    |

Le prestazioni generali possono variare in base al rumore elettromagnetico circostante, alla vicinanza tra i nodi, alla potenza impostata e alla velocità di elaborazione della porta seriale USB.

### Limitazioni attuali

### Nessuna consegna garantita (Best Effort)
Il collegamento radio LoRa funziona in modalità broadcast unidirezionale senza pacchetti di ACK (Acknowledge) o ritrasmissioni automatiche. Alcuni pacchetti potrebbero andare persi in caso di forte rumore radio.

### Disponibilità dei dati SBS
Non tutti i messaggi emessi dai velivoli contengono contemporaneamente tutti i parametri. I dati sulla posizione (latitudine/longitudine), altitudine e velocità vengono trasmessi dal transponder in momenti separati e saranno gradualmente aggregati nel database locale del ricevitore.

### Duty cycle e Normative
L'uso delle frequenze libere nella banda ISM 868 MHz deve rispettare rigorosamente le normative nazionali ed europee (ETSI) relative al tempo massimo di trasmissione consentito (Duty Cycle, tipicamente l'1% su questa banda).

## Autore
Sviluppato da: [StringLess80](https://github.com/StringLess80)