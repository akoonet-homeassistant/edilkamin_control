"""Moteur de programmation Edilkamin Control.

Reprend la logique des automatisations validées en production :
application des profils, dérogation de consigne, réglages manuels, priorité Relax manuelle,
présence (« si absent »), vérification après changement de plage, resynchronisation au retour
de l'ESP32, planning de secours publié en MQTT et suivi du réservoir de granulés.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime, timedelta
import json
import logging
import re
from typing import Any
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_CALL_SERVICE, EVENT_HOMEASSISTANT_STARTED
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
    CONF_HOLIDAYS,
    CONF_IGNITION_LOG,
    CONF_IGNITIONS,
    CONF_STOP_LOG,
    CONF_WINDOW_CLOSE_DELAY,
    CONF_WINDOW_OPEN_DELAY,
    CONF_WINDOWS,
    HISTORY_DAYS,
    HOLIDAY,
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
    K_WINDOW,
    K_WINDOW_END,
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
    ALARM_HISTORY,
    STATUS_OFF,
    STATUS_OK,
    STATUS_STOPPING,
    STATUS_UNAVAILABLE,
    VERIFY_DELAY,
    VERIFY_GUARD,
)

_LOGGER = logging.getLogger(__name__)
_LEGACY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})")

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


def _event_day(value: Any) -> date | None:
    """Jour d'un début ou d'une fin d'événement de calendrier (« AAAA-MM-JJ » ou date et heure)."""
    if not value:
        return None
    s = str(value)
    if len(s) == 10:
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None
    dt = dt_util.parse_datetime(s)
    return dt_util.as_local(dt).date() if dt else None


def _weekday_in(days: list[int], day: date) -> bool:
    return day.weekday() in days


