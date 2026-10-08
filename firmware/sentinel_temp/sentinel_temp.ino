#include <WiFi.h>
#include <ArduinoOTA.h>
#include <DHT.h>
#include <PubSubClient.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "secrets.h"
#include "ca_cert.h"
#include "client_cert.h"  // certificat et clé de l'ESP32 (TLS mutuel), générés par lancer.ps1

// ================= Broches =================
#define DHTPIN     4
#define DHTTYPE    DHT22
#define PIR_PIN    27
#define MQ2_PIN    34
#define BUZZER_PIN 26
#define LED_PIN    25

// OLED principal SSD1306 en I2C
#define OLED_SDA      21
#define OLED_SCL      22
#define OLED_ADDRESS  0x3C
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 oled(
  SCREEN_WIDTH,
  SCREEN_HEIGHT,
  &Wire,
  -1
);

bool oledOk = false;

// ================= Deuxième OLED =================
// OLED réservé aux alertes
#define ALERT_OLED_SDA      19
#define ALERT_OLED_SCL      18
#define ALERT_OLED_ADDRESS  0x3C

// Deuxième contrôleur I2C matériel de l'ESP32
TwoWire AlertWire = TwoWire(1);

Adafruit_SSD1306 alertOled(
  SCREEN_WIDTH,
  SCREEN_HEIGHT,
  &AlertWire,
  -1
);

bool alertOledOk = false;

// ================= Réseau =================
// WIFI_SSID, WIFI_PASSWORD, MQTT_HOST, MQTT_USER, MQTT_PASSWORD : voir secrets.h
// IP en DHCP (Wi-Fi du labo, pas d'adresse fixe gérée par nous).
const char* TABLE_ID = "table1";

const char* ssid     = WIFI_SSID;
const char* password = WIFI_PASSWORD;

// MQTT_HOST défini dans secrets.h (IP du PC, change avec le DHCP du labo)
const int   MQTT_PORT = 8883;

String topicSensors;
String topicCmd;

DHT dht(DHTPIN, DHTTYPE);
WiFiClientSecure wifiClient;
PubSubClient mqtt(wifiClient);

// ================= Intervalles (ms) =================
const unsigned long SENSOR_INTERVAL  = 2000;
const unsigned long PUBLISH_INTERVAL = 5000;
const unsigned long REFRESH_INTERVAL = 500;
const unsigned long WIFI_RETRY       = 30000;
const unsigned long MQTT_RETRY       = 5000;

// Rafraîchissement du deuxième OLED
const unsigned long ALERT_REFRESH_INTERVAL = 100;

// ================= Alarme gaz =================
const int GAS_THRESHOLD  = 500;
const int GAS_HYSTERESIS = 200;

const unsigned long MQ2_WARMUP    = 60000;
const unsigned long BEEP_INTERVAL = 250;

bool gasAlarm = false;
bool buzzerManual = false;
bool ledManual = false;
bool beepState = false;

unsigned long lastBeep = 0;

unsigned long lastSensor = 0;
unsigned long lastPublish = 0;
unsigned long lastRefresh = 0;
unsigned long lastAlertRefresh = 0;

unsigned long lastWifiTry = 0;
unsigned long lastMqttTry = 0;

// ================= Dernières valeurs =================
float temp = NAN;
float hum = NAN;

int gas = 0;
int pir = 0;

bool dhtOk = false;

// Permet de ne pas signaler une erreur DHT avant la première lecture
bool sensorsReadOnce = false;

bool wifiWasConnected = false;
bool otaStarted = false;

// ================= Commandes MQTT =================
void onCommand(char* topic, byte* payload, unsigned int length) {
  String msg;

  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }

  // Le buzzer est géré par handleBuzzer().
  // L'alarme gaz reste prioritaire.
  if (msg.indexOf("\"buzzer\":\"on\"") >= 0) {
    buzzerManual = true;
  } else if (msg.indexOf("\"buzzer\":\"off\"") >= 0) {
    buzzerManual = false;
  }

  if (msg.indexOf("\"led\":\"on\"") >= 0) {
    ledManual = true;
  } else if (msg.indexOf("\"led\":\"off\"") >= 0) {
    ledManual = false;
  }

  Serial.println("Commande reçue : " + msg);
}

