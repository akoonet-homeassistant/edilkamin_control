"""Réservoir bientôt vide (seuil d'heures de chauffe)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import EdilkaminEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([ReservoirLow(entry.runtime_data)])


class ReservoirLow(EdilkaminEntity, BinarySensorEntity):
    _attr_icon = "mdi:grain"

    def __init__(self, ctl) -> None:
        super().__init__(ctl, "reservoir_low")

    @property
    def is_on(self) -> bool:
        return self.ctl.reservoir_low()
