#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include "Adafruit_VL53L0X.h"
#include <Adafruit_MLX90393.h>

/**
 * FIRMWARE UNIFICADO - BRAZO ROBÓTICO + SENSORES
 * - Bus 0 (21, 22): PCA9685, VL53L0X, Magnetómetro 1
 * - Bus 1 (17, 16): Magnetómetro 2
 */

// --- CONFIGURACIÓN DE PINES I2C ---
#define SDA0 21
#define SCL0 22
#define SDA1 15
#define SCL1 4

// Instancias
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);
Adafruit_VL53L0X lox = Adafruit_VL53L0X();
Adafruit_MLX90393 mag1 = Adafruit_MLX90393();
Adafruit_MLX90393 mag2 = Adafruit_MLX90393();

#define SERVOMIN  100       
#define SERVOMAX  575 

// {0:Base, 1:Hombro, 2:Hombro_Inv, 6:Codo, 12:Pinza, 13:Roll, 15:Pitch}
int angulosActuales[16] = {90, 180, 0, 0, 0, 0, 140, 0, 0, 0, 0, 0, 80, 0, 0, 90};
int retardosSeguros[16] = {15, 20, 20, 20, 20, 20, 25, 20, 20, 20, 20, 20, 15, 20, 20, 15}; 

unsigned long lastSensorTime = 0;
const int sensorInterval = 100; 

void setup() {
  Serial.begin(115200);
  
  // Inicializar Buses I2C
  Wire.begin(SDA0, SCL0);   // Bus principal
  Wire1.begin(SDA1, SCL1);  // Bus secundario
  
  // 1. Inicializar PCA9685 (Bus 0)
  pwm.begin();
  pwm.setPWMFreq(60); 

  // 2. Inicializar ToF (Bus 0)
  if (!lox.begin()) Serial.println("ERR:TOF_NOT_FOUND");

  // 3. Inicializar Magnetómetro 1 (Bus 0)
  if (!mag1.begin_I2C(0x0C, &Wire)) {
    Serial.println("ERR:MAG1_NOT_FOUND");
  } else {
    mag1.setGain(MLX90393_GAIN_1X);
  }

  // 4. Inicializar Magnetómetro 2 (Bus 1)
  if (!mag2.begin_I2C(0x0C, &Wire1)) {
    Serial.println("ERR:MAG2_NOT_FOUND");
  } else {
    mag2.setGain(MLX90393_GAIN_1X);
  }

  // Movimiento inicial suave a posición HOME
  for(int i=0; i<16; i++){
    if(i == 2) { // Pin 2 es espejo del 1
      pwm.setPWM(2, 0, (SERVOMIN + SERVOMAX) - map(angulosActuales[1], 0, 180, SERVOMIN, SERVOMAX));
    } else {
      pwm.setPWM(i, 0, map(angulosActuales[i], 0, 180, SERVOMIN, SERVOMAX));
    }
  }
  Serial.println("SYSTEM_READY");
}

void loop() {
  // --- 1. RECEPCIÓN DE COMANDOS ---
  if (Serial.available() > 0) {
    if (Serial.peek() == '$') {
      Serial.read(); // Quitar '$'
      String comando = Serial.readStringUntil('\n');
      if (procesarComando(comando)) {
        Serial.println("OK"); 
        while(Serial.available() > 0) Serial.read(); // Limpiar buffer
      }
    } else {
      Serial.read(); // Limpiar basura
    }
  }

  // --- 2. ENVÍO DE SENSORES (ASÍNCRONO) ---
  unsigned long currentMillis = millis();
  if (currentMillis - lastSensorTime >= sensorInterval) {
    // Lectura ToF
    VL53L0X_RangingMeasurementData_t measure;
    lox.rangingTest(&measure, false);
    if (measure.RangeStatus != 4) {
      Serial.print("DIST:"); Serial.println(measure.RangeMilliMeter);
    }

    // Lectura Magnetómetro 1
    float mx1, my1, mz1;
    if (mag1.readData(&mx1, &my1, &mz1)) {
      Serial.print("MAG1:");
      Serial.print(mx1); Serial.print(",");
      Serial.print(my1); Serial.print(",");
      Serial.println(mz1);
    }

    // Lectura Magnetómetro 2
    float mx2, my2, mz2;
    if (mag2.readData(&mx2, &my2, &mz2)) {
      Serial.print("MAG2:");
      Serial.print(mx2); Serial.print(",");
      Serial.print(my2); Serial.print(",");
      Serial.println(mz2);
    }
    
    lastSensorTime = currentMillis;
  }
}

bool procesarComando(String comando) {
  comando.trim();
  if (comando.length() == 0) return false;

  int pines[16], destinos[16], contador = 0;
  int startIndex = 0;

  // Extraer múltiples pares pin,angulo;
  while (startIndex < comando.length() && contador < 16) {
    int sepIndex = comando.indexOf(';', startIndex);
    String parStr = (sepIndex == -1) ? comando.substring(startIndex) : comando.substring(startIndex, sepIndex);
    startIndex = (sepIndex == -1) ? comando.length() : sepIndex + 1;

    int commaIndex = parStr.indexOf(',');
    if (commaIndex != -1) {
      int pin = parStr.substring(0, commaIndex).toInt();
      int ang = parStr.substring(commaIndex + 1).toInt();
      if (pin >= 0 && pin <= 15 && ang >= 0 && ang <= 180) {
        pines[contador] = pin;
        destinos[contador] = ang;
        contador++;
      }
    }
  }

  if (contador > 0) {
    moverSimultaneo(pines, destinos, contador);
    return true;
  }
  return false;
}

void moverSimultaneo(int pines[], int destinos[], int cantidad) {
  long tiempoMaximoMs = 0;
  int pulsosInicio[16], pulsosFin[16];

  for (int i = 0; i < cantidad; i++) {
    int pin = pines[i];
    long tReq = abs(destinos[i] - angulosActuales[pin]) * (long)retardosSeguros[pin];
    if (tReq > tiempoMaximoMs) tiempoMaximoMs = tReq;
    
    pulsosInicio[i] = map(angulosActuales[pin], 0, 180, SERVOMIN, SERVOMAX);
    pulsosFin[i]    = map(destinos[i], 0, 180, SERVOMIN, SERVOMAX);
  }

  if (tiempoMaximoMs == 0) return;

  int pasoMs = 15; 
  int numPasos = tiempoMaximoMs / pasoMs;
  if (numPasos < 1) numPasos = 1;

  for (int p = 1; p <= numPasos; p++) {
    for (int i = 0; i < cantidad; i++) {
      int pin = pines[i];
      int pulsoActual = pulsosInicio[i] + ((pulsosFin[i] - pulsosInicio[i]) * p) / numPasos;
      pwm.setPWM(pin, 0, pulsoActual);
      
      // Hombro Doble Automático
      if (pin == 1) {
        pwm.setPWM(2, 0, (SERVOMIN + SERVOMAX) - pulsoActual);
      }
    }
    delay(pasoMs); 
  }

  // Actualizar estados finales
  for (int i = 0; i < cantidad; i++) {
    angulosActuales[pines[i]] = destinos[i];
    if (pines[i] == 1) angulosActuales[2] = 180 - destinos[i];
  }
}