// ================= WiFi =================
void onWifiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    Serial.printf("Deconnexion WiFi, raison : %d\n", info.wifi_sta_disconnected.reason);
  }
}

bool wifiOk() {
  return WiFi.status() == WL_CONNECTED;
}

void startWifi() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);

  //WiFi.config(
  //  local_IP,
  //  gateway,
  //  subnet,
  //  primaryDNS
  //);

  WiFi.begin(ssid, password);

  lastWifiTry = millis();

  Serial.println("Connexion WiFi lancée...");
}

void handleWifi() {
  if (wifiOk()) {
    if (!wifiWasConnected) {
      wifiWasConnected = true;
      Serial.printf("WiFi OK sur '%s' (canal %d)\n", WiFi.SSID().c_str(), WiFi.channel());
      Serial.print("IP ESP : ");      Serial.println(WiFi.localIP());
      Serial.print("Passerelle : ");  Serial.println(WiFi.gatewayIP());
      Serial.print("MAC ESP : ");     Serial.println(WiFi.macAddress());
      Serial.printf("RSSI : %d dBm\n", WiFi.RSSI());
    }

    if (!otaStarted) {
      ArduinoOTA.setHostname("SentinelG999");
      ArduinoOTA.setPassword(OTA_PASSWORD);
      ArduinoOTA.begin();

      otaStarted = true;
    }

    return;
  }

  if (wifiWasConnected) {
    wifiWasConnected = false;

    Serial.println(
      "WiFi perdu, reconnexion automatique en cours..."
    );

    lastWifiTry = millis();
  }

  if (millis() - lastWifiTry >= WIFI_RETRY) {
    lastWifiTry = millis();

    Serial.println(
      "Toujours pas de WiFi, nouvelle tentative..."
    );

    WiFi.reconnect();
  }
}

// ================= MQTT =================
void handleMqtt() {
  if (!wifiOk()) {
    return;
  }

  if (mqtt.connected()) {
    mqtt.loop();
    return;
  }

  if (millis() - lastMqttTry < MQTT_RETRY) {
    return;
  }

  lastMqttTry = millis();

  Serial.print("Connexion MQTT... ");

  if (mqtt.connect("esp32-table1", MQTT_USER, MQTT_PASSWORD)) {
    Serial.println("OK");
    mqtt.subscribe(topicCmd.c_str());
  } else {
    Serial.print("échec, code ");
    Serial.println(mqtt.state());
  }
}

bool mqttOk() {
  return wifiOk() && mqtt.connected();
}

// ================= Capteurs =================
void readSensors() {
  sensorsReadOnce = true;

  float t = dht.readTemperature();
  float h = dht.readHumidity();

  dhtOk = !(isnan(t) || isnan(h));

  if (dhtOk) {
    temp = t;
    hum = h;
  } else {
    Serial.println(
      "Erreur de lecture DHT : vérifie le câblage"
    );
  }

  gas = analogRead(MQ2_PIN);
  pir = digitalRead(PIR_PIN);
}

void publishSensors() {
  if (!mqttOk()) {
    return;
  }

  char payload[160];

  if (dhtOk) {
    snprintf(
      payload,
      sizeof(payload),
      "{\"temp\":%.1f,\"hum\":%.1f,\"gas\":%d,\"pir\":%d,\"alarm\":%d}",
      temp,
      hum,
      gas,
      pir,
      gasAlarm ? 1 : 0
    );
  } else {
    // On publie quand même le gaz :
    // une alarme ne doit pas être bloquée par le DHT.
    snprintf(
      payload,
      sizeof(payload),
      "{\"gas\":%d,\"pir\":%d,\"alarm\":%d}",
      gas,
      pir,
      gasAlarm ? 1 : 0
    );
  }

  mqtt.publish(topicSensors.c_str(), payload);

  Serial.print("Publié : ");
  Serial.println(payload);
}

// ================= Alarme gaz / buzzer =================
bool mq2Ready() {
  return millis() >= MQ2_WARMUP;
}

