#include <Arduino.h>
#include <ArduinoJson.h>
#include <Helper.h>
#include <LittleFS.h>
#include <NimBLEDevice.h>
#include <PubSubClient.h>
#include <TelnetStream.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <WebServer.h>
#include <map>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Update.h>
#include <Preferences.h>

#define DEBUG 1 // 0 = Off, 1 = Local, 2 = Telnet
#if DEBUG == 1
#define debug(x) Serial.print(x)
#define debugln(x) Serial.println(x)
#elif DEBUG == 2
#define debug(x) TelnetStream.print(x)
#define debugln(x) TelnetStream.println(x)
#else
#define debug(x)
#define debugln(x)
#endif

const char *hostname PROGMEM = "edilkaminble";

char mqtt_server[40];
char mqtt_port[6] = "1883";
char mqtt_user[32];
char mqtt_pass[32];
char ntp_server[40] = "pool.ntp.org";
char ntp_offset[6] = "7200";
char web_pass[33] = ""; // 2026.11.2 : mot de passe de la page web (vide = page desactivee)

// Flag for saving data
bool shouldSaveConfig = false;

// Callback notifying us of the need to save config
void saveConfigCallback() {
  Serial.println("Should save config");
  shouldSaveConfig = true;
}

enum states {
  START,
  BT_CONNECT_CHECK,
  BT_CHECK_ON_OFF_TIMES,
  CHECK_BT_WRITE_QUEUE,
  DO_NEXT_QUERY,
  BT_WRITE_REQUEST,
  AWAIT_BT_RESPONSE,
  PROCESSING_BT_RESPONSE,
  DONE_PROCESSING_BT_RESPONSE,
};

Helper h;
uint8_t status = START;
bool doBtConnect = true;
bool btResponse = false;
byte *btData;
bool btWriteRequest = false;
uint8_t btRetryCount = 0;
const uint8_t btMaxRetries = 1;
static BLEUUID serviceUUID("abf0");
static BLEUUID charUUIDWrite("abf1");
static BLEUUID charUUIDRead("abf2");
static boolean bleDoConnect = false;
static boolean bleConnected = false;
static boolean bleEverConnected = false; // akoonet-6
static boolean bleDoScan = false;
static BLERemoteCharacteristic *pRemoteCharacteristicWrite;
static BLERemoteCharacteristic *pRemoteCharacteristicRead;
static BLEAdvertisedDevice *myDevice;
static BLEClient *pClient;
unsigned long currentMillis = 0;
unsigned long msLastQuery = 0;
unsigned long msLastMqttConnect = 0;
unsigned long msLastBleConnect = 0;
unsigned long writeTimestamp = 0;
unsigned long bleLastConnect = 0;
unsigned long bleLastSwitchOff = 0;
// 2026.11.3 : lectures rapprochees et deconnexion des la fin du cycle, pour
// laisser le Bluetooth du poele libre (une seule connexion a la fois : la
// telecommande et l'application Edilkamin en ont besoin aussi)
const long queryInterval = 500;
const long responseTimeout = 2000;
const long connectTimeout = 1000 * 30;     // 30 sec
const long bleConnectTimeout = 1000 * 300; // 5 min
const long bleOnTime = 1000 * 30;          // 30 sec (plafond : le cycle se termine normalement avant)
const long bleOffTime = 1000 * 120;        // 2 min

byte currentFan1Level = 0;
// akoonet: ventilateurs 2 et 3 (registre 1322 = 0x052A)
// akoonet-2 : valide sur Bild 9+ -> ventilateur 2 = octet BAS du registre 1322
// octet haut = inconnu (vaut 6 sur un poele a 2 ventilateurs), conserve tel que lu
byte currentFan2Level = 0;
byte currentFan23HiByte = 0;
bool fan23Known = false;      // au moins une lecture valide du registre 1322
byte currentPowerLevel = 0;
bool automatic = false;

struct btWriteMapping {
  Helper::btCmds name;
  byte cmd[6];
  uint8_t tries; // akoonet-11 : nombre de remises en file apres echec
};

// akoonet-11 : commande en cours (verification de la reponse, remise en file)
byte currentCmd[6] = {0, 0, 0, 0, 0, 0};
uint8_t currentTries = 0;

uint8_t btWriteQueueIndex = 0;
// akoonet-10 : file portee de 10 a 20 places (NO_CMD = 0, le reste est
// initialise a zero par le compilateur)
const uint8_t btWriteQueueLength = 20;
btWriteMapping btWriteQueue[btWriteQueueLength] = {};

// akoonet-12 : ecriture verifiee. Apres l'accuse de reception d'une ecriture,
// le registre est relu ; pendant 3 min, toute lecture de ce registre qui ne
// donne pas la valeur ecrite provoque une reecriture (2 au maximum).
struct writeVerify {
  bool active;
  bool confirmed;      // valeur deja relue identique au moins une fois
  uint16_t reg;
  Helper::btCmds op;
  byte cmd[6];
  uint8_t mask;        // 1 = octet haut, 2 = octet bas, 3 = les deux
  uint8_t rewrites;
  unsigned long since;
};
const uint8_t verifyLength = 8;
writeVerify verifies[verifyLength] = {};
const unsigned long verifyWindow = 1000UL * 180; // 3 min
const uint8_t verifyMaxRewrites = 2;

// akoonet-12 : compteurs (remis a zero au demarrage de l'ESP32)
uint32_t statVerified = 0;  // ecritures relues identiques
uint32_t statRewrites = 0;  // reecritures apres une relecture differente
uint32_t statFailed = 0;    // abandonnees (sans reponse ou valeur jamais relue)
unsigned long msLastDiag = 0;
const unsigned long diagInterval = 1000UL * 60;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

void otaState(const char *state, int pct, const char *msg);
// 2026.11.2 : derniere valeur de chaque etat publie, pour la page web
std::map<String, String> stateCache;
bool statePublish(const char *topic, const char *payload, bool retained = false) {
  static const char pre[] = "edilkamin/322707E4/";
  const size_t pl = sizeof(pre) - 1, tl = strlen(topic);
  if (tl > pl + 6 && strncmp(topic, pre, pl) == 0 &&
      strcmp(topic + tl - 6, "/state") == 0) {
    String k(topic + pl);
    k.remove(k.length() - 6);
    if (!k.startsWith("debug"))
      stateCache[k] = payload;
  }
  return mqttClient.publish(topic, payload, retained);
}
Helper::btCmds currentOp;

struct queryLookup {
  const Helper::btCmds name;
  const byte *cmd;
};
uint8_t queryIndex = 0;
const uint8_t queryQueueElements = 19; // akoonet-11 : READ_FAN retire (meme registre que READ_POWER)
const queryLookup queryQueue[] = {
    {Helper::READ_MAIN_ENV_TEMP, h.readMainEnvTemp}, // 2026.11.3 : lue en premier
    {Helper::READ_POWER, h.readPower},
    {Helper::READ_AUTOMATIC, h.readAutomatic},
    {Helper::READ_ON_OFF_CHRONO, h.readOnOffChrono},
    {Helper::READ_THERMOCOUPLE_TEMP, h.readThermocoupleTemperature},
    {Helper::READ_TEMPERATURE, h.readTemperature},
    {Helper::READ_RELAX, h.readRelax},
    {Helper::READ_FIREPLACE_MAIN_STATUS, h.readFireplaceMainStatus},
    {Helper::READ_STANDBY_STATUS, h.readStandbyStatus},
    {Helper::READ_WARNING_FLAGS, h.readWarningFlags},
    // akoonet
    {Helper::READ_FAN_23, h.readFan23},
    // akoonet-4 : alarmes et compteurs
    {Helper::READ_ALARM, h.readAlarm},
    {Helper::READ_TOTAL_ALARMS, h.readTotalAlarms},
    {Helper::READ_PELLET_REMAINING, h.readPelletRemaining},
    // akoonet-5 : valeurs reelles (machine)
    {Helper::READ_FIREPLACE_CURRENT_POWER, h.readFireplaceCurrentPower},
    {Helper::READ_FAN_23_MACHINE, h.readFan23Machine},
    // candidats compteurs (lecture d'un mot a la fois)
    {Helper::READ_COUNTER_CANDIDATE, h.readCand02C2},
    {Helper::READ_COUNTER_CANDIDATE, h.readCand0334},
    {Helper::READ_COUNTER_CANDIDATE, h.readCand0335}};

// akoonet-4 : registre de la derniere commande envoyee (pour les candidats)
uint16_t currentReg = 0;
const uint8_t candCount = 3; // akoonet-8
const uint16_t candRegs[candCount] = {0x02C2, 0x0334, 0x0335};
int32_t candValues[candCount] = {-1, -1, -1};
int32_t lastAlarmCode = -1;
// 2026.11.2 : horloge du poele (registres 0x0316 a 0x0319, lus un par un, format a confirmer)
int32_t clockWords[4] = {-1, -1, -1, -1};
uint32_t clockFrameTs = 0; // horodatage de la trame de reponse du poele
unsigned long msLastClockRead = 0;
// 2026.11.3 : occupation du Bluetooth du poele
uint8_t cycleQueries = 0;          // lectures lancees depuis le reveil
bool blePrev = false;              // etat de connexion au tour precedent
unsigned long bleSessionStart = 0; // debut de la connexion en cours
unsigned long bleLastSessionMs = 0;
unsigned long bleOnMsWindow = 0;   // temps connecte dans la fenetre en cours
unsigned long bleWindowStart = 0;
const unsigned long bleWindowMs = 1000UL * 60 * 15;
int bleOccupancyPct = -1;          // derniere fenetre de 15 min complete
uint32_t bleTimeouts = 0;
const unsigned long clockReadInterval = 1000UL * 60 * 10;

// akoonet-8 : libelles des alarmes (notice Bild Up 2022, p. 62-63)
const char *alarmLabel(byte n) {
  switch (n) {
  case 1: return "Débit d'air de combustion insuffisant";
  case 2: return "Vitesse du ventilateur de fumées incorrecte";
  case 3: return "Absence de flamme, fumées trop froides";
  case 4: return "Échec de l'allumage";
  case 5: return "Rupture du capteur de débit d'air";
  case 6: return "Rupture du thermocouple de fumées";
  case 7: return "Température maximale des fumées dépassée";
  case 8: return "Température excessive dans le poêle";
  case 9: return "Rupture du motoréducteur";
  case 10: return "Surchauffe de la carte électronique";
  case 11: return "Déclenchement du pressostat de sécurité";
  case 12: return "Panne de la sonde de température ambiante";
  case 14: return "Panne de la sonde ambiante de canalisation";
  case 20: return "Panne du motoréducteur";
  default: return "Alarme inconnue";
  }
}

// akoonet: libelle d'un niveau de ventilation (1-5 = 20-100 %, 6 = Auto)
const char *fanLevelLabel(byte level) {
  switch (level) {
  case 0: return "Arrêt"; // akoonet-7 : ventilateur 2 arrete (vu sur le poele)
  case 1: return "20%";
  case 2: return "40%";
  case 3: return "60%";
  case 4: return "80%";
  case 5: return "100%";
  case 6: return "Auto";
  default: return nullptr;
  }
}

void publishFan2(byte fan2) {
  const char *label = fanLevelLabel(fan2);
  if (label)
    statePublish("edilkamin/322707E4/fan2_mode/state", label, true);
}

void hexDebug(byte *data, size_t length) {
  char output[(length * 2) + 1];
  char *ptr = &output[0];
  int i;
  for (i = 0; i < length; i++) {
    ptr += sprintf(ptr, "%02X", (int)data[i]);
  }
  debug(output);
}

void queueBtCommand(Helper::btCmds name, byte *cmd) {
  // akoonet-10 : une commande qui vise le meme registre avec la meme fonction
  // (lecture 0x03 ou ecriture 0x06) remplace celle deja en attente au lieu
  // d'occuper une place de plus : la derniere valeur demandee l'emporte.
  for (uint8_t i = 0; i < btWriteQueueLength; i++) {
    if (btWriteQueue[i].name != Helper::NO_CMD &&
        btWriteQueue[i].cmd[1] == cmd[1] && btWriteQueue[i].cmd[2] == cmd[2] &&
        btWriteQueue[i].cmd[3] == cmd[3]) {
      // Registre 1321 (0x0529) = [ventilateur 1][puissance] : une ecriture
      // ventilateur 1 en attente et une ecriture puissance se fusionnent,
      // chacune garde l'octet de l'autre.
      byte merged[6];
      memcpy(merged, cmd, 6);
      if (cmd[1] == 6 && cmd[2] == 5 && cmd[3] == 41) {
        if (name == Helper::SET_FAN_1 &&
            btWriteQueue[i].name == Helper::SET_WRITE_NEW_POWER)
          merged[5] = btWriteQueue[i].cmd[5];
        else if (name == Helper::SET_WRITE_NEW_POWER &&
                 btWriteQueue[i].name == Helper::SET_FAN_1)
          merged[4] = btWriteQueue[i].cmd[4];
      }
      btWriteQueue[i].name = name;
      memcpy(btWriteQueue[i].cmd, merged, 6);
      btWriteQueue[i].tries = 0;
      debug(F(", replaced at index:"));
      debugln(i);
      return;
    }
  }
  for (uint8_t i = 0; i < btWriteQueueLength; i++) {
    if (btWriteQueue[i].name == Helper::NO_CMD) {
      btWriteQueue[i].name = name;
      memcpy(btWriteQueue[i].cmd, cmd, 6);
      btWriteQueue[i].tries = 0;
      debug(F(", queued at index:"));
      debug(i);
      debugln();
      return;
    }
  }
  // akoonet-10 : file pleine. Une ecriture prend la place d'une lecture
  // (les lectures reviennent a chaque tour) ; sinon la commande est perdue
  // et on le signale au lieu de l'ignorer en silence.
  if (cmd[1] != 3) {
    for (uint8_t i = 0; i < btWriteQueueLength; i++) {
      if (btWriteQueue[i].cmd[1] == 3) {
        btWriteQueue[i].name = name;
        memcpy(btWriteQueue[i].cmd, cmd, 6);
        btWriteQueue[i].tries = 0;
        debug(F(", queue full, read replaced at index:"));
        debugln(i);
        return;
      }
    }
  }
  debugln(F(", queue full, command DROPPED"));
  statePublish("edilkamin/322707E4/debug/state", "write queue full: command dropped");
}

