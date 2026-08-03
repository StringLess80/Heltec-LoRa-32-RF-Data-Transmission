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

volatile bool receivedFlag = false;
volatile bool buttonPressed = false;

// Statistiche e Storico
uint32_t rxCount = 0;
float lastRSSI = 0.0;
float lastSNR = 0.0;
size_t lastLength = 0;

const int MAX_HIST = 20;
float rssiHistory[MAX_HIST];
int historyIndex = 0;

// Gestione Pagine
volatile uint8_t currentPage = 0;
const uint8_t TOTAL_PAGES = 3;

// ISR per la ricezione LoRa
#if defined(ESP32)
  void IRAM_ATTR setFlag() {
#else
  void setFlag() {
#endif
  receivedFlag = true;
}

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

// Aggiunge un valore RSSI allo storico traslando i vecchi elementi
void addRSSItoHistory(float newRSSI) {
  for (int i = 0; i < MAX_HIST - 1; i++) {
    rssiHistory[i] = rssiHistory[i + 1];
  }
  rssiHistory[MAX_HIST - 1] = newRSSI;
  if (historyIndex < MAX_HIST) {
    historyIndex++;
  }
}

// DISEGNO PAGINA 0: Statistiche principali dell'ultimo pacchetto
void drawPage0() {
  u8g2.setFont(u8g2_font_helvB08_tr);
  u8g2.drawStr(0, 10, "LIVE MONITOR");
  u8g2.drawHLine(0, 13, 128);

  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.setCursor(0, 27);
  u8g2.print("Ricevuti:  "); u8g2.print(rxCount);
  
  u8g2.setCursor(0, 39);
  u8g2.print("RSSI:      "); u8g2.print(lastRSSI, 1); u8g2.print(" dBm");

  u8g2.setCursor(0, 51);
  u8g2.print("SNR:       "); u8g2.print(lastSNR, 1); u8g2.print(" dB");

  u8g2.setCursor(0, 63);
  u8g2.print("Payload:   "); u8g2.print(lastLength); u8g2.print(" bytes");
}

// DISEGNO PAGINA 1: Grafico storico RSSI
void drawPage1() {
  u8g2.setFont(u8g2_font_helvB08_tr);
  u8g2.drawStr(0, 10, "STORICO RSSI (dBm)");
  u8g2.drawHLine(0, 13, 128);

  // Box del grafico (X: 18 a 118, Y: 18 a 54)
  int graphX = 18;
  int graphY = 18;
  int graphW = 100;
  int graphH = 36;
  u8g2.drawFrame(graphX, graphY, graphW, graphH);

  // Etichette assi Y
  u8g2.setFont(u8g2_font_5x7_tr);
  u8g2.drawStr(0, 23, "-40");
  u8g2.drawStr(0, 54, "-120");

  // Disegno del grafico a linee
  if (historyIndex > 0) {
    int pointsToShow = historyIndex < MAX_HIST ? historyIndex : MAX_HIST;
    int stepX = graphW / (MAX_HIST - 1);
    
    int prevX = -1;
    int prevY = -1;

    for (int i = 0; i < pointsToShow; i++) {
      // Calcolo indice reale nello storico
      int idx = MAX_HIST - pointsToShow + i;
      float val = rssiHistory[idx];

      // Limita il valore RSSI tra -120 e -40 per la visualizzazione
      float constrainedVal = constrain(val, -120.0, -40.0);
      
      // Mappa il valore nello spazio verticale del grafico (inversamente proporzionale)
      int py = graphY + graphH - map(constrainedVal, -120, -40, 0, graphH);
      int px = graphX + (i * stepX);

      if (i > 0 && prevY != -1) {
        u8g2.drawLine(prevX, prevY, px, py);
      }
      u8g2.drawDisc(px, py, 1); // Piccolo punto sul valore

      prevX = px;
      prevY = py;
    }
  } else {
    u8g2.setFont(u8g2_font_6x12_tr);
    u8g2.drawStr(25, 38, "In attesa dati...");
  }

  // Footer pagina
  u8g2.setFont(u8g2_font_5x7_tr);
  u8g2.drawStr(18, 62, "Meno recenti -> Recenti");
}

// DISEGNO PAGINA 2: Configurazione di sistema
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

// Funzione per dumpare la memoria dello schermo via seriale
void inviaScreenshot() {
  Serial.println("\n---START_SCREENSHOT---");
  
  uint8_t *buffer = u8g2.getBufferPtr();
  for (uint16_t i = 0; i < 1024; i++) {
    if (buffer[i] < 0x10) Serial.print("0");
    Serial.print(buffer[i], HEX);
  }
  
  Serial.println("\n---END_SCREENSHOT---");
}

// Rendering generale
void updateOLED() {
  u8g2.clearBuffer();
  
  switch (currentPage) {
    case 0: drawPage0(); break;
    case 1: drawPage1(); break;
    case 2: drawPage2(); break;
  }
  
  // Indicatore di pagina in basso a destra (piccoli pallini)
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
  // Start USB serial communication
  Serial.begin(115200);

  // Attiva alimentazione display OLED (Vext)
  pinMode(VEXT_PIN, OUTPUT);
  digitalWrite(VEXT_PIN, LOW); 
  delay(50);

  // Configura pulsante PRG (BOOT) come input con pull-up
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), buttonISR, FALLING);

  // Inizializza storico RSSI a valori nulli
  for (int i = 0; i < MAX_HIST; i++) {
    rssiHistory[i] = -140.0;
  }

  // Inizializza OLED con font pulito
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
    while (true);
  }

  radio.setSpreadingFactor(7);
  radio.setBandwidth(125.0);
  radio.setCodingRate(5);

  // Configura interrupt LoRa
  radio.setDio1Action(setFlag);

  // Metti in ascolto
  radio.startReceive();

  // Prima visualizzazione
  updateOLED();
}