void checkGasAlarm() {
  bool before = gasAlarm;

  if (!mq2Ready()) {
    gasAlarm = false;
  } else if (!gasAlarm && gas >= GAS_THRESHOLD) {
    gasAlarm = true;
  } else if (
    gasAlarm &&
    gas < GAS_THRESHOLD - GAS_HYSTERESIS
  ) {
    gasAlarm = false;
  }

  if (gasAlarm != before) {
    Serial.println(
      gasAlarm
        ? "!!! ALERTE GAZ !!!"
        : "Gaz revenu a la normale"
    );

    lastPublish = millis();

    // Envoi immédiat sans attendre les 5 secondes
    publishSensors();
  }
}

void handleBuzzer() {
  if (gasAlarm) {
    // Bip intermittent tant que l'alarme est active
    if (millis() - lastBeep >= BEEP_INTERVAL) {
      lastBeep = millis();
      beepState = !beepState;

      digitalWrite(
        BUZZER_PIN,
        beepState ? HIGH : LOW
      );
    }
  } else {
    beepState = false;

    digitalWrite(
      BUZZER_PIN,
      buzzerManual ? HIGH : LOW
    );
  }
}

void handleLed() {
  digitalWrite(LED_PIN, ledManual ? HIGH : LOW);
}

// ================= Écran OLED principal =================
void showScreen() {
  if (!oledOk) {
    return;
  }

  char line[22];

  oled.clearDisplay();
  oled.setTextSize(1);
  oled.setTextColor(SSD1306_WHITE);

  // En-tête
  if (gasAlarm) {
    if (beepState) {
      oled.fillRect(
        0,
        0,
        SCREEN_WIDTH,
        10,
        SSD1306_WHITE
      );

      oled.setTextColor(SSD1306_BLACK);
    }

    oled.setCursor(10, 1);
    oled.print("!! ALERTE GAZ !!");

    oled.setTextColor(SSD1306_WHITE);
  } else {
    oled.setCursor(0, 0);
    oled.print("SENTINEL-X  ");
    oled.print(TABLE_ID);
  }

  oled.drawFastHLine(
    0,
    10,
    SCREEN_WIDTH,
    SSD1306_WHITE
  );

  // Température / humidité
  oled.setCursor(0, 14);

  if (dhtOk) {
    snprintf(
      line,
      sizeof(line),
      "Temp: %.1f C",
      temp
    );

    oled.println(line);
    oled.setCursor(0, 24);

    snprintf(
      line,
      sizeof(line),
      "Hum : %.1f %%",
      hum
    );

    oled.println(line);
  } else {
    oled.println("DHT22: erreur");
    oled.setCursor(0, 24);
    oled.println("Verif cablage");
  }

  // Gaz
  oled.setCursor(0, 34);

  if (mq2Ready()) {
    snprintf(
      line,
      sizeof(line),
      "Gaz : %d",
      gas
    );
  } else {
    snprintf(
      line,
      sizeof(line),
      "Gaz : chauffe %lus",
      (MQ2_WARMUP - millis()) / 1000
    );
  }

  oled.println(line);

  // Mouvement
  oled.setCursor(0, 44);

  snprintf(
    line,
    sizeof(line),
    "Mouvement: %s",
    pir ? "OUI" : "non"
  );

  oled.println(line);

  // Connexions
  oled.drawFastHLine(
    0,
    53,
    SCREEN_WIDTH,
    SSD1306_WHITE
  );

  oled.setCursor(0, 56);

  const char* mqttTxt =
    !wifiOk()
      ? "--"
      : (mqtt.connected() ? "OK" : "NOK");

  snprintf(
    line,
    sizeof(line),
    "WiFi:%s  MQTT:%s",
    wifiOk() ? "OK" : "NOK",
    mqttTxt
  );

  oled.print(line);
  oled.display();
}

void handleDisplay() {
  unsigned long now = millis();

  if (now - lastRefresh >= REFRESH_INTERVAL) {
    lastRefresh = now;
    showScreen();
  }
}

// ================= Deuxième OLED : alertes =================
enum AlertScreenState {
  ALERT_NONE,
  ALERT_MQ2_WARMUP,
  ALERT_GAS,
  ALERT_MOVEMENT,
  ALERT_DHT,
  ALERT_WIFI,
  ALERT_MQTT
};

