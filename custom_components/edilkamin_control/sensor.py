"""Capteurs : programmation appliquée, prochain changement, réservoir de granulés."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import F_NAME
from .entity import EdilkaminEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    ctl = entry.runtime_data
    ents: list[SensorEntity] = [
        CurrentProfile(ctl),
        NextChange(ctl),
        HoursSensor(ctl, "reservoir_hours", ctl.reservoir_hours, "mdi:timer-sand", True),
        HoursSensor(ctl, "reservoir_average", ctl.reservoir_average, "mdi:chart-bell-curve"),
        HoursSensor(ctl, "reservoir_autonomy", ctl.reservoir_autonomy, "mdi:gauge"),
    ]
    if ctl.cfg.get("pellet_entry"):
        ents.append(HoursSensor(ctl, "stock_autonomy", ctl.stock_autonomy, "mdi:silo"))
    async_add_entities(ents)


class CurrentProfile(EdilkaminEntity, SensorEntity):
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, ctl) -> None:
        super().__init__(ctl, "current_profile")

    @property
    def native_value(self) -> str:
        p = self.ctl.by_id(self.ctl.state.get("current"))
        return p[F_NAME] if p else self.ctl.word("none")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        st = self.ctl.state
        i = self.ctl.index_of(st.get("current"))
        return {
            "profile": (i + 1) if i is not None else None,
            "profile_id": st.get("current"),
            "substitution": st.get("substitution"),
            "occupied": self.ctl.occupied,
            "resync": st.get("resync"),
            "observe": self.ctl.observe,
        }


class NextChange(EdilkaminEntity, SensorEntity):
    _attr_icon = "mdi:clock-fast"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, ctl) -> None:
        super().__init__(ctl, "next_change")

    @property
    def native_value(self) -> datetime | None:
        return self.ctl.next_change


class HoursSensor(EdilkaminEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_suggested_display_precision = 1

    def __init__(self, ctl, key: str, getter, icon: str, measure: bool = False) -> None:
        super().__init__(ctl, key)
        self._getter = getter
        self._attr_icon = icon
        if measure:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        return self._getter()

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._attr_translation_key == "reservoir_average":
            return {"durations": self.ctl.reservoir.get("durations"), "last_load_kg": self.ctl.reservoir.get("last_load")}
        return None
