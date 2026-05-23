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

void setup() {
  // Bajamos a 460800 para máxima estabilidad con JPEG
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
  config.xclk_freq_hz = 10000000; // 10MHz es más estable para OV2640

  config.pixel_format = PIXFORMAT_JPEG; 
  config.frame_size = FRAMESIZE_VGA;      
  config.jpeg_quality = 10;
  config.fb_count = 2; 

  esp_err_t err = esp_camera_init(&config);
  int retry = 0;
  while (err != ESP_OK && retry < 3) {
    Serial.printf("Camera init failed with error 0x%x. Retrying... (%d)\n", err, retry+1);
    delay(500);
    err = esp_camera_init(&config);
    retry++;
  }



  if (err != ESP_OK) {
    Serial.println("CAMERA_CRITICAL_FAILURE");
    delay(2000);
    ESP.restart();
  }

  sensor_t * s = esp_camera_sensor_get();
  if (s != NULL) {
    // --- TUS AJUSTES MANUALES EXACTOS ---
    // 1. Control de Exposición y Luz
    // Estas funciones determinan qué tan clara u oscura se ve la imagen.
    
    // Activa o desactiva el Control Automático de Exposición (AEC).
    s->set_exposure_ctrl(s, 0);    // Opciones: 1 (Auto), 0 (Manual).

    // Establece el tiempo de exposición manualmente (solo si set_exposure_ctrl es 0).
    s -> set_aec_value(s, 220); // Opciones: 0 a 1200 (Aproximadamente, depende del sensor). Valores más altos = más luz pero más desenfoque de movimiento.
    
    //Ajusta el "objetivo" de brillo que el modo automático intenta alcanzar.
    //s->set_ae_level(s, 1);       //Opciones: -2, -1, 0, 1, 2.

    // Ajusta el brillo de la imagen mediante procesamiento.
    // s->set_brightness(sensor, level); // Opciones: -2 a 2 (siendo 0 el neutral).

    //Activa el Control Automático de Ganancia (AGC). La ganancia amplifica la señal de luz digitalmente (genera ruido)
    s->set_gain_ctrl(s, 0); //  Opciones: 1 (Auto), 0 (Manual).
    s->set_agc_gain(s, 0);  //   Opciones: 0 a 30.
    // Ganancia manual (solo si set_gain_ctrl es 0).

    // 2. Control de Color y Balance de Blancos
    // Determina la fidelidad de los colores y la temperatura (frío/cálido).

    //Activa el Balance de Blancos Automático (AWB).
    s->set_whitebal(s, 1);  // Opciones: 1 (Auto), 0 (Manual).
    //Presets de temperatura de color (solo si set_whitebal es 1).
    //s->set_wb_mode(s,0); //Opciones: 0: Auto * 1: Sunny (Soleado) * 2: Cloudy (Nublado) * 3: Office (Luz de oficina/Fluorescente) * 4: Home (Luz de casa/Incandescente) 
    // Determina si el hardware puede aplicar ganancia a los canales de color por separado.
    // s->set_awb_gain(s, 1); //  Opciones: 1 (Habilitado), 0 (Deshabilitado).
    // s->set_reg(s, 0xff, 0xff, 0x01);
    // s->set_reg(s, 0x01, 0xff, 0); // AZUL
    // s->set_reg(s, 0x02, 0xff, 0); // ROJO 
    // s->set_reg(s, 0xff, 0xff, 0x00);
    
    //   3. Nitidez y Calidad de Imagen
    // Funciones para mejorar el detalle o reducir imperfecciones.

    //  * set_contrast(sensor, level): Diferencia entre zonas claras y oscuras.
    //      * Opciones: -2 a 2.
    //  * set_sharpness(sensor, level): Realza los bordes de los objetos.
    //      * Opciones: -2 a 2.
    //  * set_denoise(sensor, level): Filtro para reducir el "grano" o ruido digital.
    //      * Opciones: 0 (Apagado) a 2 (Máximo).
    //  * set_quality(sensor, quality): Calidad de compresión JPEG.
    //      * Opciones: 0 a 63. (Cuidado: 0 es la calidad más alta, pero genera archivos tan grandes que el ESP32 puede colapsar. Se recomienda entre 10 y
    //        20).

    s->set_sharpness(s, 2);

  }
  
  delay(500); // Tiempo para que el sensor se estabilice
  Serial.println("CAMERA_READY");
}

void loop() {
  if (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    
    if (line.length() > 0) {
      char comando = line[0];
      
      if (comando == 'R') {
        camera_fb_t * fb = esp_camera_fb_get();
        if (!fb) {
          Serial.println("DEBUG: Capture Failed");
          return;
        }
        
        Serial.write("IMG:", 4);
        uint32_t image_len = fb->len;
        Serial.write((const uint8_t*)&image_len, 4);
        Serial.write(fb->buf, fb->len);
        Serial.flush(); 
        
        esp_camera_fb_return(fb);
      } else if (comando == 'P') {
        Serial.println("PONG");
      }
    }
  }
}
