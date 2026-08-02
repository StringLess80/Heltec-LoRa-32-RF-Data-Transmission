#include <RadioLib.h>

// Initialize SX1262 for Heltec V3
// CS=8, DIO1=14, RST=12, BUSY=13
SX1262 radio = new Module(8, 14, 12, 13);

#define SYNC_0 0x55
#define SYNC_1 0xAA
#define HEADER_SIZE 7

uint8_t txBuffer[300];
uint16_t txIndex = 0;
uint16_t expectedLength = 0;
bool syncing = true;

void setup() {
  Serial.setRxBufferSize(1024);
  Serial.begin(115200);

  int state = radio.begin(868.0);
  if (state != RADIOLIB_ERR_NONE) {
    while (true); // Halt on failure
  }

  radio.setSpreadingFactor(7);
  radio.setBandwidth(125.0);
  radio.setCodingRate(5);
  radio.setOutputPower(14); // ~25mW
}

void loop() {
  // Read raw binary data from Serial
  while (Serial.available()) {
    uint8_t c = Serial.read();

    if (syncing) {
      if (txIndex == 0 && c == SYNC_0) {
        txBuffer[txIndex++] = c;
      } else if (txIndex == 1 && c == SYNC_1) {
        txBuffer[txIndex++] = c;
        syncing = false; // Sync found, start reading the rest of the packet
      } else {
        // Sync failed, reset
        txIndex = 0;
        if (c == SYNC_0) {
          txBuffer[txIndex++] = c;
        }
      }
    } else {
      txBuffer[txIndex++] = c;

      // Once we have the full 7-byte header, extract the payload length to calculate total packet size
      if (txIndex == HEADER_SIZE) {
        uint8_t payloadLen = txBuffer[6];
        // Total Size = Header (7) + Payload + CRC (2)
        expectedLength = HEADER_SIZE + payloadLen + 2; 
      }

      // If we have received the exact amount of bytes for the full packet
      if (txIndex > HEADER_SIZE && txIndex >= expectedLength) {
        
        // Transmit the binary packet over LoRa
        radio.transmit(txBuffer, expectedLength);

        // Reset state machine for the next packet
        txIndex = 0;
        syncing = true;
      }
    }

    // Safety buffer bound check
    if (txIndex >= sizeof(txBuffer)) {
      txIndex = 0;
      syncing = true;
    }
  }
}