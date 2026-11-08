"""Capteurs : programmation appliquée, prochain changement, réservoir de granulés."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import F_NAME
from .entity import EdilkaminEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    ctl = entry.runtime_data
    ents: list[SensorEntity] = [
        CurrentProfile(ctl),
        NextChange(ctl),
        IgnitionHistory(ctl),
        AlarmHistory(ctl),
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


class IgnitionHistory(EdilkaminEntity, SensorEntity):
    """Dernier allumage ; l'attribut history liste les allumages des 3 derniers jours."""

    _attr_icon = "mdi:fire-circle"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, ctl) -> None:
        super().__init__(ctl, "last_ignition")

    @property
    def native_value(self) -> datetime | None:
        h = self.ctl.ignition_history()
        return dt_util.parse_datetime(h[0]["start"]) if h else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # copie : un arrêt modifie la liste en place, HA ne verrait aucun changement
        return {"history": deepcopy(self.ctl.ignition_history()), "counter": self.ctl.ignitions_entity}


class AlarmHistory(EdilkaminEntity, SensorEntity):
    """Début de la dernière alarme ; l'attribut history liste les 10 dernières (début, fin, libellé)."""

    _attr_icon = "mdi:alert-circle-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, ctl) -> None:
        super().__init__(ctl, "last_alarm")

    @property
    def native_value(self) -> datetime | None:
        h = self.ctl.alarm_history()
        return dt_util.parse_datetime(h[0]["start"]) if h else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"history": deepcopy(self.ctl.alarm_history()), "alarm": self.ctl.alarm_entity}


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
        key = self._attr_translation_key
        if key == "reservoir_average":
            return {"durations": list(self.ctl.reservoir.get("durations") or []), "last_load_kg": self.ctl.reservoir.get("last_load")}
        if key == "reservoir_hours":
            return {"bags_per_fill": self.ctl.cfg.get("bags_per_fill"), "pellet_tracking": bool(self.ctl.pellet_consumed)}
        if key == "stock_autonomy" and self.ctl.pellet_stock:
            s = self.hass.states.get(self.ctl.pellet_stock)
            if s is not None:
                kg = None
                try:
                    kg = float(s.state)
                except (TypeError, ValueError):
                    pass
                return {"stock_bags": s.attributes.get("stock_sacs"), "stock_kg": kg, "stock_entity": self.ctl.pellet_stock}
        return None
