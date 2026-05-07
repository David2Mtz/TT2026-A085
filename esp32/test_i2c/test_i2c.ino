#include <Wire.h>

/**
 * TEST I2C - ESCÁNER DE DISPOSITIVOS
 * Este código ayuda a verificar si la ESP32 detecta el PCA9685 y el sensor VL53L0X.
 * Pines: SDA=21, SCL=22
 */

void setup() {
  // Inicializamos el bus I2C con los pines de la ESP32
  Wire.begin(21, 22);
  
  Serial.begin(115200);
  while (!Serial); // Esperar a que el monitor serie esté listo
  Serial.println("\n--- ESCÁNER I2C PARA ESP32 ---");
}

void loop() {
  byte error, address;
  int nDevices = 0;

  Serial.println("Escaneando...");

  for(address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("Dispositivo encontrado en dirección 0x");
      if (address < 16) Serial.print("0");
      Serial.print(address, HEX);

      if (address == 0x40) Serial.println(" (Controlador de Servos PCA9685)");
      else if (address == 0x29) Serial.println(" (Sensor VL53L0X)");
      else Serial.println(" (Desconocido)");

      nDevices++;
    }
    else if (error == 4) {
      Serial.print("Error desconocido en dirección 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
    }    
  }

  if (nDevices == 0) {
    Serial.println("No se encontraron dispositivos I2C. Revisa el cableado y la alimentación.");
  } else {
    Serial.println("Escaneo finalizado.\n");
  }

  delay(5000); // Esperar 5 segundos antes del siguiente escaneo
}