// Détermine l'alerte prioritaire à afficher
int getAlertScreenState() {
  // Priorité 1 : gaz
  if (gasAlarm) {
    return ALERT_GAS;
  }

  // Priorité 2 : détection de mouvement
  if (pir) {
    return ALERT_MOVEMENT;
  }

  // Priorité 3 : erreur DHT22
  if (sensorsReadOnce && !dhtOk) {
    return ALERT_DHT;
  }

  // Priorité 4 : perte du WiFi
  if (!wifiOk()) {
    return ALERT_WIFI;
  }

  // Priorité 5 : perte de MQTT
  if (!mqtt.connected()) {
    return ALERT_MQTT;
  }

  // Préchauffage du MQ-2
  if (!mq2Ready()) {
    return ALERT_MQ2_WARMUP;
  }

  return ALERT_NONE;
}

// Affiche un texte centré sur le deuxième OLED
void printAlertCentered(
  const char* text,
  int y,
  int textSize,
  uint16_t color
) {
  int16_t x1;
  int16_t y1;

  uint16_t width;
  uint16_t height;

  alertOled.setTextSize(textSize);
  alertOled.setTextColor(color);

  alertOled.getTextBounds(
    text,
    0,
    y,
    &x1,
    &y1,
    &width,
    &height
  );

  int x = (SCREEN_WIDTH - width) / 2;

  if (x < 0) {
    x = 0;
  }

  alertOled.setCursor(x, y);
  alertOled.print(text);
}

// Affiche une alerte qui clignote en noir et blanc
void drawFlashingAlert(
  const char* title,
  const char* message,
  unsigned long flashInterval = 300
) {
  bool inverted =
    ((millis() / flashInterval) % 2) == 0;

  uint16_t background =
    inverted ? SSD1306_WHITE : SSD1306_BLACK;

  uint16_t foreground =
    inverted ? SSD1306_BLACK : SSD1306_WHITE;

  alertOled.fillScreen(background);

  printAlertCentered(
    title,
    6,
    2,
    foreground
  );

  alertOled.drawFastHLine(
    5,
    28,
    SCREEN_WIDTH - 10,
    foreground
  );

  printAlertCentered(
    message,
    39,
    1,
    foreground
  );
}

// Animation affichée lorsqu'il n'y a aucune alerte
void drawNormalAnimation() {
  alertOled.clearDisplay();
  alertOled.setTextColor(SSD1306_WHITE);

  printAlertCentered(
    "SENTINEL-X",
    0,
    1,
    SSD1306_WHITE
  );

  printAlertCentered(
    "ZONE SECURISEE",
    53,
    1,
    SSD1306_WHITE
  );

  // Petit radar animé
  alertOled.drawCircle(
    64,
    31,
    18,
    SSD1306_WHITE
  );

  alertOled.drawCircle(
    64,
    31,
    10,
    SSD1306_WHITE
  );

  alertOled.drawPixel(
    64,
    31,
    SSD1306_WHITE
  );

  int scanY = 14 + ((millis() / 40) % 35);

  alertOled.drawFastHLine(
    46,
    scanY,
    37,
    SSD1306_WHITE
  );
}

// Affichage du préchauffage du MQ-2
void drawMq2Warmup() {
  alertOled.clearDisplay();
  alertOled.setTextColor(SSD1306_WHITE);

  printAlertCentered(
    "MQ-2",
    5,
    2,
    SSD1306_WHITE
  );

  printAlertCentered(
    "PRECHAUFFAGE",
    29,
    1,
    SSD1306_WHITE
  );

  unsigned long remaining = 0;

  if (millis() < MQ2_WARMUP) {
    remaining =
      (MQ2_WARMUP - millis() + 999) / 1000;
  }

  char remainingText[22];

  snprintf(
    remainingText,
    sizeof(remainingText),
    "Encore %lu secondes",
    remaining
  );

  printAlertCentered(
    remainingText,
    44,
    1,
    SSD1306_WHITE
  );
}

