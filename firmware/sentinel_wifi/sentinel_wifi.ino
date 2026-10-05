#include <WiFi.h>
#include <ArduinoOTA.h>

// 1. Configuration de l'IP fixe et du réseau de table
IPAddress local_IP(192, 168, 52, 50);   // IP statique fixée pour l'ESP32[cite: 3, 4]
IPAddress gateway(192, 168, 52, 1);     // IP du PC Serveur (Hotspot)
IPAddress subnet(255, 255, 255, 0);     // Masque de sous-réseau[cite: 4]
IPAddress primaryDNS(192, 168, 52, 1);

// Identifiants Wi-Fi
const char* ssid = "Sentinel_G9";
const char* password = "Sentinel_G9";

void setup() {
  Serial.begin(115200);

  // 2. Application de la configuration IP statique
  if (!WiFi.config(local_IP, gateway, subnet, primaryDNS)) {
    Serial.println("Erreur de configuration IP statique");
  }

  // 3. Connexion au Wi-Fi Hotspot
  WiFi.begin(ssid, password);
  Serial.print("Connexion au Wi-Fi ");
  Serial.print(ssid);
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nConnecté au Wi-Fi !");
  Serial.print("Adresse IP fixe de l'ESP32 : ");
  Serial.println(WiFi.localIP());

  // 4. Configuration pour les mises à jour sans fil (OTA)
  ArduinoOTA.setHostname("Sentinel-X-ESP32");
  ArduinoOTA.setPassword("SentinelAdmin2026!"); // Mot de passe pour flasher à distance

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
  // Indispensable pour écouter les demandes de téléversement à distance
  ArduinoOTA.handle();
  
  delay(10);
}
