/**
 * TEST SIMPLE DE BOTÓN - PIN 34
 * 
 * Conexión sugerida (Active High):
 * - Pin 34 -> Botón -> 3.3V
 * - Pin 34 -> Resistencia 10k -> GND (Importante: el pin 34 no tiene pull-down interna)
 */

#define BUTTON_PIN 34

bool ultimoEstado = LOW;

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT);
  Serial.println("--- TEST DE BOTÓN INICIADO ---");
  Serial.println("Esperando pulsacion en el pin 34...");
}

void loop() {
  bool estadoActual = digitalRead(BUTTON_PIN);

  // Detectar cuando se presiona (flanco de subida)
  if (estadoActual == HIGH ) {
    Serial.println("boton precionado");
    delay(50); // Pequeño anti-rebote
  }

  ultimoEstado = estadoActual;
}