// akoonet-12 : octets a comparer pour verifier une ecriture (0 = pas de
// verification : marche/arret, registre 0x031C, est une commande et non un etat)
uint8_t verifyMaskFor(Helper::btCmds op) {
  switch (op) {
  case Helper::SET_WRITE_NEW_TEMP: return 3;     // 0x0525 : consigne x10
  case Helper::SET_FAN_1: return 1;              // 0x0529 : octet haut = V1
  case Helper::SET_WRITE_NEW_POWER: return 2;    // 0x0529 : octet bas = puissance
  case Helper::SET_FAN_2: return 2;              // 0x052A : octet bas = V2
  case Helper::SET_RELAX_STATUS: return 2;       // 0x052B
  case Helper::SET_STANDBY_STATUS: return 1;     // 0x052C
  case Helper::SET_ON_OFF_CHRONO: return 2;      // 0x0522
  case Helper::SET_CHANGE_AUTO_SWITCH: return 1; // 0x0523
  default: return 0;
  }
}

bool writePendingFor(byte hi, byte lo) {
  for (uint8_t i = 0; i < btWriteQueueLength; i++)
    if (btWriteQueue[i].name != Helper::NO_CMD && btWriteQueue[i].cmd[1] == 6 &&
        btWriteQueue[i].cmd[2] == hi && btWriteQueue[i].cmd[3] == lo)
      return true;
  return false;
}

// Met en file la lecture periodique qui correspond a ce registre
void queueReadOf(uint16_t reg) {
  for (uint8_t q = 0; q < queryQueueElements; q++) {
    const byte *c = queryQueue[q].cmd;
    if (c[1] == 3 && ((c[2] << 8) | c[3]) == reg && c[5] == 1) {
      byte btCmd[6];
      memcpy(btCmd, c, 6);
      queueBtCommand(queryQueue[q].name, btCmd);
      return;
    }
  }
}

void registerVerify(Helper::btCmds op, const byte *cmd, uint8_t rewrites) {
  uint8_t mask = verifyMaskFor(op);
  if (!mask)
    return;
  uint16_t reg = (cmd[2] << 8) | cmd[3];
  int8_t slot = -1;
  for (uint8_t i = 0; i < verifyLength; i++)
    if (verifies[i].active && verifies[i].reg == reg) {
      // ventilation 1 et puissance partagent 0x0529 : on cumule les octets
      if (verifies[i].op != op && reg == 0x0529) {
        mask |= verifies[i].mask;
      }
      slot = i;
      break;
    }
  if (slot < 0)
    for (uint8_t i = 0; i < verifyLength; i++)
      if (!verifies[i].active || currentMillis - verifies[i].since > verifyWindow) {
        slot = i;
        break;
      }
  if (slot < 0)
    slot = 0;
  verifies[slot].active = true;
  verifies[slot].confirmed = false;
  verifies[slot].reg = reg;
  verifies[slot].op = op;
  memcpy(verifies[slot].cmd, cmd, 6);
  verifies[slot].mask = mask;
  verifies[slot].rewrites = rewrites;
  verifies[slot].since = currentMillis;
  queueReadOf(reg);
}

// Appelee pour chaque reponse de lecture d'un seul registre
bool checkVerify(uint16_t reg, byte hi, byte lo) {
  bool rewriting = false;
  for (uint8_t i = 0; i < verifyLength; i++) {
    writeVerify &v = verifies[i];
    if (!v.active || v.reg != reg)
      continue;
    if (currentMillis - v.since > verifyWindow) {
      v.active = false;
      continue;
    }
    bool ok = (!(v.mask & 1) || hi == v.cmd[4]) && (!(v.mask & 2) || lo == v.cmd[5]);
    if (ok) {
      if (!v.confirmed) {
        v.confirmed = true;
        statVerified++;
      }
      continue;
    }
    char dbg[96];
    if (v.confirmed) {
      // La valeur a bien ete appliquee puis a change : reglage fait sur le
      // poele ou la telecommande. On le respecte (pas de reecriture).
      snprintf(dbg, sizeof(dbg), "verification %04X: modifie sur le poele (%02X%02X)",
               reg, hi, lo);
      statePublish("edilkamin/322707E4/debug/state", dbg);
      v.active = false;
      continue;
    }
    if (writePendingFor(v.cmd[2], v.cmd[3])) {
      // une commande plus recente vise deja ce registre : elle l'emporte
      v.active = false;
      continue;
    }
    if (v.rewrites < verifyMaxRewrites) {
      statRewrites++;
      snprintf(dbg, sizeof(dbg),
               "verification %04X: relu %02X%02X au lieu de %02X%02X, reecriture %u",
               reg, hi, lo, v.cmd[4], v.cmd[5], v.rewrites + 1);
      statePublish("edilkamin/322707E4/debug/state", dbg);
      byte cmd[6];
      memcpy(cmd, v.cmd, 6);
      Helper::btCmds op = v.op;
      uint8_t n = v.rewrites + 1;
      v.active = false;
      queueBtCommand(op, cmd);
      // le nombre de reecritures suit la commande (repris a l'accuse)
      for (uint8_t k = 0; k < btWriteQueueLength; k++)
        if (btWriteQueue[k].name == op && memcmp(btWriteQueue[k].cmd, cmd, 6) == 0)
          btWriteQueue[k].tries = 0x80 | n;
      rewriting = true;
    } else {
      statFailed++;
      snprintf(dbg, sizeof(dbg),
               "verification %04X: valeur %02X%02X non appliquee apres %u reecritures",
               reg, v.cmd[4], v.cmd[5], v.rewrites);
      statePublish("edilkamin/322707E4/debug/state", dbg);
      v.active = false;
    }
  }
  return rewriting;
}

const char *resetReasonLabel() {
  switch (esp_reset_reason()) {
  case ESP_RST_POWERON: return "Mise sous tension";
  case ESP_RST_EXT: return "Broche de reset";
  case ESP_RST_SW: return "Redémarrage logiciel (chien de garde du firmware)";
  case ESP_RST_PANIC: return "Plantage (panic)";
  case ESP_RST_INT_WDT: return "Chien de garde (interruptions)";
  case ESP_RST_TASK_WDT: return "Chien de garde (tâche bloquée)";
  case ESP_RST_WDT: return "Chien de garde";
  case ESP_RST_DEEPSLEEP: return "Sortie de veille profonde";
  case ESP_RST_BROWNOUT: return "Chute de tension (brownout)";
  case ESP_RST_SDIO: return "SDIO";
  default: return "Inconnue";
  }
}

// ---------------------------------------------------------------------------
// Edilkamin Control : planning de secours
// L'integration Edilkamin Control publie ses programmations (message retenu) sur
// edilkamin/322707E4/schedule. Format v2 : jusqu'a 10 plages avec jours (j, bit 0
// = lundi) et silence (r) ; format v1 (akoonet-13) : 5 plages, tous les jours.
// L'ESP32 les garde en flash (/schedule.json). Si Home Assistant est absent
// depuis 5 min (serveur MQTT injoignable, ou "offline" sur homeassistant/status),
// l'ESP32 applique lui-meme les debuts et fins de plage.
// ---------------------------------------------------------------------------
#define MAX_SLOTS 10
struct schedSlot {
  bool active;
  uint16_t start, end; // minutes depuis minuit
  uint16_t consX10;    // consigne x 10
  uint8_t standby;     // 1 = Stand-by, 0 = Marche
  uint8_t power;       // 0 = Auto, 1-5
  uint8_t fan1;        // 1-5, 6 = Auto
  uint8_t fan2;        // 0 = Arret, 1-5, 6 = Auto
  uint8_t relax;       // 1 = silence (Relax)
  uint8_t days;        // jours, bit 0 = lundi ... bit 6 = dimanche
};
schedSlot sched[MAX_SLOTS] = {};
uint8_t schedCount = 0;
bool schedLoaded = false;
bool haOnline = true;
unsigned long msHaOffline = 0;     // instant du "offline" de HA (0 = en ligne)
unsigned long msMqttLost = 0;      // debut de la coupure MQTT (0 = connecte)
unsigned long msLastMqttAttempt = 0;
unsigned long msLastSchedCheck = 0;
bool fallbackActive = false;
int8_t fbLastProfile = -2;         // -1 = hors profil, 0-9 = plage 1-10
bool stoveStatusKnown = false;
bool stoveIsOff = false;
int16_t envTempX10 = -1;
const unsigned long fallbackDelay = 1000UL * 300; // 5 min sans HA
const char *TZ_PARIS = "CET-1CEST,M3.5.0,M10.5.0/3";

bool parseSchedule(const char *json, size_t len) {
  JsonDocument doc;
  if (deserializeJson(doc, json, len))
    return false;
  JsonArray p = doc["p"].as<JsonArray>();
  uint8_t version = doc["v"] | 1;
  if (p.isNull() || p.size() > MAX_SLOTS || (version == 1 && p.size() != 5))
    return false;
  schedSlot tmp[MAX_SLOTS] = {};
  uint8_t n = 0;
  for (JsonObject o : p) {
    schedSlot &t = tmp[n];
    t.active = (o["a"] | 0) == 1;
    t.start = o["d"] | 0;
    t.end = o["f"] | 0;
    t.consX10 = o["c"] | 190;
    t.standby = o["m"] | 1;
    t.power = o["pu"] | 0;
    t.fan1 = o["v1"] | 6;
    t.fan2 = o["v2"] | 6;
    t.relax = o["r"] | 0;
    t.days = o["j"] | 127;
    if (t.start >= 1440 || t.end >= 1440 || t.consX10 < 50 || t.consX10 > 400 ||
        t.power > 5 || t.fan1 < 1 || t.fan1 > 6 || t.fan2 > 6 || t.relax > 1 ||
        t.days == 0 || t.days > 127)
      return false;
    n++;
  }
  memcpy(sched, tmp, sizeof(sched));
  schedCount = n;
  schedLoaded = true;
  return true;
}

void loadScheduleFile() {
  if (!LittleFS.exists("/schedule.json"))
    return;
  File f = LittleFS.open("/schedule.json", "r");
  if (!f)
    return;
  String s = f.readString();
  f.close();
  if (parseSchedule(s.c_str(), s.length()))
    debugln(F("Planning de secours charge depuis la flash"));
}

void storeSchedule(const char *json, size_t len) {
  if (!parseSchedule(json, len)) {
    statePublish("edilkamin/322707E4/debug/state", "planning recu invalide");
    return;
  }
  String old;
  File r = LittleFS.open("/schedule.json", "r");
  if (r) {
    old = r.readString();
    r.close();
  }
  if (old.length() == len && memcmp(old.c_str(), json, len) == 0)
    return; // inchange : pas d'ecriture en flash
  File w = LittleFS.open("/schedule.json", "w");
  if (w) {
    w.write((const uint8_t *)json, len);
    w.close();
  }
  statePublish("edilkamin/322707E4/debug/state", "planning de secours enregistre");
}

// La plage contient-elle l'instant (m minutes, jour wd 0 = lundi) ?
// Debut = fin : toute la journee. La partie apres minuit d'une plage qui passe
// minuit appartient au jour du debut.
bool slotMatches(const schedSlot &s, uint16_t m, uint8_t wd) {
  bool today = s.days & (1 << wd);
  bool yesterday = s.days & (1 << ((wd + 6) % 7));
  if (s.start == s.end)
    return today;
  if (s.start < s.end)
    return today && s.start <= m && m < s.end;
  return (m >= s.start && today) || (m < s.end && yesterday);
}

// -2 = heure inconnue ou pas de planning, -1 = hors profil, 0-9 = plage
int8_t currentProfile() {
  if (!schedLoaded)
    return -2;
  struct tm t;
  if (!getLocalTime(&t, 0) || t.tm_year < 124)
    return -2;
  uint16_t m = t.tm_hour * 60 + t.tm_min;
  uint8_t wd = (t.tm_wday + 6) % 7; // 0 = lundi
  for (uint8_t n = 0; n < schedCount; n++) // la premiere de la liste l'emporte
    if (sched[n].active && slotMatches(sched[n], m, wd))
      return n;
  return -1;
}

void applyProfile(int8_t p) {
  byte c[6];
  char dbg[64];
  if (p < 0) {
    memcpy(c, h.setOnOff, 6);
    c[5] = 0;
    queueBtCommand(Helper::SET_ON_OFF, c);
    statePublish("edilkamin/322707E4/debug/state", "secours: hors profil, extinction");
    return;
  }
  const schedSlot &s = sched[p];
  memcpy(c, h.setRelaxStatus, 6);
  c[4] = c[5] = s.relax ? 1 : 0;
  queueBtCommand(Helper::SET_RELAX_STATUS, c);
  memcpy(c, h.setWriteNewTemperature, 6);
  c[4] = s.consX10 >> 8;
  c[5] = s.consX10 & 0xFF;
  queueBtCommand(Helper::SET_WRITE_NEW_TEMP, c);
  memcpy(c, h.setStandbyStatus, 6);
  c[4] = c[5] = s.standby ? 1 : 0;
  queueBtCommand(Helper::SET_STANDBY_STATUS, c);
  if (s.power == 0) {
    memcpy(c, h.setChangeAutoSwitch, 6);
    c[4] = 1;
    queueBtCommand(Helper::SET_CHANGE_AUTO_SWITCH, c);
    if (currentPowerLevel != 0) {
      memcpy(c, h.setFan1, 6);
      c[4] = s.fan1;
      c[5] = currentPowerLevel;
      queueBtCommand(Helper::SET_FAN_1, c);
    }
  } else {
    // 2026.11.2 : une puissance manuelle demande de couper le mode automatique
    // du poele, sinon il reste en Auto (defaut du firmware d'origine)
    memcpy(c, h.setChangeAutoSwitch, 6);
    c[4] = 0;
    queueBtCommand(Helper::SET_CHANGE_AUTO_SWITCH, c);
    memcpy(c, h.setWriteNewPower, 6);
    c[4] = s.fan1;
    c[5] = s.power;
    queueBtCommand(Helper::SET_WRITE_NEW_POWER, c);
  }
  if (fan23Known) {
    memcpy(c, h.setFan2, 6);
    c[4] = currentFan23HiByte;
    c[5] = s.fan2;
    queueBtCommand(Helper::SET_FAN_2, c);
  }
  bool ignite = stoveStatusKnown && stoveIsOff &&
                (!s.standby || (envTempX10 > 0 && envTempX10 < (int16_t)s.consX10));
  if (ignite) {
    memcpy(c, h.setOnOff, 6);
    c[5] = 1;
    queueBtCommand(Helper::SET_ON_OFF, c);
  }
  snprintf(dbg, sizeof(dbg), "secours: profil %d applique%s", p + 1,
           ignite ? " + allumage" : "");
  statePublish("edilkamin/322707E4/debug/state", dbg);
}