void loop() {
  // Gestione del pulsante PRG (pressione breve o lunga)
  if (buttonPressed) {
    buttonPressed = false;
    unsigned long pressStart = millis();
    bool isLongPress = false;

    // Monitora lo stato del pulsante finché rimane premuto
    while (digitalRead(BUTTON_PIN) == LOW) {
      if (millis() - pressStart > 2000) { // Premuto per più di 2 secondi
        isLongPress = true;
        
        // 1. Invia IMMEDIATAMENTE lo screenshot (che contiene la pagina attiva)
        inviaScreenshot();
        
        // 2. Solo ORA diamo il feedback visivo di "scatto avvenuto" disegnando la cornice
        u8g2.clearBuffer();
        u8g2.drawFrame(0, 0, 128, 64);
        u8g2.sendBuffer();
        
        delay(500); // Mostra la cornice per mezzo secondo
        updateOLED(); // Ripristina la schermata originale (ri-disegna la pagina corrente)
        break;
      }
    }

    if (!isLongPress) {
      // Pressione normale: cambia pagina
      currentPage = (currentPage + 1) % TOTAL_PAGES;
      updateOLED();
    }
  }

  // Gestione del pacchetto ricevuto
  if (receivedFlag) {
    receivedFlag = false;

    size_t length = radio.getPacketLength();

    if (length > 0) {
      uint8_t rxBuffer[256];

      int state = radio.readData(rxBuffer, length);

      if (state == RADIOLIB_ERR_NONE) {
        rxCount++;
        lastRSSI = radio.getRSSI();
        lastSNR = radio.getSNR();
        lastLength = length;

        // Salva l'RSSI nello storico del grafico
        addRSSItoHistory(lastRSSI);

        // Invia i dati raw via USB Serial prima di aggiornare il display
        Serial.write(rxBuffer, length);

        // Aggiorna la schermata attuale con le nuove statistiche
        updateOLED();
      }
    }

    // Ritorna in ascolto
    radio.startReceive();
  }
}