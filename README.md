# Heltec LoRa 32 – ADS‑B over LoRa (V2 Technical Update)

Bridge **ADS‑B → LoRa** basato su **ESP32 Heltec LoRa 32** e **dump1090/readsb**. 

Il progetto acquisisce i dati di traffico aereo in tempo reale, li comprime utilizzando un protocollo binario proprietario e li trasmette tramite tecnologia LoRa a lunga distanza. Un secondo nodo ricevente decodifica i pacchetti e visualizza i velivoli in una dashboard avanzata.

---

## 1. Architettura di Sistema

```text
SITO DI RICEZIONE (SORGENTE)              CANALE RADIO              SITO DI MONITORAGGIO (DESTINAZIONE)
    +-------------------------------+                                      +---------------------------------+
    | ANTENNA ADS-B (1090 MHz)      |                                      |       DASHBOARD UTENTE          |
    +---------------+---------------+                                      |           (RICH UI)             |
                    |                                                      +---------------^-----------------+
                    v                                                                      |
    +---------------+---------------+                                      +---------------+-----------------+
    |    dump1090 / readsb          |                                      |      PYTHON RICEVITORE          |
    | (Server TCP - Porta 30003)    |                                      |          (recv.py)              |
    +---------------+---------------+                                      +---------------^-----------------+
                    |                                                                      |
          (TCP Socket/Localhost)           ONDE RADIO (868 MHz)                   (Serial USB @ 115200)
                    v                      ((((  ~ ~ ~  ))))                               |
    +---------------+---------------+                                      +---------------+-----------------+
    |   PYTHON TRASMETTITORE        |             LoRa                     |       HELTEC LoRa 32            |
    |       (transmit.py)           |      +-----------------+             |          (RICEVENTE)            |
    +---------------+---------------+      |                 |             +---------------+-----------------+
                    |                      |  HELTEC LoRa 32 |                             ^
          (Serial USB @ 115200) ----------->  (TRASMITTENTE) +-----------------------------+
                                           |                 |
                                           +-----------------+
```

---

## 2. Evoluzione del Protocollo (V2)

L'aggiornamento alla V2 segna il passaggio fondamentale da una trasmissione basata su testo ASCII a una pura trasmissione **binaria, asincrona e cross-platform**.

### V1: Modalità Testuale (Legacy)
Inizialmente il sistema trasmetteva stringhe di testo (es. `ICA:4CA123,ALT:32000`) separate da ritorni a capo (`\n`). Questo metodo generava un altissimo **Time-on-Air (ToA)** su LoRa, causava colli di bottiglia e la seriale corrompeva spesso i dati.

### V2: Protocollo Binario e Gestione Asincrona (Attuale)
- **Maschera di Bit (Bitmask) Dinamica:** I dati sono impacchettati in byte grezzi. La lunghezza del pacchetto si adatta automaticamente ai dati disponibili.
- **Aggregazione Dati (Anti-Frammentazione):** I pacchetti grezzi `dump1090` sono nativamente frammentati. V2 implementa una cache in memoria che raggruppa tutti i parametri di un singolo aereo (Altitudine, Posizione, Velocità) prima di generare il pacchetto radio, garantendo l'invio di dati sempre completi.
- **Pacing di Trasmissione (Anti-Overflow):** La comunicazione Seriale-ESP32 è stata slegata dalla velocità di lettura del Socket. Il software ora inietta i pacchetti nella seriale rispettando fisicamente i tempi di trasmissione (Airtime) del chip LoRa SX1262 (~100ms), annullando totalmente la perdita di pacchetti per *Buffer Overflow*.
- **Integrità (CRC16 Zlib):** Inserito un checksum per scartare alla radice i pacchetti corrotti da interferenze radio.

---

## 3. Specifiche Tecniche del Pacchetto (Layout Binario)

