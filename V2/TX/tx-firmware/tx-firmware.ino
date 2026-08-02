#include <RadioLib.h>
#include <U8g2lib.h>
#include <Wire.h>

// Initialize SX1262 for Heltec V3
// CS=8, DIO1=14, RST=12, BUSY=13
SX1262 radio = new Module(8, 14, 12, 13);

// Initialize OLED for Heltec V3 (SDA=17, SCL=18, RST=21)
U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, /* reset=*/ 21, /* clock=*/ 18, /* data=*/ 17);

#define VEXT_PIN 36
#define BUTTON_PIN 0 // Pulsante PRG (BOOT) su Heltec V3

#define SYNC_0 0x55
#define SYNC_1 0xAA
#define HEADER_SIZE 7

uint8_t txBuffer[300];
uint16_t txIndex = 0;
uint16_t expectedLength = 0;
bool syncing = true;

// Statistiche di trasmissione
uint32_t txCount = 0;
uint16_t lastTxLength = 0;
int lastTxState = RADIOLIB_ERR_NONE;

// Gestione Pagine
volatile uint8_t currentPage = 0;
const uint8_t TOTAL_PAGES = 3;
volatile bool buttonPressed = false;

// ISR per il pulsante PRG con debounce integrato
#if defined(ESP32)
  void IRAM_ATTR buttonISR() {
#else
  void buttonISR() {
#endif
  static unsigned long lastInterruptTime = 0;
  unsigned long interruptTime = millis();
  if (interruptTime - lastInterruptTime > 200) { // Debounce di 200ms
    buttonPressed = true;
    lastInterruptTime = interruptTime;
  }
}

// DISEGNO PAGINA 0: Pannello di controllo Trasmissione
void drawPage0() {
  u8g2.setFont(u8g2_font_helvB08_tr);
  u8g2.drawStr(0, 10, "TX DASHBOARD");
  u8g2.drawHLine(0, 13, 128);

  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.setCursor(0, 27);
  u8g2.print("Inviati:    "); u8g2.print(txCount);

  u8g2.setCursor(0, 39);
  u8g2.print("Ultimo TX:  "); u8g2.print(lastTxLength); u8g2.print(" bytes");

  u8g2.setCursor(0, 51);
  u8g2.print("Stato TX:   ");
  if (lastTxState == RADIOLIB_ERR_NONE) {
    u8g2.print("OK (0)");
  } else {
    u8g2.print("ERR ("); u8g2.print(lastTxState); u8g2.print(")");
  }

  u8g2.setCursor(0, 63);
  u8g2.print("Potenza:    +14 dBm");
}

// DISEGNO PAGINA 1: Stato dell'interfaccia seriale e parser
void drawPage1() {
  u8g2.setFont(u8g2_font_helvB08_tr);
  u8g2.drawStr(0, 10, "STATO SERIALE (RX)");
  u8g2.drawHLine(0, 13, 128);

  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.setCursor(0, 27);
  u8g2.print("Fase: ");
  u8g2.print(syncing ? "Ricerca Sync" : "Ricezione Dati");

  u8g2.setCursor(0, 39);
  u8g2.print("Ricevuti:  "); u8g2.print(txIndex); u8g2.print(" bytes");

  u8g2.setCursor(0, 51);
  u8g2.print("Attesi:    ");
  if (syncing) {
    u8g2.print("-");
  } else {
    u8g2.print(expectedLength); u8g2.print(" bytes");
  }

  u8g2.setCursor(0, 63);
  u8g2.print("Buffer RX: 1024 bytes");
}

// DISEGNO PAGINA 2: Configurazione parametri LoRa
void drawPage2() {
  u8g2.setFont(u8g2_font_helvB08_tr);
  u8g2.drawStr(0, 10, "CONFIGURAZIONE LORA");
  u8g2.drawHLine(0, 13, 128);

  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.setCursor(0, 27);
  u8g2.print("Freq:  868.0 MHz");

  u8g2.setCursor(0, 39);
  u8g2.print("SF:    7");

  u8g2.setCursor(0, 51);
  u8g2.print("BW:    125.0 kHz");

  u8g2.setCursor(0, 63);
  u8g2.print("CR:    4/5");
}

// Rendering generale basato sulla pagina attiva
void updateOLED() {
  u8g2.clearBuffer();
  
  switch (currentPage) {
    case 0: drawPage0(); break;
    case 1: drawPage1(); break;
    case 2: drawPage2(); break;
  }
  
  // Indicatori di pagina (pallini) in alto a destra
  for (int i = 0; i < TOTAL_PAGES; i++) {
    if (i == currentPage) {
      u8g2.drawDisc(112 + (i * 5), 5, 2);
    } else {
      u8g2.drawCircle(112 + (i * 5), 5, 2);
    }
  }

  u8g2.sendBuffer();
}

void setup() {
  // Configura buffer seriale esteso per evitare perdite di byte durante la trasmissione
  Serial.setRxBufferSize(1024);
  Serial.begin(115200);

  // Attiva l'alimentazione del display (Vext)
  pinMode(VEXT_PIN, OUTPUT);
  digitalWrite(VEXT_PIN, LOW); 
  delay(50);

  // Configura pulsante PRG (BOOT) come input con pull-up
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), buttonISR, FALLING);

  // Inizializza OLED
  u8g2.begin();
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_helvB08_tr);
  u8g2.drawStr(0, 25, "Inizializzazione...");
  u8g2.sendBuffer();

  // Inizializza modulo radio
  int state = radio.begin(868.0);
  if (state != RADIOLIB_ERR_NONE) {
    u8g2.clearBuffer();
    u8g2.drawStr(0, 20, "Errore LoRa!");
    u8g2.setCursor(0, 35);
    u8g2.print("Codice: "); u8g2.print(state);
    u8g2.sendBuffer();
    while (true); // Halt on failure
  }

  radio.setSpreadingFactor(7);
  radio.setBandwidth(125.0);
  radio.setCodingRate(5);
  radio.setOutputPower(14); // ~25mW

  // Prima visualizzazione
  updateOLED();
}