void checkFallback() {
  bool mqttOk = mqttClient.connected();
  if (mqttOk)
    msMqttLost = 0;
  else if (!msMqttLost)
    msMqttLost = currentMillis | 1;
  bool haGone = (!mqttOk && msMqttLost && currentMillis - msMqttLost >= fallbackDelay) ||
                (mqttOk && !haOnline && msHaOffline &&
                 currentMillis - msHaOffline >= fallbackDelay);
  int8_t p = currentProfile();
  if (haGone && p != -2) {
    if (!fallbackActive) {
      // HA vient de disparaitre : le poele est deja regle pour la plage en
      // cours, on n'agit qu'au prochain changement de plage
      fallbackActive = true;
      fbLastProfile = p;
      statePublish("edilkamin/322707E4/debug/state", "secours: active");
    } else if (p != fbLastProfile) {
      applyProfile(p);
      fbLastProfile = p;
    }
  } else if (fallbackActive && !haGone) {
    fallbackActive = false;
    statePublish("edilkamin/322707E4/debug/state", "secours: HA de retour");
  }
}

const char *fallbackLabel() {
  if (!schedLoaded)
    return "Pas de planning";
  if (currentProfile() == -2)
    return "Heure inconnue";
  return fallbackActive ? "Actif" : "En veille";
}

