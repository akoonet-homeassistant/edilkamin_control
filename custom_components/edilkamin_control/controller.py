"""Moteur de programmation Edilkamin Control.

Reprend la logique des automatisations validées en production :
application des profils, dérogation de consigne, réglages manuels, priorité Relax manuelle,
présence (« si absent »), vérification après changement de plage, resynchronisation au retour
de l'ESP32, planning de secours publié en MQTT et suivi du réservoir de granulés.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
import logging
from typing import Any
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_time,
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ALL_DAYS,
    APPLY_GUARD,
    CONF_BAGS_PER_FILL,
    CONF_CHRONO,
    CONF_CLIMATE,
    CONF_FAN2,
    CONF_MQTT_TOPIC,
    CONF_OBSERVE,
    CONF_PELLET_ENTRY,
    CONF_PRESENCE,
    CONF_RELAX,
    CONF_SCHEDULE_FORMAT,
    CONF_STANDBY,
    CONF_STATUS,
    DOMAIN,
    ESP_BACK_DELAY,
    ESP_DEFAULT_VALUES,
    F_ABSENT,
    F_ACTIVE,
    F_DAYS,
    F_END,
    F_FAN1,
    F_FAN2,
    F_ID,
    F_MODE,
    F_NAME,
    F_POWER,
    F_RELAX,
    F_SETPOINT,
    F_START,
    FULL_RESEND,
    K_EDIT,
    K_ESP_BACK,
    K_FORCED,
    K_MANUAL_END,
    K_OVERRIDE_CANCEL,
    K_PLANNING_ON,
    K_PRESENCE,
    K_RELAX_END,
    K_SLOT,
    K_START,
    MANUAL_RESET_FIELDS,
    MAX_PROFILES,
    MODE_RUN,
    MODE_STANDBY,
    SCHEDULE_DEBOUNCE,
    SIGNAL_UPDATE,
    STATUS_NOT_BURNING,
    STATUS_OFF,
    STATUS_STOPPING,
    STATUS_UNAVAILABLE,
    VERIFY_DELAY,
    VERIFY_GUARD,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
AWAY_ALARM_STATES = ("armed_away", "armed_vacation")
HOME_ALARM_STATES = ("disarmed", "armed_home", "armed_night")
_LOCALIZED = {
    "fr": {"auto": "Automatique", "none": "Aucun", "no": "Non", "profile": "Profil", "new": "Nouvelle"},
    "en": {"auto": "Automatic", "none": "None", "no": "No", "profile": "Profile", "new": "New"},
}


def to_minutes(value: str | None) -> int:
    """« HH:MM[:SS] » → minutes depuis minuit."""
    try:
        h, m = str(value).split(":")[:2]
        return (int(h) % 24) * 60 + int(m) % 60
    except (ValueError, AttributeError):
        return 0


def profile_matches(profile: dict, now: datetime) -> bool:
    """La plage de la programmation contient-elle l'instant donné (jours compris) ?

    Début = fin : toute la journée. Plage pouvant passer minuit : la partie après minuit
    appartient au jour du début.
    """
    d, f = to_minutes(profile[F_START]), to_minutes(profile[F_END])
    m = now.hour * 60 + now.minute
    wd = now.weekday()
    days = profile.get(F_DAYS) or ALL_DAYS
    if d == f:
        return wd in days
    if d < f:
        return d <= m < f and wd in days
    if m >= d:
        return wd in days
    if m < f:
        return (wd - 1) % 7 in days
    return False


class EdilkaminController:
    """État et logique d'une entrée Edilkamin Control."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.profiles: list[dict[str, Any]] = []
        self.state: dict[str, Any] = {}
        self.reservoir: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._unsubs: list = []
        self._slot_unsub = None
        self._verify_unsub = None
        self._verify_kind: str | None = None
        self._esp_unsub = None
        self._sched_unsub = None
        self._save_unsub = None
        self.last_apply: datetime | None = None
        self.last_verify: datetime | None = None
        self.current_changed: datetime = dt_util.utcnow()
        self.next_change: datetime | None = None
        self.occupied: bool = True
        self.pellet_stock: str | None = None
        self.pellet_consumed: str | None = None

    # ------------------------------------------------------------------ configuration
    @property
    def cfg(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def ent(self, key: str) -> str | None:
        return self.cfg.get(key) or None

    @property
    def observe(self) -> bool:
        """Mode observation : la programmation calcule et journalise, sans commander le poêle."""
        return bool(self.cfg.get(CONF_OBSERVE, False))

    @property
    def lang(self) -> str:
        return "fr" if (self.hass.config.language or "fr").startswith("fr") else "en"

    def word(self, key: str) -> str:
        return _LOCALIZED[self.lang][key]

    # ------------------------------------------------------------------ persistance
    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.profiles = data.get("profiles") or self._default_profiles()
        self.state = {
            "planning": True,
            "forced": None,
            "override": False,
            "override_ref": None,
            "manual": False,
            "relax_manual": False,
            "resync": False,
            "current": None,
            "substitution": False,
            "alert_threshold": 0.0,
            **data.get("state", {}),
        }
        self.reservoir = {"hours": 0.0, "since": None, "durations": [], "last_load": None, "alerted": False,
                          **data.get("reservoir", {})}
        for p in self.profiles:
            self._normalize(p)

    def _default_profiles(self) -> list[dict]:
        base = self.new_profile()
        return [
            {**base, F_ID: uuid.uuid4().hex[:8], F_NAME: "Matin" if self.lang == "fr" else "Morning",
             F_START: "06:30", F_END: "08:30", F_SETPOINT: 20.0, F_MODE: MODE_RUN, F_DAYS: list(ALL_DAYS)},
            {**base, F_ID: uuid.uuid4().hex[:8], F_NAME: "Soirée" if self.lang == "fr" else "Evening",
             F_START: "17:30", F_END: "22:30", F_SETPOINT: 21.0, F_MODE: MODE_STANDBY, F_DAYS: list(ALL_DAYS)},
        ]

    def new_profile(self, **values: Any) -> dict:
        p = {
            F_ID: uuid.uuid4().hex[:8], F_NAME: self.word("new"), F_ACTIVE: True, F_START: "07:00", F_END: "09:00",
            F_DAYS: list(ALL_DAYS), F_SETPOINT: 20.0, F_MODE: MODE_STANDBY, F_POWER: "Auto", F_FAN1: "Auto",
            F_FAN2: self._default_fan2(), F_RELAX: False, F_ABSENT: None,
        }
        p.update({k: v for k, v in values.items() if v is not None and k in p})
        return self._normalize(p)

    def _default_fan2(self) -> str | None:
        opts = self.fan2_options()
        if not opts:
            return None
        return "Auto" if "Auto" in opts else opts[0]

    @staticmethod
    def _normalize(p: dict) -> dict:
        p[F_START] = str(p.get(F_START, "00:00"))[:5]
        p[F_END] = str(p.get(F_END, "00:00"))[:5]
        days = sorted({int(d) for d in (p.get(F_DAYS) or ALL_DAYS) if 0 <= int(d) <= 6})
        p[F_DAYS] = days or list(ALL_DAYS)
        p[F_SETPOINT] = round(float(p.get(F_SETPOINT, 20)) * 2) / 2
        if p.get(F_MODE) not in (MODE_RUN, MODE_STANDBY):
            p[F_MODE] = MODE_STANDBY if str(p.get(F_MODE, "")).lower().startswith("stand") else MODE_RUN
        p.setdefault(F_ACTIVE, True)
        p.setdefault(F_RELAX, False)
        p.setdefault(F_ABSENT, None)
        return p

    @callback
    def async_save(self) -> None:
        """Enregistrement différé (regroupe les écritures)."""
        self._store.async_delay_save(
            lambda: {"profiles": self.profiles, "state": self.state, "reservoir": self.reservoir}, 2
        )

    @callback
    def notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(self.entry.entry_id))

    # ------------------------------------------------------------------ accès aux profils
    def index_of(self, pid: str | None) -> int | None:
        for i, p in enumerate(self.profiles):
            if p[F_ID] == pid:
                return i
        return None

    def by_id(self, pid: str | None) -> dict | None:
        i = self.index_of(pid)
        return None if i is None else self.profiles[i]

    def by_number(self, n: int) -> dict | None:
        return self.profiles[n - 1] if 1 <= n <= len(self.profiles) else None

    def label(self, pid: str | None) -> str:
        """Libellé d'un menu : « P2 · Journée »."""
        i = self.index_of(pid)
        return f"P{i + 1} · {self.profiles[i][F_NAME]}" if i is not None else ""

    def pid_from_label(self, label: str) -> str | None:
        for p in self.profiles:
            if self.label(p[F_ID]) == label:
                return p[F_ID]
        return None

    # ------------------------------------------------------------------ état du poêle
    def _st(self, key: str) -> State | None:
        e = self.ent(key)
        return self.hass.states.get(e) if e else None

    def climate_attr(self, attr: str) -> Any:
        s = self._st(CONF_CLIMATE)
        return s.attributes.get(attr) if s else None

    def climate_heat(self) -> bool:
        s = self._st(CONF_CLIMATE)
        return bool(s and s.state == "heat")

    def status(self) -> str | None:
        s = self._st(CONF_STATUS)
        if s is None:
            c = self._st(CONF_CLIMATE)
            return None if c is None else ("unavailable" if c.state in STATUS_UNAVAILABLE else None)
        return s.state

    def esp_available(self) -> bool:
        st = self.status()
        if st is not None:
            return st not in STATUS_UNAVAILABLE
        c = self._st(CONF_CLIMATE)
        return bool(c and c.state not in STATUS_UNAVAILABLE)

    def fan1_options(self) -> list[str]:
        return list(self.climate_attr("fan_modes") or ["Auto", "20%", "40%", "60%", "80%", "100%"])

    def fan2_options(self) -> list[str]:
        s = self._st(CONF_FAN2)
        if s is None:
            return [] if not self.ent(CONF_FAN2) else ["Arrêt", "Auto", "20%", "40%", "60%", "80%", "100%"]
        return list(s.attributes.get("options") or [])

    def power_options(self) -> list[str]:
        opts = self.climate_attr("preset_modes") or ["Auto", "Man. P1", "Man. P2", "Man. P3", "Man. P4", "Man. P5"]
        return [o for o in opts if o not in ("none", "None")]

    # ------------------------------------------------------------------ démarrage / arrêt
    async def async_start(self) -> None:
        hass = self.hass
        watch = [e for e in (self.ent(CONF_CLIMATE), self.ent(CONF_FAN2), self.ent(CONF_STANDBY),
                             self.ent(CONF_RELAX), self.ent(CONF_STATUS)) if e]
        self._unsubs.append(async_track_state_change_event(hass, watch, self._on_stove_event))
        if self.ent(CONF_PRESENCE):
            self._update_occupied(hass.states.get(self.ent(CONF_PRESENCE)), initial=True)
            self._unsubs.append(async_track_state_change_event(hass, [self.ent(CONF_PRESENCE)], self._on_presence))
        self._setup_pellet()
        self._unsubs.append(async_track_time_change(hass, self._on_midnight, hour=0, minute=0, second=0))
        self._unsubs.append(async_track_time_interval(hass, self._on_tick, timedelta(minutes=5)))
        # Réservoir : reprendre le compteur selon l'état actuel
        self._reservoir_status(self.status(), dt_util.utcnow(), restart=True)

        async def _started(_: Event | None = None) -> None:
            self.schedule_next_slot()
            self.schedule_publish(0)
            await self.async_apply(K_START)

        if hass.state is CoreState.running:
            hass.async_create_task(_started())
        else:
            self._unsubs.append(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _started))

    async def async_stop(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()
        for name in ("_slot_unsub", "_verify_unsub", "_esp_unsub", "_sched_unsub"):
            u = getattr(self, name)
            if u:
                u()
            setattr(self, name, None)
        await self._store.async_save({"profiles": self.profiles, "state": self.state, "reservoir": self.reservoir})

    # ------------------------------------------------------------------ plages horaires
    def target(self, now: datetime | None = None) -> str | None:
        """Programmation active dont la plage contient l'heure : la première de la liste l'emporte."""
        now = now or dt_util.now()
        for p in self.profiles:
            if p[F_ACTIVE] and profile_matches(p, now):
                return p[F_ID]
        return None

    def _boundary_effective(self, p: dict, minutes: int, is_end: bool, when: datetime) -> bool:
        """Un début ou une fin de plage compte-t-il ce jour-là (jours de la programmation) ?"""
        days = p.get(F_DAYS) or ALL_DAYS
        wd = when.weekday()
        if not is_end or to_minutes(p[F_START]) == to_minutes(p[F_END]):
            return wd in days
        # Fin d'une plage qui passe minuit : elle appartient au jour du début
        if to_minutes(p[F_END]) < to_minutes(p[F_START]):
            return (wd - 1) % 7 in days
        return wd in days

    def next_slot(self, after: datetime | None = None) -> datetime | None:
        """Prochain début ou fin de plage d'une programmation activée (jours compris)."""
        now = (after or dt_util.now()).replace(second=0, microsecond=0)
        best: datetime | None = None
        for p in self.profiles:
            if not p[F_ACTIVE]:
                continue
            for key, is_end in ((F_START, False), (F_END, True)):
                mins = to_minutes(p[key])
                for day in range(0, 8):
                    cand = (now + timedelta(days=day)).replace(hour=mins // 60, minute=mins % 60)
                    if cand <= now:
                        continue
                    if self._boundary_effective(p, mins, is_end, cand):
                        if best is None or cand < best:
                            best = cand
                        break
        return best

    @callback
    def schedule_next_slot(self) -> None:
        if self._slot_unsub:
            self._slot_unsub()
            self._slot_unsub = None
        nxt = self.next_slot()
        self.next_change = nxt
        if nxt is not None:
            self._slot_unsub = async_track_point_in_time(self.hass, self._on_slot, nxt)
        self.notify()

    async def _on_slot(self, _now: datetime) -> None:
        self._slot_unsub = None
        self.schedule_next_slot()
        await self.async_apply(K_SLOT)
        self.schedule_verify(K_SLOT)

    # ------------------------------------------------------------------ application des profils
    async def async_apply(self, kind: str, edit: tuple[str, str] | None = None) -> None:
        async with self._lock:
            try:
                await self._apply(kind, edit)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Erreur pendant l'application des profils (%s)", kind)
            self.async_save()
            self.notify()

    async def _apply(self, kind: str, edit: tuple[str, str] | None) -> None:
        st = self.state
        self.last_apply = dt_util.utcnow()

        if kind == K_ESP_BACK and not st["resync"]:
            return  # aucun changement pendant la coupure de l'ESP32

        # Changement de plage pendant un forçage : fin du forçage, reprise comme un forçage
        if kind == K_SLOT and st["forced"]:
            st["forced"] = None
            kind = K_FORCED

        # Fin des réglages manuels
        if st["manual"] and (
            kind in (K_SLOT, K_PLANNING_ON, K_FORCED)
            or (kind == K_EDIT and edit and edit[0] == st["current"] and edit[1] in MANUAL_RESET_FIELDS)
        ):
            st["manual"] = False

        cible = self.target()
        prec = st["current"]
        forced = st["forced"] if self.by_id(st["forced"]) else None
        manuel = st["manual"]
        complet = kind == K_PLANNING_ON
        derog = st["override"]
        ref = float(st["override_ref"] or 0)
        forcer = kind == K_FORCED and forced is not None
        planif = st["planning"]
        n = forced or cible
        np = self.by_id(n)
        subst = bool(np and not forced and np.get(F_ABSENT) and self.by_id(np[F_ABSENT]) and not self.occupied)
        c = np[F_ABSENT] if subst else n
        cp = self.by_id(c)
        on_c, on_p = cp is not None, prec is not None
        cons = float(cp[F_SETPOINT]) if cp else 19.0
        edit_cible = kind == K_EDIT and edit is not None and edit[0] in (c, n)
        mode_p = cp[F_MODE] if cp else MODE_STANDBY
        heat = self.climate_heat()
        temp = self.climate_attr("current_temperature")
        temp = float(temp) if temp is not None else 99.0
        status = self.status()

        bascule = planif and not manuel and (
            complet
            or forcer
            or on_c != on_p
            or (kind == K_ESP_BACK and on_c != heat)
            or (kind in (K_SLOT, K_MANUAL_END) and on_c and status == STATUS_OFF
                and (mode_p != MODE_STANDBY or temp < cons))
        )
        fin_derog = derog and (complet or forcer or not on_c or cons < ref
                               or (edit_cible and edit is not None and edit[1] == F_SETPOINT))

        # Programmation désactivée sans forçage : affichage du profil seulement
        if not planif and not forced:
            st["substitution"] = subst
            self._set_current(c)
            st["resync"] = False
            return

        # Modification ou présence sans effet sur le profil appliqué
        if (kind == K_EDIT and c == prec and not edit_cible) or (kind == K_PRESENCE and c == prec):
            return

        if fin_derog:
            st["override"] = False
        if complet and self.ent(CONF_CHRONO):
            ch = self._st(CONF_CHRONO)
            if ch and ch.state == "on":
                await self._svc("switch", "turn_off", {"entity_id": self.ent(CONF_CHRONO)})
        st["substitution"] = subst
        self._set_current(c)
        if not self.esp_available():
            st["resync"] = True

        full = kind in FULL_RESEND
        clim = self.ent(CONF_CLIMATE)
        if not on_c and bascule:
            await self._svc("climate", "set_hvac_mode", {"entity_id": clim, "hvac_mode": "off"})
        elif on_c and (bascule or heat or planif):
            if bascule and not heat:
                await self._svc("climate", "set_hvac_mode", {"entity_id": clim, "hvac_mode": "heat"})
            preset = cp[F_POWER] or "Auto"
            if not manuel and (full or self.climate_attr("preset_mode") != preset):
                await self._svc("climate", "set_preset_mode", {"entity_id": clim, "preset_mode": preset})
            cur_t = float(self.climate_attr("temperature") or 0)
            if (not derog or fin_derog) and (full or abs(cur_t - cons) > 0.05):
                await self._svc("climate", "set_temperature", {"entity_id": clim, "temperature": cons})
            sb_ent = self.ent(CONF_STANDBY)
            if sb_ent and not manuel:
                sb_on = self._st(CONF_STANDBY) is not None and self._st(CONF_STANDBY).state == "on"
                want = mode_p == MODE_STANDBY
                if full or sb_on != want:
                    await self._svc("switch", "turn_on" if want else "turn_off", {"entity_id": sb_ent})
            if not st["relax_manual"]:
                rx_ent = self.ent(CONF_RELAX)
                rx_state = self._st(CONF_RELAX).state if self._st(CONF_RELAX) else None
                if cp[F_RELAX]:
                    if rx_ent and (full or rx_state != "on"):
                        await self._svc("switch", "turn_on", {"entity_id": rx_ent})
                else:
                    if rx_ent and (full or rx_state != "off"):
                        await self._svc("switch", "turn_off", {"entity_id": rx_ent})
                    if not manuel and cp[F_FAN1] and (full or self.climate_attr("fan_mode") != cp[F_FAN1]):
                        await self._svc("climate", "set_fan_mode", {"entity_id": clim, "fan_mode": cp[F_FAN1]})
                    f2 = self.ent(CONF_FAN2)
                    if f2 and not manuel and cp.get(F_FAN2):
                        f2s = self._st(CONF_FAN2)
                        if full or (f2s and f2s.state != cp[F_FAN2]):
                            await self._svc("select", "select_option", {"entity_id": f2, "option": cp[F_FAN2]})
        if self.esp_available():
            st["resync"] = False

    def _set_current(self, pid: str | None) -> None:
        if self.state["current"] != pid:
            self.state["current"] = pid
            self.current_changed = dt_util.utcnow()
            self.schedule_verify("profile")

    async def _svc(self, domain: str, service: str, data: dict) -> None:
        if self.observe:
            self._log(f"Observation : {domain}.{service} {json.dumps({k: v for k, v in data.items() if k != 'entity_id'}, ensure_ascii=False)}",
                      data.get("entity_id"))
            return
        try:
            await self.hass.services.async_call(domain, service, data, blocking=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Commande %s.%s refusée : %s", domain, service, err)

    def _log(self, message: str, entity_id: str | None = None) -> None:
        if "logbook" not in self.hass.config.components:
            _LOGGER.info(message)
            return
        from homeassistant.components.logbook import async_log_entry  # noqa: PLC0415

        async_log_entry(self.hass, "Edilkamin Control", message, DOMAIN, entity_id or self.ent(CONF_CLIMATE))

    # ------------------------------------------------------------------ vérification
    @callback
    def schedule_verify(self, kind: str) -> None:
        if not self.state.get("planning"):
            return
        if self._verify_unsub:
            self._verify_unsub()
        self._verify_kind = kind
        self._verify_unsub = async_call_later(self.hass, VERIFY_DELAY, self._on_verify)

    async def _on_verify(self, _now: datetime) -> None:
        self._verify_unsub = None
        kind = self._verify_kind
        st = self.state
        if not st["planning"] or st["forced"] or st["override"] or not self.esp_available():
            return
        async with self._lock:
            self.last_verify = dt_util.utcnow()
            c = st["current"]
            cp = self.by_id(c)
            status = self.status()
            manuel = st["manual"]
            clim = self.ent(CONF_CLIMATE)
            transition = (dt_util.utcnow() - self.current_changed).total_seconds() < 330
            if cp is None:
                if not manuel and transition and status not in (STATUS_OFF, *STATUS_STOPPING):
                    await self._svc("climate", "set_hvac_mode", {"entity_id": clim, "hvac_mode": "off"})
                    self._log(f"Vérification : extinction hors programmation renvoyée (statut {status})")
                return
            cons = float(cp[F_SETPOINT])
            t_amb = self.climate_attr("current_temperature")
            t_amb = float(t_amb) if t_amb is not None else 99.0
            t_lue = float(self.climate_attr("temperature") or 0)
            sb = self._st(CONF_STANDBY)
            err_cons = abs(t_lue - cons) > 0.05
            err_marche = not manuel and kind == K_SLOT and status == STATUS_OFF and (
                cp[F_MODE] != MODE_STANDBY or t_amb < cons)
            err_preset = not manuel and self.climate_attr("preset_mode") != cp[F_POWER]
            err_sb = not manuel and sb is not None and (sb.state == "on") != (cp[F_MODE] == MODE_STANDBY)
            if not (err_cons or err_preset or err_sb or err_marche):
                return
            if err_preset:
                await self._svc("climate", "set_preset_mode", {"entity_id": clim, "preset_mode": cp[F_POWER]})
            if err_cons:
                await self._svc("climate", "set_temperature", {"entity_id": clim, "temperature": cons})
            if err_sb:
                await self._svc("switch", "turn_on" if cp[F_MODE] == MODE_STANDBY else "turn_off",
                                {"entity_id": self.ent(CONF_STANDBY)})
            if err_marche:
                await self._svc("climate", "set_hvac_mode", {"entity_id": clim, "hvac_mode": "heat"})
            parts = []
            if err_cons:
                parts.append(f"consigne {cons} (lue {t_lue})")
            if err_preset:
                parts.append(f"puissance {cp[F_POWER]}")
            if err_sb:
                parts.append("stand-by")
            if err_marche:
                parts.append("allumage (statut Off)")
            self._log(f"Vérification {cp[F_NAME]} : renvoi " + ", ".join(parts))

    # ------------------------------------------------------------------ événements du poêle
    @callback
    def _on_stove_event(self, event: Event) -> None:
        eid = event.data["entity_id"]
        old: State | None = event.data.get("old_state")
        new: State | None = event.data.get("new_state")
        if new is None:
            return
        if eid == self.ent(CONF_STATUS) or (not self.ent(CONF_STATUS) and eid == self.ent(CONF_CLIMATE)):
            self._on_status(old, new)
        if eid == self.ent(CONF_CLIMATE):
            if old is not None and old.attributes.get("temperature") != new.attributes.get("temperature"):
                self._detect_override(old, new)
            if old is not None and old.attributes.get("fan_mode") != new.attributes.get("fan_mode"):
                self._detect_manual("fan1", old.attributes.get("fan_mode"), new.attributes.get("fan_mode"), old, new)
            if old is not None and old.attributes.get("preset_mode") != new.attributes.get("preset_mode"):
                self._detect_manual("preset", old.attributes.get("preset_mode"), new.attributes.get("preset_mode"), old, new)
            if old is not None and old.state != new.state and old.state in ("off", "heat") and new.state in ("off", "heat"):
                self._detect_manual("marche", old.state, new.state, old, new)
        elif eid == self.ent(CONF_FAN2) and old is not None and old.state != new.state:
            self._detect_manual("fan2", old.state, new.state, old, new)
        elif eid == self.ent(CONF_STANDBY) and old is not None and old.state != new.state:
            self._detect_manual("standby", old.state, new.state, old, new)
        elif eid == self.ent(CONF_RELAX) and old is not None and old.state != new.state:
            self._on_relax(old.state, new.state)

    def _on_status(self, old: State | None, new: State) -> None:
        now = dt_util.utcnow()
        self._reservoir_status(new.state, now)
        was = old.state if old else None
        if was in STATUS_UNAVAILABLE and new.state not in STATUS_UNAVAILABLE:
            if self._esp_unsub:
                self._esp_unsub()
            self._esp_unsub = async_call_later(self.hass, ESP_BACK_DELAY, self._on_esp_back)
        elif new.state in STATUS_UNAVAILABLE and self._esp_unsub:
            self._esp_unsub()
            self._esp_unsub = None
        self.notify()

    async def _on_esp_back(self, _now: datetime) -> None:
        self._esp_unsub = None
        self.schedule_publish(0)
        await self.async_apply(K_ESP_BACK)

    def _active_control(self) -> bool:
        return self.state["planning"] or bool(self.state["forced"])

    def _guard(self, ts: datetime | None, seconds: int) -> bool:
        """True si l'instant est en dehors de la fenêtre qui suit ts."""
        return ts is None or (dt_util.utcnow() - ts).total_seconds() > seconds

    def _detect_override(self, old: State, new: State) -> None:
        """Consigne changée et différente de la programmation en cours : dérogation."""
        if not self._active_control():
            return
        if old.state in STATUS_UNAVAILABLE or new.state in STATUS_UNAVAILABLE:
            return
        t = new.attributes.get("temperature")
        cp = self.by_id(self.state["current"])
        if t is None or cp is None:
            return
        if abs(float(t) - float(cp[F_SETPOINT])) <= 0.05:
            return
        if not self._guard(self.last_apply, APPLY_GUARD):
            return
        self.state["override_ref"] = float(cp[F_SETPOINT])
        self.state["override"] = True
        self.async_save()
        self.notify()

    def _expected(self, what: str, cp: dict, value: Any) -> Any:
        if what == "fan1":
            return cp[F_FAN1]
        if what == "fan2":
            return cp.get(F_FAN2)
        if what == "preset":
            return cp[F_POWER]
        if what == "standby":
            return "on" if cp[F_MODE] == MODE_STANDBY else "off"
        return value

    def _detect_manual(self, what: str, before: Any, after: Any, old: State, new: State) -> None:
        """Ventilations, puissance, stand-by, marche/arrêt changés à la main : réglages manuels."""
        st = self.state
        if not self._active_control() or st["manual"]:
            return
        cp = self.by_id(st["current"])
        if cp is None:
            return
        if old.state in STATUS_UNAVAILABLE or new.state in STATUS_UNAVAILABLE:
            return
        if before == after or str(before) in ESP_DEFAULT_VALUES or str(after) in ESP_DEFAULT_VALUES:
            return
        user = new.context is not None and new.context.user_id is not None
        if what == "marche":
            manual = user
        else:
            hors = self._guard(self.last_apply, APPLY_GUARD) and self._guard(self.last_verify, VERIFY_GUARD)
            manual = after != self._expected(what, cp, after) and (user or hors)
        if not manual:
            return
        st["manual"] = True
        names = {"fan1": "ventilation 1", "fan2": "ventilation 2", "preset": "puissance",
                 "standby": "stand-by", "marche": "marche/arrêt"}
        self._log(f"Réglage manuel ({names[what]} : {before} → {after}"
                  f"{', depuis Home Assistant' if user else ', relu sur le poêle'}) : la programmation ne renverra "
                  "plus ventilations, puissance, stand-by ni marche/arrêt jusqu'au prochain changement de plage.")
        self.async_save()
        self.notify()

    def _on_relax(self, before: str, after: str) -> None:
        """Relax activé à la main hors programmation : prioritaire jusqu'à minuit."""
        st = self.state
        if before == "off" and after == "on" and st["planning"] and not st["relax_manual"]:
            cp = self.by_id(st["current"])
            if not (cp and cp[F_RELAX]) and self._guard(self.last_apply, 30):
                st["relax_manual"] = True
                self.async_save()
                self.notify()
        elif before == "on" and after == "off" and st["relax_manual"]:
            st["relax_manual"] = False
            self.hass.async_create_task(self.async_apply(K_RELAX_END))

    async def _on_midnight(self, _now: datetime) -> None:
        if self.state["relax_manual"]:
            self.state["relax_manual"] = False
            await self.async_apply(K_RELAX_END)

    # ------------------------------------------------------------------ présence
    def _update_occupied(self, s: State | None, initial: bool = False) -> bool:
        """Maison occupée ? Renvoie True si la valeur a changé."""
        if s is None or s.state in STATUS_UNAVAILABLE:
            return False
        dom = s.entity_id.split(".")[0]
        val: bool | None
        if dom == "alarm_control_panel":
            val = False if s.state in AWAY_ALARM_STATES else True if s.state in HOME_ALARM_STATES else None
        elif dom == "zone":
            try:
                val = float(s.state) > 0
            except ValueError:
                val = None
        elif s.state in ("on", "home"):
            val = True
        elif s.state in ("off", "not_home"):
            val = False
        else:
            val = s.state == "home" if dom in ("person", "device_tracker") else None
        if val is None or val == self.occupied:
            return False
        self.occupied = val
        return not initial

    @callback
    def _on_presence(self, event: Event) -> None:
        if self._update_occupied(event.data.get("new_state")):
            self.notify()
            self.hass.async_create_task(self.async_apply(K_PRESENCE))
            self.schedule_verify(K_PRESENCE)

    # ------------------------------------------------------------------ actions des entités
    async def async_set_planning(self, on: bool) -> None:
        if self.state["planning"] == on:
            return
        self.state["planning"] = on
        if on:
            await self.async_apply(K_PLANNING_ON)
        else:
            self.async_save()
            self.notify()

    async def async_set_forced(self, pid: str | None) -> None:
        self.state["forced"] = pid
        await self.async_apply(K_FORCED)

    async def async_set_override(self, on: bool) -> None:
        if on:
            cp = self.by_id(self.state["current"])
            self.state["override_ref"] = float(cp[F_SETPOINT]) if cp else None
            self.state["override"] = True
            self.async_save()
            self.notify()
        elif self.state["override"]:
            self.state["override"] = False
            await self.async_apply(K_OVERRIDE_CANCEL)

    async def async_set_manual(self, on: bool) -> None:
        if on:
            self.state["manual"] = True
            self.async_save()
            self.notify()
        elif self.state["manual"]:
            self.state["manual"] = False
            await self.async_apply(K_MANUAL_END)

    async def async_set_relax_manual(self, on: bool) -> None:
        self.state["relax_manual"] = on
        if on:
            self.async_save()
            self.notify()
        else:
            await self.async_apply(K_RELAX_END)

    async def async_set_field(self, pid: str, field: str, value: Any) -> None:
        p = self.by_id(pid)
        if p is None or p.get(field) == value:
            return
        p[field] = value
        self._normalize(p)
        self.schedule_next_slot()
        self.schedule_publish()
        await self.async_apply(K_EDIT, (pid, field))

    async def async_set_threshold(self, value: float) -> None:
        self.state["alert_threshold"] = float(value)
        self.async_save()
        self.notify()

    # Ajout / suppression : l'entrée est rechargée pour créer ou retirer les entités
    async def async_add_profile(self, values: dict) -> dict:
        if len(self.profiles) >= MAX_PROFILES:
            raise ValueError(f"{MAX_PROFILES} programmations au maximum")
        p = self.new_profile(**values)
        if p[F_POWER] not in self.power_options():
            p[F_POWER] = "Auto"
        self.profiles.append(p)
        await self._structure_changed()
        return p

    async def async_remove_profile(self, pid: str) -> None:
        i = self.index_of(pid)
        if i is None:
            return
        self.profiles.pop(i)
        for p in self.profiles:
            if p.get(F_ABSENT) == pid:
                p[F_ABSENT] = None
        if self.state["forced"] == pid:
            self.state["forced"] = None
        ent_reg = er.async_get(self.hass)
        for e in er.async_entries_for_config_entry(ent_reg, self.entry.entry_id):
            if e.unique_id.startswith(f"{self.entry.entry_id}_{pid}_"):
                ent_reg.async_remove(e.entity_id)
        await self._structure_changed()

    async def async_move_profile(self, pid: str, position: int) -> None:
        i = self.index_of(pid)
        if i is None:
            return
        p = self.profiles.pop(i)
        self.profiles.insert(max(0, min(len(self.profiles), position - 1)), p)
        await self._structure_changed()

    async def _structure_changed(self) -> None:
        await self._store.async_save({"profiles": self.profiles, "state": self.state, "reservoir": self.reservoir})
        self.hass.config_entries.async_schedule_reload(self.entry.entry_id)

    # ------------------------------------------------------------------ planning de secours (ESP32)
    @callback
    def schedule_publish(self, delay: float = SCHEDULE_DEBOUNCE) -> None:
        if not self.ent(CONF_MQTT_TOPIC):
            return
        if self._sched_unsub:
            self._sched_unsub()
        self._sched_unsub = async_call_later(self.hass, delay, self._publish)

    @staticmethod
    def _pct(value: str | None, auto: int, off: int | None = None) -> int:
        v = str(value or "")
        if v == "Auto":
            return auto
        if v.endswith("%"):
            try:
                return max(1, min(5, int(v[:-1]) // 20))
            except ValueError:
                return auto
        return off if off is not None else auto

    def schedule_payload(self) -> dict:
        fmt = self.cfg.get(CONF_SCHEDULE_FORMAT, "v2")
        out = []
        for p in self.profiles[: (5 if fmt == "v1" else MAX_PROFILES)]:
            pw = str(p[F_POWER])
            item = {
                "a": 1 if p[F_ACTIVE] else 0, "d": to_minutes(p[F_START]), "f": to_minutes(p[F_END]),
                "c": int(round(float(p[F_SETPOINT]) * 10)), "m": 1 if p[F_MODE] == MODE_STANDBY else 0,
                "pu": int(pw[-1]) if pw.startswith("Man. P") and pw[-1].isdigit() else 0,
                "v1": self._pct(p[F_FAN1], 6), "v2": self._pct(p.get(F_FAN2), 6, 0),
            }
            if fmt != "v1":
                item["r"] = 1 if p[F_RELAX] else 0
                item["j"] = sum(1 << d for d in (p.get(F_DAYS) or ALL_DAYS))
            out.append(item)
        if fmt == "v1":  # firmware akoonet-13 : exactement 5 plages
            while len(out) < 5:
                out.append({"a": 0, "d": 0, "f": 0, "c": 190, "m": 1, "pu": 0, "v1": 6, "v2": 6})
            return {"v": 1, "p": out}
        return {"v": 2, "p": out}

    async def _publish(self, _now: datetime | None = None) -> None:
        self._sched_unsub = None
        topic = self.ent(CONF_MQTT_TOPIC)
        if not topic or "mqtt" not in self.hass.config.components:
            return
        payload = json.dumps(self.schedule_payload(), separators=(",", ":"))
        try:
            await self.hass.services.async_call(
                "mqtt", "publish", {"topic": topic, "payload": payload, "qos": 1, "retain": True}, blocking=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Planning de secours non publié : %s", err)

    # ------------------------------------------------------------------ réservoir de granulés
    def _reservoir_status(self, status: str | None, now: datetime, restart: bool = False) -> None:
        """Compte les heures de chauffe (statut ni arrêté ni indisponible) depuis le dernier remplissage."""
        r = self.reservoir
        burning = status not in STATUS_NOT_BURNING
        since = dt_util.parse_datetime(r["since"]) if r.get("since") else None
        if restart and since and burning:
            return  # redémarrage de HA en pleine chauffe : le comptage reprend depuis l'instant mémorisé
        if since:
            r["hours"] = float(r["hours"]) + max(0.0, (now - since).total_seconds()) / 3600
        r["since"] = now.isoformat() if burning else None
        self.async_save()

    def reservoir_hours(self) -> float:
        r = self.reservoir
        h = float(r["hours"])
        if r.get("since"):
            since = dt_util.parse_datetime(r["since"])
            if since:
                h += (dt_util.utcnow() - since).total_seconds() / 3600
        return round(h, 2)

    def reservoir_average(self) -> float | None:
        d = self.reservoir.get("durations") or []
        return round(sum(d) / len(d), 1) if d else None

    def reservoir_autonomy(self) -> float | None:
        """Heures de chauffe restantes estimées (au moins 2 réservoirs mesurés)."""
        d = self.reservoir.get("durations") or []
        avg = self.reservoir_average()
        if len(d) < 2 or avg is None:
            return None
        return round(max(0.0, avg - self.reservoir_hours()), 1)

    def stock_autonomy(self) -> float | None:
        """Heures de chauffe permises par le stock de Suivi Stock Pellet."""
        if not self.pellet_stock:
            return None
        d = self.reservoir.get("durations") or []
        avg = self.reservoir_average()
        s = self.hass.states.get(self.pellet_stock)
        if s is None or len(d) < 2 or avg is None:
            return None
        bags = s.attributes.get("stock_sacs")
        if bags is None:
            try:
                bags = float(s.state) / float(s.attributes.get("poids_sac_kg") or 15)
            except (TypeError, ValueError):
                return None
        per_fill = float(self.cfg.get(CONF_BAGS_PER_FILL) or 1)
        return round(float(bags) / per_fill * avg, 0)

    def reservoir_low(self) -> bool:
        th = float(self.state.get("alert_threshold") or 0)
        return th > 0 and self.reservoir_hours() >= th

    @callback
    def reservoir_filled(self, load_kg: float | None = None) -> None:
        r = self.reservoir
        h = self.reservoir_hours()
        if h > 0.5:
            r["durations"] = ([round(h, 1)] + list(r.get("durations") or []))[:10]
        r["hours"] = 0.0
        r["since"] = dt_util.utcnow().isoformat() if self.status() not in STATUS_NOT_BURNING else None
        r["alerted"] = False
        if load_kg is not None:
            r["last_load"] = round(load_kg, 1)
        self.async_save()
        self.notify()

    async def async_press_filled(self) -> None:
        """Bouton « Réservoir rempli » : passe par Suivi Stock Pellet s'il est configuré."""
        if self.pellet_consumed and "suivi_stock_pellet" in self.hass.config.components:
            await self.hass.services.async_call(
                "suivi_stock_pellet", "log_consumption",
                {"unit": "bag", "qty_bags": float(self.cfg.get(CONF_BAGS_PER_FILL) or 1)}, blocking=True)
            # La hausse de « Consommé » remet le compteur à zéro (_on_pellet)
            return
        self.reservoir_filled()

    def _setup_pellet(self) -> None:
        entry_id = self.cfg.get(CONF_PELLET_ENTRY)
        if not entry_id:
            return
        ent_reg = er.async_get(self.hass)
        for e in er.async_entries_for_config_entry(ent_reg, entry_id):
            if e.domain != "sensor":
                continue
            if e.unique_id.endswith("_consomme_kg"):
                self.pellet_consumed = e.entity_id
            elif e.unique_id.endswith("_stock"):
                self.pellet_stock = e.entity_id
        if self.pellet_consumed:
            self._unsubs.append(async_track_state_change_event(self.hass, [self.pellet_consumed], self._on_pellet))
        if self.pellet_stock:
            self._unsubs.append(async_track_state_change_event(self.hass, [self.pellet_stock], lambda _e: self.notify()))

    @callback
    def _on_pellet(self, event: Event) -> None:
        """« Consommé » qui augmente dans Suivi Stock Pellet = réservoir rempli (une baisse est ignorée)."""
        old, new = event.data.get("old_state"), event.data.get("new_state")
        try:
            before, after = float(old.state), float(new.state)
        except (AttributeError, TypeError, ValueError):
            return
        if after > before:
            self.reservoir_filled(after - before)

    @callback
    def _on_tick(self, _now: datetime) -> None:
        self.notify()
