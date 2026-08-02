#include <RadioLib.h>

// Initialize SX1262 for Heltec V3
// CS=8, DIO1=14, RST=12, BUSY=13
SX1262 radio = new Module(8, 14, 12, 13);

volatile bool receivedFlag = false;

// IRAM_ATTR is important on newer ESP32 cores for interrupts to avoid crashes
#if defined(ESP32)
  void IRAM_ATTR setFlag() {
#else
  void setFlag() {
#endif
  receivedFlag = true;
}

void setup() {
  // Start USB serial communication
  Serial.begin(115200);

  int state = radio.begin(868.0);
  if (state != RADIOLIB_ERR_NONE) {
    while (true); // Halt on failure
  }

  radio.setSpreadingFactor(7);
  radio.setBandwidth(125.0);
  radio.setCodingRate(5);

  // When a packet arrives, the SX1262 pulls DIO1 high
  radio.setDio1Action(setFlag);

  // Put module in continuous receive mode
  radio.startReceive();
}

void loop() {
  if (receivedFlag) {
    // Reset flag
    receivedFlag = false;

    // Get the length of the received binary packet
    size_t length = radio.getPacketLength();

    if (length > 0) {
      uint8_t rxBuffer[256]; // The max SX1262 payload is 256 bytes

      // Read binary packet from LoRa chip buffer
      int state = radio.readData(rxBuffer, length);

      if (state == RADIOLIB_ERR_NONE) {
        // Write exactly the raw bytes via USB Serial (DO NOT use println)
        Serial.write(rxBuffer, length);
      }
    }

    // Immediately go back to listening
    radio.startReceive();
  }
}