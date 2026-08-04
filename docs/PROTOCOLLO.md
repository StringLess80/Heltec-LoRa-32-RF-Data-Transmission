# Documentazione tecnica protocollo di compressione TX

## Architettura del Sistema

```
[ Dump1090 / SBS ] 
       │ (TCP Port 30003 - Format ASCII SBS-1)
       ▼
[ Non-Blocking Data Receiver & In-Memory DB ]
       │
       ▼
[ Semantic Delta Evaluation Engine ] ──(No change)──► [ Drop Frame ]
       │ (Change detected OR Timer Expired)
       ▼
[ Binary Struct Packer (Dynamic Bitmask) ]
       │
       ▼
[ Asynchronous Bounded Ring Queue ]
       │ (Airtime Rate Limiting: >= 50ms)
       ▼
[ UART Serial -> LoRa Radio Transceiver ]
```

---

## Specifiche del Frame Binario

Il pacchetto ha una struttura **Little-Endian (`<`)** a lunghezza variabile con overhead fisso minimizzato a **9 Byte** (Header + Trailer CRC).

### Layout Memoria del Pacchetto

### 1. Header (7 Byte Fisso)
| Campo | Tipo | Dimensione | Descrizione |
| :--- | :--- | :--- | :--- |
| `SYNC` | `uint16` | 2 Byte | Preambolo di sincronizzazione costante (`0xAA55`). |
| `SEQ` | `uint16` | 2 Byte | Progressivo del pacchetto (0 - 65535) per packet loss tracking. |
| `MASK` | `uint16` | 2 Byte | Maschera di bit indicante i campi presenti nel Payload. |
| `LEN` | `uint8` | 1 Byte | Lunghezza in byte del solo campo Payload (0 - 255). |

### 2. Payload (Variabile: da 4 a 30 Byte)
I campi sono serializzati sequenzialmente in base all'ordine dei bit attivi nel `MASK` (dal bit `0` al bit `10`).

| Bit MASK | Codice | Campo | Tipo Dato | Dim. | Quantizzazione / Encoding |
| :---: | :---: | :--- | :---: | :---: | :--- |
| `0x0001` | **ICA** | ICAO Address | `uint32` | 4 B | Convertito da Hex String (24-bit). |
| `0x0002` | **CAL** | Callsign | `char[8]` | 8 B | ASCII Padded con `0x00` a destra. |
| `0x0004` | **ALT** | Altitudine | `uint16` | 2 B | Integer in Piedi ($0 \dots 65535$ ft). |
| `0x0008` | **VEL** | Velocità | `uint16` | 2 B | Integer in Nodi ($0 \dots 65535$ kt). |
| `0x0010` | **DIR** | Direzione | `uint16` | 2 B | Gradi normalizzati ($0 \dots 359^\circ$). |
| `0x0020` | **LAT** | Latitudine | `int32` | 4 B | Fixed-point: $\text{Valore} \times 10^7$ (Risoluzione $\approx 11\text{ mm}$). |
| `0x0040` | **LON** | Longitudine | `int32` | 4 B | Fixed-point: $\text{Valore} \times 10^7$ (Risoluzione $\approx 11\text{ mm}$). |
| `0x0080` | **VER** | Vertical Rate | `int16` | 2 B | Piedi/Minuto con segno ($-32768 \dots 32767$). |
| `0x0100` | **SQU** | Squawk Code | `uint16` | 2 B | Decodificato da Notazione Ottale. |
| `0x0200` | **GRO** | Ground State | `uint8` | 1 B | Flag Boolean (`1` = On Ground, `0` = Airborne). |
| `0x0400` | **TIP** | Tipo MSG SBS | `uint8` | 1 B | Id Tipo Messaggio SBS ($1 \dots 8$). |

### 3. Trailer (2 Byte Fisso)
| Campo | Tipo | Dimensione | Descrizione |
| :--- | :--- | :--- | :--- |
| `CRC` | `uint16` | 2 Byte | CRC32 (`zlib.crc32`) calcolato su `Header + Payload`, troncato tramite mascheramento Bitwise `& 0xFFFF`. |

---

