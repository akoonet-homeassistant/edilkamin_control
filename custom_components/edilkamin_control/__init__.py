"""Edilkamin Control : programmation d'un poêle Edilkamin piloté par ESP32 (MQTT)."""

from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CARD_URL,
    DOMAIN,
    F_ABSENT,
    F_ACTIVE,
    F_DAYS,
    F_END,
    F_FAN1,
    F_FAN2,
    F_ID,
    F_MODE,
    F_NAME,
    F_POWER,
    F_RELAX,
    F_SETPOINT,
    F_START,
    MODES,
    VERSION,
)
from .controller import EdilkaminController

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
    Platform.TIME,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_DAYS = vol.All(cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))])
_TIME = vol.Match(r"^\d{1,2}:\d{2}(:\d{2})?$")
_ENTRY = vol.Optional("entry_id")
_PROFILE = vol.All(vol.Coerce(int), vol.Range(min=1))

SCHEMA_ADD = vol.Schema({
    _ENTRY: cv.string,
    vol.Optional(F_NAME): cv.string,
    vol.Optional(F_START): _TIME,
    vol.Optional(F_END): _TIME,
    vol.Optional(F_DAYS): _DAYS,
    vol.Optional(F_SETPOINT): vol.Coerce(float),
    vol.Optional(F_MODE): vol.In(MODES),
    vol.Optional(F_POWER): cv.string,
    vol.Optional(F_FAN1): cv.string,
    vol.Optional(F_FAN2): cv.string,
    vol.Optional(F_RELAX): cv.boolean,
    vol.Optional(F_ACTIVE): cv.boolean,
})
SCHEMA_PROFILE = vol.Schema({_ENTRY: cv.string, vol.Required("profile"): _PROFILE})
SCHEMA_DAYS = vol.Schema({_ENTRY: cv.string, vol.Required("profile"): _PROFILE, vol.Required(F_DAYS): _DAYS})
SCHEMA_MOVE = vol.Schema({_ENTRY: cv.string, vol.Required("profile"): _PROFILE, vol.Required("position"): _PROFILE})
SCHEMA_ENTRY = vol.Schema({_ENTRY: cv.string})

type EdilkaminConfigEntry = ConfigEntry[EdilkaminController]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Carte Lovelace servie par l'intégration et services."""
    await _register_card(hass)
    _register_services(hass)
    return True


async def _register_card(hass: HomeAssistant) -> None:
    # Dossier www servi en /edilkamin_control/ : carte et images des poêles
    path = Path(__file__).parent / "www"
    try:
        from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

        await hass.http.async_register_static_paths([StaticPathConfig(f"/{DOMAIN}", str(path), False)])
    except (ImportError, AttributeError):  # Home Assistant ancien
        hass.http.register_static_path(f"/{DOMAIN}", str(path), False)
    from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415

    try:
        add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    except KeyError:  # interface non chargée (tests)
        _LOGGER.debug("Interface non chargée : carte non déclarée")


def _controller(hass: HomeAssistant, call: ServiceCall) -> EdilkaminController:
    entries = [e for e in hass.config_entries.async_loaded_entries(DOMAIN)] \
        if hasattr(hass.config_entries, "async_loaded_entries") \
        else [e for e in hass.config_entries.async_entries(DOMAIN) if getattr(e, "runtime_data", None)]
    wanted = call.data.get("entry_id")
    for e in entries:
        if wanted in (None, e.entry_id):
            return e.runtime_data
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_entry")


def _profile(ctl: EdilkaminController, n: int) -> dict:
    p = ctl.by_number(n)
    if p is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_profile",
                                     translation_placeholders={"profile": str(n)})
    return p


def _register_services(hass: HomeAssistant) -> None:
    async def add_profile(call: ServiceCall) -> None:
        ctl = _controller(hass, call)
        values = {k: v for k, v in call.data.items() if k != "entry_id"}
        try:
            await ctl.async_add_profile(values)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    async def remove_profile(call: ServiceCall) -> None:
        ctl = _controller(hass, call)
        await ctl.async_remove_profile(_profile(ctl, call.data["profile"])[F_ID])

    async def set_profile_days(call: ServiceCall) -> None:
        ctl = _controller(hass, call)
        await ctl.async_set_field(_profile(ctl, call.data["profile"])[F_ID], F_DAYS, sorted(set(call.data[F_DAYS])))

    async def move_profile(call: ServiceCall) -> None:
        ctl = _controller(hass, call)
        await ctl.async_move_profile(_profile(ctl, call.data["profile"])[F_ID], call.data["position"])

    async def reservoir_filled(call: ServiceCall) -> None:
        _controller(hass, call).reservoir_filled()

    async def publish_schedule(call: ServiceCall) -> None:
        _controller(hass, call).schedule_publish(0)

    hass.services.async_register(DOMAIN, "add_profile", add_profile, SCHEMA_ADD)
    hass.services.async_register(DOMAIN, "remove_profile", remove_profile, SCHEMA_PROFILE)
    hass.services.async_register(DOMAIN, "set_profile_days", set_profile_days, SCHEMA_DAYS)
    hass.services.async_register(DOMAIN, "move_profile", move_profile, SCHEMA_MOVE)
    hass.services.async_register(DOMAIN, "reservoir_filled", reservoir_filled, SCHEMA_ENTRY)
    hass.services.async_register(DOMAIN, "publish_schedule", publish_schedule, SCHEMA_ENTRY)


async def async_setup_entry(hass: HomeAssistant, entry: EdilkaminConfigEntry) -> bool:
    ctl = EdilkaminController(hass, entry)
    await ctl.async_load()
    entry.runtime_data = ctl
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await ctl.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: EdilkaminConfigEntry) -> None:
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EdilkaminConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_stop()
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    from homeassistant.helpers.storage import Store  # noqa: PLC0415

    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()


