"""Bouton « Réservoir rempli »."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import EdilkaminEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([ReservoirFilled(entry.runtime_data)])


class ReservoirFilled(EdilkaminEntity, ButtonEntity):
    _attr_icon = "mdi:basket-fill"

    def __init__(self, ctl) -> None:
        super().__init__(ctl, "reservoir_filled")

    async def async_press(self) -> None:
        await self.ctl.async_press_filled()