void loop() {
  // Gestione del cambio pagina tramite pulsante PRG
  if (buttonPressed) {
    buttonPressed = false;
    currentPage = (currentPage + 1) % TOTAL_PAGES;
    updateOLED();
  }

  // Lettura dati binari grezzi da interfaccia Seriale
  while (Serial.available()) {
    uint8_t c = Serial.read();

    if (syncing) {
      if (txIndex == 0 && c == SYNC_0) {
        txBuffer[txIndex++] = c;
      } else if (txIndex == 1 && c == SYNC_1) {
        txBuffer[txIndex++] = c;
        syncing = false; // Sincronizzazione completata, inizia la lettura del pacchetto
        
        // Aggiorna lo stato sul display se l'utente si trova in Pagina 1
        if (currentPage == 1) {
          updateOLED();
        }
      } else {
        txIndex = 0;
        if (c == SYNC_0) {
          txBuffer[txIndex++] = c;
        }
      }
    } else {
      txBuffer[txIndex++] = c;

      // Estrazione lunghezza del payload dal byte di intestazione dedicato
      if (txIndex == HEADER_SIZE) {
        uint8_t payloadLen = txBuffer[6];
        // Dimensione Totale = Header (7) + Payload + CRC (2)
        expectedLength = HEADER_SIZE + payloadLen + 2; 
        
        if (currentPage == 1) {
          updateOLED();
        }
      }

      // Se l'intero pacchetto è stato accumulato nel buffer
      if (txIndex > HEADER_SIZE && txIndex >= expectedLength) {
        
        // Esegue la trasmissione radio
        lastTxLength = expectedLength;
        lastTxState = radio.transmit(txBuffer, expectedLength);
        
        if (lastTxState == RADIOLIB_ERR_NONE) {
          txCount++;
        }

        // Reset dello stato del parser per il pacchetto successivo
        txIndex = 0;
        syncing = true;

        // Aggiorna la schermata con le nuove statistiche di TX
        updateOLED();
      }
    }

    // Controllo di sicurezza sui limiti del buffer
    if (txIndex >= sizeof(txBuffer)) {
      txIndex = 0;
      syncing = true;
      if (currentPage == 1) {
        updateOLED();
      }
    }
  }
}