void publishDiag() {
  char heure[8] = "?";
  struct tm t;
  if (getLocalTime(&t, 0) && t.tm_year >= 124)
    snprintf(heure, sizeof(heure), "%02d:%02d", t.tm_hour, t.tm_min);
  uint8_t nActifs = 0;
  for (uint8_t i = 0; i < schedCount; i++)
    if (schedLoaded && sched[i].active)
      nActifs++;
  char out[512];
  snprintf(out, sizeof(out),
           "{\"uptime\":%lu,\"reset\":\"%s\",\"heap\":%u,\"heap_min\":%u,"
           "\"rssi\":%d,\"verifiees\":%lu,\"reecritures\":%lu,\"echecs\":%lu,"
           "\"secours\":\"%s\",\"heure_esp\":\"%s\",\"profils_actifs\":%u,"
           "\"profil_secours\":%d,\"ip\":\"%s\",\"ble_occupation\":%d,"
           "\"ble_derniere_s\":%.1f,\"ble_sans_reponse\":%lu,\"version\":\"" FW_VERSION "\"}",
           (unsigned long)(millis() / 1000), resetReasonLabel(),
           (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap(),
           (int)WiFi.RSSI(), (unsigned long)statVerified,
           (unsigned long)statRewrites, (unsigned long)statFailed,
           fallbackLabel(), heure, nActifs,
           fbLastProfile >= 0 ? fbLastProfile + 1 : 0, WiFi.localIP().toString().c_str(),
           bleOccupancyPct, bleLastSessionMs / 1000.0, (unsigned long)bleTimeouts);
  statePublish("edilkamin/322707E4/diag/state", out, true);
  statePublish("edilkamin/322707E4/ip/state", WiFi.localIP().toString().c_str(), true);
}

void nextQuery() {
  byte btCmd[6];
  debugln();
  debug(F("Next Query Command:"));
  debug(queryQueue[queryIndex].name);
  debug(F(",command:"));
  hexDebug((unsigned char *)queryQueue[queryIndex].cmd, 6);
  memcpy(btCmd, queryQueue[queryIndex].cmd, 6);
  queueBtCommand(queryQueue[queryIndex].name, btCmd);
  if (cycleQueries < 255)
    cycleQueries++;

  if (queryIndex < queryQueueElements - 1)
    queryIndex++;
  else
    queryIndex = 0;
}

bool writeQueueHasElements() {
  for (uint8_t i = 0; i < btWriteQueueLength; i++) {
    if (btWriteQueue[i].name != Helper::NO_CMD)
      return true;
  }
  return false;
}

static byte lastBtPacket[32];

void writeBtData() {
  for (uint8_t i = 0; i < btWriteQueueLength; i++) {
    if (btWriteQueue[i].name != Helper::NO_CMD) {
      currentOp = btWriteQueue[i].name;
      currentReg = (btWriteQueue[i].cmd[2] << 8) | btWriteQueue[i].cmd[3];
      memcpy(currentCmd, btWriteQueue[i].cmd, 6);
      currentTries = btWriteQueue[i].tries;
      debug(F("-> Write, queue-index:"));
      debug(i);
      debug(F(", "));
      debug(F("cmd:"));
      debug(currentOp);
      debug(", data:");
      h.createBtPacket(btWriteQueue[i].cmd, 6, lastBtPacket);
      hexDebug(btWriteQueue[i].cmd, 6);
      debugln();
      btWriteQueue[i].name = Helper::NO_CMD;
      pRemoteCharacteristicWrite->writeValue(lastBtPacket, 32);
      break;
    }
  }
}
void processBtResponseData(byte *btData) {
  debug(F("<- Read, data:"));
  Helper::structDatagram d;
  h.getBtContent(btData, 32, &d);
  hexDebug(d.payload, 6);
  debugln();
  // akoonet-11 : rejeter une reponse qui ne correspond pas a la commande en
  // cours (reponse tardive a la commande precedente, trame inattendue).
  // Ecriture : la reponse renvoie le registre ecrit. Lecture : le nombre
  // d'octets doit valoir 2 x le nombre de registres demandes.
  {
    bool ok = d.payload[0] == 1 && d.payload[1] == currentCmd[1];
    if (ok && d.payload[1] == 6)
      ok = d.payload[2] == currentCmd[2] && d.payload[3] == currentCmd[3];
    else if (ok && d.payload[1] == 3)
      ok = d.payload[2] == 2 * currentCmd[5];
    if (!ok) {
      char dbg[64];
      snprintf(dbg, sizeof(dbg), "reponse ignoree: %02X %02X %02X %02X (cmd %02X %02X%02X)",
               d.payload[0], d.payload[1], d.payload[2], d.payload[3],
               currentCmd[1], currentCmd[2], currentCmd[3]);
      debugln(dbg);
      statePublish("edilkamin/322707E4/debug/state", dbg);
      return;
    }
  }
  if (d.payload[1] == 6) { // Set Response
    // akoonet-12 : relecture du registre ecrit pour verifier la valeur
    registerVerify(currentOp, currentCmd,
                   (currentTries & 0x80) ? (currentTries & 0x7F) : 0);
    debug(F("Set-Response for cmd:"));
    debug(currentOp);
    debug("; data:");
    hexDebug(d.payload, 6);
    debugln("");
    if (currentOp == Helper::SET_ON_OFF) {
      if (d.payload[5] == 1)
        statePublish("edilkamin/322707E4/hvac_mode/state", "heat", true);
      else if (d.payload[5] == 0)
        statePublish("edilkamin/322707E4/hvac_mode/state", "off", true);
    } else if (currentOp == Helper::SET_RELAX_STATUS) {
      if (d.payload[4] == 0 && d.payload[5] == 0)
        statePublish("edilkamin/322707E4/relax/state", "OFF", true);
      else if (d.payload[4] == 1 && d.payload[5] == 1)
        statePublish("edilkamin/322707E4/relax/state", "ON", true);
    } else if (currentOp == Helper::SET_WRITE_NEW_POWER && !automatic) {
      currentFan1Level = d.payload[4];
      currentPowerLevel = d.payload[5];
      switch (d.payload[5]) {
      case 1:
        statePublish("edilkamin/322707E4/preset_mode/state", "Man. P1", true);
        break;
      case 2:
        statePublish("edilkamin/322707E4/preset_mode/state", "Man. P2", true);
        break;
      case 3:
        statePublish("edilkamin/322707E4/preset_mode/state", "Man. P3", true);
        break;
      case 4:
        statePublish("edilkamin/322707E4/preset_mode/state", "Man. P4", true);
        break;
      case 5:
        statePublish("edilkamin/322707E4/preset_mode/state", "Man. P5", true);
        break;
      }
    } else if (currentOp == Helper::SET_FAN_1) {
      currentFan1Level = d.payload[4];
      currentPowerLevel = d.payload[5];
      switch (d.payload[4]) {
      case 1:
        statePublish("edilkamin/322707E4/fan_mode/state", "20%", true);
        break;
      case 2:
        statePublish("edilkamin/322707E4/fan_mode/state", "40%", true);
        break;
      case 3:
        statePublish("edilkamin/322707E4/fan_mode/state", "60%", true);
        break;
      case 4:
        statePublish("edilkamin/322707E4/fan_mode/state", "80%", true);
        break;
      case 5:
        statePublish("edilkamin/322707E4/fan_mode/state", "100%", true);
        break;
      case 6:
        statePublish("edilkamin/322707E4/fan_mode/state", "Auto", true);
        break;
      }
    } else if (currentOp == Helper::SET_ON_OFF_CHRONO) {
      if (d.payload[5] == 0)
        statePublish("edilkamin/322707E4/chrono_mode/state", "OFF", true);
      else if (d.payload[5] == 1)
        statePublish("edilkamin/322707E4/chrono_mode/state", "ON", true);
    } else if (currentOp == Helper::SET_STANDBY_STATUS) {
      if (d.payload[4] == 0 && d.payload[5] == 0)
        statePublish("edilkamin/322707E4/standby/state", "OFF", true);
      else if (d.payload[4] == 1 && d.payload[5] == 1)
        statePublish("edilkamin/322707E4/standby/state", "ON", true);
    } else if (currentOp == Helper::SET_CHANGE_AUTO_SWITCH) {
      if (d.payload[4] == 0) {
        automatic = false;
        statePublish("edilkamin/322707E4/automatic_mode/state", "OFF", true);
      } else if (d.payload[4] == 1) {
        automatic = true;
        statePublish("edilkamin/322707E4/automatic_mode/state", "ON", true);
        statePublish("edilkamin/322707E4/preset_mode/state", "Auto", true);
      }
    } else if (currentOp == Helper::SET_FAN_2) { // akoonet
      currentFan23HiByte = d.payload[4];
      currentFan2Level = d.payload[5];
      publishFan2(currentFan2Level);
    } else if (currentOp == Helper::SET_WRITE_NEW_TEMP) {
      uint16_t r = (d.payload[4] << 8) + d.payload[5];
      float x = r * 0.1;
      char msg_out[10];
      dtostrf(x, 2, 1, msg_out);
      statePublish("edilkamin/322707E4/target_temperature/state",
                         msg_out, true);
    }
  } else if (d.payload[1] == 3) { // Query Response
    // akoonet-12 : controle d'une ecriture recente sur ce registre
    // Si la valeur relue n'est pas celle ecrite et qu'une reecriture part,
    // l'ancienne valeur n'est pas publiee (evite un aller-retour dans HA).
    if (currentCmd[5] == 1 && checkVerify(currentReg, d.payload[3], d.payload[4]))
      return;
    debug(F("Response for query-cmd:"));
    debug(currentOp);
    debug("; data:");
    hexDebug(d.payload, 6);

    debugln();
    if (currentOp == Helper::READ_AUTOMATIC) {
      if (d.payload[3] == 1) {
        automatic = true;
        statePublish("edilkamin/322707E4/automatic_mode/state", "ON", true);
        statePublish("edilkamin/322707E4/preset_mode/state", "Auto", true);
      } else if (d.payload[3] == 0) {
        automatic = false;
        statePublish("edilkamin/322707E4/automatic_mode/state", "OFF", true);
      }
    } else if (currentOp == Helper::READ_POWER) {
      // akoonet-11 : registre 1321 = [ventilateur 1][puissance] lu une seule
      // fois (READ_FAN, qui relisait le meme registre, est retire de la file)
      currentFan1Level = d.payload[3];
      switch (d.payload[3]) {
      case 1: statePublish("edilkamin/322707E4/fan_mode/state", "20%", true); break;
      case 2: statePublish("edilkamin/322707E4/fan_mode/state", "40%", true); break;
      case 3: statePublish("edilkamin/322707E4/fan_mode/state", "60%", true); break;
      case 4: statePublish("edilkamin/322707E4/fan_mode/state", "80%", true); break;
      case 5: statePublish("edilkamin/322707E4/fan_mode/state", "100%", true); break;
      case 6: statePublish("edilkamin/322707E4/fan_mode/state", "Auto", true); break;
      }
      currentPowerLevel = d.payload[4];
      if (!automatic) {
        switch (d.payload[4]) {
        case 1: statePublish("edilkamin/322707E4/preset_mode/state", "Man. P1", true); break;
        case 2: statePublish("edilkamin/322707E4/preset_mode/state", "Man. P2", true); break;
        case 3: statePublish("edilkamin/322707E4/preset_mode/state", "Man. P3", true); break;
        case 4: statePublish("edilkamin/322707E4/preset_mode/state", "Man. P4", true); break;
        case 5: statePublish("edilkamin/322707E4/preset_mode/state", "Man. P5", true); break;
        }
      }
    } else if (currentOp == Helper::READ_MAIN_ENV_TEMP) {
      // akoonet-11 : lecture sur 16 bits (le code d'origine ne lisait que
      // l'octet bas : au-dela de 25,5 C la valeur repartait de zero)
      uint16_t r = (d.payload[3] << 8) + d.payload[4];
      if (r > 0 && r < 600) {
        envTempX10 = r; // akoonet-13
        float x = r * 0.1;
        char msg_out[10];
        dtostrf(x, 3, 1, msg_out);
        statePublish("edilkamin/322707E4/temperature/state", msg_out, true);
      }
    } else if (currentOp == Helper::READ_THERMOCOUPLE_TEMP) {
      uint16_t r = (d.payload[3] << 8) + d.payload[4];
      r = (r * 0.1) + 0.5;
      char msg_out[10];
      itoa(r, msg_out, 10);
      statePublish("edilkamin/322707E4/thermocouple_temperature/state",
                         msg_out, true);
    } else if (currentOp == Helper::READ_TEMPERATURE) {
      uint16_t r = (d.payload[3] << 8) + d.payload[4];
      float x = r * 0.1;
      char msg_out[10];
      dtostrf(x, 2, 1, msg_out);
      statePublish("edilkamin/322707E4/target_temperature/state",
                         msg_out, true);
    } else if (currentOp == Helper::READ_FAN) {
      currentFan1Level = d.payload[3];
      switch (d.payload[3]) {
      case 1:
        statePublish("edilkamin/322707E4/fan_mode/state", "20%", true);
        break;
      case 2:
        statePublish("edilkamin/322707E4/fan_mode/state", "40%", true);
        break;
      case 3:
        statePublish("edilkamin/322707E4/fan_mode/state", "60%", true);
        break;
      case 4:
        statePublish("edilkamin/322707E4/fan_mode/state", "80%", true);
        break;
      case 5:
        statePublish("edilkamin/322707E4/fan_mode/state", "100%", true);
        break;
      case 6:
        statePublish("edilkamin/322707E4/fan_mode/state", "Auto", true);
        break;
      }
    } else if (currentOp == Helper::READ_RELAX) {
      if (d.payload[4] == 0)
        statePublish("edilkamin/322707E4/relax/state", "OFF", true);
      else if (d.payload[4] == 1)
        statePublish("edilkamin/322707E4/relax/state", "ON", true);
    } else if (currentOp == Helper::READ_STANDBY_STATUS) {
      if (d.payload[3] == 0)
        statePublish("edilkamin/322707E4/standby/state", "OFF", true);
      else if (d.payload[3] == 1)
        statePublish("edilkamin/322707E4/standby/state", "ON", true);
    } else if (currentOp == Helper::READ_ON_OFF_CHRONO) {
      if (d.payload[4] == 0)
        statePublish("edilkamin/322707E4/chrono_mode/state", "OFF", true);
      else if (d.payload[4] == 1)
        statePublish("edilkamin/322707E4/chrono_mode/state", "ON", true);
    } else if (currentOp == Helper::READ_FIREPLACE_MAIN_STATUS) {
      stoveStatusKnown = true; // akoonet-13
      stoveIsOff = (d.payload[3] == 0 && d.payload[4] == 0);
      // akoonet-9 : apres une sortie de veille (stand-by), le poele repart
      // seul et rien ne republiait "heat" : le thermostat restait sur Arret.
      // Phases d'allumage (3 a 7) et marche (Ok) => hvac_mode = heat.
      if ((d.payload[4] == 1 && d.payload[3] >= 3 && d.payload[3] <= 7) ||
          (d.payload[3] == 2 && d.payload[4] == 2))
        statePublish("edilkamin/322707E4/hvac_mode/state", "heat", true);
      if (d.payload[3] == 1 && d.payload[4] == 1)
        statePublish("edilkamin/322707E4/status/state", "Cleaning", true);
      else if (d.payload[3] == 3 && d.payload[4] == 1)
        statePublish("edilkamin/322707E4/status/state",
                           "Loading Pellets", true);
      else if (d.payload[3] == 4 && d.payload[4] == 1)
        statePublish("edilkamin/322707E4/status/state",
                           "Ignition - charge suspend", true);
      else if (d.payload[3] == 5 && d.payload[4] == 1)
        statePublish("edilkamin/322707E4/status/state",
                           "Check exhaust gas temperature", true);
      else if (d.payload[3] == 6 && d.payload[4] == 1)
        statePublish("edilkamin/322707E4/status/state",
                           "Threshold temperature check", true);
      else if (d.payload[3] == 7 && d.payload[4] == 1)
        statePublish("edilkamin/322707E4/status/state", "Warmup", true);
      else if (d.payload[3] == 2 && d.payload[4] == 2)
        statePublish("edilkamin/322707E4/status/state", "Ok", true);
      else if (d.payload[3] == 0 && d.payload[4] == 3)
        statePublish("edilkamin/322707E4/status/state", "Shutdown", true);
      else if (d.payload[3] == 0 && d.payload[4] == 4)
        statePublish("edilkamin/322707E4/status/state", "Extinction", true);
      else if (d.payload[3] == 0 && d.payload[4] == 0) {
        statePublish("edilkamin/322707E4/status/state", "Off", true);
        statePublish("edilkamin/322707E4/hvac_mode/state", "off", true);
      } else {
        debug(F("Unknown status combination: "));
        debug(d.payload[3]);
        debug(F("/"));
        debugln(d.payload[4]);
        char dbg[40]; // akoonet-11 : publie pour identification
        snprintf(dbg, sizeof(dbg), "statut inconnu: %u/%u", d.payload[3], d.payload[4]);
        statePublish("edilkamin/322707E4/debug/state", dbg);
      }
    } else if (currentOp == Helper::READ_WARNING_FLAGS) {
      // akoonet-11 : la reserve est le bit 2 (valeur 4) ; un autre
      // avertissement actif en meme temps ne doit pas la masquer
      if (d.payload[4] & 4) // Pellet low
        statePublish("edilkamin/322707E4/pellet_level/state", "Empty", true);
      else
        statePublish("edilkamin/322707E4/pellet_level/state", "Ok", true);
      if (d.payload[4] & ~4) {
        char dbg[40];
        snprintf(dbg, sizeof(dbg), "avertissements: 0x%02X%02X", d.payload[3], d.payload[4]);
        statePublish("edilkamin/322707E4/debug/state", dbg);
      }
    } else if (currentOp == Helper::READ_ALARM) { // akoonet-4
      // akoonet-8 : numero d'alarme = octet HAUT (valide : 0x0900 = A09)
      int32_t code = (d.payload[3] << 8) + d.payload[4];
      byte num = d.payload[3] ? d.payload[3] : d.payload[4];
      char msg_out[16];
      snprintf(msg_out, sizeof(msg_out), "%u", num);
      statePublish("edilkamin/322707E4/alarm_code/state", msg_out, true);
      statePublish("edilkamin/322707E4/alarm/state",
                         code != 0 ? "ON" : "OFF", true);
      char label[80];
      if (code == 0)
        snprintf(label, sizeof(label), "Aucune");
      else
        snprintf(label, sizeof(label), "A%02u %s", num, alarmLabel(num));
      statePublish("edilkamin/322707E4/alarm_label/state", label, true);
      lastAlarmCode = code;
    } else if (currentOp == Helper::READ_FIREPLACE_CURRENT_POWER) { // akoonet-5
      char msg_out[48];
      snprintf(msg_out, sizeof(msg_out), "haut=%u bas=%u (0x%02X%02X)",
               d.payload[3], d.payload[4], d.payload[3], d.payload[4]);
      statePublish("edilkamin/322707E4/machine_power_raw/state", msg_out, true);
      // akoonet-11 : octet bas = puissance reelle, octet haut = ventilateur 1 reel
      char v[8];
      snprintf(v, sizeof(v), "%u", d.payload[4]);
      statePublish("edilkamin/322707E4/real_power/state", v, true);
      snprintf(v, sizeof(v), "%u", d.payload[3] * 20);
      statePublish("edilkamin/322707E4/real_fan1/state", v, true);
    } else if (currentOp == Helper::READ_FAN_23_MACHINE) { // akoonet-5
      char msg_out[48];
      snprintf(msg_out, sizeof(msg_out), "haut=%u bas=%u (0x%02X%02X)",
               d.payload[3], d.payload[4], d.payload[3], d.payload[4]);
      statePublish("edilkamin/322707E4/machine_fan23_raw/state", msg_out, true);
      // akoonet-11 : octet bas = ventilateur 2 reel (0 avec Relax et V2 Arret)
      char v[8];
      snprintf(v, sizeof(v), "%u", d.payload[4] * 20);
      statePublish("edilkamin/322707E4/real_fan2/state", v, true);
    } else if (currentOp == Helper::READ_TOTAL_ALARMS) { // akoonet-4
      char msg_out[16];
      // akoonet-8 : lu 0x0303 pour 3 alarmes (cloud) -> octet bas (a confirmer)
      snprintf(msg_out, sizeof(msg_out), "%u", d.payload[4]);
      statePublish("edilkamin/322707E4/total_alarms/state", msg_out, true);
    } else if (currentOp == Helper::READ_DATE_TIME && currentReg >= 0x0316 &&
               currentReg <= 0x0319) { // 2026.11.2 : horloge du poele (brut)
      uint8_t k = currentReg - 0x0316;
      clockWords[k] = (d.payload[3] << 8) + d.payload[4];
      clockFrameTs = ((uint32_t)d.timestamp[0] << 24) | ((uint32_t)d.timestamp[1] << 16) |
                     ((uint32_t)d.timestamp[2] << 8) | d.timestamp[3];
      if (k == 3) {
        char raw[64];
        snprintf(raw, sizeof(raw), "0316=%04lX 0317=%04lX 0318=%04lX 0319=%04lX",
                 (long)(clockWords[0] & 0xFFFF), (long)(clockWords[1] & 0xFFFF),
                 (long)(clockWords[2] & 0xFFFF), (long)(clockWords[3] & 0xFFFF));
        statePublish("edilkamin/322707E4/stove_clock_raw/state", raw, true);
        char ts[24] = "?";
        time_t t = (time_t)clockFrameTs;
        struct tm lt;
        if (clockFrameTs > 1600000000UL && localtime_r(&t, &lt))
          strftime(ts, sizeof(ts), "%d/%m/%Y %H:%M:%S", &lt);
        statePublish("edilkamin/322707E4/stove_frame_time/state", ts, true);
      }
    } else if (currentOp == Helper::READ_PELLET_REMAINING) { // akoonet-4
      char msg_out[16];
      snprintf(msg_out, sizeof(msg_out), "%u", (d.payload[3] << 8) + d.payload[4]);
      statePublish("edilkamin/322707E4/pellet_remaining/state", msg_out, true);
    } else if (currentOp == Helper::READ_COUNTER_CANDIDATE) { // akoonet-4
      for (uint8_t k = 0; k < candCount; k++) {
        if (candRegs[k] == currentReg)
          candValues[k] = (d.payload[3] << 8) + d.payload[4];
      }
      char out[200];
      char *ptr = out;
      size_t left = sizeof(out);
      for (uint8_t k = 0; k < candCount && left > 1; k++) {
        int n;
        if (candValues[k] < 0)
          n = snprintf(ptr, left, "%s%04X=?", k ? " " : "", candRegs[k]);
        else
          n = snprintf(ptr, left, "%s%04X=%ld", k ? " " : "", candRegs[k],
                       (long)candValues[k]);
        if (n < 0 || (size_t)n >= left)
          break;
        ptr += n;
        left -= n;
      }
      statePublish("edilkamin/322707E4/counters_raw/state", out, true);
      // akoonet-8 : 0x0334 = nombre d'allumages (valide : 2 et 9 = cloud)
      if (currentReg == 0x0334) {
        char ign[16];
        snprintf(ign, sizeof(ign), "%u", (d.payload[3] << 8) + d.payload[4]);
        statePublish("edilkamin/322707E4/ignitions/state", ign, true);
      }
    } else if (currentOp == Helper::READ_FAN_23) { // akoonet
      currentFan23HiByte = d.payload[3];
      currentFan2Level = d.payload[4];
      fan23Known = true;
      publishFan2(currentFan2Level);
    }
  }
}

// MQTT-Callback
// ---------------------------------------------------------------- 2026.11.2
// Page web d'etat (protegee par mot de passe) et adresse IP en MQTT
WebServer web(80);

// 2026.11.2 : reglages (MQTT, NTP, mot de passe de la page) dans la zone NVS,
// comme le Wi-Fi : ils survivent a un changement de repartition de la memoire
void saveConfigKey(const char *key, const char *value) {
  Preferences pr;
  if (pr.begin("edk", false)) {
    pr.putString(key, value);
    pr.end();
  }
}

void saveAllConfig() {
  Preferences pr;
  if (!pr.begin("edk", false))
    return;
  pr.putString("mqtt_server", mqtt_server);
  pr.putString("mqtt_port", mqtt_port);
  pr.putString("mqtt_user", mqtt_user);
  pr.putString("mqtt_pass", mqtt_pass);
  pr.putString("ntp_server", ntp_server);
  pr.putString("ntp_offset", ntp_offset);
  pr.putString("web_pass", web_pass);
  pr.putBool("ok", true);
  pr.end();
}

// Renvoie true si des reglages ont ete trouves dans la zone NVS
bool loadNvsConfig() {
  Preferences pr;
  if (!pr.begin("edk", true))
    return false;
  bool ok = pr.getBool("ok", false);
  if (ok) {
    pr.getString("mqtt_server", mqtt_server, sizeof(mqtt_server));
    pr.getString("mqtt_port", mqtt_port, sizeof(mqtt_port));
    pr.getString("mqtt_user", mqtt_user, sizeof(mqtt_user));
    pr.getString("mqtt_pass", mqtt_pass, sizeof(mqtt_pass));
    pr.getString("ntp_server", ntp_server, sizeof(ntp_server));
    pr.getString("ntp_offset", ntp_offset, sizeof(ntp_offset));
    pr.getString("web_pass", web_pass, sizeof(web_pass));
  }
  pr.end();
  return ok;
}

void publishWebState() {
  statePublish("edilkamin/322707E4/web_page/state", web_pass[0] ? "Protégée" : "Désactivée", true);
}

void publishWebDiscovery() {
  String ip = WiFi.localIP().toString();
  String dev = "\"device\": {\"identifiers\": [\"322707E4\"],\"configuration_url\": \"http://" + ip + "/\"}";
  String c = "{\"name\": \"ESP32 adresse IP\",\"unique_id\": \"322707E4_edilkamin_ip\",\"icon\": \"mdi:ip-network\","
             "\"entity_category\": \"diagnostic\",\"state_topic\": \"edilkamin/322707E4/ip/state\"," + dev + "}";
  mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_ip/config", c.c_str(), true);
  c = "{\"name\": \"Page web\",\"unique_id\": \"322707E4_edilkamin_web_page\",\"icon\": \"mdi:web\","
      "\"entity_category\": \"diagnostic\",\"state_topic\": \"edilkamin/322707E4/web_page/state\"," + dev + "}";
  mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_web_page/config", c.c_str(), true);
  c = "{\"name\": \"Mot de passe de la page web\",\"unique_id\": \"322707E4_edilkamin_web_password\",\"icon\": \"mdi:form-textbox-password\","
      "\"entity_category\": \"config\",\"mode\": \"password\",\"min\": 0,\"max\": 32,"
      "\"command_topic\": \"edilkamin/322707E4/web_password/set\"," + dev + "}";
  mqttClient.publish("homeassistant/text/edilkamin_322707E4_web_password/config", c.c_str(), true);
  c = "{\"name\": \"Horloge du poêle (brut)\",\"unique_id\": \"322707E4_edilkamin_stove_clock_raw\",\"icon\": \"mdi:clock-outline\","
      "\"entity_category\": \"diagnostic\",\"state_topic\": \"edilkamin/322707E4/stove_clock_raw/state\"," + dev + "}";
  mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_stove_clock_raw/config", c.c_str(), true);
  c = "{\"name\": \"Horodatage des trames du poêle\",\"unique_id\": \"322707E4_edilkamin_stove_frame_time\",\"icon\": \"mdi:clock-check-outline\","
      "\"entity_category\": \"diagnostic\",\"state_topic\": \"edilkamin/322707E4/stove_frame_time/state\"," + dev + "}";
  mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_stove_frame_time/config", c.c_str(), true);
  c = "{\"name\": \"Occupation du Bluetooth\",\"unique_id\": \"322707E4_edilkamin_ble_occupancy\",\"icon\": \"mdi:bluetooth-connect\","
      "\"unit_of_measurement\": \"%\",\"state_class\": \"measurement\",\"entity_category\": \"diagnostic\","
      "\"state_topic\": \"edilkamin/322707E4/ble_occupancy/state\","
      "\"json_attributes_topic\": \"edilkamin/322707E4/diag/state\","
      "\"json_attributes_template\": \"{{ {'derniere_connexion_s': value_json.ble_derniere_s, 'lectures_sans_reponse': value_json.ble_sans_reponse} | tojson }}\"," + dev + "}";
  mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_ble_occupancy/config", c.c_str(), true);
  c = "{\"name\": \"Durée de connexion Bluetooth\",\"unique_id\": \"322707E4_edilkamin_ble_session\",\"icon\": \"mdi:timer-outline\","
      "\"unit_of_measurement\": \"s\",\"device_class\": \"duration\",\"state_class\": \"measurement\",\"entity_category\": \"diagnostic\","
      "\"state_topic\": \"edilkamin/322707E4/ble_session/state\"," + dev + "}";
  mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_ble_session/config", c.c_str(), true);
  statePublish("edilkamin/322707E4/ip/state", ip.c_str(), true);
  publishWebState();
  otaState("pret", 0, "");
}

void mqttCallback(String topic, byte *message, unsigned int length); // 2026.11.6 : utilise par /cmd
static const char WEB_PAGE[] PROGMEM = R"HTML(<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Poêle Edilkamin</title>
<style>
:root{--bg:#f4f5f7;--card:#fff;--txt:#1c1f23;--sub:#6b7280;--acc:#f06b21;--ok:#2e7d32;--bad:#c62828;--line:#e5e7eb}
@media(prefers-color-scheme:dark){:root{--bg:#111315;--card:#1c1f23;--txt:#e8eaed;--sub:#9aa0a6;--line:#2c3036}}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:720px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:4px 0 2px}.top{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap}
.sub{color:var(--sub);font-size:13px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.tile{background:var(--card);border-radius:14px;padding:12px 14px;box-shadow:0 1px 2px rgba(0,0,0,.06)}
.tile b{display:block;font-size:22px;font-weight:600;margin-top:2px}.tile span{color:var(--sub);font-size:12px}
.card{background:var(--card);border-radius:14px;padding:4px 14px;margin-bottom:12px;box-shadow:0 1px 2px rgba(0,0,0,.06)}
.card h2{font-size:14px;margin:10px 0 4px;color:var(--sub);font-weight:600;text-transform:uppercase;letter-spacing:.04em}
table{width:100%;border-collapse:collapse}td{padding:7px 0;border-top:1px solid var(--line)}td:last-child{text-align:right;font-weight:600}
.slot td{vertical-align:top}.slot td:first-child{font-weight:600;white-space:nowrap;padding-right:10px}.slot .det{color:var(--sub);font-size:13px;font-weight:400}.slot.off td{opacity:.5}.slot.cur td:first-child{color:var(--acc)}
.tcr{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 0;border-top:1px solid var(--line);flex-wrap:wrap}.tcr:first-child{border-top:0}
.seg{display:flex;flex-wrap:wrap;gap:4px}.seg button,.pm{border:1px solid var(--line);background:var(--bg);color:var(--txt);border-radius:9px;padding:6px 10px;font:inherit;font-size:14px;cursor:pointer;min-width:38px}
.seg button.on{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600}.pm{font-size:20px;width:44px;height:40px;padding:0}
.big{border:0;border-radius:12px;padding:10px 18px;font:inherit;font-weight:600;color:#fff;cursor:pointer;background:var(--acc)}.big.stop{background:var(--sub)}.big.conf{background:var(--bad)}
.cons{font-size:22px;font-weight:600;min-width:92px;text-align:center}
.acc{color:var(--acc)}.ok{color:var(--ok)}.bad{color:var(--bad)}
</style></head><body><main>
<div class="top"><div><h1>Poêle Edilkamin</h1><div class="sub" id="maj">Chargement…</div></div><div class="sub" id="ver"></div></div>
<div class="grid" id="tiles"></div>
<div class="card"><h2>Télécommande</h2><div id="tc"></div><div class="sub" id="tcmsg" style="min-height:18px;padding:0 0 8px"></div></div>
<div class="card"><h2>Poêle</h2><table id="poele"></table></div>
<div class="card"><h2>Granulés et compteurs</h2><table id="compteurs"></table></div>
<div class="card"><h2>ESP32</h2><table id="esp"></table></div>
<div class="card"><h2>Planning de secours</h2><div class="sub" id="schedinfo" style="padding:4px 0 6px"></div><table id="sched"></table></div>
<div class="card"><h2>Mettre à jour le firmware</h2>
<form method="post" action="/update" enctype="multipart/form-data" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:8px 0 12px">
<input type="file" name="firmware" accept=".bin" required><button style="padding:6px 14px;border-radius:10px;border:0;background:var(--acc);color:#fff;font-weight:600">Installer</button></form></div>
</main><script>
const ST={"Off":"Éteint","Ok":"En marche","Warmup":"Préchauffage","Loading Pellets":"Chargement des granulés","Shutdown":"Extinction","Extinction":"Extinction","Final cleaning":"Nettoyage final","Check exhaust gas temperature":"Contrôle des fumées","Ignition - charge suspend":"Allumage"};
const onoff=v=>v==="ON"?"Activé":v==="OFF"?"Désactivé":v;
const deg=v=>v==null||v===""?"—":(Number(v).toLocaleString("fr-FR",{minimumFractionDigits:1,maximumFractionDigits:1})+" °C");
const dur=s=>{s=Number(s)||0;const j=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return (j?j+" j ":"")+h+" h "+String(m).padStart(2,"0")};
const E=v=>String(v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
const row=(l,v,c)=>v==null||v===""?"":`<tr><td>${E(l)}</td><td class="${E(c||"")}">${E(v)}</td></tr>`;
const tile=(l,v,c)=>`<div class="tile"><span>${E(l)}</span><b class="${E(c||"")}">${E(v??"—")}</b></div>`;
let S={},pendT=null,tT=null,offArm=0;
async function cmd(t,v){const m=document.getElementById("tcmsg");m.textContent="Envoi…";
 try{const r=await fetch("/cmd",{method:"POST",headers:{"X-ECC":"1","Content-Type":"application/x-www-form-urlencoded"},body:"t="+encodeURIComponent(t)+"&v="+encodeURIComponent(v)});
 m.textContent=r.ok?"Ordre envoyé au poêle, confirmation à la prochaine lecture.":"Ordre refusé ("+r.status+")";}catch(e){m.textContent="ESP32 injoignable";}
 setTimeout(maj,2000);setTimeout(maj,6000);}
const seg=(t,cur,opts)=>`<div class="seg">${opts.map(([v,l])=>`<button class="${v===cur?"on":""}" data-t="${E(t)}" data-v="${E(v)}">${E(l)}</button>`).join("")}</div>`;
const LV=[["20%","1"],["40%","2"],["60%","3"],["80%","4"],["100%","5"],["Auto","Auto"]];
function tc(d){S=d;const on=d.hvac_mode==="heat";const t=pendT!=null?pendT:Number(d.target_temperature);
 document.getElementById("tc").innerHTML=
 `<div class="tcr"><span>Marche</span><button class="big ${on?(offArm>Date.now()?"conf":"stop"):""}" id="onoff">${on?(offArm>Date.now()?"Confirmer l'arrêt":"Éteindre"):"Allumer"}</button></div>`+
 `<div class="tcr"><span>Consigne</span><div style="display:flex;align-items:center;gap:6px"><button class="pm" data-d="-0.5">−</button><span class="cons">${E(isNaN(t)?"—":deg(t))}</span><button class="pm" data-d="0.5">+</button></div></div>`+
 `<div class="tcr"><span>Puissance</span>${seg("preset_mode",d.preset_mode,[["Auto","Auto"],["Man. P1","P1"],["Man. P2","P2"],["Man. P3","P3"],["Man. P4","P4"],["Man. P5","P5"]])}</div>`+
 `<div class="tcr"><span>Ventilation 1</span>${seg("fan_mode",d.fan_mode,LV)}</div>`+
 (d.fan2_mode!=null?`<div class="tcr"><span>Ventilation 2</span>${seg("fan2_mode",d.fan2_mode,[["Arrêt","Arrêt"],...LV])}</div>`:"")+
 `<div class="tcr"><span>Stand-by</span>${seg("standby",d.standby,[["OFF","Non"],["ON","Oui"]])}</div>`+
 `<div class="tcr"><span>Silence (Relax)</span>${seg("relax",d.relax,[["OFF","Non"],["ON","Oui"]])}</div>`;}
document.addEventListener("click",e=>{const b=e.target.closest("button");if(!b||!document.getElementById("tc").contains(b))return;
 if(b.id==="onoff"){if(S.hvac_mode==="heat"){if(offArm>Date.now()){offArm=0;cmd("hvac_mode","off");}else{offArm=Date.now()+4000;setTimeout(()=>tc(S),4100);}}else cmd("hvac_mode","heat");tc(S);return;}
 if(b.dataset.d){const base=pendT!=null?pendT:Number(S.target_temperature)||19;pendT=Math.min(30,Math.max(5,Math.round((base+Number(b.dataset.d))*2)/2));tc(S);
  clearTimeout(tT);tT=setTimeout(()=>{const v=pendT;cmd("target_temperature",v.toFixed(1));setTimeout(()=>{pendT=null;},6500);},1200);return;}
 if(b.dataset.t)cmd(b.dataset.t,b.dataset.v);});
async function maj(){try{const r=await fetch("/api",{cache:"no-store"});if(!r.ok)throw 0;const d=await r.json(),g=d.diag||{};
const st=d.status||"",alarm=d.alarm==="ON";tc(d);
document.getElementById("tiles").innerHTML=
 tile("État",alarm?"Alarme":(ST[st]||st||"—"),alarm?"bad":st==="Ok"?"acc":"")+
 tile("Ambiante",deg(d.temperature))+tile("Consigne",deg(d.target_temperature),"acc")+
 tile("Puissance",(d.preset_mode||"—")+(d.real_power?` · réelle P${d.real_power}`:""));
document.getElementById("poele").innerHTML=
 row("Marche",d.hvac_mode==="heat"?"Allumé":d.hvac_mode==="off"?"Éteint":d.hvac_mode)+
 row("Stand-by",onoff(d.standby))+row("Silence (Relax)",onoff(d.relax))+row("Chrono",onoff(d.chrono_mode))+
 row("Mode automatique",onoff(d.automatic_mode))+row("Ventilation 1",d.fan_mode+(d.real_fan1!=null?` (réelle ${d.real_fan1} %)`:""))+
 row("Ventilation 2",d.fan2_mode!=null?d.fan2_mode+(d.real_fan2!=null?` (réelle ${d.real_fan2} %)`:""):null)+
 row("Température des fumées",d.thermocouple_temperature!=null?d.thermocouple_temperature+" °C":null)+
 row("Alarme",alarm?(d.alarm_label||d.alarm_code||"Oui"):"Aucune",alarm?"bad":"ok");
document.getElementById("compteurs").innerHTML=
 row("Niveau de granulés",d.pellet_level,d.pellet_level&&d.pellet_level!=="Ok"?"bad":"")+row("Granulés restants",d.pellet_remaining)+
 row("Allumages",d.ignitions)+row("Alarmes (total)",d.total_alarms);
document.getElementById("esp").innerHTML=
 row("Bluetooth",onoff(d.bluetooth),d.bluetooth==="ON"?"ok":"bad")+row("MQTT",d.mqtt?"Connecté":"Déconnecté",d.mqtt?"ok":"bad")+
 row("Adresse IP",d.ip)+row("Occupation du Bluetooth (15 min)",d.ble_occupancy!=null?d.ble_occupancy+" %":null)+row("Dernière connexion Bluetooth",d.ble_session!=null?String(d.ble_session).replace(".",",")+" s":null)+row("Lectures sans réponse",g.ble_sans_reponse)+row("Signal WiFi",g.rssi!=null?g.rssi+" dBm":null)+row("Planning de secours",g.secours)+
 row("Heure de l'ESP32",g.heure_esp)+row("Horloge du poêle (brut)",d.stove_clock_raw)+row("Horodatage des trames du poêle",d.stove_frame_time)+row("Fonctionne depuis",dur(d.uptime))+row("Dernier redémarrage",g.reset)+
 row("Mémoire libre",d.heap!=null?Math.round(d.heap/1024)+" Ko":null);
const hm=m=>String(Math.floor(m/60)).padStart(2,"0")+":"+String(m%60).padStart(2,"0");
const JR=["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"];
const jours=b=>b===127?"Tous les jours":b===31?"Lundi au vendredi":b===96?"Week-end":JR.filter((_,i)=>b>>i&1).join(", ");
const ven=v=>v===6?"Auto":v===0?"Arrêt":"V"+v;
const sc=d.sched||[];
document.getElementById("schedinfo").textContent=!d.sched_loaded?"Aucun planning reçu de Home Assistant.":
 d.sched_fallback?"Actif : Home Assistant est absent, l'ESP32 applique ces plages.":"En veille : Home Assistant pilote le poêle. Ces plages servent seulement s'il est absent plus de 5 min.";
document.getElementById("sched").innerHTML=sc.map((p,i)=>{const cur=d.sched_fallback&&d.sched_current===i;
 const det=p.m?"Stand-by":"Marche";
 return `<tr class="slot${p.a?"":" off"}${cur?" cur":""}"><td>Plage ${i+1}${cur?" ●":""}<div class="det">${E(p.a?hm(p.d)+" → "+hm(p.f):"désactivée")}</div></td><td>${E(deg(p.c/10))}<div class="det">${E(jours(p.j)+" · "+det+" · "+(p.pu?"P"+p.pu:"Puissance auto")+" · Vent. "+ven(p.v1)+" / "+ven(p.v2)+(p.r?" · Silence":""))}</div></td></tr>`}).join("");
document.getElementById("ver").textContent="Firmware "+(d.version||"");
document.getElementById("maj").textContent="Mis à jour à "+new Date().toLocaleTimeString("fr-FR");
}catch(e){document.getElementById("maj").textContent="ESP32 injoignable, nouvel essai…";}}
maj();setInterval(maj,5000);
</script></body></html>)HTML";

// ---------------------------------------------------------------- 2026.11.2
// Mise a jour a distance (OTA) : ordre MQTT de Home Assistant (adresse + MD5)
// ou fichier envoye depuis la page web. Deux emplacements de programme : en cas
// d'echec, l'ESP32 redemarre sur la version precedente.
String otaUrl, otaMd5;
bool otaPending = false;

void otaState(const char *state, int pct, const char *msg) {
  char out[200];
  snprintf(out, sizeof(out), "{\"state\":\"%s\",\"progress\":%d,\"message\":\"%s\",\"version\":\"" FW_VERSION "\"}",
           state, pct, msg);
  statePublish("edilkamin/322707E4/ota/state", out, true);
  mqttClient.loop();
}

void otaRun() {
  otaPending = false;
  if (otaMd5.length() != 32) {
    otaState("erreur", 0, "MD5 manquant ou invalide");
    return;
  }
  HTTPClient http;
  WiFiClient plain;
  WiFiClientSecure secure;
  bool ok;
  if (otaUrl.startsWith("https://")) {
    // L'authenticite du fichier est garantie par le MD5 fourni par Home Assistant
    secure.setInsecure();
    ok = http.begin(secure, otaUrl);
  } else {
    ok = http.begin(plain, otaUrl);
  }
  if (!ok) {
    otaState("erreur", 0, "adresse invalide");
    return;
  }
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  http.setTimeout(15000);
  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    char m[48];
    snprintf(m, sizeof(m), "telechargement refuse (HTTP %d)", code);
    otaState("erreur", 0, m);
    http.end();
    return;
  }
  int len = http.getSize();
  if (len <= 0 || !Update.begin(len)) {
    otaState("erreur", 0, "taille invalide ou place insuffisante");
    http.end();
    return;
  }
  Update.setMD5(otaMd5.c_str());
  otaState("installation", 0, "telechargement");
  WiFiClient *stream = http.getStreamPtr();
  uint8_t buf[1024];
  int done = 0, lastPct = -1;
  unsigned long msLast = millis();
  while (done < len && millis() - msLast < 20000) {
    size_t avail = stream->available();
    if (!avail) {
      delay(5);
      continue;
    }
    int n = stream->readBytes(buf, avail > sizeof(buf) ? sizeof(buf) : avail);
    if (n <= 0)
      continue;
    if (Update.write(buf, n) != (size_t)n)
      break;
    done += n;
    msLast = millis();
    int pct = (int)((done * 100LL) / len);
    if (pct / 10 != lastPct / 10) {
      lastPct = pct;
      otaState("installation", pct, "telechargement");
    }
  }
  http.end();
  if (done != len || !Update.end()) {
    Update.abort();
    otaState("erreur", 0, Update.hasError() ? Update.errorString() : "telechargement incomplet");
    return;
  }
  otaState("termine", 100, "redemarrage");
  delay(1000);
  ESP.restart();
}

bool webAuth() {
  if (!web_pass[0]) {
    web.send(403, "text/plain; charset=utf-8",
             "Page desactivee : definir un mot de passe (entite « Mot de passe de la page web » dans Home Assistant).");
    return false;
  }
  if (!web.authenticate("admin", web_pass)) {
    web.requestAuthentication(BASIC_AUTH, "Edilkamin");
    return false;
  }
  return true;
}

void webSetup() {
  web.on("/", HTTP_GET, []() {
    if (!webAuth())
      return;
    web.sendHeader("Cache-Control", "no-store");
    web.send_P(200, "text/html; charset=utf-8", WEB_PAGE);
  });
  web.on("/api", HTTP_GET, []() {
    if (!webAuth())
      return;
    JsonDocument d;
    for (auto &kv : stateCache) {
      if (kv.first == "diag") {
        JsonDocument g;
        if (!deserializeJson(g, kv.second))
          d["diag"] = g;
      } else
        d[kv.first] = kv.second;
    }
    d["ip"] = WiFi.localIP().toString();
    d["mqtt"] = mqttClient.connected();
    d["uptime"] = (unsigned long)(millis() / 1000);
    d["heap"] = (unsigned)ESP.getFreeHeap();
    d["version"] = FW_VERSION;
    // 2026.11.5 : planning de secours recu de Home Assistant
    d["sched_loaded"] = schedLoaded;
    d["sched_fallback"] = fallbackActive;
    d["sched_current"] = fbLastProfile;
    JsonArray sa = d["sched"].to<JsonArray>();
    for (uint8_t i = 0; i < schedCount; i++) {
      JsonObject o = sa.add<JsonObject>();
      o["a"] = sched[i].active ? 1 : 0;
      o["d"] = sched[i].start;
      o["f"] = sched[i].end;
      o["c"] = sched[i].consX10;
      o["m"] = sched[i].standby;
      o["pu"] = sched[i].power;
      o["v1"] = sched[i].fan1;
      o["v2"] = sched[i].fan2;
      o["r"] = sched[i].relax;
      o["j"] = sched[i].days;
    }
    String out;
    serializeJson(d, out);
    web.sendHeader("Cache-Control", "no-store");
    web.send(200, "application/json", out);
  });
  // 2026.11.6 : telecommande de la page web. Memes ordres que Home Assistant
  // (passent par mqttCallback). En-tete X-ECC exige : un formulaire d'un autre
  // site ne peut pas l'envoyer (protection CSRF).
  web.on("/cmd", HTTP_POST, []() {
    if (!webAuth())
      return;
    if (web.header("X-ECC") != "1") {
      web.send(403, "text/plain", "refuse");
      return;
    }
    String t = web.arg("t"), v = web.arg("v");
    static const char *allowed[] = {"hvac_mode", "target_temperature", "preset_mode", "fan_mode",
                                    "fan2_mode", "standby", "relax"};
    bool ok = false;
    for (auto a : allowed)
      if (t == a)
        ok = true;
    if (!ok || v.length() == 0 || v.length() > 16) {
      web.send(400, "text/plain", "ordre invalide");
      return;
    }
    debugln("Page web : " + t + " = " + v);
    mqttCallback("edilkamin/322707E4/" + t + "/set", (byte *)v.c_str(), v.length());
    web.sendHeader("Cache-Control", "no-store");
    web.send(200, "text/plain", "ok");
  });
  // 2026.11.2 : envoi d'un firmware (.bin) depuis la page
  web.on(
      "/update", HTTP_POST,
      []() {
        if (!webAuth())
          return;
        bool ok = !Update.hasError();
        web.sendHeader("Connection", "close");
        web.send(200, "text/plain; charset=utf-8",
                 ok ? "Firmware installe, redemarrage..." : "Echec de l'installation");
        if (ok) {
          delay(1000);
          ESP.restart();
        }
      },
      []() {
        HTTPUpload &up = web.upload();
        if (up.status == UPLOAD_FILE_START) {
          if (!web_pass[0] || !web.authenticate("admin", web_pass)) {
            Update.abort();
            return;
          }
          otaState("installation", 0, "envoi depuis la page web");
          Update.begin(UPDATE_SIZE_UNKNOWN);
        } else if (up.status == UPLOAD_FILE_WRITE) {
          if (Update.isRunning())
            Update.write(up.buf, up.currentSize);
        } else if (up.status == UPLOAD_FILE_END) {
          if (Update.isRunning() && Update.end(true))
            otaState("termine", 100, "redemarrage");
          else
            otaState("erreur", 0, "envoi refuse");
        }
      });
  web.onNotFound([]() { web.send(404, "text/plain", "Introuvable"); });
  static const char *hdrs[] = {"X-ECC"};
  web.collectHeaders(hdrs, 1); // 2026.11.6 : en-tete de la telecommande
  web.begin();
}

void mqttCallback(String topic, byte *message, unsigned int length) {
  debugln();
  debug(F("MQTT-Message arrived with topic: "));
  debug(topic);
  debug(F(". Message: "));
  String msg;
  msg.reserve(length);
  for (unsigned int i = 0; i < length; i++) {
    // debug((char)message[i]);
    msg += (char)message[i];
  }
  debug(msg);
  // debugln("");
  // akoonet-12 : un message vide sert a effacer un ordre retenu sur le serveur
  // MQTT ; il ne doit jamais etre interprete (hvac_mode vide = arret !)
  if (length == 0)
    return;
  // akoonet-12 : Home Assistant (re)demarre -> republier le diagnostic
  if (topic == "homeassistant/status") {
    if (msg == "online") {
      msLastDiag = 0;
      haOnline = true; // akoonet-13
      msHaOffline = 0;
    } else if (msg == "offline") {
      haOnline = false;
      msHaOffline = currentMillis | 1;
    }
    return;
  }
  // akoonet-13 : planning de secours envoye par Home Assistant
  if (topic == "edilkamin/322707E4/schedule") {
    storeSchedule((const char *)message, length);
    return;
  }
  // 2026.11.2 : mot de passe de la page web (vide = page desactivee)
  // 2026.11.2 : mise a jour a distance {"url": "...", "md5": "..."}
  if (topic == "edilkamin/322707E4/ota/set") {
    if (length == 0)
      return;
    JsonDocument j;
    if (deserializeJson(j, message, length) || !j["url"].is<const char *>()) {
      otaState("erreur", 0, "ordre invalide");
      return;
    }
    otaUrl = (const char *)j["url"];
    otaMd5 = j["md5"] | "";
    otaMd5.toLowerCase();
    otaPending = true;
    return;
  }
  if (topic == "edilkamin/322707E4/web_password/set") {
    if (length == 0) // message vide : effacement du message retenu, ignore
      return;
    String pw;
    for (unsigned int i = 0; i < length && i < sizeof(web_pass) - 1; i++)
      pw += (char)message[i];
    pw.trim();
    if (pw == "-") // « - » : page desactivee
      pw = "";
    strncpy(web_pass, pw.c_str(), sizeof(web_pass) - 1);
    web_pass[sizeof(web_pass) - 1] = 0;
    saveConfigKey("web_pass", web_pass);
    publishWebState();
    return;
  }
  // un ordre recu de HA prouve qu'il est en ligne
  haOnline = true;
  msHaOffline = 0;
  byte btCmd[6];
  if (topic == "edilkamin/322707E4/bluetooth/set") {
    if (msg == "ON")
      doBtConnect = true;
    if (msg == "OFF")
      doBtConnect = false;
  } else if (topic == "edilkamin/322707E4/hvac_mode/set") {
    memcpy(btCmd, h.setOnOff, 6);
    if (msg == "heat")
      btCmd[5] = 1;
    else if (msg == "off")
      btCmd[5] = 0;
    queueBtCommand(Helper::SET_ON_OFF, btCmd);
  } else if (topic == "edilkamin/322707E4/fan_mode/set" &&
             currentFan1Level != 0 &&
             currentPowerLevel !=
                 0) // ignore set command if fan & power-level is 0 (=boot)
  {
    byte btPacket[32];
    memcpy(btCmd, h.setFan1, 6);
    btCmd[5] = currentPowerLevel;
    if (msg == "20%")
      btCmd[4] = 1;
    else if (msg == "40%")
      btCmd[4] = 2;
    else if (msg == "60%")
      btCmd[4] = 3;
    else if (msg == "80%")
      btCmd[4] = 4;
    else if (msg == "100%")
      btCmd[4] = 5;
    else if (msg == "Auto")
      btCmd[4] = 6;
    queueBtCommand(Helper::SET_FAN_1, btCmd);
  } else if (topic == "edilkamin/322707E4/automatic_mode/set") {
    byte btPacket[32];
    memcpy(btCmd, h.setChangeAutoSwitch, 6);
    if (msg == "ON")
      btCmd[4] = 1;
    else if (msg == "OFF")
      btCmd[4] = 0;
    queueBtCommand(Helper::SET_CHANGE_AUTO_SWITCH, btCmd);
  } else if (topic == "edilkamin/322707E4/preset_mode/set" &&
             currentFan1Level != 0 &&
             currentPowerLevel !=
                 0) // ignore set command if fan & power-level is 0 (=boot)
  {
    byte btPacket[32];
    if (msg == "Auto") {
      memcpy(btCmd, h.setChangeAutoSwitch, 6);
      btCmd[4] = 1;
      queueBtCommand(Helper::SET_CHANGE_AUTO_SWITCH, btCmd);
    } else {
      // 2026.11.2 : couper d'abord le mode automatique du poele, sinon la
      // puissance manuelle est ignoree et le poele reste en Auto
      byte autoOff[6];
      memcpy(autoOff, h.setChangeAutoSwitch, 6);
      autoOff[4] = 0;
      queueBtCommand(Helper::SET_CHANGE_AUTO_SWITCH, autoOff);
      memcpy(btCmd, h.setWriteNewPower, 6);
      btCmd[4] = currentFan1Level;
      if (msg == "Man. P1")
        btCmd[5] = 1;
      else if (msg == "Man. P2")
        btCmd[5] = 2;
      else if (msg == "Man. P3")
        btCmd[5] = 3;
      else if (msg == "Man. P4")
        btCmd[5] = 4;
      else if (msg == "Man. P5")
        btCmd[5] = 5;
      queueBtCommand(Helper::SET_WRITE_NEW_POWER, btCmd);
    }
  } else if (topic == "edilkamin/322707E4/target_temperature/set") {
    // akoonet-11 : lecture du nombre ("22", "22.0", "21.5") au lieu de
    // retirer le point ("22" donnait 2,2 C)
    float f = msg.toFloat();
    if (f < 5 || f > 40)
      return;
    uint16_t t = (uint16_t)lroundf(f * 10);
    memcpy(btCmd, h.setWriteNewTemperature, 6);
    btCmd[4] = (uint8_t)(t >> 8);
    btCmd[5] = (uint8_t)t;
    queueBtCommand(Helper::SET_WRITE_NEW_TEMP, btCmd);
  } else if (topic == "edilkamin/322707E4/relax/set") {
    memcpy(btCmd, h.setRelaxStatus, 6);
    if (msg == "ON") {
      btCmd[4] = 1;
      btCmd[5] = 1;
    } else if (msg == "OFF") {
      btCmd[4] = 0;
      btCmd[5] = 0;
    }
    queueBtCommand(Helper::SET_RELAX_STATUS, btCmd);
  } else if (topic == "edilkamin/322707E4/airkare/set") {
  } else if (topic == "edilkamin/322707E4/chrono_mode/set") {
    memcpy(btCmd, h.setOnOffChrono, 6);
    if (msg == "ON")
      btCmd[5] = 1;
    else if (msg == "OFF")
      btCmd[5] = 0;
    queueBtCommand(Helper::SET_ON_OFF_CHRONO, btCmd);
  } else if (topic == "edilkamin/322707E4/standby/set") {
    memcpy(btCmd, h.setStandbyStatus, 6);
    if (msg == "ON") {
      btCmd[4] = 1;
      btCmd[5] = 1;
    } else if (msg == "OFF") {
      btCmd[4] = 0;
      btCmd[5] = 0;
    }
    queueBtCommand(Helper::SET_STANDBY_STATUS, btCmd);
  } else if (topic == "edilkamin/322707E4/fan2_mode/set") { // akoonet
    if (!fan23Known) {
      debugln(F("Fan 2: ecriture refusee (registre 1322 pas encore lu)"));
    } else {
      int level = -1;
      if (msg == "Arrêt")
        level = 0; // akoonet-7
      else if (msg == "20%")
        level = 1;
      else if (msg == "40%")
        level = 2;
      else if (msg == "60%")
        level = 3;
      else if (msg == "80%")
        level = 4;
      else if (msg == "100%")
        level = 5;
      else if (msg == "Auto")
        level = 6;
      if (level >= 0) {
        memcpy(btCmd, h.setFan2, 6);
        btCmd[4] = currentFan23HiByte; // octet haut conserve tel que lu
        btCmd[5] = (byte)level;        // octet bas = ventilateur 2 (valide)
        queueBtCommand(Helper::SET_FAN_2, btCmd);
      }
    }
  }
}

// MQTT reconnect
void mqttReconnect() {
  debug(F("Attempting MQTT connection..."));
  debug(F(" Server: "));
  debug(mqtt_server);
  debug(F(" User: "));
  debugln(mqtt_user);
  // akoonet-6 : dernier message (LWT) -> OFFLINE si l'ESP32 disparait
  if (mqttClient.connect(hostname, mqtt_user, mqtt_pass,
                         "edilkamin/322707E4/availability/state", 1, true,
                         "OFFLINE")) {
    msLastMqttConnect = millis(); // Reset watchdog on successful connect
    if (bleEverConnected)
      statePublish("edilkamin/322707E4/availability/state", "ONLINE", true);
    // akoonet-12 : les anciennes versions de la decouverte demandaient a HA de
    // retenir ses ordres ("retain": true). Le serveur les renvoyait a chaque
    // reconnexion de l'ESP32, qui les rejouait sur le poele. On les efface
    // AVANT de s'abonner pour ne rien rejouer.
    const char *setTopics[] = {
        "edilkamin/322707E4/fan_mode/set", "edilkamin/322707E4/hvac_mode/set",
        "edilkamin/322707E4/preset_mode/set",
        "edilkamin/322707E4/target_temperature/set",
        "edilkamin/322707E4/relax/set", "edilkamin/322707E4/automatic_mode/set",
        "edilkamin/322707E4/chrono_mode/set", "edilkamin/322707E4/standby/set",
        "edilkamin/322707E4/bluetooth/set", "edilkamin/322707E4/fan2_mode/set",
        "edilkamin/322707E4/web_password/set", "edilkamin/322707E4/ota/set"};
    for (const char *t : setTopics)
      mqttClient.publish(t, "", true);
    debugln(F("Connected. Subscripting to topics..."));
    mqttClient.subscribe("homeassistant/status");
    // akoonet-13 : HA est suppose en ligne a la (re)connexion ; s'il est
    // absent, son message "offline" (dernier message MQTT) arrivera
    haOnline = true;
    msHaOffline = 0;
    mqttClient.subscribe("edilkamin/322707E4/schedule");
    mqttClient.subscribe("edilkamin/322707E4/fan_mode/set", true);
    mqttClient.subscribe("edilkamin/322707E4/hvac_mode/set", true);
    mqttClient.subscribe("edilkamin/322707E4/preset_mode/set", true);
    mqttClient.subscribe("edilkamin/322707E4/target_temperature/set", true);
    mqttClient.subscribe("edilkamin/322707E4/relax/set", true);
    mqttClient.subscribe("edilkamin/322707E4/automatic_mode/set", true);
    // mqttClient.subscribe("edilkamin/322707E4/airkare/set");
    mqttClient.subscribe("edilkamin/322707E4/chrono_mode/set", true);
    mqttClient.subscribe("edilkamin/322707E4/standby/set", true);
    mqttClient.subscribe("edilkamin/322707E4/bluetooth/set", true);
    // akoonet
    mqttClient.subscribe("edilkamin/322707E4/fan2_mode/set", true);
    mqttClient.subscribe("edilkamin/322707E4/web_password/set", true);
    mqttClient.subscribe("edilkamin/322707E4/ota/set", true);

    debugln("Publishing Autodiscover Config to HA...");
    mqttClient.publish("homeassistant/climate/edilkamin_322707E4/config",
                       h.jsonAutodiscover, true);
    mqttClient.publish(
        "homeassistant/switch/edilkamin_322707E4_automatic_mode/config",
        h.jsonAutodiscoverAutomaticMode, true);
    mqttClient.publish("homeassistant/switch/edilkamin_322707E4_relax/config",
                       h.jsonAutodiscoverRelax, true);
    // mqttClient.publish("homeassistant/switch/edilkamin_322707E4_airkare/config",
    // h.jsonAutodiscoverAirkare);
    mqttClient.publish(
        "homeassistant/switch/edilkamin_322707E4_chrono_mode/config",
        h.jsonAutodiscoverCronoMode, true);
    mqttClient.publish("homeassistant/switch/edilkamin_322707E4_standby/config",
                       h.jsonAutodiscoverStandbyMode, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_status/config",
                       h.jsonAutodiscoverStatus, true);
    mqttClient.publish(
        "homeassistant/switch/edilkamin_322707E4_bluetooth/config",
        h.jsonAutodiscoverBluetooth, true);
    mqttClient.publish(
        "homeassistant/sensor/edilkamin_322707E4_thermocouple_temp/config",
        h.jsonAutodiscoverThermocouple, true);
    mqttClient.publish(
        "homeassistant/sensor/edilkamin_322707E4_pellet_level/config",
        h.jsonAutodiscoverPelletLevel, true);
    // akoonet
    mqttClient.publish("homeassistant/select/edilkamin_322707E4_fan2/config",
                       h.jsonAutodiscoverFan2, true);
    // akoonet-3 : suppression des entites de diagnostic et du verrou
    // (message vide retenu = HA retire l'entite)
    const char *removed[] = {
        "homeassistant/switch/edilkamin_322707E4_fan2_write/config",
        "homeassistant/sensor/edilkamin_322707E4_fan23_raw/config",
        "homeassistant/sensor/edilkamin_322707E4_number_fan/config",
        "homeassistant/text/edilkamin_322707E4_debug_read/config",
        "homeassistant/sensor/edilkamin_322707E4_debug_response/config",
        "edilkamin/322707E4/fan2_write/state",
        "edilkamin/322707E4/fan23_raw/state",
        "edilkamin/322707E4/number_fan/state",
        "edilkamin/322707E4/debug_read/state"};
    for (const char *t : removed)
      mqttClient.publish(t, "", true);
    // akoonet-4
    mqttClient.publish("homeassistant/binary_sensor/edilkamin_322707E4_alarm/config",
                       h.jsonAutodiscoverAlarm, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_alarm_code/config",
                       h.jsonAutodiscoverAlarmCode, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_total_alarms/config",
                       h.jsonAutodiscoverTotalAlarms, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_pellet_remaining/config",
                       h.jsonAutodiscoverPelletRemaining, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_counters_raw/config",
                       h.jsonAutodiscoverCountersRaw, true);
    // akoonet-8
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_alarm_label/config",
                       h.jsonAutodiscoverAlarmLabel, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_ignitions/config",
                       h.jsonAutodiscoverIgnitions, true);
    // akoonet-11
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_real_power/config",
                       h.jsonAutodiscoverRealPower, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_real_fan1/config",
                       h.jsonAutodiscoverRealFan1, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_real_fan2/config",
                       h.jsonAutodiscoverRealFan2, true);
    // akoonet-5
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_machine_power_raw/config",
                       h.jsonAutodiscoverMachinePowerRaw, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_machine_fan23_raw/config",
                       h.jsonAutodiscoverMachineFan23Raw, true);
    // akoonet-12 : diagnostic
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_diag_uptime/config",
                       h.jsonAutodiscoverDiagUptime, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_diag_reset/config",
                       h.jsonAutodiscoverDiagReset, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_diag_heap_min/config",
                       h.jsonAutodiscoverDiagHeap, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_diag_rssi/config",
                       h.jsonAutodiscoverDiagRssi, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_diag_writes_ok/config",
                       h.jsonAutodiscoverDiagWritesOk, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_diag_writes_fixed/config",
                       h.jsonAutodiscoverDiagWritesFixed, true);
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_diag_writes_failed/config",
                       h.jsonAutodiscoverDiagWritesFailed, true);
    // akoonet-13
    mqttClient.publish("homeassistant/sensor/edilkamin_322707E4_diag_fallback/config",
                       h.jsonAutodiscoverDiagFallback, true);
    publishWebDiscovery();
    msLastDiag = 0; // diagnostic publie au prochain tour
  } else {
    debug(F("failed, rc="));
    debug(mqttClient.state());
  }
  //}
}

