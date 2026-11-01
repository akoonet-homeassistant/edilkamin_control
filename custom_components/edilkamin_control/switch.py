"""Interrupteurs : programmation, dérogation, réglages manuels, Relax manuel, programmations."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import F_ACTIVE, F_RELAX
from .entity import EdilkaminEntity, ProfileEntity, profile_ids


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    ctl = entry.runtime_data
    ents: list[SwitchEntity] = [
        StateSwitch(ctl, "planning", "planning", ctl.async_set_planning, "mdi:calendar-clock"),
        StateSwitch(ctl, "override", "override", ctl.async_set_override, "mdi:hand-back-right"),
        StateSwitch(ctl, "manual_settings", "manual", ctl.async_set_manual, "mdi:hand-back-right-outline"),
        StateSwitch(ctl, "relax_priority", "relax_manual", ctl.async_set_relax_manual, "mdi:volume-off"),
    ]
    for pid in profile_ids(ctl):
        ents.append(ProfileSwitch(ctl, pid, "active", F_ACTIVE, "mdi:calendar-check"))
        if ctl.ent("relax"):
            ents.append(ProfileSwitch(ctl, pid, "relax", F_RELAX, "mdi:volume-off"))
    async_add_entities(ents)


class StateSwitch(EdilkaminEntity, SwitchEntity):
    def __init__(self, ctl, key: str, state_key: str, setter, icon: str) -> None:
        super().__init__(ctl, key)
        self._key = state_key
        self._setter = setter
        self._attr_icon = icon

    @property
    def is_on(self) -> bool:
        return bool(self.ctl.state.get(self._key))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._key == "override":
            return {"reference": self.ctl.state.get("override_ref")}
        if self._key == "manual":
            nxt = self.ctl.next_change
            return {"until": nxt.isoformat() if nxt else None}
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._setter(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._setter(False)


class ProfileSwitch(ProfileEntity, SwitchEntity):
    def __init__(self, ctl, pid: str, key: str, field: str, icon: str) -> None:
        super().__init__(ctl, pid, key, field)
        self._attr_icon = icon

    @property
    def is_on(self) -> bool:
        p = self.profile
        return bool(p and p[self.field])

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.set_value(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.set_value(False)