def profile_matches(profile: dict, now: datetime, day_in: Callable[[list[int], date], bool] = _weekday_in) -> bool:
    """La plage de la programmation contient-elle l'instant donné (jours compris) ?

    Début = fin : toute la journée. Plage pouvant passer minuit : la partie après minuit
    appartient au jour du début. day_in dit si un jour compte (jours fériés compris).
    """
    d, f = to_minutes(profile[F_START]), to_minutes(profile[F_END])
    m = now.hour * 60 + now.minute
    days = profile.get(F_DAYS) or ALL_DAYS
    today = now.date()
    if d == f:
        return day_in(days, today)
    if d < f:
        return d <= m < f and day_in(days, today)
    if m >= d:
        return day_in(days, today)
    if m < f:
        return day_in(days, today - timedelta(days=1))
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
        self.ignitions: list[dict[str, Any]] = []
        self.ignitions_entity: str | None = None
        self.alarms: list[dict[str, Any]] = []  # 10 dernières alarmes, la plus récente en premier
        self.alarm_entity: str | None = None
        self.alarm_label_entity: str | None = None
        self.legacy_logs: tuple[str | None, str | None] = (None, None)
        self._lock = asyncio.Lock()
        self._unsubs: list = []
        self._slot_unsub = None
        self._verify_unsub = None
        self._verify_kind: str | None = None
        self._esp_unsub = None
        self._ignite_unsub = None
        self._ignite_tries = 0
        self._win_open_unsub = None   # coupure en attente (fenêtre ouverte depuis moins que le délai)
        self._win_close_unsub = None  # reprise en attente (fenêtres refermées depuis moins que le délai)
        self.window_cut_at: datetime | None = None
        self.window_resume_at: datetime | None = None
        self.esp_back_at: datetime | None = None
        self._sched_unsub = None
        self._save_unsub = None
        self.last_apply: datetime | None = None
        self.last_verify: datetime | None = None
        self.current_changed: datetime = dt_util.utcnow()
        self.next_change: datetime | None = None
        self.holidays: set[date] = set()  # jours fériés des 10 prochains jours
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
            "window": False,           # fenêtre ouverte : poêle coupé, programmation suspendue
            "window_heat": False,      # le poêle était allumé au moment de la coupure
            "window_override": False,  # rallumé à la main fenêtre ouverte : pas de nouvelle coupure avant fermeture
            "window_since": None,
            **data.get("state", {}),
        }
        self.ignitions = list(data.get("ignitions") or [])
        self.alarms = list(data.get("alarms") or [])[:ALARM_HISTORY]
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
        days = sorted({int(d) for d in (p.get(F_DAYS) or ALL_DAYS) if 0 <= int(d) <= HOLIDAY})
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
            lambda: {"profiles": self.profiles, "state": self.state, "reservoir": self.reservoir, "ignitions": self.ignitions, "alarms": self.alarms}, 2
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
        # Compteur d'allumages : configuré, sinon cherché sur l'appareil du thermostat
        self.ignitions_entity = self.ent(CONF_IGNITIONS)
        if not self.ignitions_entity:
            from .config_flow import detect_siblings  # noqa: PLC0415

            self.ignitions_entity = detect_siblings(hass, self.ent(CONF_CLIMATE)).get(CONF_IGNITIONS)
        # Alarme du firmware (état et libellé), trouvée sur l'appareil du thermostat
        from .config_flow import detect_alarm  # noqa: PLC0415

        self.alarm_entity, self.alarm_label_entity = detect_alarm(hass, self.ent(CONF_CLIMATE))
        # Alarme terminée pendant l'arrêt de Home Assistant : l'alarme ouverte est fermée
        st_al = hass.states.get(self.alarm_entity) if self.alarm_entity else None
        if st_al is not None and st_al.state == "off" and self.alarms and self.alarms[0].get("end") is None:
            self.alarms[0]["end"] = dt_util.utcnow().isoformat()
        watch = [e for e in (self.ent(CONF_CLIMATE), self.ent(CONF_FAN2), self.ent(CONF_STANDBY),
                             self.ent(CONF_RELAX), self.ent(CONF_STATUS), self.ignitions_entity,
                             self.alarm_entity, self.alarm_label_entity) if e]
        self._unsubs.append(async_track_state_change_event(hass, watch, self._on_stove_event))
        # Historique déjà tenu par une automatisation (input_text) : repris et suivi
        from .config_flow import detect_logs  # noqa: PLC0415

        found = detect_logs(hass)
        self.legacy_logs = (self.ent(CONF_IGNITION_LOG) or found.get(CONF_IGNITION_LOG),
                            self.ent(CONF_STOP_LOG) or found.get(CONF_STOP_LOG))
        if self.legacy_logs[0]:
            self._import_legacy()
            self._unsubs.append(async_track_state_change_event(
                hass, [e for e in self.legacy_logs if e], self._on_legacy_log))
        # Ordres donnés par un utilisateur (carte, tableau de bord, application, assistant vocal)
        self._unsubs.append(hass.bus.async_listen(EVENT_CALL_SERVICE, self._on_call_service))
        if self.ent(CONF_PRESENCE):
            self._update_occupied(hass.states.get(self.ent(CONF_PRESENCE)), initial=True)
            self._unsubs.append(async_track_state_change_event(hass, [self.ent(CONF_PRESENCE)], self._on_presence))
        self._setup_pellet()
        if self.windows():
            self._unsubs.append(async_track_state_change_event(hass, self.windows(), self._on_window_event))
        self._unsubs.append(async_track_time_change(hass, self._on_midnight, hour=0, minute=0, second=0))
        self._unsubs.append(async_track_time_interval(hass, self._on_tick, timedelta(minutes=5)))
        # Réservoir : reprendre le compteur selon l'état actuel
        self._reservoir_status(self.status(), dt_util.utcnow(), restart=True)

        async def _started(_: Event | None = None) -> None:
            self._import_legacy_reservoir()
            await self.async_refresh_holidays()
            self.schedule_next_slot()
            self.schedule_publish(0)
            self._windows_changed()
            await self.async_apply(K_START)

        if hass.state is CoreState.running:
            hass.async_create_task(_started())
        else:
            # écoute unique : ne pas la retirer au déchargement si elle a déjà servi
            fired = False

            async def _once(event: Event) -> None:
                nonlocal fired
                fired = True
                await _started(event)

            unsub = hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _once)
            self._unsubs.append(lambda: None if fired else unsub())

    async def async_stop(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()
        for name in ("_slot_unsub", "_verify_unsub", "_esp_unsub", "_sched_unsub", "_ignite_unsub",
                     "_win_open_unsub", "_win_close_unsub"):
            u = getattr(self, name)
            if u:
                u()
            setattr(self, name, None)
        await self._store.async_save({"profiles": self.profiles, "state": self.state, "reservoir": self.reservoir, "ignitions": self.ignitions, "alarms": self.alarms})

    # ------------------------------------------------------------------ plages horaires
    def target(self, now: datetime | None = None) -> str | None:
        """Programmation active dont la plage contient l'heure : la première de la liste l'emporte."""
        now = now or dt_util.now()
        for p in self.profiles:
            if p[F_ACTIVE] and profile_matches(p, now, self.day_in):
                return p[F_ID]
        return None

    def _boundary_effective(self, p: dict, minutes: int, is_end: bool, when: datetime) -> bool:
        """Un début ou une fin de plage compte-t-il ce jour-là (jours de la programmation) ?"""
        days = p.get(F_DAYS) or ALL_DAYS
        day = when.date()
        if not is_end or to_minutes(p[F_START]) == to_minutes(p[F_END]):
            return self.day_in(days, day)
        # Fin d'une plage qui passe minuit : elle appartient au jour du début
        if to_minutes(p[F_END]) < to_minutes(p[F_START]):
            return self.day_in(days, day - timedelta(days=1))
        return self.day_in(days, day)

    # ------------------------------------------------------------------ jours fériés
    def holiday_calendar_ok(self) -> bool:
        """Calendrier des jours fériés choisi dans les options et présent dans Home Assistant."""
        cal = self.cfg.get(CONF_HOLIDAYS)
        return bool(cal) and self.hass.states.get(cal) is not None

    def holiday_mode(self, day: date) -> bool:
        """Jour férié et au moins une programmation activée cochée « Jours fériés » :
        seules ces programmations comptent ce jour-là. Sinon le jour de la semaine s'applique."""
        return day in self.holidays and any(
            p[F_ACTIVE] and HOLIDAY in (p.get(F_DAYS) or []) for p in self.profiles)

    def day_in(self, days: list[int], day: date) -> bool:
        if self.holiday_mode(day):
            return HOLIDAY in days
        return day.weekday() in days

    async def async_refresh_holidays(self) -> None:
        """Jours fériés des 10 prochains jours, lus dans le calendrier choisi (intégration Holiday)."""
        cal = self.cfg.get(CONF_HOLIDAYS)
        found: set[date] = set()
        if cal and self.hass.services.has_service("calendar", "get_events"):
            start = dt_util.start_of_local_day()
            try:
                resp = await self.hass.services.async_call(
                    "calendar", "get_events",
                    {"entity_id": cal, "start_date_time": start.isoformat(),
                     "end_date_time": (start + timedelta(days=10)).isoformat()},
                    blocking=True, return_response=True)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Jours fériés : lecture de %s impossible : %s", cal, err)
                resp = None
            for ev in ((resp or {}).get(cal) or {}).get("events", []):
                first, last = _event_day(ev.get("start")), _event_day(ev.get("end"))
                if first is None:
                    continue
                if last is None or last <= first:
                    last = first + timedelta(days=1)
                d = first
                while d < last and len(found) < 40:
                    found.add(d)
                    d += timedelta(days=1)
        changed = found != self.holidays
        self.holidays = found
        if changed:
            self.notify()

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

        slot_change = kind == K_SLOT
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
            or (kind == K_WINDOW_END and on_c != heat)
            or (kind in (K_SLOT, K_MANUAL_END) and on_c and status == STATUS_OFF
                and (mode_p != MODE_STANDBY or temp < cons))
        )
        # Dérogation de consigne : gardée jusqu'au prochain changement de la programmation
        # (début ou fin de plage, programmation appliquée qui change, forçage, réactivation,
        # passage hors programmation ou consigne de la programmation en cours modifiée)
        fin_derog = derog and (complet or forcer or not on_c or slot_change or c != prec
                               or (edit_cible and edit is not None and edit[1] == F_SETPOINT))

        # Fenêtre ouverte : poêle coupé, rien d'autre n'est envoyé jusqu'à la reprise
        if st["window"]:
            st["substitution"] = subst
            self._set_current(c)
            if heat:
                await self._svc("climate", "set_hvac_mode", {"entity_id": self.ent(CONF_CLIMATE), "hvac_mode": "off"})
            return

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
                self.schedule_ignite_check(reset=True)
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
    def schedule_ignite_check(self, reset: bool = False) -> None:
        """Allumage demandé : vérifier 4 min plus tard que le poêle démarre, sinon renvoyer l'ordre (2 fois au plus)."""
        if reset:
            self._ignite_tries = 0
        if self._ignite_unsub:
            self._ignite_unsub()
        self._ignite_unsub = async_call_later(self.hass, VERIFY_DELAY, self._on_ignite_check)

    async def _on_ignite_check(self, _now: datetime) -> None:
        self._ignite_unsub = None
        st = self.state
        if not st["planning"] or st["manual"] or st["window"] or not self.esp_available():
            return
        async with self._lock:
            cp = self.by_id(st["current"])
            if cp is None or self.status() != STATUS_OFF:
                return
            cons = float(self.climate_attr("temperature") or cp[F_SETPOINT])
            t_amb = self.climate_attr("current_temperature")
            t_amb = float(t_amb) if t_amb is not None else 99.0
            if cp[F_MODE] == MODE_STANDBY and t_amb >= cons:
                return
            if self._ignite_tries >= 2:
                self._log(f"Allumage {cp[F_NAME]} : le poêle reste à l'arrêt après 3 ordres d'allumage "
                          f"(ambiante {t_amb} °C, consigne {cons} °C).")
                return
            self._ignite_tries += 1
            await self._svc("climate", "set_hvac_mode", {"entity_id": self.ent(CONF_CLIMATE), "hvac_mode": "heat"})
            self._log(f"Allumage {cp[F_NAME]} : poêle toujours à l'arrêt 4 min après l'ordre "
                      f"(ambiante {t_amb} °C, consigne {cons} °C), ordre renvoyé ({self._ignite_tries}/2).")
        self.schedule_ignite_check()

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
        if not st["planning"] or st["forced"] or st["override"] or st["window"] or not self.esp_available():
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
            err_marche = not manuel and kind == K_SLOT and status == STATUS_OFF and self._ignite_unsub is None and (
                cp[F_MODE] != MODE_STANDBY or t_amb < cons)
            err_preset = not manuel and status == STATUS_OK and self.climate_attr("preset_mode") != cp[F_POWER]
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
                self.schedule_ignite_check()
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
        if old is not None and old.state in STATUS_UNAVAILABLE and new.state not in STATUS_UNAVAILABLE:
            self.esp_back_at = dt_util.utcnow()  # retour de l'ESP32 : valeurs relues, pas des réglages
        if eid == self.ent(CONF_STATUS) or (not self.ent(CONF_STATUS) and eid == self.ent(CONF_CLIMATE)):
            self._on_status(old, new)
        if self.alarm_entity and eid in (self.alarm_entity, self.alarm_label_entity):
            self._on_alarm(eid, old, new)
        if self.ignitions_entity and eid == self.ignitions_entity:
            self._on_ignition_counter(old, new)
        if (eid == self.ent(CONF_CLIMATE) and self.state["window"] and old is not None
                and old.state == "off" and new.state == "heat" and new.context and new.context.user_id):
            self._window_override()
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

    @callback
    def _on_call_service(self, event: Event) -> None:
        """Réglage du poêle demandé par un utilisateur : prend la main sur la programmation.

        L'état renvoyé ensuite par l'ESP32 arrive sans utilisateur (message MQTT) : c'est donc
        l'appel de service lui-même, qui porte l'utilisateur, qui sert à reconnaître une action manuelle.
        """
        ctx = event.context
        if ctx is None or ctx.user_id is None:
            return
        d = event.data
        domain, service = d.get("domain"), d.get("service")
        data = d.get("service_data") or {}
        ids = data.get("entity_id") or []
        if isinstance(ids, str):
            ids = [i.strip() for i in ids.split(",")]
        clim, f2, sb = self.ent(CONF_CLIMATE), self.ent(CONF_FAN2), self.ent(CONF_STANDBY)
        if domain == "climate" and clim in ids:
            if service == "set_temperature" and data.get("temperature") is not None:
                self._manual_setpoint(float(data["temperature"]))
            elif service == "set_fan_mode":
                self._manual_request("fan1", data.get("fan_mode"))
            elif service == "set_preset_mode":
                self._manual_request("preset", data.get("preset_mode"))
            elif service in ("set_hvac_mode", "turn_on", "turn_off", "toggle"):
                self._manual_request("marche", data.get("hvac_mode", service))
        elif domain == "select" and f2 and f2 in ids and service == "select_option":
            self._manual_request("fan2", data.get("option"))
        elif domain in ("switch", "homeassistant") and sb and sb in ids and service in ("turn_on", "turn_off", "toggle"):
            cur = self._st(CONF_STANDBY)
            want = "on" if service == "turn_on" else "off" if service == "turn_off" else (
                "off" if cur is not None and cur.state == "on" else "on")
            self._manual_request("standby", want)

    def _manual_setpoint(self, t: float) -> None:
        """Consigne demandée par un utilisateur, différente de la programmation en cours : dérogation."""
        cp = self.by_id(self.state["current"])
        if not self._active_control() or cp is None or abs(t - float(cp[F_SETPOINT])) <= 0.05:
            return
        if not self.state["override"]:
            self.state["override_ref"] = float(cp[F_SETPOINT])
        self.state["override"] = True
        self.async_save()
        self.notify()

    def _manual_request(self, what: str, value: Any) -> None:
        st = self.state
        cp = self.by_id(st["current"])
        if not self._active_control() or st["manual"] or cp is None or value is None:
            return
        if what != "marche" and value == self._expected(what, cp, value):
            return
        st["manual"] = True
        names = {"fan1": "ventilation 1", "fan2": "ventilation 2", "preset": "puissance",
                 "standby": "stand-by", "marche": "marche/arrêt"}
        self._log(f"Réglage manuel ({names[what]} : {value}, depuis Home Assistant) : la programmation ne renverra "
                  "plus ventilations, puissance, stand-by ni marche/arrêt jusqu'au prochain changement de plage.")
        self.async_save()
        self.notify()

    # ------------------------------------------------------------------ historique des allumages
    def _on_ignition_counter(self, old: State | None, new: State) -> None:
        """Allumage = le compteur du poêle augmente (fiable même après une coupure de l'ESP32)."""
        try:
            before, after = int(float(old.state)), int(float(new.state))
        except (AttributeError, TypeError, ValueError):
            return
        if after > before:
            self._record_start(dt_util.utcnow())

    def _record_start(self, when: datetime) -> None:
        if self.ignitions and self.ignitions[0].get("end") is None:
            self.ignitions[0]["end"] = "?"  # arrêt précédent non vu
        self.ignitions.insert(0, {"start": when.isoformat(), "end": None})
        self._prune_ignitions()
        self.async_save()
        self.notify()

    def _record_stop(self, when: datetime) -> None:
        if self.ignitions and self.ignitions[0].get("end") is None:
            self.ignitions[0]["end"] = when.isoformat()
            self.async_save()
            self.notify()

    def _prune_ignitions(self) -> None:
        """Garde les allumages des derniers jours (aujourd'hui compris)."""
        start = dt_util.start_of_local_day() - timedelta(days=HISTORY_DAYS - 1)
        keep = []
        for i, rec in enumerate(self.ignitions):
            t = dt_util.parse_datetime(rec.get("start") or "")
            if t is None or (t < start and i > 0):
                continue
            keep.append(rec)
        self.ignitions = keep[:60]

    @staticmethod
    def _legacy_time(text: str, now: datetime) -> datetime | None:
        """« jj/mm hh:mm » en heure locale ; l'année est celle qui ne place pas la date dans le futur."""
        m = _LEGACY_RE.match(text.strip())
        if not m:
            return None
        day, month, hour, minute = (int(x) for x in m.groups())
        for year in (now.year, now.year - 1):
            try:
                t = datetime(year, month, day, hour, minute, tzinfo=dt_util.get_default_time_zone())
            except ValueError:
                continue
            if t <= now + timedelta(days=1):
                return t
        return None

    @callback
    def _on_legacy_log(self, _event: Event) -> None:
        self._import_legacy()

    def _import_legacy(self) -> None:
        """Fusionne l'historique d'une automatisation existante (allumages et arrêts en input_text)."""
        starts_id, stops_id = self.legacy_logs
        st = self.hass.states.get(starts_id) if starts_id else None
        if st is None or st.state in ("", *STATUS_UNAVAILABLE):
            return
        sp = self.hass.states.get(stops_id) if stops_id else None
        stops = sp.state.split(";") if sp is not None and sp.state not in ("", *STATUS_UNAVAILABLE) else []
        now = dt_util.now()
        recs = {}
        for rec in self.ignitions:
            t = dt_util.parse_datetime(rec.get("start") or "")
            if t is not None:
                recs[t] = rec
        changed = False
        for i, text in enumerate(st.state.split(";")):
            start = self._legacy_time(text, now)
            if start is None:
                continue
            raw = stops[i].strip() if i < len(stops) else "?"
            if raw == "-":
                end = None if i == 0 else "?"
            else:
                t = self._legacy_time(raw, now)
                end = t.isoformat() if t is not None and t >= start else "?"
            same = next((r for t, r in recs.items() if abs((t - start).total_seconds()) < 180), None)
            if same is None:
                recs[start] = {"start": start.isoformat(), "end": end}
                changed = True
            elif same.get("end") in (None, "?") and end not in (None, "?") and same.get("end") != end:
                same["end"] = end  # arrêt vu par l'automatisation et pas par l'intégration
                changed = True
        if not changed:
            return
        self.ignitions = [recs[t] for t in sorted(recs, reverse=True)]
        self._prune_ignitions()
        self.async_save()
        self.notify()

    # ------------------------------------------------------------------ historique des alarmes
    def _alarm_label(self) -> str | None:
        s = self.hass.states.get(self.alarm_label_entity) if self.alarm_label_entity else None
        if s is None or s.state in ("", "Aucune", "None", "none", *STATUS_UNAVAILABLE):
            return None
        return s.state

    @callback
    def _on_alarm(self, eid: str, old: State | None, new: State) -> None:
        """Début (alarme qui passe à on) et fin (retour à off) ; libellé complété quand il arrive."""
        now = dt_util.utcnow().isoformat()
        cur = self.alarms[0] if self.alarms and self.alarms[0].get("end") is None else None
        changed = False
        if eid == self.alarm_entity:
            if new.state == "on" and cur is None and (old is None or old.state != "on"):
                self.alarms.insert(0, {"start": now, "end": None, "label": self._alarm_label()})
                self.alarms = self.alarms[:ALARM_HISTORY]
                changed = True
            elif new.state == "off" and cur is not None:
                cur["end"] = now
                cur["label"] = cur.get("label") or self._alarm_label()
                changed = True
        elif cur is not None and not cur.get("label") and self._alarm_label():
            cur["label"] = self._alarm_label()
            changed = True
        if changed:
            self.async_save()
            self.notify()

    def alarm_history(self) -> list[dict[str, Any]]:
        return self.alarms

    def ignition_history(self) -> list[dict[str, Any]]:
        self._prune_ignitions()
        return self.ignitions

    def _on_status(self, old: State | None, new: State) -> None:
        now = dt_util.utcnow()
        self._reservoir_status(new.state, now)
        if new.state in (STATUS_OFF, *STATUS_STOPPING):
            self._record_stop(now)
        elif not self.ignitions_entity and old is not None and old.state == STATUS_OFF \
                and new.state not in STATUS_NOT_BURNING:
            self._record_start(now)  # pas de compteur : sortie de « Off »
        was = old.state if old else None
        if new.state == STATUS_OK and was not in (STATUS_OK, *STATUS_UNAVAILABLE):
            self.hass.async_create_task(self._power_on_run())
        if was in STATUS_UNAVAILABLE and new.state not in STATUS_UNAVAILABLE:
            if self._esp_unsub:
                self._esp_unsub()
            self._esp_unsub = async_call_later(self.hass, ESP_BACK_DELAY, self._on_esp_back)
        elif new.state in STATUS_UNAVAILABLE and self._esp_unsub:
            self._esp_unsub()
            self._esp_unsub = None
        self.notify()

    async def _power_on_run(self) -> None:
        """Le poêle passe en marche : la puissance de la programmation (remise à Auto pendant l'allumage) est renvoyée."""
        st = self.state
        if not st["planning"] or st["manual"]:
            return
        cp = self.by_id(st["current"])
        if cp is None or not cp.get(F_POWER) or self.climate_attr("preset_mode") == cp[F_POWER]:
            return
        async with self._lock:
            self.last_apply = dt_util.utcnow()
            await self._svc("climate", "set_preset_mode", {"entity_id": self.ent(CONF_CLIMATE), "preset_mode": cp[F_POWER]})
        self._log(f"{cp[F_NAME]} : poêle en marche, puissance {cp[F_POWER]} renvoyée (remise à Auto pendant l'allumage).")

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
        if not user:
            # Valeurs relues au retour de l'ESP32 : pas un réglage fait à la main
            if self.esp_back_at and not self._guard(self.esp_back_at, ESP_BACK_DELAY + 30):
                return
            # Puissance remise d'elle-même par le poêle hors de la phase de marche (arrêt, allumage,
            # extinction) : la puissance manuelle ne s'applique qu'en marche
            if what == "preset" and self.status() != STATUS_OK:
                return
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

    async def _on_midnight(self, now: datetime) -> None:
        if self.state["relax_manual"]:
            self.state["relax_manual"] = False
            await self.async_apply(K_RELAX_END)
        # Jours fériés : relus chaque nuit ; entrée ou sortie d'un jour férié -> plages recalculées
        today = dt_util.as_local(now).date()
        before = self.holiday_mode(today), self.holiday_mode(today - timedelta(days=1))
        await self.async_refresh_holidays()
        after = self.holiday_mode(today), self.holiday_mode(today - timedelta(days=1))
        if before != after or after[0] != after[1]:
            self.schedule_next_slot()
            if self.target() != self.state.get("current"):
                await self.async_apply(K_SLOT)

    # ------------------------------------------------------------------ fenêtres ouvertes
    def windows(self) -> list[str]:
        return [e for e in (self.cfg.get(CONF_WINDOWS) or []) if e]

    def open_windows(self) -> list[str]:
        return [e for e in self.windows() if (s := self.hass.states.get(e)) is not None and s.state == "on"]

    def window_names(self, ids: list[str]) -> list[str]:
        return [((s.attributes.get("friendly_name") if (s := self.hass.states.get(e)) else None) or e) for e in ids]

    def _window_delay(self, key: str) -> float:
        try:
            return max(0.0, min(60.0, float(self.cfg.get(key) or 0))) * 60
        except (TypeError, ValueError):
            return 0.0

    @callback
    def _on_window_event(self, _event: Event) -> None:
        self._windows_changed()

    @callback
    def _windows_changed(self) -> None:
        """Ouverture : coupure après le délai. Toutes fermées : reprise après le délai."""
        st = self.state
        if self.open_windows():
            if self._win_close_unsub:
                self._win_close_unsub()
                self._win_close_unsub = None
                self.window_resume_at = None
            if not st["window"] and not st["window_override"] and self._win_open_unsub is None:
                d = self._window_delay(CONF_WINDOW_OPEN_DELAY)
                self.window_cut_at = dt_util.utcnow() + timedelta(seconds=d)
                self._win_open_unsub = async_call_later(self.hass, d, self._on_window_cut)
        else:
            if self._win_open_unsub:
                self._win_open_unsub()
                self._win_open_unsub = None
                self.window_cut_at = None
            if st["window_override"]:
                st["window_override"] = False
                self.async_save()
            if st["window"] and self._win_close_unsub is None:
                d = self._window_delay(CONF_WINDOW_CLOSE_DELAY)
                self.window_resume_at = dt_util.utcnow() + timedelta(seconds=d)
                self._win_close_unsub = async_call_later(self.hass, d, self._on_window_resume)
        self.notify()

    async def _on_window_cut(self, _now: datetime | None = None) -> None:
        self._win_open_unsub = None
        self.window_cut_at = None
        st = self.state
        opened = self.open_windows()
        if not opened or st["window"] or st["window_override"]:
            return
        lit = self.climate_heat() or self.status() not in STATUS_NOT_BURNING
        st["window"] = True
        st["window_heat"] = lit
        st["window_since"] = dt_util.utcnow().isoformat()
        if self._ignite_unsub:
            self._ignite_unsub()
            self._ignite_unsub = None
        self._log(f"Fenêtre ouverte ({', '.join(self.window_names(opened))}) : "
                  + ("poêle coupé, la programmation reprendra à la fermeture." if lit
                     else "le poêle est à l'arrêt, la programmation ne l'allumera pas tant qu'elle est ouverte."),
                  self.ent(CONF_CLIMATE))
        await self.async_apply(K_WINDOW)

    async def _on_window_resume(self, _now: datetime | None = None) -> None:
        self._win_close_unsub = None
        self.window_resume_at = None
        st = self.state
        if self.open_windows() or not st["window"]:
            return
        st["window"] = False
        was = st["window_heat"]
        st["window_heat"] = False
        st["window_since"] = None
        if st["planning"] or st["forced"]:
            self._log("Fenêtres fermées : reprise de la programmation.", self.ent(CONF_CLIMATE))
            await self.async_apply(K_WINDOW_END)
            self.schedule_verify(K_SLOT)
        else:
            if was:
                self._log("Fenêtres fermées : poêle rallumé (il était allumé avant l'ouverture).", self.ent(CONF_CLIMATE))
                await self._svc("climate", "set_hvac_mode", {"entity_id": self.ent(CONF_CLIMATE), "hvac_mode": "heat"})
            self.async_save()
            self.notify()

    @callback
    def _window_override(self) -> None:
        """Poêle rallumé à la main fenêtre ouverte : la coupure est levée jusqu'à la fermeture."""
        st = self.state
        st["window"] = False
        st["window_heat"] = False
        st["window_since"] = None
        st["window_override"] = True
        if self._win_close_unsub:
            self._win_close_unsub()
            self._win_close_unsub = None
            self.window_resume_at = None
        self._log("Poêle rallumé à la main fenêtre ouverte : pas de nouvelle coupure avant la fermeture des fenêtres.",
                  self.ent(CONF_CLIMATE))
        self.async_save()
        self.notify()

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
        await self._store.async_save({"profiles": self.profiles, "state": self.state, "reservoir": self.reservoir, "ignitions": self.ignitions, "alarms": self.alarms})
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
                # L'ESP32 ne connaît pas les jours fériés : jours de la semaine seulement ;
                # une programmation « jours fériés » seule n'est pas envoyée (désactivée)
                j = sum(1 << d for d in (p.get(F_DAYS) or ALL_DAYS) if d < HOLIDAY)
                item["j"] = j or 127
                if not j:
                    item["a"] = 0
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
        if self.observe:
            # Mode observation : rien n'est envoyé à l'ESP32, pas même le planning de secours
            self._log(f"Observation : planning de secours non publié sur {topic} "
                      f"({sum(1 for p in self.profiles if p[F_ACTIVE])} plage(s) active(s))", self.ent(CONF_CLIMATE))
            return
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

    def _import_legacy_reservoir(self) -> None:
        """Reprise unique du suivi de réservoir tenu par une automatisation (vue Poêle).

        Heures depuis le remplissage, durées des derniers réservoirs, dernier chargement et seuil d'alerte,
        trouvés par leur nom (…heures_depuis_remplissage, …durees_reservoirs, …dernier_chargement,
        …seuil_alerte_reservoir). Fait une seule fois : les réglages faits ensuite ne sont pas écrasés.
        """
        if self.state.get("legacy_reservoir"):
            return
        from .config_flow import detect_reservoir_logs  # noqa: PLC0415

        found = detect_reservoir_logs(self.hass)

        def num(key: str) -> float | None:
            st = self.hass.states.get(found[key]) if key in found else None
            try:
                return float(st.state) if st is not None else None
            except ValueError:
                return None

        r = self.reservoir
        done = []
        st = self.hass.states.get(found["durations"]) if "durations" in found else None
        if st is not None and st.state not in ("", *STATUS_UNAVAILABLE):
            durations = []
            for x in st.state.split(";"):
                try:
                    durations.append(round(float(x.replace(",", ".")), 1))
                except ValueError:
                    continue
            if durations:
                r["durations"] = durations[:10]
                done.append("durées")
        hours = num("hours")
        if hours is not None and hours >= 0:
            r["hours"] = hours
            r["since"] = dt_util.utcnow().isoformat() if self.status() not in STATUS_NOT_BURNING else None
            done.append("heures")
        load = num("load")
        if load and r.get("last_load") is None:
            r["last_load"] = round(load, 1)
            done.append("dernier chargement")
        threshold = num("threshold")
        if threshold and not float(self.state.get("alert_threshold") or 0):
            self.state["alert_threshold"] = threshold
            done.append("seuil")
        if not done:
            return
        r["alerted"] = self.reservoir_low()  # pas de nouvelle alerte pour un seuil déjà dépassé
        self.state["legacy_reservoir"] = True
        self._log("Réservoir de granulés repris de l'automatisation existante : " + ", ".join(done) + ".")
        self.async_save()
        self.notify()

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
