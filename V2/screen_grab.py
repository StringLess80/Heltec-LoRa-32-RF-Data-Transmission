import serial
import time
from PIL import Image

# Configura la tua porta COM corretta (es. 'COM3' su Windows o '/dev/ttyUSB0' su Linux/macOS)
PORTA_SERIALE = '/dev/ttyUSB0' 
BAUD_RATE = 115200

def salva_immagine(hex_data):
    try:
        # Convertiamo la stringa esadecimale in byte reali
        raw_data = bytes.fromhex(hex_data)
        if len(raw_data) != 1024:
            print(f"Errore: dimensione buffer errata ({len(raw_data)} byte invece di 1024)")
            return

        # Il display SSD1306 della Heltec è organizzato in 8 "pagine" verticali, ciascuna di 128 colonne.
        # Ogni byte rappresenta 8 pixel verticali. Ricostruiamo la matrice corretta:
        img = Image.new('1', (128, 64)) # '1' sta per pixel monocromatico (1-bit)
        pixel_map = img.load()

        for page in range(8):
            for col in range(128):
                byte = raw_data[page * 128 + col]
                for bit in range(8):
                    y = page * 8 + bit
                    x = col
                    # Estraiamo il singolo bit (0 = spento, 1 = acceso)
                    pixel_val = (byte >> bit) & 1
                    pixel_map[x, y] = pixel_val * 255 # Convertiamo in scala 0-255 per il salvataggio

        filename = f"screenshot_{int(time.time())}.png"
        img.save(filename)
        print(f"Screenshot salvato con successo: {filename}")
    except Exception as e:
        print(f"Errore durante la conversione: {e}")

def main():
    print(f"In ascolto sulla porta {PORTA_SERIALE}... Premi a lungo il pulsante PRG sulla scheda Heltec.")
    ser = serial.Serial(PORTA_SERIALE, BAUD_RATE, timeout=1)
    
    buffer_ricezione = ""
    registrazione = False

    while True:
        try:
            if ser.in_waiting > 0:
                linea = ser.readline().decode('utf-8', errors='ignore').strip()
                
                if "---START_SCREENSHOT---" in linea:
                    print("Ricezione screenshot in corso...")
                    buffer_ricezione = ""
                    registrazione = True
                elif "---END_SCREENSHOT---" in linea:
                    registrazione = False
                    salva_immagine(buffer_ricezione)
                elif registrazione:
                    buffer_ricezione += linea
            time.sleep(0.01)
        except KeyboardInterrupt:
            print("\nChiusura programma.")
            break
        except Exception as e:
            print(f"Errore di connessione: {e}")
            break

    ser.close()

if __name__ == "__main__":
    main()