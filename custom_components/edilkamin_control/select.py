"""Menus : programmation forcée et réglages des programmations."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_FAN2, F_ABSENT, F_FAN1, F_FAN2, F_ID, F_MODE, F_POWER, MODES
from .entity import EdilkaminEntity, ProfileEntity, profile_ids


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    ctl = entry.runtime_data
    ents: list[SelectEntity] = [ForcedProfile(ctl)]
    for pid in profile_ids(ctl):
        ents.append(ProfileMode(ctl, pid))
        ents.append(ProfileOption(ctl, pid, "power", F_POWER, "mdi:speedometer", ctl.power_options))
        ents.append(ProfileOption(ctl, pid, "fan1", F_FAN1, "mdi:fan", ctl.fan1_options))
        if ctl.ent(CONF_FAN2):
            ents.append(ProfileOption(ctl, pid, "fan2", F_FAN2, "mdi:fan-chevron-up", ctl.fan2_options))
        if ctl.presence_entities():
            ents.append(ProfileAbsent(ctl, pid))
    async_add_entities(ents)


class ForcedProfile(EdilkaminEntity, SelectEntity):
    """Automatique, ou une programmation appliquée jusqu'au prochain début/fin de plage."""

    _attr_icon = "mdi:calendar-star"

    def __init__(self, ctl) -> None:
        super().__init__(ctl, "forced_profile")

    @property
    def options(self) -> list[str]:
        return [self.ctl.word("auto")] + [self.ctl.label(p[F_ID]) for p in self.ctl.profiles]

    @property
    def current_option(self) -> str:
        f = self.ctl.state.get("forced")
        return self.ctl.label(f) if self.ctl.by_id(f) else self.ctl.word("auto")

    async def async_select_option(self, option: str) -> None:
        await self.ctl.async_set_forced(self.ctl.pid_from_label(option))


class ProfileMode(ProfileEntity, SelectEntity):
    _attr_icon = "mdi:sleep"
    _attr_options = MODES

    def __init__(self, ctl, pid: str) -> None:
        super().__init__(ctl, pid, "mode", F_MODE)

    @property
    def current_option(self) -> str | None:
        p = self.profile
        return p[F_MODE] if p else None

    async def async_select_option(self, option: str) -> None:
        await self.set_value(option)


class ProfileOption(ProfileEntity, SelectEntity):
    """Puissance, ventilation 1 ou 2 : mêmes valeurs que les entités du poêle."""

    def __init__(self, ctl, pid: str, key: str, field: str, icon: str, options) -> None:
        super().__init__(ctl, pid, key, field)
        self._attr_icon = icon
        self._options = options

    @property
    def options(self) -> list[str]:
        opts = list(self._options())
        cur = self.current_option
        if cur and cur not in opts:
            opts.append(cur)
        return opts

    @property
    def current_option(self) -> str | None:
        p = self.profile
        return p.get(self.field) if p else None

    async def async_select_option(self, option: str) -> None:
        await self.set_value(option)


class ProfileAbsent(ProfileEntity, SelectEntity):
    """Programmation appliquée à la place de celle-ci quand la maison est vide."""

    _attr_icon = "mdi:home-export-outline"

    def __init__(self, ctl, pid: str) -> None:
        super().__init__(ctl, pid, "absent", F_ABSENT)

    @property
    def options(self) -> list[str]:
        return [self.ctl.word("no")] + [self.ctl.label(p[F_ID]) for p in self.ctl.profiles if p[F_ID] != self.pid]

    @property
    def current_option(self) -> str | None:
        p = self.profile
        if not p:
            return None
        return self.ctl.label(p[F_ABSENT]) if self.ctl.by_id(p.get(F_ABSENT)) else self.ctl.word("no")

    async def async_select_option(self, option: str) -> None:
        await self.set_value(self.ctl.pid_from_label(option))
