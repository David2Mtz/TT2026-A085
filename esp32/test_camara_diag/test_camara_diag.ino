#include "Arduino.h"
#include "esp_camera.h"

// SCCB_Init y SCCB_Read están disponibles internamente pero a veces 
// requieren declaraciones según la versión del board support package.
// Usaremos el bus I2C estándar para leer los registros de identificación.
#include <Wire.h>

// Pines para AI-Thinker
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define PWDN_GPIO_NUM     32

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n--- IDENTIFICACIÓN PROFUNDA DE SENSOR ---");

  // Encender el sensor (PWDN a LOW)
  pinMode(PWDN_GPIO_NUM, OUTPUT);
  digitalWrite(PWDN_GPIO_NUM, LOW);
  delay(500);

  Wire.begin(SIOD_GPIO_NUM, SIOC_GPIO_NUM);
  
  // La dirección I2C de la mayoría de sensores OmniVision (incluyendo OV2640) es 0x30
  byte sensor_addr = 0x30;
  
  auto readRegister = [&](byte reg) -> byte {
    Wire.beginTransmission(sensor_addr);
    Wire.write(reg);
    if (Wire.endTransmission() != 0) return 0xFF;
    Wire.requestFrom(sensor_addr, (byte)1);
    if (Wire.available()) return Wire.read();
    return 0xFF;
  };

  Serial.println("Leyendo registros de identificación...");
  
  // Registros estándar de identificación OV
  byte midh = readRegister(0x1C); // Manufacturer ID High
  byte midl = readRegister(0x1D); // Manufacturer ID Low
  byte pid  = readRegister(0x0A); // Product ID
  byte ver  = readRegister(0x0B); // Version ID

  Serial.printf("Fabricante (MID): 0x%02X 0x%02X\n", midh, midl);
  Serial.printf("Producto (PID): 0x%02X\n", pid);
  Serial.printf("Versión (VER): 0x%02X\n", ver);

  if (pid == 0x26) {
    Serial.println("\nRESULTADO: El chip se identifica como OV2640.");
    Serial.println("Si la librería falla con 0x106, es probable que:");
    Serial.println("1. El sensor esté respondiendo con ruido.");
    Serial.println("2. El cable flex tenga una línea de datos (D0-D7) en corto.");
    Serial.println("3. El reloj XCLK sea inestable.");
  } else if (pid == 0x76 || pid == 0x77) {
    Serial.println("\nRESULTADO: Es una OV7670. No soporta JPEG.");
  } else if (pid == 0xFF) {
    Serial.println("\nRESULTADO: No hay respuesta del sensor (0xFF).");
    Serial.println("Verifica que el flex esté bien insertado y que el sensor reciba 3.3V.");
  } else {
    Serial.printf("\nRESULTADO: Sensor desconocido (PID: 0x%02X).\n", pid);
    Serial.println("No es una OV2640 estándar.");
  }
}

void loop() {}
