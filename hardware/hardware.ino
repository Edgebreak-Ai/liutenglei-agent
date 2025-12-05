#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <IRremoteESP8266.h>
#include <IRsend.h>

// --- WiFi Configuration ---
const char* ssid = "Xander";
const char* password = "e9c7uekd";

// --- IR Pin and Codes Configuration ---
constexpr uint16_t kIrLedPin = 5;
constexpr uint8_t IR_BITS = 24;

// This is the SINGLE IR code that toggles the fan's state (On->Off or Off->On)
constexpr uint32_t IR_CODE_TOGGLE_FAN = 0x80C0C0;

// Power adjustment codes remain the same
constexpr uint32_t IR_CODE_ADD_POWER = 0x80B0B0;
constexpr uint32_t IR_CODE_LOWER_POWER = 0x808888;


// --- Global Objects ---
IRsend irsend(kIrLedPin);
ESP8266WebServer server(80);

// --- State Management ---
// This variable holds the current known state of the fan.
// We assume it's OFF on startup. Use the web UI to sync if this is wrong.
bool isFanOn = false;


/**
 * @brief Reusable function to send an IR signal and log it to Serial.
 * @param code The IR code to transmit.
 * @param bits The number of bits in the IR code.
 */
void sendIRSignal(uint32_t code, uint8_t bits) {
  Serial.printf("Sending IR Signal -> Protocol: MIDEA, Code: 0x%06X, Bits: %d\n", code, bits);
  irsend.send(MIDEA24, code, bits);
  Serial.println("Signal sent successfully.");
}

/**
 * @brief Handles the root URL and dynamically generates the HTML page.
 */
void handleRoot() {
  String html = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width,initial-scale=1'>
  <title>ESP8266 State Remote</title>
  <style>
    body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; background-color: #f4f4f4; }
    h2, h3 { color: #333; }
    .container { border: 1px solid #ccc; background-color: #fff; padding: 20px; margin: 20px auto; max-width: 400px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    button { padding: 12px 24px; font-size: 18px; margin: 5px; cursor: pointer; border: none; border-radius: 5px; color: white; }
    .btn-main { background-color: #28a745; }
    .btn-main.off { background-color: #dc3545; }
    .btn-sync { background-color: #ffc107; color: #333; font-size: 14px; padding: 8px 16px;}
  </style>
</head>
<body>
  <h2>ESP8266 Midea IR Remote</h2>)rawliteral";

  // --- Main Fan Control (Dynamic Section) ---
  html += "<div class='container'>";
  html += "<h3>Main Control</h3>";
  html += "<p>Current State: <b>";
  html += (isFanOn ? "ON" : "OFF");
  html += "</b></p>";
  html += "<form action='/toggle' method='post'>";
  if (isFanOn) {
    html += "<button type='submit' class='btn-main off'>Turn OFF</button>";
  } else {
    html += "<button type='submit' class='btn-main'>Turn ON</button>";
  }
  html += "</form></div>";
  
  // --- Power Control (Static Section) ---
  html += R"rawliteral(
  <div class="container">
    <h3>Power Control</h3>
    <form action='/send_add_power' method='post' style='display:inline;'>
      <button type='submit'>Increase Power</button>
    </form>
    <form action='/send_lower_power' method='post' style='display:inline;'>
      <button type='submit'>Decrease Power</button>
    </form>
  </div>)rawliteral";

  // --- Manual Sync Control (Static Section) ---
  html += R"rawliteral(
  <div class="container">
    <h3>Manual Sync</h3>
    <p>If the state above is wrong, correct it here. This will NOT send an IR signal.</p>
    <form action='/set_state' method='post' style='display:inline;'>
      <button type='submit' name='state' value='on' class='btn-sync'>Set state to ON</button>
    </form>
    <form action='/set_state' method='post' style='display:inline;'>
      <button type='submit' name='state' value='off' class='btn-sync'>Set state to OFF</button>
    </form>
  </div>)rawliteral";

  html += "</body></html>";
  server.send(200, "text/html", html);
}

/**
 * @brief Handles the toggle request: sends IR and flips the state.
 */
void handleToggle() {
  sendIRSignal(IR_CODE_TOGGLE_FAN, IR_BITS);
  isFanOn = !isFanOn; // Flip the state
  Serial.printf("New fan state: %s\n", (isFanOn ? "ON" : "OFF"));
  server.sendHeader("Location", "/");
  server.send(303);
}

/**
 * @brief Handles manual state correction from the UI. Does not send IR.
 */
void handleSetState() {
  if (server.hasArg("state")) {
    String stateArg = server.arg("state");
    if (stateArg == "on") {
      isFanOn = true;
    } else if (stateArg == "off") {
      isFanOn = false;
    }
    Serial.printf("State manually synced to: %s\n", (isFanOn ? "ON" : "OFF"));
  }
  server.sendHeader("Location", "/");
  server.send(303);
}

/**
 * @brief Handles the '/send_add_power' POST request.
 */
void handleSendAddPower() {
  sendIRSignal(IR_CODE_ADD_POWER, IR_BITS);
  server.sendHeader("Location", "/");
  server.send(303);
}

/**
 * @brief Handles the '/send_lower_power' POST request.
 */
void handleSendLowerPower() {
  sendIRSignal(IR_CODE_LOWER_POWER, IR_BITS);
  server.sendHeader("Location", "/");
  server.send(303);
}

void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println("\nStarting ESP8266 State-aware IR Remote...");

  irsend.begin();

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected!");
  Serial.print("IP Address: http://");
  Serial.println(WiFi.localIP());

  // --- Web Server Routes ---
  server.on("/", HTTP_GET, handleRoot);
  server.on("/toggle", HTTP_POST, handleToggle);
  server.on("/set_state", HTTP_POST, handleSetState);
  server.on("/send_add_power", HTTP_POST, handleSendAddPower);
  server.on("/send_lower_power", HTTP_POST, handleSendLowerPower);
  
  server.begin();
  Serial.println("HTTP server started.");
}

void loop() {
  server.handleClient();
}