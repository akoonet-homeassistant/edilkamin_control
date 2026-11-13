"""Assistant de configuration Edilkamin Control."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_BAGS_PER_FILL,
    CONF_CHRONO,
    CONF_CLIMATE,
    CONF_FAN2,
    CONF_FIRMWARE_URL,
    CONF_WINDOW_CLOSE_DELAY,
    CONF_WINDOW_OPEN_DELAY,
    CONF_HOLIDAYS,
    CONF_WINDOWS,
    CONF_IGNITION_LOG,
    CONF_IGNITIONS,
    CONF_STOP_LOG,
    CONF_MQTT_TOPIC,
    CONF_OBSERVE,
    CONF_PELLET_ENTRY,
    CONF_PRESENCE,
    CONF_RELAX,
    CONF_SCHEDULE_FORMAT,
    CONF_STANDBY,
    CONF_STATUS,
    ALARM_SUFFIXES,
    DEVICE_SUFFIXES,
    DOMAIN,
)

PRESENCE_DOMAINS = ["alarm_control_panel", "person", "device_tracker", "zone", "group",
                    "input_boolean", "binary_sensor", "switch"]
NONE = "none"


def detect_siblings(hass: HomeAssistant, climate: str) -> dict[str, str]:
    """Entités du firmware sur le même appareil que le thermostat (statut, ventilation 2…)."""
    reg = er.async_get(hass)
    ent = reg.async_get(climate)
    found: dict[str, str] = {}
    if ent is None or ent.device_id is None:
        return found
    siblings = [e.entity_id for e in er.async_entries_for_device(reg, ent.device_id)]
    for key, (domain, suffixes) in DEVICE_SUFFIXES.items():
        for eid in siblings:
            if eid.startswith(domain + ".") and any(eid.endswith(s) for s in suffixes):
                found[key] = eid
                break
    return found


def detect_alarm(hass: HomeAssistant, climate: str | None) -> tuple[str | None, str | None]:
    """Alarme du firmware (binary_sensor) et son libellé (sensor), sur l'appareil du thermostat."""
    reg = er.async_get(hass)
    ent = reg.async_get(climate) if climate else None
    if ent is None or ent.device_id is None:
        return None, None
    siblings = [e.entity_id for e in er.async_entries_for_device(reg, ent.device_id)]
    out = []
    for key in ("alarm", "alarm_label"):
        domain, suffixes = ALARM_SUFFIXES[key]
        out.append(next((e for e in siblings if e.startswith(domain + ".") and any(e.endswith(x) for x in suffixes)), None))
    return out[0], out[1]


def detect_logs(hass: HomeAssistant) -> dict[str, str]:
    """Historique tenu par une automatisation : input_text « …derniers_allumages » et « …derniers_arrets »."""
    found: dict[str, str] = {}
    for st in hass.states.async_all("input_text"):
        eid = st.entity_id
        if CONF_IGNITION_LOG not in found and eid.endswith("allumages") and "poele" in eid:
            found[CONF_IGNITION_LOG] = eid
        elif CONF_STOP_LOG not in found and eid.endswith("arrets") and "poele" in eid:
            found[CONF_STOP_LOG] = eid
    return found


def detect_reservoir_logs(hass: HomeAssistant) -> dict[str, str]:
    """Suivi de réservoir tenu par une automatisation (vue Poêle), trouvé par le nom des entités."""
    wanted = {
        "hours": ("sensor", "heures_depuis_remplissage"),
        "durations": ("input_text", "durees_reservoirs"),
        "load": ("input_number", "dernier_chargement"),
        "threshold": ("input_number", "seuil_alerte_reservoir"),
    }
    found: dict[str, str] = {}
    for key, (domain, suffix) in wanted.items():
        for st in hass.states.async_all(domain):
            if st.entity_id.endswith(suffix) and "poele" in st.entity_id:
                found[key] = st.entity_id
                break
    return found


def guess_topic(hass: HomeAssistant, climate: str) -> str:
    """Sujet du planning de secours d'après l'identifiant MQTT du thermostat (« 322707E4_… »)."""
    ent = er.async_get(hass).async_get(climate)
    if ent and ent.platform == "mqtt" and ent.unique_id and "_" in ent.unique_id:
        return f"edilkamin/{ent.unique_id.split('_')[0]}/schedule"
    return ""


def pellet_entries(hass: HomeAssistant) -> list[selector.SelectOptionDict]:
    return [selector.SelectOptionDict(value=e.entry_id, label=e.title)
            for e in hass.config_entries.async_entries("suivi_stock_pellet")]