static uint8_t btDataBuffer[32];

static void bleNotifyCallback(BLERemoteCharacteristic *pBLERemoteCharacteristic,
                              uint8_t *pData, size_t length, bool isNotify) {
  memcpy(btDataBuffer, pData, min(length, (size_t)32));
  btResponse = true;
  btData = btDataBuffer;
}

class MyClientCallback : public BLEClientCallbacks {
  void onConnect(BLEClient *pclient) {}

  void onDisconnect(BLEClient *pclient) {
    bleConnected = false;
    debugln();
    debugln(F("BLE disconnected..."));
  }
};

static MyClientCallback myClientCallback;

bool connectToServer() {
  debug(F("Forming a connection to "));
  debugln(myDevice->getAddress().toString().c_str());

  if (pClient == nullptr) {
    pClient = BLEDevice::createClient();
    debugln(F(" - Created client"));
    pClient->setClientCallbacks(&myClientCallback);
  }

  // Connect to the remote BLE Server.
  if (!pClient->connect(myDevice)) {
    debugln(F(" - Failed to connect to server"));
    return false;
  }
  debugln(F(" - Connected to server"));

  // Obtain a reference to the service we are after in the remote BLE server.
  BLERemoteService *pRemoteService = pClient->getService(serviceUUID);
  if (pRemoteService == nullptr) {
    debug(F("Failed to find our service UUID: "));
    debugln(serviceUUID.toString().c_str());
    pClient->disconnect();
    return false;
  }
  debugln(F(" - Found our service"));

  // Obtain a reference to the characteristic in the service of the remote BLE
  // server.
  pRemoteCharacteristicWrite = pRemoteService->getCharacteristic(charUUIDWrite);
  pRemoteCharacteristicRead = pRemoteService->getCharacteristic(charUUIDRead);
  if (pRemoteCharacteristicWrite == nullptr ||
      pRemoteCharacteristicRead == nullptr) {
    debug(F("Failed to find our characteristic UUID: "));
    // debugln(charUUIDWrite.toString().c_str());
    pClient->disconnect();
    return false;
  }
  debugln(F(" - Found our characteristic"));

  if (pRemoteCharacteristicRead->canNotify()) {
    pRemoteCharacteristicRead->subscribe(true, bleNotifyCallback, false);
  }

  bleConnected = true;
  bleEverConnected = true;
  debugln(F("Publishing Online-state to HA..."));
  statePublish("edilkamin/322707E4/availability/state", "ONLINE", true);
  return true;
}

