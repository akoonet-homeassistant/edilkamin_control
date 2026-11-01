"""Début et fin des programmations."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import F_END, F_START
from .entity import ProfileEntity, profile_ids


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    ctl = entry.runtime_data
    ents = []
    for pid in profile_ids(ctl):
        ents.append(ProfileTime(ctl, pid, "start", F_START, "mdi:clock-start"))
        ents.append(ProfileTime(ctl, pid, "end", F_END, "mdi:clock-end"))
    async_add_entities(ents)


class ProfileTime(ProfileEntity, TimeEntity):
    def __init__(self, ctl, pid: str, key: str, field: str, icon: str) -> None:
        super().__init__(ctl, pid, key, field)
        self._attr_icon = icon

    @property
    def native_value(self) -> time | None:
        p = self.profile
        if not p:
            return None
        h, m = p[self.field].split(":")[:2]
        return time(int(h), int(m))

    async def async_set_value(self, value: time) -> None:
        await self.set_value(f"{value.hour:02d}:{value.minute:02d}")