// Met à jour le deuxième écran
void showAlertScreen() {
  if (!alertOledOk) {
    return;
  }

  int state = getAlertScreenState();

  switch (state) {
    case ALERT_GAS:
      drawFlashingAlert(
        "GAZ!",
        "EVACUATION"
      );
      break;

    case ALERT_MOVEMENT:
      drawFlashingAlert(
        "INTRUS!",
        "MOUVEMENT DETECTE",
        500
      );
      break;

    case ALERT_DHT:
      drawFlashingAlert(
        "ERREUR",
        "CAPTEUR DHT22",
        700
      );
      break;

    case ALERT_WIFI:
      drawFlashingAlert(
        "RESEAU",
        "WIFI DECONNECTE",
        700
      );
      break;

    case ALERT_MQTT:
      drawFlashingAlert(
        "SERVEUR",
        "MQTT DECONNECTE",
        700
      );
      break;

    case ALERT_MQ2_WARMUP:
      drawMq2Warmup();
      break;

    case ALERT_NONE:
    default:
      drawNormalAnimation();
      break;
  }

  alertOled.display();
}

void handleAlertDisplay() {
  unsigned long now = millis();

  if (
    now - lastAlertRefresh >=
    ALERT_REFRESH_INTERVAL
  ) {
    lastAlertRefresh = now;
    showAlertScreen();
  }
}

// ================= setup / loop =================
void setup() {
  Serial.begin(115200);
  delay(100);

  pinMode(PIR_PIN, INPUT);
  pinMode(MQ2_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);

  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_PIN, LOW);

  dht.begin();

  // ================= Premier OLED =================
  Wire.begin(OLED_SDA, OLED_SCL);

  oledOk = oled.begin(
    SSD1306_SWITCHCAPVCC,
    OLED_ADDRESS
  );

  if (oledOk) {
    oled.clearDisplay();
    oled.setTextSize(1);
    oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(0, 0);

    oled.println("SENTINEL-X");
    oled.println("----------------");
    oled.println("Demarrage...");

    oled.display();
  } else {
    Serial.println(
      "OLED introuvable ! "
      "(le systeme continue sans ecran)"
    );
  }

  // ================= Deuxième OLED =================
  // Deuxième bus I2C :
  // SDA = GPIO 19
  // SCL = GPIO 18
  AlertWire.begin(
    ALERT_OLED_SDA,
    ALERT_OLED_SCL,
    400000
  );

  /*
    false à la fin évite que la bibliothèque
    réinitialise le deuxième bus I2C avec
    les broches par défaut.
  */
  alertOledOk = alertOled.begin(
    SSD1306_SWITCHCAPVCC,
    ALERT_OLED_ADDRESS,
    true,
    false
  );

  if (alertOledOk) {
    alertOled.clearDisplay();
    alertOled.setTextSize(1);
    alertOled.setTextColor(SSD1306_WHITE);
    alertOled.setCursor(0, 0);

    alertOled.println("SENTINEL-X");
    alertOled.println("----------------");
    alertOled.println("Ecran alertes");
    alertOled.println("Demarrage...");

    alertOled.display();

    Serial.println(
      "Deuxieme OLED initialise"
    );
  } else {
    Serial.println(
      "Deuxieme OLED introuvable "
      "sur GPIO 19/18"
    );
  }

  topicSensors =
    String("sentinelx/") +
    TABLE_ID +
    "/sensors";

  topicCmd =
    String("sentinelx/") +
    TABLE_ID +
    "/cmd";

  wifiClient.setCACert(CA_CERT);            // vérifie le broker
  wifiClient.setCertificate(CLIENT_CERT);    // TLS mutuel : l'ESP32 prouve son identité au broker
  wifiClient.setPrivateKey(CLIENT_KEY);

  mqtt.setServer(
    MQTT_HOST,
    MQTT_PORT
  );

  mqtt.setCallback(onCommand);
  mqtt.setSocketTimeout(2);

  WiFi.onEvent(onWifiEvent);

  startWifi();
}

void loop() {
  if (otaStarted) {
    ArduinoOTA.handle();
  }

  handleWifi();
  handleMqtt();

  unsigned long now = millis();

  if (now - lastSensor >= SENSOR_INTERVAL) {
    lastSensor = now;

    readSensors();
    checkGasAlarm();
  }

  if (
    now - lastPublish >=
    PUBLISH_INTERVAL
  ) {
    lastPublish = now;
    publishSensors();
  }

  handleBuzzer();
  handleLed();

  // Premier OLED
  handleDisplay();

  // Deuxième OLED réservé aux alertes
  handleAlertDisplay();
}