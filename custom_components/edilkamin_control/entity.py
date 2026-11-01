"""Entités de base Edilkamin Control."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, F_DAYS, F_ID, F_NAME, SIGNAL_UPDATE, VERSION
from .controller import EdilkaminController


class EdilkaminEntity(Entity):
    """Entité globale de l'intégration."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, ctl: EdilkaminController, key: str) -> None:
        self.ctl = ctl
        self._attr_translation_key = key
        self._attr_unique_id = f"{ctl.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ctl.entry.entry_id)},
            name=ctl.entry.title,
            manufacturer="akoonet-homeassistant",
            model="Edilkamin Control",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(
            self.hass, SIGNAL_UPDATE.format(self.ctl.entry.entry_id), self.async_write_ha_state))


class ProfileEntity(EdilkaminEntity):
    """Entité d'un champ d'une programmation (attribut « profile » = position dans la liste)."""

    def __init__(self, ctl: EdilkaminController, pid: str, key: str, field: str) -> None:
        super().__init__(ctl, f"profile_{key}")
        self.pid = pid
        self.field = field
        self._attr_unique_id = f"{ctl.entry.entry_id}_{pid}_{key}"

    @property
    def profile(self) -> dict | None:
        return self.ctl.by_id(self.pid)

    @property
    def available(self) -> bool:
        return self.profile is not None

    @property
    def translation_placeholders(self) -> dict[str, str]:  # nom de la programmation dans le nom
        p = self.profile
        return {"profile": p[F_NAME] if p else self.pid}

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        i = self.ctl.index_of(self.pid)
        attrs: dict[str, Any] = {"profile": (i + 1) if i is not None else None, "profile_id": self.pid}
        if self.field == "active" and self.profile:
            attrs[F_DAYS] = self.profile[F_DAYS]
        return attrs

    async def set_value(self, value: Any) -> None:
        await self.ctl.async_set_field(self.pid, self.field, value)


def profile_ids(ctl: EdilkaminController) -> list[str]:
    return [p[F_ID] for p in ctl.profiles]