def entities_schema(hass: HomeAssistant, d: dict[str, Any]) -> vol.Schema:
    def ent(domain: str | list[str]) -> selector.EntitySelector:
        return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))

    def opt(key: str) -> vol.Optional:
        return vol.Optional(key, description={"suggested_value": d.get(key)})

    schema: dict[Any, Any] = {
        vol.Required(CONF_STATUS, default=d.get(CONF_STATUS, vol.UNDEFINED)): ent("sensor"),
        vol.Required(CONF_STANDBY, default=d.get(CONF_STANDBY, vol.UNDEFINED)): ent("switch"),
        opt(CONF_FAN2): ent("select"),
        opt(CONF_RELAX): ent("switch"),
        opt(CONF_CHRONO): ent("switch"),
        opt(CONF_IGNITIONS): ent("sensor"),
        opt(CONF_IGNITION_LOG): ent(["input_text", "text"]),
        opt(CONF_STOP_LOG): ent(["input_text", "text"]),
        opt(CONF_PRESENCE): ent(PRESENCE_DOMAINS),
        opt(CONF_MQTT_TOPIC): selector.TextSelector(),
        opt(CONF_FIRMWARE_URL): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.URL)),
        opt(CONF_WINDOWS): selector.EntitySelector(selector.EntitySelectorConfig(
            domain="binary_sensor", device_class=["window", "door", "opening", "garage_door"], multiple=True)),
        vol.Required(CONF_WINDOW_OPEN_DELAY, default=d.get(CONF_WINDOW_OPEN_DELAY, 2)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=60, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.SLIDER)),
        vol.Required(CONF_WINDOW_CLOSE_DELAY, default=d.get(CONF_WINDOW_CLOSE_DELAY, 0)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=60, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.SLIDER)),
        opt(CONF_HOLIDAYS): ent("calendar"),
        vol.Required(CONF_SCHEDULE_FORMAT, default=d.get(CONF_SCHEDULE_FORMAT, "v2")): selector.SelectSelector(
            selector.SelectSelectorConfig(options=["v2", "v1"], translation_key="schedule_format",
                                          mode=selector.SelectSelectorMode.DROPDOWN)),
    }
    pe = pellet_entries(hass)
    if pe:
        schema[vol.Required(CONF_PELLET_ENTRY, default=d.get(CONF_PELLET_ENTRY) or NONE)] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=[selector.SelectOptionDict(value=NONE, label="—"), *pe],
                                          mode=selector.SelectSelectorMode.DROPDOWN))
        schema[vol.Required(CONF_BAGS_PER_FILL, default=d.get(CONF_BAGS_PER_FILL, 1))] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=0.5, max=10, step=0.5, mode=selector.NumberSelectorMode.BOX))
    schema[vol.Required(CONF_OBSERVE, default=d.get(CONF_OBSERVE, False))] = selector.BooleanSelector()
    return vol.Schema(schema)


def clean(user_input: dict[str, Any]) -> dict[str, Any]:
    out = dict(user_input)
    if out.get(CONF_PELLET_ENTRY) == NONE:
        out[CONF_PELLET_ENTRY] = None
    out[CONF_WINDOWS] = list(out.get(CONF_WINDOWS) or [])
    for k in (CONF_FAN2, CONF_RELAX, CONF_CHRONO, CONF_IGNITIONS, CONF_IGNITION_LOG, CONF_STOP_LOG, CONF_PRESENCE, CONF_MQTT_TOPIC, CONF_FIRMWARE_URL, CONF_HOLIDAYS):
        out.setdefault(k, None)
        if out[k] == "":
            out[k] = None
    return out


class EdilkaminControlConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Étape 1 : le thermostat du poêle (firmware ESP32)."""
        if user_input is not None:
            climate = user_input[CONF_CLIMATE]
            await self.async_set_unique_id(climate)
            self._abort_if_unique_id_configured()
            self._data = {CONF_CLIMATE: climate}
            return await self.async_step_entities()
        candidates = [s.entity_id for s in self.hass.states.async_all("climate")]
        # Thermostat proposé : celui dont l'appareil porte les entités du firmware (statut et stand-by)
        default = next((c for c in candidates if {CONF_STATUS, CONF_STANDBY} <= detect_siblings(self.hass, c).keys()),
                       next((c for c in candidates if "edilkamin" in c), candidates[0] if len(candidates) == 1 else vol.UNDEFINED))
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_CLIMATE, default=default): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate"))}),
        )

    async def async_step_entities(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Étape 2 : entités détectées sur l'appareil, présence, planning de secours, granulés."""
        climate = self._data[CONF_CLIMATE]
        if user_input is not None:
            data = {**self._data, **clean(user_input)}
            state = self.hass.states.get(climate)
            title = (state.attributes.get("friendly_name") if state else None) or "Poêle"
            return self.async_create_entry(title=title, data=data)
        defaults = {**detect_siblings(self.hass, climate), **detect_logs(self.hass),
                    CONF_MQTT_TOPIC: guess_topic(self.hass, climate)}
        pe = pellet_entries(self.hass)
        if pe:
            defaults[CONF_PELLET_ENTRY] = pe[0]["value"]
        return self.async_show_form(step_id="entities", data_schema=entities_schema(self.hass, defaults),
                                    description_placeholders={"climate": climate})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EdilkaminControlOptionsFlow()


class EdilkaminControlOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=clean(user_input))
        current = {**self.config_entry.data, **self.config_entry.options}
        for k, v in detect_logs(self.hass).items():
            current[k] = current.get(k) or v
        return self.async_show_form(step_id="init", data_schema=entities_schema(self.hass, current))