/**
 * Scan for BLE servers and find the first one that advertises the service we
 * are looking for.
 */
class MyAdvertisedDeviceCallbacks : public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice *advertisedDevice) {
    debug(F("BLE Advertised Device found: "));
    debugln(advertisedDevice->toString().c_str());

    if (advertisedDevice->haveServiceUUID() &&
        advertisedDevice->isAdvertisingService(serviceUUID)) {
      BLEDevice::getScan()->stop();
      myDevice = advertisedDevice; /** Just save the reference now, no need to
                                      copy the object */
      bleDoConnect = true;
      bleDoScan = true;
    }
  }
};

void setup() {
  Serial.begin(115200);

  // Check if Boot Button (GPIO 0) is pressed for factory reset
  pinMode(0, INPUT_PULLUP);
  // Wait to ensure it's a deliberate press (simple debounce/hold check)
  if (digitalRead(0) == LOW) {
    delay(500); // Wait 500ms
    if (digitalRead(0) == LOW) {
      Serial.println("Factory Reset initiated...");

      // Mount FS to delete config
      if (LittleFS.begin(true)) {
        if (LittleFS.exists("/config.json")) {
          LittleFS.remove("/config.json");
          Serial.println("Deleted config.json");
        }
        LittleFS.end();
      }

      Preferences pr; // 2026.11.2 : reglages en NVS
      if (pr.begin("edk", false)) {
        pr.clear();
        pr.end();
      }
      WiFiManager wm;
      wm.resetSettings();
      Serial.println("WiFiManager settings reset");

      Serial.println("Restarting...");
      delay(1000);
      ESP.restart();
    }
  }

  // Mount LittleFS
  bool nvsConfig = loadNvsConfig(); // 2026.11.2
  if (LittleFS.begin(true)) {
    Serial.println("mounted file system");
    if (!nvsConfig && LittleFS.exists("/config.json")) {
      // file exists, reading and loading
      Serial.println("reading config file");
      File configFile = LittleFS.open("/config.json", "r");
      if (configFile) {
        Serial.println("opened config file");
        JsonDocument json;
        DeserializationError error = deserializeJson(json, configFile);
        if (!error) {
          Serial.println("\nparsed json");
          strcpy(mqtt_server, json["mqtt_server"]);
          strcpy(mqtt_port, json["mqtt_port"]);
          strcpy(mqtt_user, json["mqtt_user"]);
          strcpy(mqtt_pass, json["mqtt_pass"]);
          strcpy(ntp_server, json["ntp_server"]);
          strcpy(ntp_offset, json["ntp_offset"]);
          strlcpy(web_pass, json["web_pass"] | "", sizeof(web_pass));
          saveAllConfig(); // 2026.11.2 : reprise de l'ancien fichier dans la zone NVS
        } else {
          Serial.println("failed to load json config");
        }
        configFile.close();
      }
    }
  } else {
    Serial.println("failed to mount FS");
  }

  WiFiManagerParameter custom_mqtt_server("server", "mqtt server", mqtt_server,
                                          40);
  WiFiManagerParameter custom_mqtt_port("port", "mqtt port", mqtt_port, 6);
  WiFiManagerParameter custom_mqtt_user("user", "mqtt user", mqtt_user, 32);
  WiFiManagerParameter custom_mqtt_pass("pass", "mqtt pass", mqtt_pass, 32);
  WiFiManagerParameter custom_ntp_server("ntp", "ntp server", ntp_server, 40);
  WiFiManagerParameter custom_ntp_offset("ntp_offset", "ntp offset", ntp_offset,
                                         6);
  WiFiManagerParameter custom_web_pass("web_pass", "mot de passe page web (vide = desactivee)",
                                       web_pass, 32);

  WiFiManager wifiManager;

  wifiManager.setSaveConfigCallback(saveConfigCallback);
  wifiManager.addParameter(&custom_mqtt_server);
  wifiManager.addParameter(&custom_mqtt_port);
  wifiManager.addParameter(&custom_mqtt_user);
  wifiManager.addParameter(&custom_mqtt_pass);
  wifiManager.addParameter(&custom_ntp_server);
  wifiManager.addParameter(&custom_ntp_offset);
  wifiManager.addParameter(&custom_web_pass);

  wifiManager.setHostname(hostname);
  wifiManager.setTitle("Configuration");

  // akoonet-13 : apres une coupure de courant, la box peut demarrer apres
  // l'ESP32 ; sans delai, le portail de configuration restait ouvert pour
  // toujours. Au bout de 3 min sans configuration, on redemarre et on reessaie.
  wifiManager.setConfigPortalTimeout(180);
  // 2026.11.2 : sans serveur MQTT (premier demarrage, ou reglages perdus alors que
  // le Wi-Fi est encore connu), le portail Edilkamin_BT_AP s'ouvre quand meme
  bool portalOk;
  if (mqtt_server[0]) {
    portalOk = wifiManager.autoConnect("Edilkamin_BT_AP");
  } else {
    // Reglages MQTT a saisir : page « Setup » (parametres seuls, le Wi-Fi connu est
    // garde), page « Configure WiFi » si le Wi-Fi est aussi a saisir
    static bool paramsSaved = false;
    wifiManager.setParamsPage(true);
    std::vector<const char *> menu = {"param", "wifi", "exit"};
    wifiManager.setMenu(menu);
    wifiManager.setSaveParamsCallback([]() {
      shouldSaveConfig = true;
      paramsSaved = true;
    });
    wifiManager.setConfigPortalBlocking(false);
    wifiManager.startConfigPortal("Edilkamin_BT_AP");
    unsigned long t0 = millis();
    while (!paramsSaved && millis() - t0 < 600000UL) {
      if (wifiManager.process())
        break; // Wi-Fi saisi et connecte
      delay(10);
    }
    if (paramsSaved)
      delay(1500); // laisser la page de confirmation s'afficher
    wifiManager.stopConfigPortal();
    if (WiFi.status() != WL_CONNECTED) {
      WiFi.mode(WIFI_STA);
      WiFi.begin();
      for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++)
        delay(500);
    }
    portalOk = WiFi.status() == WL_CONNECTED && (paramsSaved || shouldSaveConfig);
  }
  if (!portalOk) {
    Serial.println("failed to connect and hit timeout");
    delay(3000);
    ESP.restart();
    delay(5000);
  }

  Serial.println("connected.");

  strcpy(mqtt_server, custom_mqtt_server.getValue());
  strcpy(mqtt_port, custom_mqtt_port.getValue());
  strcpy(mqtt_user, custom_mqtt_user.getValue());
  strcpy(mqtt_pass, custom_mqtt_pass.getValue());
  strcpy(ntp_server, custom_ntp_server.getValue());
  strcpy(ntp_offset, custom_ntp_offset.getValue());
  if (shouldSaveConfig)
    strlcpy(web_pass, custom_web_pass.getValue(), sizeof(web_pass));

  if (shouldSaveConfig) {
    Serial.println("saving config");
    saveAllConfig(); // 2026.11.2 : zone NVS
    Serial.println("config saved");
  }

  // akoonet-13 : heure de Paris avec changement d'heure automatique (le
  // decalage fixe ntp_offset n'est plus utilise ; l'horodatage des trames
  // Bluetooth reste en temps UNIX, independant du fuseau)
  configTzTime(TZ_PARIS, ntp_server);
  loadScheduleFile();
  TelnetStream.begin();
  webSetup(); // 2026.11.2 : page web
  mqttClient.setServer(mqtt_server, atoi(mqtt_port));
  mqttClient.setBufferSize(2048);
  mqttClient.setCallback(mqttCallback);
  msLastMqttConnect = millis(); // Reset MQTT watchdog timer
  msLastBleConnect = millis();
  BLEDevice::init("");
  BLEScan *pBLEScan = BLEDevice::getScan();
  pBLEScan->setAdvertisedDeviceCallbacks(new MyAdvertisedDeviceCallbacks());
  pBLEScan->setInterval(1349);
  pBLEScan->setWindow(449);
  pBLEScan->setActiveScan(true);
  pBLEScan->start(5, false);
}

