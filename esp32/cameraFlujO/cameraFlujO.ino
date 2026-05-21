#include "esp_camera.h"

// --- PINES PARA XIAO ESP32-S3 SENSE ---
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     10
#define SIOD_GPIO_NUM     40
#define SIOC_GPIO_NUM     39

#define Y9_GPIO_NUM       48
#define Y8_GPIO_NUM       11
#define Y7_GPIO_NUM       12
#define Y6_GPIO_NUM       14
#define Y5_GPIO_NUM       16
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       17
#define Y2_GPIO_NUM       15
#define VSYNC_GPIO_NUM    38
#define HREF_GPIO_NUM     47
#define PCLK_GPIO_NUM     13

#define LED_PIN           21

void setup() {
  // BAJAMOS A 460800 PARA EVITAR ERRORES DE SINCRONIZACIÓN
  Serial.begin(460800); 

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA; 
  config.jpeg_quality = 15;          
  config.fb_count = 2;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    delay(1000);
    ESP.restart();
  }

  sensor_t * s = esp_camera_sensor_get();
  
  // --- CORRECCIÓN PERMANENTE DE COLOR (Mata el Verde) ---
  s->set_whitebal(s, 1);       // Desactivar Balance de Blancos Automático
  s->set_awb_gain(s, 1);       // Habilitar ganancias manuales
  
  // Ajuste de registros para sensor MJY (Clon compatible OV2640)
  s->set_reg(s, 0xff, 0xff, 0x01); // Seleccionar banco 1
  s->set_reg(s, 0x03, 0xff, 175);  // Ganancia Azul (Perfil MJY)
  s->set_reg(s, 0x05, 0xff, 125);  // Ganancia Rojo (Perfil MJY)
  s->set_reg(s, 0xff, 0xff, 0x00); // Regresar al banco 0


  s->set_exposure_ctrl(s, 1);  // Mantener exposición automática para el brillo
  s->set_gain_ctrl(s, 1);      
}

void loop() {
  if (Serial.available() > 0) {
    char comando = Serial.read();
    
    if (comando == 'R') {
      while(Serial.available() > 0) Serial.read();
      camera_fb_t * fb = esp_camera_fb_get();
      if (!fb) return;
      
      Serial.write((const uint8_t*)"IMG:", 4);
      uint32_t image_len = fb->len;
      Serial.write((const uint8_t*)&image_len, 4);
      Serial.write(fb->buf, fb->len);
      Serial.flush();
      
      esp_camera_fb_return(fb);
    }
  }
}