## Algoritmo di Trasmissione Semantica (Delta Engine)

Per evitare di inviare pacchetti ridondanti quando un aeromobile è in fase di volo stazionario o di crociera uniforme, l'engine valuta i dati in arrivo dallo stack SBS ed emette pacchetti secondo **tre strategie**:

### 1. Frame Completo (`FULL`)
Forzato ogni **`FULL_FRAME_INTERVAL` (5.0 secondi)** per consentire ai nuovi ricevitori (o ricevitori che hanno perso pacchetti) di ricostruire la telemetria completa dell'aereo.
* **Payload:** Tutti i campi selezionati dall'utente nell'inizializzazione.

### 2. Frame Differenziale (`DELTA`)
Valutato ad una frequenza massima di **2Hz per aereo (`MIN_INTERVAL_PER_AIRCRAFT = 0.5s`)**. Un campo viene inserito nel payload **solamente se** la variazione rispetto all'ultimo valore inviato supera le soglie di tolleranza impostate:

$$\Delta = |\text{Valore}_{\text{attuale}} - \text{Valore}_{\text{ultimo\_inviato}}| \ge \text{Soglia}$$

#### Soglie Cinematch Default (`THRESHOLDS`)
* **Altitudine (`ALT`):** $\ge 50 \text{ ft}$
* **Velocità (`VEL`):** $\ge 5 \text{ kt}$
* **Direzione (`DIR`):** $\ge 3^\circ$
* **Posizione (`LAT`/`LON`):** $\ge 0.002^\circ$ ($\approx 220 \text{ metri}$)
* **Vertical Rate (`VER`):** $\ge 150 \text{ ft/min}$

### 3. Frame di Evento (`EVENT`)
Triggerato istantaneamente in caso di cambio di stato critico non continuo:
* Variazione del codice **Squawk** (`SQU`).
* Transizione dello stato a terra **Ground State** (`GRO`).

---

## Ottimizzazioni di Prestazioni e Gestione Banda
1. **Pre-compilazione di C Struct:** L'inizializzazione dell'encoder fa uso di `struct.Struct` nativo in C (`STRUCT_I`, `STRUCT_H`, ecc.) per azzerare l'overhead di parsing a runtime.
2. **Bufferizzazione Circolare limitata:** La coda di trasmissione seriale `tx_queue` ha un limite rigido di `maxlen=20` pacchetti. In caso di congestione radio, la coda scarta automaticamente i pacchetti più vecchi per evitare latenze nell'invio di dati di posizionamento tempo-reale.
3. **Pacing del TX Airtime:** Imposto un ritardo minimo non-bloccante di **`50 ms` (`LORA_TX_AIRTIME_DELAY`)** tra trasmissioni seriali successive per sincronizzarsi con la durata fisica dell'invio via LoRa (prevenendo la saturazione del buffer del modulo radio RF).
4. **Garbage Collection dinamica del DB in-memory:** Gli aeromobili non più rilevati (nessun aggiornamento SBS per $> 60\text{s}$) vengono rimossi dalla RAM.

---

## Esempio Pratico di Compressione

Immaginiamo un aereo (ICAO: `4B1812`) in virata che cambia solo la **Rotta** (da $120^\circ$ a $126^\circ$):

* **Formato Standard SBS (ASCII):** 
  `MSG,3,1,1,4B1812,1,2023/10/27,12:00:00.000,2023/10/27,12:00:00.000,,35000,,,45.464,9.190,,,,,,`
  *Dimensione:* **~95 Byte (760 Bit)**

* **Formato Compresso ASBP-LoRa (Payload Delta):**
  * **Header:** `SYNC` (2B) + `SEQ` (2B) + `MASK` (2B) + `LEN` (1B)
  * **Mask Active Bits:** `BIT 0` (ICAO) | `BIT 4` (DIR) $\rightarrow$ `0x0011`
  * **Payload:** `ICAO` (4B) + `DIR` (2B)
  * **Trailer:** `CRC16` (2B)
  * *Dimensione Totale:* **15 Byte (120 Bit)**

**Rapporto di Compressione:** **$\approx 84.2\%$ di riduzione della dimensione dei dati.**