Il pacchetto base (inviato dal Python TX all'ESP32 TX) è composto da un Header fisso di **7 Byte**, un Payload variabile e un Checksum finale. Tutta la serializzazione avviene in architettura **Little-Endian**.

| Offset | Campo | Tipo | Descrizione |
|---|---|---|---|
| 0 | **SYNC** | Uint16 | Firma fissa `0x55 0xAA` per l'allineamento hardware/software. |
| 2 | **SEQ** | Uint16 | Contatore sequenziale per rilevare pacchetti persi. |
| 4 | **MASK** | Uint16 | Maschera di bit. Ogni bit a `1` indica la presenza di un campo nel payload. |
| 6 | **LEN** | Uint8 | Lunghezza (byte) del solo Payload (estrattore hardware per l'ESP32). |
| 7 | **PAYLOAD** | Mixed | Dati grezzi concatenati in base alla MASK (ICAO, ALT, LAT...). |
| n | **CRC** | Uint16 | Checksum CRC16 del solo payload. |

### Mappatura della Maschera (Bitmask Table)
| Bit | Codice | Dimensione | Conversione Tecnica | Python Struct |
|---|---|---|---|---|
| 0 | **ICA** | 4B | ICAO Hex → Integer 32-bit | `<I` |
| 1 | **CAL** | 8B | Stringa ASCII (padding nullo) | `8s` |
| 2 | **ALT** | 2B | Piedi → Metri (Unsigned Short) | `<H` |
| 3 | **VEL** | 2B | Nodi → Km/h (Unsigned Short) | `<H` |
| 4 | **DIR** | 2B | Heading (0-359°) | `<H` |
| 5 | **LAT** | 4B | Gradi Decimali → Float × $10^7$ (Int32) | `<i` |
| 6 | **LON** | 4B | Gradi Decimali → Float × $10^7$ (Int32) | `<i` |
| 7 | **VER** | 2B | Vertical Rate (Signed Short) | `<h` |
| 8 | **SQU** | 2B | Codice Transponder | `<H` |
| 9 | **GRO** | 1B | Flag Ground State (1 = Terra, 0 = In volo) | `<B` |
| 10| **TIP** | 1B | Tipo Messaggio BaseStation (1-8) | `<B` |

### 3.1 Parsing Dinamico del Payload e Compressione Dati
A differenza dei protocolli testuali (CSV/JSON), non esistono delimitatori. Il parsing avviene tramite una **logica a puntatore sequenziale (offset)** guidata dalla `MASK` a 16-bit. 

Inoltre, il protocollo massimizza l'efficienza convertendo i numeri in blocchi di memoria fissi. Ad esempio, **l'Altitudine** viene convertita in metri e archiviata come Unsigned Short (`<H`). Che un aereo voli a 100 metri (`0x0064`) o a 15.000 metri (`0x3A98`), il pacchetto occuperà sempre e solo **2 byte**, stabilizzando il footprint RF.

---

## 4. Funzionamento Componenti Software

### Trasmettitore (`TX/transmitter.py`)
- **Selettore Dinamico:** Al boot, l'utente sceglie quali campi trasmettere. 
- **Non-Blocking Socket & Caching:** Legge i frammenti SBS-1 ad altissima velocità senza bloccarsi, e popola un dizionario temporaneo (`aircraft_db`) unendo Altitudine, Posizione e Velocità man mano che arrivano in messaggi separati.
- **Trasmissione Cadenzata (Pacing):** Il ciclo di invio LoRa valuta due parametri critici:
  - `MIN_INTERVAL_PER_AIRCRAFT` (es. 2.0s): Evita che lo stesso aereo saturi la coda.
  - `LORA_TX_AIRTIME_DELAY` (es. 0.1s): Impone una pausa fisica tra un pacchetto LoRa e il successivo, permettendo all'ESP32 di svuotare il buffer RF senza sovrascrivere i dati seriali.

### Ricevitore (`RX/receiver.py`)
- **Gestione Buffer Circolare:** Legge i byte grezzi in streaming continuo ricostruendo matematicamente i pacchetti, anche se arrivano "spezzati" via USB.
- **Dashboard Autoadattiva (Rigid Grid):** L'interfaccia basata su `Rich` genera una griglia che calcola automaticamente le colonne in base alla larghezza del terminale. I box dei velivoli hanno una dimensione fissa (inserendo `---` in caso di dati parziali o in attesa) per garantire una UI pulita, allineata e priva di "salti" visivi.
- **Persistence:** Rimuove i target dal display se non si ricevono aggiornamenti entro un timeout configurabile (150 secondi).

---

## 5. Requisiti Hardware e Software

### Hardware
- **2x ESP32 Heltec LoRa 32 V2/V3** (SX1276 o SX1262).
- Antenne sintonizzate sulla frequenza **868 MHz** (Europa).
- Host per il monitoraggio (Windows, macOS o Linux) e Host per `dump1090` / `readsb`.

### Software (Python)
L'ambiente Python richiede le seguenti librerie, installabili tramite gestore di pacchetti:
```bash
pip install pyserial rich
```

---

## 6. Installazione e Avvio

### 1. Flash del Firmware V2
Tramite Arduino IDE o PlatformIO, caricare i firmware V2 sulle rispettive schede (il codice TX su una scheda e il codice RX sull'altra). Il firmware V1 legacy non è compatibile con i nuovi script di gestione Python. *(Nota: per il TX è caldamente suggerito aumentare il buffer seriale inserendo `Serial.setRxBufferSize(1024);` prima del `Serial.begin`)*.

### 2. Setup Ricevitore (RX)
- Assicurarsi che l'ESP32 RX sia collegato tramite USB.
- Eseguire lo script di ricezione:
  ```bash
  python receiver.py
  ```
- Selezionare la porta seriale corrispondente dal menu interattivo.

### 3. Setup Trasmettitore (TX)
- Assicurarsi che `dump1090` o `readsb` sia attivo sulla porta 30003.
- Collegare l'ESP32 TX ed eseguire:
  ```bash
  python transmitter.py
  ```
- All'avvio, selezionare la porta seriale corrispondente e i campi che si desidera trasmettere (es: inserire `1 2 3 5 6` per abilitare l'invio sequenziale di ICAO, Callsign, Altitudine, Latitudine e Longitudine).

---

## 7. Analisi Dashboard RX
I target vengono visualizzati come card individuali aggiornate in tempo reale con colori diagnostici in base all'intervallo di ricezione:
- **Verde (< 15s):** Velivolo tracciato attivamente, dati completi e pacchetti radio costanti.
- **Giallo (< 60s):** Ricezione intermittente o segnale in attenuazione (es. aereo ai confini della copertura LoRa).
- **Rosso (> 60s):** Segnale radio perso, in attesa della rimozione automatica (al raggiungimento dei 150s).

![Monitor ADS-B LoRa](screenshots/03.png)

---

## 8. Considerazioni sull'Occupazione di Banda (Airtime)
LoRa ha una larghezza di banda estremamente limitata. 

Nel vecchio protocollo, trasmettere un frammento SBS con la sola Altitudine e poi un frammento con la sola Posizione obbligava il chip LoRa ad accendersi due volte. Grazie alla **nuova logica di Caching (Aggregazione)**, il Python TX invia un singolo pacchetto completo per aereo. 

Utilizzando il protocollo binario V2, un pacchetto contenente (ICAO, ALT, VEL, LAT, LON) occupa circa **19 byte totali**. 
A parità di parametri radio (Spreading Factor 7, Bandwidth 125kHz), questa architettura riduce drasticamente il *Time-on-Air* (ToA), consentendo di gestire simultaneamente un numero maggiore di velivoli senza collassare il canale radio o violare le normative sui duty-cycle.

---

**Autore:** Alessandro Iglina  
**GitHub:** [https://github.com/StringLess80](https://github.com/StringLess80)