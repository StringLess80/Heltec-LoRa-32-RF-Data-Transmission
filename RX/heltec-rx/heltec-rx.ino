#include <RadioLib.h>  // Libreria per controllare il chip LoRa SX1262

// Crea l'oggetto radio specificando i pin della Heltec V3:
// CS=8, DIO1=14, RST=12, BUSY=13
SX1262 radio = new Module(8, 14, 12, 13);

volatile bool receivedFlag = false;

void setFlag() {
  receivedFlag = true;  // Imposta il flag di ricezione
}

void setup() {
  // Avvia la comunicazione USB seriale verso il PC
  Serial.begin(115200);

  radio.begin(868.0);           // 868 MHz
  radio.setSpreadingFactor(7);  // da valutare
  radio.setBandwidth(125.0);    // larghezza di banda, 125 kHz
  radio.setCodingRate(5);

  /* Quando arriva un pacchetto, il chip SX1262 alza DIO1
  e l'ESP32 esegue setFlag(). */
  radio.setDio1Action(setFlag);

  // Mette il modulo in ricezione continua
  radio.startReceive();
}

void loop() {

  if (receivedFlag) {
    // Azzera flag
    receivedFlag = false;

    String str;

    // Legge pacchetto dal buffer chip LoRa
    if (radio.readData(str) == RADIOLIB_ERR_NONE) {

      // Invia il testo ricevuto tramite USB seriale
      Serial.println(str);
    }

    // ztorna in ascolto
    radio.startReceive();
  }
}