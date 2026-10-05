#include <WiFi.h>
#include <ArduinoOTA.h>

// 1. Configuration IP et réseau
IPAddress local_IP(192, 168, 52, 50);   // IP statique pour l'ESP32[cite: 3, 4]
IPAddress gateway(192, 168, 52, 1);     // IP du PC Serveur Hotspot[cite: 4]
IPAddress subnet(255, 255, 255, 0);     // Masque de sous-réseau[cite: 4]
IPAddress primaryDNS(8, 8, 8, 8);

// Identifiants Wi-Fi
const char* ssid = "Sentinel_G9";
const char* password = "Sentinel_G9";

void setup() {
  Serial.begin(115200);
  delay(100);

  // Reinitialisation propre du Wi-Fi
  WiFi.mode(WIFI_OFF);
  delay(100);
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(100);

  // 2. Application de la configuration IP statique
  if (!WiFi.config(local_IP, gateway, subnet, primaryDNS)) {
    Serial.println("Erreur de configuration IP statique");
  }

  // 3. Connexion au Wi-Fi Hotspot
  WiFi.begin(ssid, password);
  Serial.print("Connexion au Wi-Fi ");
  Serial.print(ssid);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    attempts++;

    // Relance la demande de connexion si delai depasse (15 sec)
    if (attempts > 30) {
      Serial.println("\nEchec temporaire, nouvelle tentative...");
      WiFi.begin(ssid, password);
      attempts = 0;
    }
  }

  Serial.println("\nConnecté au Wi-Fi !");
  Serial.print("Adresse IP fixe de l'ESP32 : ");
  Serial.println(WiFi.localIP());

  // 4. Configuration OTA
  ArduinoOTA.setHostname("Sentinel_G9");
  ArduinoOTA.setPassword("Sentinel_G9");

  ArduinoOTA.onStart([]() {
    Serial.println("Début du téléversement OTA...");
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("\nTéléversement OTA terminé !");
  });
  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("Erreur OTA [%u]\n", error);
  });

  ArduinoOTA.begin();
  Serial.println("Service OTA prêt !");
}

void loop() {
  ArduinoOTA.handle();
  delay(10);
}
