"""Consigne des programmations et seuil d'alerte du réservoir."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import F_SETPOINT
from .entity import EdilkaminEntity, ProfileEntity, profile_ids


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    ctl = entry.runtime_data
    lo = float(ctl.climate_attr("min_temp") or 15)
    hi = float(ctl.climate_attr("max_temp") or 30)
    step = float(ctl.climate_attr("target_temp_step") or 0.5)
    ents: list[NumberEntity] = [ProfileSetpoint(ctl, pid, lo, hi, step) for pid in profile_ids(ctl)]
    ents.append(AlertThreshold(ctl))
    async_add_entities(ents)


class ProfileSetpoint(ProfileEntity, NumberEntity):
    _attr_icon = "mdi:thermometer"
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, ctl, pid: str, lo: float, hi: float, step: float) -> None:
        super().__init__(ctl, pid, "setpoint", F_SETPOINT)
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi
        self._attr_native_step = step

    @property
    def native_value(self) -> float | None:
        p = self.profile
        return float(p[F_SETPOINT]) if p else None

    async def async_set_native_value(self, value: float) -> None:
        await self.set_value(float(value))


class AlertThreshold(EdilkaminEntity, NumberEntity):
    _attr_icon = "mdi:timer-alert-outline"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 200
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, ctl) -> None:
        super().__init__(ctl, "reservoir_alert")

    @property
    def native_value(self) -> float:
        return float(self.ctl.state.get("alert_threshold") or 0)

    async def async_set_native_value(self, value: float) -> None:
        await self.ctl.async_set_threshold(value)
