"""Constantes de l'intégration Edilkamin Control."""

from __future__ import annotations

DOMAIN = "edilkamin_control"
VERSION = "2026.11.17"

# Clés de configuration (entrée de configuration / options)
CONF_CLIMATE = "climate"
CONF_STATUS = "status"
CONF_FAN2 = "fan2"
CONF_STANDBY = "standby"
CONF_RELAX = "relax"
CONF_CHRONO = "chrono"
CONF_PRESENCE = "presence"
CONF_MQTT_TOPIC = "mqtt_topic"
CONF_PELLET_ENTRY = "pellet_entry"
CONF_BAGS_PER_FILL = "bags_per_fill"
CONF_OBSERVE = "observe"
CONF_SCHEDULE_FORMAT = "schedule_format"
CONF_IGNITIONS = "ignitions"
CONF_IGNITION_LOG = "ignition_log"  # input_text « jj/mm hh:mm;… » d'une automatisation existante
CONF_STOP_LOG = "stop_log"
CONF_FIRMWARE_URL = "firmware_url"  # manifeste JSON du firmware ESP32 (mise à jour à distance)
CONF_WINDOWS = "windows"  # fenêtres et portes surveillées (binary_sensor)
CONF_WINDOW_OPEN_DELAY = "window_open_delay"  # min d'ouverture avant de couper le poêle (0 à 60)
CONF_WINDOW_CLOSE_DELAY = "window_close_delay"  # min après la fermeture avant de reprendre (0 à 60)
FIRMWARE_MANIFEST_URL = "https://akoonet-homeassistant.github.io/edilkamin_control/webflash/ota.json"

# Entités du firmware recherchées sur le même appareil que le thermostat
DEVICE_SUFFIXES: dict[str, tuple[str, tuple[str, ...]]] = {
    CONF_STATUS: ("sensor", ("_status", "_statut")),
    CONF_FAN2: ("select", ("_ventilation_2", "_fan_2", "_fan2")),
    CONF_STANDBY: ("switch", ("_standby",)),
    CONF_RELAX: ("switch", ("_relax",)),
    CONF_CHRONO: ("switch", ("_chrono",)),
    CONF_IGNITIONS: ("sensor", ("_nombre_d_allumages", "_ignitions")),
}

# Modes d'une programmation
MODE_RUN = "run"
MODE_STANDBY = "standby"
MODES = [MODE_RUN, MODE_STANDBY]

# Statuts du poêle (firmware ESP32)
STATUS_OFF = "Off"
STATUS_OK = "Ok"
STATUS_STOPPING = ("Shutdown", "Extinction")
STATUS_UNAVAILABLE = ("unavailable", "unknown")
# Statuts qui ne comptent pas comme « chauffe » pour le réservoir
STATUS_NOT_BURNING = (STATUS_OFF, *STATUS_STOPPING, *STATUS_UNAVAILABLE, "", None)

# Valeurs par défaut publiées par l'ESP32 à son redémarrage : ignorées par la détection manuelle
ESP_DEFAULT_VALUES = ("low", "none", "None", "")

# Délais (secondes), repris des automatisations validées
APPLY_GUARD = 300  # dérogation / réglage manuel ignorés 5 min après une application
VERIFY_GUARD = 600  # réglage manuel ignoré 10 min après une vérification
VERIFY_DELAY = 240  # vérification 4 min après un changement de plage
ESP_BACK_DELAY = 60  # retour de l'ESP32 : 1 min de stabilité avant resynchronisation
SCHEDULE_DEBOUNCE = 10  # regroupement des modifications avant envoi du planning

MAX_PROFILES = 10  # limite du planning de secours (firmware)
HISTORY_DAYS = 3  # historique des allumages gardé

# Déclencheurs internes de l'application des profils
K_SLOT = "slot"  # début ou fin de plage
K_START = "start"  # démarrage de Home Assistant
K_PLANNING_ON = "planning_on"  # programmation réactivée
K_OVERRIDE_CANCEL = "override_cancel"
K_RELAX_END = "relax_end"
K_EDIT = "edit"
K_FORCED = "forced"
K_PRESENCE = "presence"
K_ESP_BACK = "esp_back"
K_MANUAL_END = "manual_end"
K_WINDOW = "window"  # fenêtre ouverte : poêle coupé
K_WINDOW_END = "window_end"  # fenêtres refermées : reprise
FULL_RESEND = (K_ESP_BACK, K_PLANNING_ON)

# Champs d'une programmation
F_ID = "id"
F_NAME = "name"
F_ACTIVE = "active"
F_START = "start"
F_END = "end"
F_DAYS = "days"
F_SETPOINT = "setpoint"
F_MODE = "mode"
F_POWER = "power"
F_FAN1 = "fan1"
F_FAN2 = "fan2"
F_RELAX = "relax"
F_ABSENT = "absent"
# Champs dont la modification met fin aux réglages manuels si la programmation est en cours
MANUAL_RESET_FIELDS = (F_FAN1, F_FAN2, F_MODE, F_POWER)

ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]

SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"

CARD_URL = f"/{DOMAIN}/edilkamin-control-card.js"
