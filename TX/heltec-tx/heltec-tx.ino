#include <RadioLib.h>

// Crea l'oggetto radio specificando i pin della Heltec V3:
// CS=8, DIO1=14, RST=12, BUSY=13
SX1262 radio = new Module(8, 14, 12, 13);

void setup() {
  Serial.begin(115200);

  radio.begin(868.0);           // 868 MHz
  radio.setSpreadingFactor(7);  // da valutare
  radio.setBandwidth(125.0);    // larghezza di banda, 125 kHz
  radio.setCodingRate(5);
  radio.setOutputPower(14);  // P. di tramsissione 14 dbm circa 25 mW
}

void loop() {
  if (Serial.available()) {
    String msg = Serial.readStringUntil('\n');

    int state = radio.transmit(msg);

    if (state == RADIOLIB_ERR_NONE) {
      Serial.println("TX OK");
    } else {
      Serial.print("TX ERR: ");
      Serial.println(state);
    }
  }
}