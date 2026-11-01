"""Nom des programmations."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import F_NAME
from .entity import ProfileEntity, profile_ids


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    ctl = entry.runtime_data
    async_add_entities(ProfileName(ctl, pid) for pid in profile_ids(ctl))


class ProfileName(ProfileEntity, TextEntity):
    _attr_icon = "mdi:form-textbox"
    _attr_native_min = 1
    _attr_native_max = 40

    def __init__(self, ctl, pid: str) -> None:
        super().__init__(ctl, pid, "name", F_NAME)

    @property
    def native_value(self) -> str | None:
        p = self.profile
        return p[F_NAME] if p else None

    async def async_set_value(self, value: str) -> None:
        value = value.strip()
        if value:
            await self.set_value(value)
