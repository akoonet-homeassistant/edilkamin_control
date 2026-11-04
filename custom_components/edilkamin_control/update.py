"""Mise à jour à distance du firmware de l'ESP32 (firmware Edilkamin Control 2026.11.2 ou plus récent)."""

from __future__ import annotations

from datetime import timedelta
import json
import logging
from typing import Any
from urllib.parse import urljoin

from homeassistant.components.update import UpdateDeviceClass, UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import CONF_FIRMWARE_URL, CONF_MQTT_TOPIC, FIRMWARE_MANIFEST_URL
from .entity import EdilkaminEntity

_LOGGER = logging.getLogger(__name__)
CHECK_INTERVAL = timedelta(hours=6)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    ctl = entry.runtime_data
    topic = ctl.ent(CONF_MQTT_TOPIC)
    if topic and topic.endswith("/schedule"):
        async_add_entities([FirmwareUpdate(ctl, topic.rsplit("/", 1)[0])])


def _version_key(v: str | None) -> tuple:
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return ()


class FirmwareUpdate(EdilkaminEntity, UpdateEntity):
    """Firmware de l'ESP32 : version installée lue en MQTT, dernière version lue sur le manifeste."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS

    def __init__(self, ctl, base: str) -> None:
        super().__init__(ctl, "firmware")
        self.base = base
        self._ota: dict[str, Any] = {}
        self._manifest: dict[str, Any] = {}
        self._manifest_url = ctl.cfg.get(CONF_FIRMWARE_URL) or FIRMWARE_MANIFEST_URL

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        from homeassistant.components import mqtt  # noqa: PLC0415

        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            return

        @callback
        def _on_state(msg) -> None:
            try:
                self._ota = json.loads(msg.payload)
            except (TypeError, ValueError):
                return
            self.async_write_ha_state()

        self.async_on_remove(await mqtt.async_subscribe(self.hass, f"{self.base}/ota/state", _on_state))
        self.async_on_remove(async_track_time_interval(self.hass, self._check, CHECK_INTERVAL))
        self.hass.async_create_task(self._check())

    async def _check(self, _now=None) -> None:
        await self._fetch_manifest()
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """« Rechercher les mises à jour » (homeassistant.update_entity) : relit le manifeste."""
        await self._fetch_manifest()

    async def _fetch_manifest(self) -> None:
        try:
            resp = await async_get_clientsession(self.hass).get(self._manifest_url, timeout=20)
            resp.raise_for_status()
            data = json.loads(await resp.text())
            if data.get("version") and data.get("url") and len(str(data.get("md5", ""))) == 32:
                data["url"] = urljoin(self._manifest_url, data["url"])
                self._manifest = data
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Manifeste du firmware illisible (%s) : %s", self._manifest_url, err)

    @property
    def available(self) -> bool:
        return bool(self._ota.get("version"))  # firmware sans mise à jour à distance : entité indisponible

    @property
    def installed_version(self) -> str | None:
        return self._ota.get("version")

    @property
    def latest_version(self) -> str | None:
        latest = self._manifest.get("version")
        if not latest or _version_key(latest) < _version_key(self.installed_version):
            return self.installed_version
        return latest

    @property
    def title(self) -> str:
        return "Firmware Edilkamin Control (ESP32)"

    @property
    def release_url(self) -> str | None:
        return self._manifest.get("release_url")

    @property
    def release_summary(self) -> str | None:
        return self._manifest.get("summary")

    @property
    def in_progress(self) -> bool:
        return self._ota.get("state") == "installation"

    @property
    def update_percentage(self) -> int | None:
        return int(self._ota.get("progress", 0)) if self.in_progress else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"esp32_state": self._ota.get("state"), "esp32_message": self._ota.get("message"),
                "manifest_url": self._manifest_url}

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        from homeassistant.components import mqtt  # noqa: PLC0415

        if not self._manifest:
            await self._check()
        if not self._manifest:
            raise RuntimeError("Manifeste du firmware introuvable")
        payload = json.dumps({"url": self._manifest["url"], "md5": self._manifest["md5"].lower(),
                              "version": self._manifest["version"]})
        self._ota = {**self._ota, "state": "installation", "progress": 0}
        self.async_write_ha_state()
        await mqtt.async_publish(self.hass, f"{self.base}/ota/set", payload, qos=1, retain=False)