void loop() {
  currentMillis = millis();
  web.handleClient(); // 2026.11.2 : page web
  if (otaPending) // 2026.11.2 : mise a jour demandee par Home Assistant
    otaRun();

  // Telnet-Terminal
  switch (TelnetStream.read()) {
  case 'c':
    debugln("Bye...");
    TelnetStream.flush();
    TelnetStream.stop();
    break;
  }

  // BLE Watchdog - Restart ESP if no connect for 5min
  if (!bleConnected) {
    if (currentMillis - msLastBleConnect >= bleConnectTimeout) {
      debugln(F("BLE not connected watchdog triggered - ESP Restart..."));
      ESP.restart();
    }
  } else {
    msLastBleConnect = currentMillis;
  }

  // akoonet-13 : plus de redemarrage quand le serveur MQTT est injoignable
  // (Mosquitto s'arrete avec Home Assistant) : l'ESP32 continue de piloter le
  // poele et retente la connexion toutes les 15 s sans bloquer le Bluetooth.
  if (!mqttClient.loop() || !mqttClient.connected()) {
    if (msLastMqttAttempt == 0 || currentMillis - msLastMqttAttempt >= 15000) {
      msLastMqttAttempt = currentMillis | 1;
      mqttReconnect();
    }
  } else {
    msLastMqttConnect = currentMillis;
  }

  // akoonet-13 : planning de secours, verifie toutes les 20 s
  if (currentMillis - msLastSchedCheck >= 20000) {
    msLastSchedCheck = currentMillis;
    checkFallback();
  }

  // akoonet-12 : diagnostic toutes les minutes (et des la connexion MQTT)
  if (mqttClient.connected() &&
      (msLastDiag == 0 || currentMillis - msLastDiag >= diagInterval)) {
    publishDiag();
    msLastDiag = currentMillis ? currentMillis : 1;
  }
  // 2026.11.3 : duree des connexions et occupation sur 15 min
  if (bleWindowStart == 0)
    bleWindowStart = currentMillis ? currentMillis : 1;
  if (bleConnected && !blePrev) {
    bleSessionStart = currentMillis;
  } else if (!bleConnected && blePrev) {
    bleLastSessionMs = currentMillis - bleSessionStart;
    bleOnMsWindow += currentMillis - max(bleSessionStart, bleWindowStart);
    char v[16];
    snprintf(v, sizeof(v), "%.1f", bleLastSessionMs / 1000.0);
    statePublish("edilkamin/322707E4/ble_session/state", v, true);
  }
  blePrev = bleConnected;
  if (currentMillis - bleWindowStart >= bleWindowMs) {
    unsigned long on = bleOnMsWindow + (bleConnected ? currentMillis - max(bleSessionStart, bleWindowStart) : 0);
    bleOccupancyPct = (int)((on * 100UL + (currentMillis - bleWindowStart) / 2) / (currentMillis - bleWindowStart));
    bleOnMsWindow = 0;
    bleWindowStart = currentMillis;
    char v[8];
    snprintf(v, sizeof(v), "%d", bleOccupancyPct);
    statePublish("edilkamin/322707E4/ble_occupancy/state", v, true);
  }

  // 2026.11.2 : lecture de l'horloge du poele toutes les 10 min
  if (bleConnected && (msLastClockRead == 0 || currentMillis - msLastClockRead >= clockReadInterval)) {
    msLastClockRead = currentMillis ? currentMillis : 1;
    for (uint8_t k = 0; k < 4; k++) {
      byte c[6] = {1, 3, 3, (byte)(22 + k), 0, 1};
      queueBtCommand(Helper::READ_DATE_TIME, c);
    }
  }

  if (bleDoConnect == true) {
    if (connectToServer()) {
      debugln(F("We are now connected to the BLE Server."));
      statePublish("edilkamin/322707E4/bluetooth/state", "ON", true);
    } else
      debugln(F("Failed to connect to the MQTT-Server; there is nothing more "
                "we will do."));
    bleDoConnect = false;
  }

  if (!doBtConnect && bleConnected) {
    if (pClient->isConnected()) {
      pClient->disconnect();
      // statePublish("edilkamin/322707E4/availability/state",
      // "OFFLINE", true);
      statePublish("edilkamin/322707E4/bluetooth/state", "OFF", true);
    }
  } else if (!bleConnected && doBtConnect) {
    BLEDevice::getScan()->start(5, false);
    statePublish("edilkamin/322707E4/bluetooth/state", "ON", true);
    status = START;
  }

  switch (status) {
  case START:
    status = CHECK_BT_WRITE_QUEUE;
    break;
  case DO_NEXT_QUERY:
    if (currentMillis - msLastQuery >= queryInterval) {
      msLastQuery = currentMillis;
      nextQuery();
      status = CHECK_BT_WRITE_QUEUE;
    }
    break;
  case CHECK_BT_WRITE_QUEUE:
    if (writeQueueHasElements())
      status = BT_CONNECT_CHECK;
    else
      status = BT_CHECK_ON_OFF_TIMES;
    break;
  case BT_CHECK_ON_OFF_TIMES:
    // 2026.11.3 : deconnexion des que toutes les valeurs ont ete relues
    // (file d'ecriture vide), ou au plus tard apres bleOnTime
    if (bleConnected && (cycleQueries >= queryQueueElements ||
                         currentMillis - bleLastConnect >= bleOnTime)) {
      doBtConnect = false;
      bleLastSwitchOff = currentMillis;
      cycleQueries = 0;
      queryIndex = 0; // la temperature sera relue en premier au prochain reveil
      status = START;
    } else if (bleConnected && !doBtConnect) {
      status = START; // deconnexion en cours : rien a envoyer
    } else if (bleConnected) {
      status = DO_NEXT_QUERY;
    } else if (!bleConnected && currentMillis - bleLastSwitchOff >= bleOffTime) {
      debugln(F("Bluetooth wake up..."));
      status = DO_NEXT_QUERY;
    } else if (!bleConnected) {
      status = START;
    }
    break;
  case BT_CONNECT_CHECK:
    if (bleConnected && doBtConnect)
      status = BT_WRITE_REQUEST;
    else if (bleConnected) {
      // 2026.11.3 : attendre la fin de la deconnexion, puis reconnecter
      if (pClient == nullptr || !pClient->isConnected())
        bleConnected = false; // rappel de deconnexion manque
      status = BT_CONNECT_CHECK;
    }
    else {
      status = BT_CONNECT_CHECK;
      doBtConnect = true;
      bleLastConnect = currentMillis;
    }
    break;
  case BT_WRITE_REQUEST:
    btResponse = false;
    btRetryCount = 0;
    writeBtData();
    writeTimestamp = currentMillis;
    status = AWAIT_BT_RESPONSE;
    break;
  case AWAIT_BT_RESPONSE:
    if (btResponse) {
      status = PROCESSING_BT_RESPONSE;
    } else if (currentMillis - writeTimestamp >= responseTimeout) {
      if (btRetryCount < btMaxRetries) {
        btRetryCount++;
        debug(F("Bluetooth Response Timeout, retry "));
        debug(btRetryCount);
        debug(F("/"));
        debugln(btMaxRetries);
        btResponse = false;
        pRemoteCharacteristicWrite->writeValue(lastBtPacket, 32);
        writeTimestamp = currentMillis;
      } else {
        debug(F("Bluetooth Response Timeout for cmd "));
        debugln(currentOp);
        bleTimeouts++;
        // akoonet-11 : une ecriture sans reponse est remise une fois en file,
        // sauf si une commande plus recente vise deja le meme registre
        if (currentCmd[1] == 6 && currentTries == 0) {
          bool newer = false;
          for (uint8_t i = 0; i < btWriteQueueLength; i++)
            if (btWriteQueue[i].name != Helper::NO_CMD &&
                btWriteQueue[i].cmd[1] == 6 &&
                btWriteQueue[i].cmd[2] == currentCmd[2] &&
                btWriteQueue[i].cmd[3] == currentCmd[3])
              newer = true;
          if (!newer) {
            queueBtCommand(currentOp, currentCmd);
            for (uint8_t i = 0; i < btWriteQueueLength; i++)
              if (btWriteQueue[i].name == currentOp &&
                  memcmp(btWriteQueue[i].cmd, currentCmd, 6) == 0)
                btWriteQueue[i].tries = 1;
            statePublish("edilkamin/322707E4/debug/state",
                               "ecriture sans reponse: remise en file");
          } else {
            statePublish("edilkamin/322707E4/debug/state",
                               "ecriture sans reponse: remplacee par une plus recente");
          }
        } else if (currentCmd[1] == 6) {
          statFailed++; // akoonet-12
          statePublish("edilkamin/322707E4/debug/state",
                             "ecriture sans reponse: abandonnee");
        }
        status = START;
      }
    }
    break;
  case PROCESSING_BT_RESPONSE:
    processBtResponseData(btData);
    status = DONE_PROCESSING_BT_RESPONSE;
    break;
  case DONE_PROCESSING_BT_RESPONSE:
    status = START;
    break;
  };
}
