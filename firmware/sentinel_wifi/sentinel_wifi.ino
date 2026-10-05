#include <WiFi.h>

// Configuration du réseau et de l'IP fixe
IPAddress local_IP(192, 168, 52, 50);   // IP statique pour l'ESP32
IPAddress gateway(192, 168, 52, 1);     // IP du PC Serveur Hotspot
IPAddress subnet(255, 255, 255, 0);     // Masque de sous-réseau
IPAddress primaryDNS(8, 8, 8, 8);

const char* ssid = "Sentinel_G9";        // Nom de ton Wi-Fi Hotspot
const char* password = "Sentinel_G9";    // Mot de passe de ton Hotspot

void setup() {
  Serial.begin(115200);

  // Application de la configuration IP statique
  if (!WiFi.config(local_IP, gateway, subnet, primaryDNS)) {
    Serial.println("Erreur de configuration IP statique");
  }

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
}

void loop() {
  delay(1000);
}
