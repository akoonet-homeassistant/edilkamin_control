"""Réservoir bientôt vide (seuil d'heures de chauffe) et coupure fenêtre ouverte."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import EdilkaminEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    ctl = entry.runtime_data
    entities: list[BinarySensorEntity] = [ReservoirLow(ctl)]
    if ctl.windows():
        entities.append(WindowCut(ctl))
    async_add_entities(entities)


class ReservoirLow(EdilkaminEntity, BinarySensorEntity):
    _attr_icon = "mdi:grain"

    def __init__(self, ctl) -> None:
        super().__init__(ctl, "reservoir_low")

    @property
    def is_on(self) -> bool:
        return self.ctl.reservoir_low()


class WindowCut(EdilkaminEntity, BinarySensorEntity):
    """Allumé quand une fenêtre ouverte a coupé le poêle (programmation suspendue)."""

    def __init__(self, ctl) -> None:
        super().__init__(ctl, "window_cut")

    @property
    def is_on(self) -> bool:
        return bool(self.ctl.state.get("window"))

    @property
    def icon(self) -> str:
        return "mdi:window-open-variant" if self.is_on else "mdi:window-closed-variant"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.ctl
        opened = c.open_windows()
        return {
            "open_windows": c.window_names(opened),
            "since": c.state.get("window_since"),
            "cut_at": c.window_cut_at.isoformat() if c.window_cut_at else None,
            "resume_at": c.window_resume_at.isoformat() if c.window_resume_at else None,
            "was_on": bool(c.state.get("window_heat")),
            "manual_override": bool(c.state.get("window_override")),
        }
