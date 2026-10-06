#include <WiFi.h>
#include <ArduinoOTA.h>
#include <DHT.h>
#include <PubSubClient.h>
#include "secrets.h"

#define DHTPIN 4
#define DHTTYPE DHT22
#define PIR_PIN 27
#define MQ2_PIN 34
#define BUZZER_PIN 26

const char* TABLE_ID = "table1";

IPAddress local_IP(192, 168, 52, 50);
IPAddress gateway(192, 168, 52, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress primaryDNS(8, 8, 8, 8);

const char* ssid = "Sentinel_G9";
const char* password = "Sentinel_G9";

const char* MQTT_HOST = "192.168.52.1";
const int MQTT_PORT = 1883;

String topicSensors;
String topicCmd;

DHT dht(DHTPIN, DHTTYPE);
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

const unsigned long PUBLISH_INTERVAL = 5000;
unsigned long lastPublish = 0;

void onCommand(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  if (msg.indexOf("\"on\"") >= 0) {
    digitalWrite(BUZZER_PIN, HIGH);
  } else if (msg.indexOf("\"off\"") >= 0) {
    digitalWrite(BUZZER_PIN, LOW);
  }
  Serial.println("Commande reçue : " + msg);
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(100);
  WiFi.config(local_IP, gateway, subnet, primaryDNS);
  WiFi.begin(ssid, password);
  Serial.print("Connexion au Wi-Fi ");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Adresse IP de l'ESP32 : ");
  Serial.println(WiFi.localIP());
}

void connectMqtt() {
  while (!mqtt.connected()) {
    Serial.print("Connexion MQTT... ");
    if (mqtt.connect("esp32-table1", MQTT_USER, MQTT_PASSWORD)) {
      Serial.println("OK");
      mqtt.subscribe(topicCmd.c_str());
    } else {
      Serial.print("échec, code ");
      Serial.println(mqtt.state());
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(100);

  pinMode(PIR_PIN, INPUT);
  pinMode(MQ2_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  dht.begin();

  topicSensors = String("sentinelx/") + TABLE_ID + "/sensors";
  topicCmd = String("sentinelx/") + TABLE_ID + "/cmd";

  connectWifi();

  ArduinoOTA.setHostname("Sentinel_G9");
  ArduinoOTA.setPassword("Sentinel_G9");
  ArduinoOTA.begin();

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onCommand);
}

void loop() {
  ArduinoOTA.handle();

  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
  }
  if (!mqtt.connected()) {
    connectMqtt();
  }
  mqtt.loop();

  if (millis() - lastPublish < PUBLISH_INTERVAL) {
    return;
  }
  lastPublish = millis();

  float temp = dht.readTemperature();
  float hum = dht.readHumidity();
  int gas = analogRead(MQ2_PIN);
  int pir = digitalRead(PIR_PIN);

  if (isnan(temp) || isnan(hum)) {
    Serial.println("Erreur de lecture DHT : vérifie le câblage");
    return;
  }

  char payload[128];
  snprintf(payload, sizeof(payload),
           "{\"temp\":%.1f,\"hum\":%.1f,\"gas\":%d,\"pir\":%d}",
           temp, hum, gas, pir);
  mqtt.publish(topicSensors.c_str(), payload);

  Serial.print("Publié : ");
  Serial.println(payload);
}
