/*
 * Edilkamin Control Card
 * Carte Lovelace pour le pilotage d'un poêle Edilkamin (firmware Edilkamin Control ESP32)
 * et la programmation de l'intégration Edilkamin Control.
 * Aucune dépendance (pas de button-card, card-mod, stack-in-card).
 */
const ECC_VERSION = "2026.11.16";

// Échappement HTML de toute valeur venant de Home Assistant ou de la configuration
// (noms de programmation, états, options, libellés d'alarme, noms d'entités…)
const ECC_ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const eccE = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ECC_ESC[c]);

const ECC_I18N = {
  fr: {
    title: "Poêle",
    off: "Éteint", ignition: "Allumage", on: "En chauffe", shutdown: "Extinction",
    alarm: "Alarme", standby_wait: "En veille (Stand-by)", unknown: "Inconnu", unavailable: "Indisponible",
    lit: "Allumé", unlit: "Éteint", confirm_on: "Allumer ?", confirm_off: "Éteindre ?",
    power: "Puissance", power_auto: "Auto", in_progress: "en cours",
    setpoint: "Consigne", room: "Ambiante", current_temp: "Température actuelle", hvac_heat: "Chauffage", hvac_off: "Éteint", fans: "Ventilation & modes",
    fan1: "Ventilation 1", fan2: "Ventilation 2", relax: "Relax (silence)", standby: "Stand-by",
    stopped: "arrêté", stop: "Arrêt",
    planning: "Programmation", planning_on: "Programmation activée", planning_off: "Programmation désactivée",
    no_profile: "Aucun profil", forced: "forcé", automatic: "Automatique",
    override: "Consigne manuelle", override_txt: "maintenue jusqu’au prochain changement de plage",
    manual: "Réglages manuels", manual_txt: "ventilations, puissance, stand-by gardés jusqu’à",
    next_slot: "la prochaine plage", relax_txt: "silence (Relax) gardé jusqu’à minuit",
    win_cut: "Fenêtre ouverte : poêle coupé", win_closed: "Fenêtres fermées : poêle coupé", win_wait: "Fenêtre ouverte", win_cut_at: "coupure du poêle à", win_resume_close: "la programmation reprendra à la fermeture",
    win_resume_at: "reprise de la programmation à", give_back: "Rendre la main", cancel: "Annuler",
    profile: "Profil", mode_run: "Marche", mode_standby: "Stand-by", all_day: "toute la journée",
    tracking: "Suivi", last24: "24 dernières heures", ignitions: "Allumages",
    alarm_now: "Alarme en cours", none: "Aucune", pellets: "Granulés", pellets_ok: "OK", pellets_low: "Réserve",
    temp: "Température", power_short: "Puiss.", exhaust: "Fumées",
    silence: "Silence", days: ["L", "M", "M", "J", "V", "S", "D"], every_day: "tous les jours", weekdays: "lun.–ven.", weekend: "sam.–dim.",
    add_profile: "Ajouter une programmation", del: "Supprimer", confirm_del: "Supprimer ?", close: "Fermer",
    name: "Nom", start: "Début", end: "Fin", fan1s: "Ventil. 1", fan2s: "Ventil. 2",
    manage: "Gérer les programmations", schedules: "Programmations", new_schedule: "Nouvelle programmation", create: "Créer",
    new_name: "Nouvelle", if_away: "Si absent", move_up: "Monter", move_down: "Descendre",
    reservoir: "Réservoir de granulés", res_hours: "Chauffe depuis le remplissage", last_load: "Dernier chargement",
    last_res: "Durée du dernier réservoir", avg_res: "Durée moyenne d’un réservoir", res_auto: "Autonomie estimée du réservoir",
    alert_after: "Alerte après (0 = désactivée)", stove_reserve: "Réserve signalée par le poêle", stock_left: "Stock restant (Suivi Stock Pellet)",
    stock_auto: "Autonomie du stock", filled: "Réservoir rempli", poured: "J’ai versé", bags: "sac(s)", confirm_fill: "Confirmer ?",
    reserve_low: "Réserve", ok: "OK", pending2: "après 2 réservoirs", bag_unit: "sacs", bag_one: "sac",
    ign_title: "Allumages des 3 derniers jours", ign_on: "Allumage", ign_off: "Arrêt", duration: "Durée", running: "en cours",
    today: "Aujourd’hui", yesterday: "Hier", total: "Total", average: "Moyenne", no_ign: "Aucun allumage enregistré.", counter: "Compteur du poêle",
    ign_one: "allumage", ign_many: "allumages", priority: "En cas de chevauchement, la programmation la plus haute dans la liste l’emporte.", back: "Retour",
  },
  en: {
    title: "Stove",
    off: "Off", ignition: "Igniting", on: "Heating", shutdown: "Shutting down",
    alarm: "Alarm", standby_wait: "Standby (waiting)", unknown: "Unknown", unavailable: "Unavailable",
    lit: "On", unlit: "Off", confirm_on: "Turn on?", confirm_off: "Turn off?",
    power: "Power", power_auto: "Auto", in_progress: "now",
    setpoint: "Setpoint", room: "Room", current_temp: "Current temperature", hvac_heat: "Heat", hvac_off: "Off", fans: "Fans & modes",
    fan1: "Fan 1", fan2: "Fan 2", relax: "Relax (silent)", standby: "Standby",
    stopped: "stopped", stop: "Off",
    planning: "Schedule", planning_on: "Schedule enabled", planning_off: "Schedule disabled",
    no_profile: "No profile", forced: "forced", automatic: "Automatic",
    override: "Manual setpoint", override_txt: "kept until the next slot change",
    manual: "Manual settings", manual_txt: "fans, power, standby kept until",
    next_slot: "the next slot", relax_txt: "silent mode (Relax) kept until midnight",
    win_cut: "Window open: stove off", win_closed: "Windows closed: stove off", win_wait: "Window open", win_cut_at: "stove turned off at", win_resume_close: "the schedule resumes once closed",
    win_resume_at: "schedule resumes at", give_back: "Give back", cancel: "Cancel",
    profile: "Profile", mode_run: "Run", mode_standby: "Standby", all_day: "all day",
    tracking: "Tracking", last24: "Last 24 hours", ignitions: "Ignitions",
    alarm_now: "Current alarm", none: "None", pellets: "Pellets", pellets_ok: "OK", pellets_low: "Low",
    temp: "Temperature", power_short: "Power", exhaust: "Exhaust",
    silence: "Silent", days: ["M", "T", "W", "T", "F", "S", "S"], every_day: "every day", weekdays: "Mon–Fri", weekend: "Sat–Sun",
    add_profile: "Add a schedule", del: "Delete", confirm_del: "Delete?", close: "Close",
    name: "Name", start: "Start", end: "End", fan1s: "Fan 1", fan2s: "Fan 2",
    manage: "Manage schedules", schedules: "Schedules", new_schedule: "New schedule", create: "Create",
    new_name: "New", if_away: "If away", move_up: "Move up", move_down: "Move down",
    reservoir: "Pellet hopper", res_hours: "Burn time since refill", last_load: "Last load",
    last_res: "Last hopper duration", avg_res: "Average hopper duration", res_auto: "Estimated hopper autonomy",
    alert_after: "Alert after (0 = off)", stove_reserve: "Reserve reported by the stove", stock_left: "Stock left (Suivi Stock Pellet)",
    stock_auto: "Stock autonomy", filled: "Hopper refilled", poured: "I poured", bags: "bag(s)", confirm_fill: "Confirm?",
    reserve_low: "Reserve", ok: "OK", pending2: "after 2 hoppers", bag_unit: "bags", bag_one: "bag",
    ign_title: "Ignitions of the last 3 days", ign_on: "Ignition", ign_off: "Stop", duration: "Duration", running: "running",
    today: "Today", yesterday: "Yesterday", total: "Total", average: "Average", no_ign: "No ignition recorded.", counter: "Stove counter",
    ign_one: "ignition", ign_many: "ignitions", priority: "When schedules overlap, the one highest in the list wins.", back: "Back",
  },
};

// Images intégrées : « bild9 » (Bild 9+, par défaut) et « generic » (dessin). Vitre en % d'un cadre 140 × 212.
const ECC_IMAGES = {
  bild9: { src: "/edilkamin_control/bild9.svg", window: { x: 57.8, y: 34.9, width: 29.5, height: 33.5 } },
};

// Suffixes des entités du firmware (même appareil que le thermostat)
const ECC_DEVICE_KEYS = {
  status: ["sensor", ["_status", "_statut"]],
  alarm: ["binary_sensor", ["_alarme", "_alarm"]],
  alarm_label: ["sensor", ["_alarme_en_cours", "_alarm_label"]],
  fan2: ["select", ["_ventilation_2", "_fan_2", "_fan2"]],
  relax: ["switch", ["_relax"]],
  standby: ["switch", ["_standby"]],
  real_power: ["sensor", ["_puissance_reelle", "_real_power"]],
  real_fan1: ["sensor", ["_ventilation_1_reelle", "_real_fan1"]],
  real_fan2: ["sensor", ["_ventilation_2_reelle", "_real_fan2"]],
  pellet: ["sensor", ["_pellet_level", "_reserve_granules"]],
  ignitions: ["sensor", ["_nombre_d_allumages", "_ignitions"]],
  exhaust: ["sensor", ["_exhaust_temperature", "_temperature_fumees"]],
};

// Entités de l'intégration Edilkamin Control (clés de traduction)
const ECC_PLANNER_KEYS = {
  planning: "planning",            // switch : programmation activée
  current_profile: "current_profile", // sensor : nom du profil appliqué
  forced_profile: "forced_profile",   // select : Automatique / Profil 1..n
  override: "override",            // switch : dérogation de consigne (attribut reference)
  manual: "manual_settings",       // switch : réglages manuels (attribut until)
  relax_prio: "relax_priority",
  window_cut: "window_cut",        // binary_sensor : fenêtre ouverte, poêle coupé (attributs open_windows, cut_at, resume_at)    // switch : silence (Relax) activé à la main, prioritaire jusqu'à minuit
  res_hours: "reservoir_hours",    // sensor : heures de chauffe depuis le remplissage
  res_avg: "reservoir_average",    // sensor : durée moyenne d'un réservoir (attribut durations)
  res_auto: "reservoir_autonomy",  // sensor : autonomie estimée du réservoir
  stock_auto: "stock_autonomy",    // sensor : autonomie du stock (Suivi Stock Pellet)
  res_alert: "reservoir_alert",    // number : seuil d'alerte (h)
  res_filled: "reservoir_filled",  // button : réservoir rempli
  res_low: "reservoir_low",        // binary_sensor : réservoir bientôt vide
  ign_hist: "last_ignition",       // sensor : dernier allumage (attribut history, 3 jours)
};
const ECC_PROFILE_KEYS = ["profile_active", "profile_start", "profile_end", "profile_setpoint", "profile_mode", "profile_name",
  "profile_power", "profile_fan1", "profile_fan2", "profile_relax", "profile_absent"];
const eccIsSb = (m) => /^stand/i.test(String(m || ""));
// Services de l'intégration utilisés par la carte
const ECC_DOMAIN = "edilkamin_control";

class EdilkaminControlCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._sig = "";
    this._confirm = null;
    this._hist = null;
    this._histAt = 0;
    this._histLoading = false;
    this._page = null;
    this._draft = null;
  }

  static getConfigElement() { return document.createElement("edilkamin-control-card-editor"); }

  static getStubConfig(hass) {
    // Thermostat proposé : celui dont l'appareil porte un capteur de statut du firmware, sinon un nom « edilkamin »
    const reg = hass.entities || {};
    const climates = Object.keys(hass.states).filter((e) => e.startsWith("climate."));
    const withStatus = climates.find((c) => {
      const dev = reg[c]?.device_id;
      return dev && Object.keys(reg).some((e) => reg[e].device_id === dev && /^sensor\..*_(status|statut)$/.test(e));
    });
    return { climate: withStatus || climates.find((e) => e.includes("edilkamin")) || climates[0] || "climate.edilkamin" };
  }

  setConfig(config) {
    if (!config || !config.climate) throw new Error("Edilkamin Control Card : « climate » est obligatoire");
    this._config = Object.assign(
      { show_header: true, show_modes: true, show_planning: true, show_tracking: true, show_graph: true, image: null, mode: "full" },
      config
    );
    this._resolved = null;
    this._sig = "";
  }

  getCardSize() { return 14; }
  getGridOptions() { return { columns: 12, min_columns: 6 }; }

  set hass(hass) {
    this._hass = hass;
    // Registre des entités modifié (programmation ajoutée ou supprimée) : nouvelle résolution
    // … ou ordre des programmations modifié (même entités, attribut « profile » renuméroté)
    const ord = this._orderSig(hass);
    if (!this._resolved || (hass.entities && hass.entities !== this._ents) || ord !== this._ord) {
      this._ents = hass.entities; this._ord = ord; this._resolve();
    }
    const sig = this._signature();
    if (sig !== this._sig) {
      this._sig = sig;
      this._render();
    }
    if (this._config.show_tracking && this._config.show_graph) this._loadHistory();
  }

  _orderSig(hass) {
    const reg = hass.entities || {};
    return Object.keys(reg).filter((e) => reg[e].platform === "edilkamin_control" && reg[e].translation_key === "profile_active")
      .map((e) => e + ":" + (hass.states[e]?.attributes?.profile ?? "")).sort().join("|");
  }

  /* ------------------------------------------------------------ entités */
  _t(k) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "fr").slice(0, 2);
    return (ECC_I18N[lang] || ECC_I18N.en)[k] || ECC_I18N.fr[k] || k;
  }

  _resolve() {
    const h = this._hass, cfg = this._config, r = { climate: cfg.climate };
    const reg = h.entities || {};
    const dev = reg[cfg.climate]?.device_id;
    const siblings = dev ? Object.keys(reg).filter((e) => reg[e].device_id === dev) : Object.keys(h.states);
    for (const [key, [domain, suffixes]] of Object.entries(ECC_DEVICE_KEYS)) {
      if (cfg[key]) { r[key] = cfg[key]; continue; }
      r[key] = siblings.find((e) => e.startsWith(domain + ".") && suffixes.some((s) => e.endsWith(s))) || null;
    }
    // Intégration Edilkamin Control : par clé de traduction
    const planner = Object.keys(reg).filter((e) => reg[e].platform === "edilkamin_control");
    for (const [key, tk] of Object.entries(ECC_PLANNER_KEYS)) {
      r[key] = cfg[key] || planner.find((e) => reg[e].translation_key === tk) || null;
    }
    const profiles = {};
    for (const e of planner) {
      const tk = reg[e].translation_key;
      if (!ECC_PROFILE_KEYS.includes(tk)) continue;
      const n = Number(h.states[e]?.attributes?.profile);
      if (!n) continue;
      profiles[n] = profiles[n] || { n };
      profiles[n][tk.replace("profile_", "")] = e;
    }
    r.profiles = cfg.profiles || Object.values(profiles).sort((a, b) => a.n - b.n);
    this._resolved = r;
  }

  _s(key) { const e = this._resolved?.[key]; return e ? this._hass.states[e] : undefined; }
  _v(key) { return this._s(key)?.state; }

  _signature() {
    const r = this._resolved, ids = [];
    for (const k of Object.keys(r)) if (typeof r[k] === "string") ids.push(r[k]);
    for (const p of r.profiles || []) for (const k of Object.keys(p)) if (k !== "n") ids.push(p[k]);
    const now = new Date();
    if (this._config?.temperature_entity) ids.push(this._config.temperature_entity);
    return ids.map((e) => this._hass.states[e]?.last_updated || "").join("|") + "|" + now.getHours() + now.getMinutes() + "|" + (this._confirm || "") + "|" + (this._page ?? "") + JSON.stringify(this._draft || "") + "|" + (this._hist ? this._histAt : 0);
  }

  _call(domain, service, data) { this._hass.callService(domain, service, data); }
  _moreInfo(entityId) {
    const ev = new Event("hass-more-info", { bubbles: true, composed: true });
    ev.detail = { entityId };
    this.dispatchEvent(ev);
  }

  /* ------------------------------------------------------------ état */
  _phase() {
    const st = this._v("status");
    if (this._v("alarm") === "on") return "alarm";
    if (!st || st === "unavailable") return "unavailable";
    if (st === "unknown") return "unknown";
    if (st === "Off") return "off";
    if (st === "Ok") return "on";
    if (st === "Shutdown" || st === "Extinction") return "shutdown";
    return "ignition";
  }

  _isOn() {
    const ph = this._phase();
    return this._v("climate") === "heat" || ["on", "ignition", "shutdown"].includes(ph);
  }

  _fmt(v, d = 1) {
    const n = Number(v);
    if (!Number.isFinite(n)) return "—";
    return n.toLocaleString(this._hass?.locale?.language || "fr", { minimumFractionDigits: d, maximumFractionDigits: d });
  }

  _realPower() {
    const pr = this._s("climate")?.attributes?.preset_mode || "Auto";
    if (pr.startsWith("Man. P")) return pr.slice(-1);
    const r = Number(this._v("real_power"));
    return r ? String(r) : null;
  }

  /* ------------------------------------------------------------ rendu */
  _render() {
    if (!this._hass || !this._resolved) return;
    const c = this._config;
    const parts = [];
    if (c.mode === "planning") {
      // Carte « menu » autonome : le gestionnaire de programmations seul
      this.shadowRoot.innerHTML = `<style>${ECC_CSS}</style><ha-card class="mgr-card">${this._manager(false)}</ha-card>`;
      this._bind();
      return;
    }
    if (c.show_header) parts.push(this._header());
    if (c.show_modes) parts.push(this._modes());
    // Programmation : la liste suit show_planning ; bandeaux et « Gérer les programmations » restent toujours
    if (this._resolved.planning || this._resolved.profiles.length) parts.push(this._planning(c.show_planning !== false));
    if (c.show_tracking) parts.push(this._tracking());
    const ov = this._page !== null ? `<div class="overlay" data-act="close-bg"><div class="sheet">${this._manager(true)}</div></div>` : "";
    this.shadowRoot.innerHTML = `<style>${ECC_CSS}</style><ha-card>${parts.join('<div class="sep"></div>')}</ha-card>${ov}`;
    this._bind();
  }

  _bind() {
    this.shadowRoot.querySelectorAll("[data-act]").forEach((el) => el.addEventListener("click", (ev) => this._onAction(ev, el)));
    this.shadowRoot.querySelectorAll("select[data-sel]").forEach((el) => el.addEventListener("change", () => this._onSelect(el)));
    this.shadowRoot.querySelectorAll("select[data-dd]").forEach((el) => el.addEventListener("change", () => this._onDD(el)));
    this.shadowRoot.querySelectorAll("input[data-in]").forEach((el) => el.addEventListener("change", () => this._onInput(el)));
    this.shadowRoot.querySelectorAll("[data-hold]").forEach((el) => el.addEventListener("pointerdown", (ev) => { ev.preventDefault(); ev.stopPropagation(); this._holdStart(el); }));
    this.shadowRoot.querySelectorAll("[data-f]").forEach((el) => {
      if (el.tagName !== "INPUT" && el.tagName !== "SELECT") return;
      el.addEventListener("change", () => { if (el.value) this._setField(el.dataset.n === "new" ? "new" : Number(el.dataset.n), el.dataset.f, el.value); });
    });
  }

  _header() {
    const ph = this._phase(), clim = this._s("climate"), a = clim?.attributes || {};
    const sb = this._v("standby") === "on";
    const veille = this._v("climate") === "heat" && sb && ph === "off";
    const ST = { off: ["off", "var(--secondary-text-color)"], ignition: ["ignition", "#ffb74d"], on: ["on", "#ff7043"],
      shutdown: ["shutdown", "#ffb74d"], alarm: ["alarm", "#e53935"], unknown: ["unknown", "#9e9e9e"], unavailable: ["unavailable", "#9e9e9e"] };
    let [stk, stc] = ST[ph] || ST.unknown;
    if (veille) [stk, stc] = ["standby_wait", "#ffab40"];
    const alarmLabel = this._v("alarm_label");
    const etat = ph === "alarm" && alarmLabel && alarmLabel !== "Aucune" ? alarmLabel : this._t(stk);

    // profil
    const forced = this._v("forced_profile");
    const opts = this._s("forced_profile")?.attributes?.options || [];
    const prof = this._v("current_profile");
    const profTxt = !this._resolved.current_profile ? "" :
      (!prof || prof === "Aucun" || prof === "none" ? this._t("no_profile") : prof + (forced && opts[0] && forced !== opts[0] ? " · " + this._t("forced") : ""));
    const profChip = this._resolved.forced_profile
      ? `<label class="chip sel"><ha-icon icon="mdi:calendar-clock"></ha-icon><span>${eccE(profTxt)}</span><ha-icon icon="mdi:chevron-down"></ha-icon>
           <select data-sel="forced_profile">${opts.map((o) => `<option value="${eccE(o)}" ${o === forced ? "selected" : ""}>${eccE(o)}</option>`).join("")}</select></label>`
      : (profTxt ? `<span class="chip"><ha-icon icon="mdi:calendar-clock"></ha-icon><span>${eccE(profTxt)}</span></span>` : "");

    // infos
    const pr = a.preset_mode || "Auto";
    const p = this._realPower();
    const puis = pr === "Auto" ? `${this._t("power")} ${this._t("power_auto")}${p ? ` (P${eccE(p)} ${this._t("in_progress")})` : ""}` : `${this._t("power")} ${eccE(pr.replace("Man. ", ""))}`;
    const relax = this._v("relax") === "on";
    const real = (k) => { const v = this._v(k); return v === undefined || v === "unknown" || v === "unavailable" ? null : Number(v); };
    const rf = (k) => { const v = real(k); return v === null ? "" : v ? ` (${v}%)` : ` (${this._t("stopped")})`; };
    const lbl = (m) => (!m ? "—" : m === "Auto" ? "Auto" : eccE(m));
    const fan2 = this._v("fan2");
    const ventil = relax
      ? `<span class="green">${this._t("relax")}</span>`
      : `V1 ${lbl(a.fan_mode)}${rf("real_fan1")}${this._resolved.fan2 ? ` · V2 ${lbl(fan2)}${rf("real_fan2")}` : ""}`;
    const low = this._v("pellet") === "Empty";

    const on = this._isOn();
    const conf = this._confirm === "power";
    return `
    <div class="head">
      <div class="title">${eccE(this._config.title || this._t("title"))}${this._thermometer()}</div>
      <div class="hdr-right">${profChip}</div>
      <div class="state" style="color:${stc}">${eccE(etat)}</div>
      <div class="anim">${this._stove(ph, veille, low)}</div>
      <div class="thermo">${this._dial(a, ph)}</div>
      <div class="infos">${puis}<br>${ventil}${low ? `<br><span class="red">⚠ ${this._t("pellets_low")}</span>` : ""}</div>
    </div>
    <div class="row2">
      <button class="btn ${on ? "hot" : ""} ${conf ? "confirm" : ""}" data-act="power">
        <ha-icon icon="${on ? "mdi:fire" : "mdi:fire-off"}"></ha-icon>
        <span>${conf ? this._t(on ? "confirm_off" : "confirm_on") : this._t(on ? "lit" : "unlit")}</span>
      </button>
      ${this._resolved.planning || this._resolved.profiles.length ? `<button class="btn" data-act="page" data-page="list">
        <ha-icon icon="mdi:calendar-edit"></ha-icon><span>${this._t("manage")}</span>
      </button>` : `<button class="btn" data-act="more" data-entity="${eccE(this._resolved.climate)}">
        <ha-icon icon="mdi:tune-variant"></ha-icon><span>${this._t("power")} ${pr === "Auto" ? this._t("power_auto") : eccE(pr.slice(-1))}</span>
      </button>`}
    </div>`;
  }

  /* Thermomètre choisi dans l'éditeur, affiché sous le titre */
  _thermometer() {
    const id = this._config.temperature_entity;
    if (!id) return "";
    const st = this._hass.states[id];
    const v = st && !["unknown", "unavailable"].includes(st.state) ? this._fmt(st.state) : "—";
    const unit = st?.attributes?.unit_of_measurement || "°C";
    const name = this._config.temperature_name ?? st?.attributes?.friendly_name ?? "";
    return `<div class="tsub" data-act="more" data-entity="${eccE(id)}" title="${eccE(name)}"><ha-icon icon="mdi:thermometer"></ha-icon>${name ? `<small>${eccE(name)} :</small>` : ""}<span>${eccE(v)}${eccE(unit)}</span></div>`;
  }

  /* Cadran du thermostat (comme la commande de thermostat de Home Assistant) */
  _dial(a, ph) {
    const min = Number(a.min_temp ?? 15), max = Number(a.max_temp ?? 30);
    const step = Number(a.target_temp_step) || 0.5;
    const target = Number(a.temperature), cur = Number(a.current_temperature);
    const heat = this._v("climate") === "heat";
    const burning = ["on", "ignition"].includes(ph);
    const R = 80, C = 100, A0 = 135, SW = 270;
    const ang = (t) => A0 + SW * Math.min(1, Math.max(0, (t - min) / (max - min || 1)));
    const pt = (deg) => { const r = (deg * Math.PI) / 180; return [C + R * Math.cos(r), C + R * Math.sin(r)]; };
    const arc = (d1, d2) => {
      if (d2 - d1 < 0.5) return "";
      const [x1, y1] = pt(d1), [x2, y2] = pt(d2);
      return `M${x1.toFixed(2)} ${y1.toFixed(2)} A${R} ${R} 0 ${d2 - d1 > 180 ? 1 : 0} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
    };
    const hasT = Number.isFinite(target), hasC = Number.isFinite(cur);
    const at = hasT ? ang(target) : A0;
    const col = heat ? "var(--ecc-accent)" : "var(--disabled-text-color, #9e9e9e)";
    let paths = `<path d="${arc(A0, A0 + SW)}" class="track"/>`;
    if (hasT) paths += `<path d="${arc(A0, at)}" stroke="${col}" class="fill"/>`;
    if (heat && burning && hasT && hasC && cur < target) paths += `<path d="${arc(ang(cur), at)}" stroke="${col}" class="act"/>`;
    const [hx, hy] = pt(at);
    const handle = hasT ? `<circle cx="${hx.toFixed(2)}" cy="${hy.toFixed(2)}" r="9" class="handle" style="stroke:${col}"/>` : "";
    const curDot = hasC && heat ? (() => { const [cx, cy] = pt(ang(cur)); return `<circle cx="${cx.toFixed(2)}" cy="${cy.toFixed(2)}" r="3" class="curdot"/>`; })() : "";
    const dec = step < 1 ? 1 : 0;
    const txt = hasT ? this._fmt(target, dec) : "—";
    const sepAt = Math.max(txt.lastIndexOf(","), txt.lastIndexOf("."));
    const ent = sepAt > 0 ? txt.slice(0, sepAt) : txt, frac = sepAt > 0 ? txt.slice(sepAt) : "";
    const label = this._t(heat ? "hvac_heat" : "hvac_off");
    return `
      <div class="curt"><small>${this._t("current_temp")}</small><b>${hasC ? this._fmt(cur) : "—"} °C</b></div>
      <div class="dial">
        <svg viewBox="0 0 200 200">${paths}${curDot}${handle}</svg>
        <div class="dc">
          <div class="dlabel">${label}</div>
          <div class="dval"><span class="dint">${ent}</span><span class="dside"><span>°C</span><span>${frac}</span></span></div>
        </div>
        <div class="dbtn">
          <button class="round" data-act="sp-" title="-"><ha-icon icon="mdi:minus"></ha-icon></button>
          <button class="round" data-act="sp+" title="+"><ha-icon icon="mdi:plus"></ha-icon></button>
        </div>
      </div>`;
  }

  _stove(ph, veille, low) {
    const img = this._config.image || "bild9";
    if (img === "generic" || img === "default") return this._stoveSvg(ph, veille, low);
    const preset = ECC_IMAGES[img];
    return this._stoveImage(preset ? preset.src : img, ph, veille, low, preset ? preset.window : null);
  }

  _stoveSvg(ph, veille, low) {
    const k = veille ? 0 : ph === "on" ? 0.75 : ph === "ignition" ? 0.35 : 0;
    const p = Math.min(5, Math.max(1, Number(this._realPower()) || 1));
    const kk = ph === "on" ? 0.45 + p * 0.11 : k;
    const relax = this._v("relax") === "on";
    const a = this._s("climate")?.attributes || {};
    const alarm = ph === "alarm";
    const flames = kk > 0 ? `
      <g transform="translate(50 74) scale(${0.8 + kk * 0.3} ${kk}) translate(-50 -74)">
        <g class="fl">
          <path d="M36 74 C26 70 28 58 34 50 C35 59 40 59 39 51 C46 60 46 72 36 74Z" fill="url(#eccF)" style="animation-delay:-.3s"/>
          <path d="M64 74 C74 70 72 58 66 50 C65 59 60 59 61 51 C54 60 54 72 64 74Z" fill="url(#eccF)" style="animation-delay:-.7s"/>
          <path d="M50 74 C32 69 35 48 44 36 C44 47 53 47 50 25 C66 41 68 68 50 74Z" fill="url(#eccF)"/>
          <path d="M50 74 C41 72 43 60 47 54 C48 61 52 60 51 51 C58 60 58 72 50 74Z" fill="#ffe082" style="animation-delay:-.5s"/>
        </g>
      </g>` : "";
    const glow = kk > 0 ? `<rect x="28" y="28" width="44" height="48" rx="3" fill="url(#eccG)" opacity="${0.4 + kk * 0.5}"/>` : "";
    const spark = ph === "ignition" ? `<circle class="blink" cx="50" cy="71" r="2.5" fill="#fff59d"/>` : "";
    const fanOn = !relax && ph !== "off" && ph !== "unavailable";
    const v1 = (Number(this._v("real_fan1")) || (parseInt(a.fan_mode) || 60)) / 20;
    const dur = Math.max(0.35, 1.9 - v1 * 0.25);
    let lcd = this._t("off").toUpperCase();
    if (alarm) lcd = this._t("alarm").toUpperCase();
    else if (veille) lcd = "STAND-BY";
    else if (ph !== "off") lcd = `${this._fmt(a.current_temperature)}°>${this._fmt(a.temperature)}° P${this._realPower() || "-"}`;
    lcd = eccE(lcd);
    const lcdCol = alarm ? "#ff5252" : "#7cffb2";
    return `
    <svg viewBox="0 0 100 150" class="stove ${kk > 0 ? "lit" : ""}">
      <defs>
        <linearGradient id="eccBody" x1="0" x2="1"><stop offset="0" stop-color="#3a3f45"/><stop offset=".5" stop-color="#4b5158"/><stop offset="1" stop-color="#2f3338"/></linearGradient>
        <linearGradient id="eccF" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#ff6f00"/><stop offset=".6" stop-color="#ffa000"/><stop offset="1" stop-color="#ffd54f"/></linearGradient>
        <radialGradient id="eccG" cx=".5" cy=".9" r=".8"><stop offset="0" stop-color="#ff9800" stop-opacity=".9"/><stop offset="1" stop-color="#ff9800" stop-opacity="0"/></radialGradient>
      </defs>
      ${ph === "on" ? [30, 50, 70].map((x, i) => `<path class="wave" d="M${x} 10 q3 -3 0 -6 q-3 -3 0 -6" fill="none" stroke="#ff8a65" stroke-width="1.4" stroke-linecap="round" style="animation-delay:${i * 0.6}s"/>`).join("") : ""}
      <rect x="18" y="12" width="64" height="122" rx="9" fill="url(#eccBody)"/>
      <rect x="18" y="12" width="64" height="9" rx="4.5" fill="#22262a"/>
      <rect x="26" y="26" width="48" height="52" rx="5" fill="#1a1d20" stroke="#6b7480" stroke-width="1.2"/>
      <rect x="28" y="28" width="44" height="48" rx="3" fill="${kk > 0 ? "#160904" : "#202428"}"/>
      ${glow}${flames}${spark}
      <rect x="28" y="28" width="44" height="48" rx="3" fill="none" stroke="rgba(255,255,255,.08)"/>
      <path d="M31 31 L40 31 L31 50 Z" fill="rgba(255,255,255,.06)"/>
      <rect x="30" y="86" width="40" height="11" rx="2" fill="#0c1720" stroke="#8f98a2" stroke-width=".6"/>
      <text x="50" y="94" text-anchor="middle" font-size="5.2" font-family="monospace" fill="${lcdCol}" ${lcd.length > 11 ? `textLength="36" lengthAdjust="spacingAndGlyphs"` : ""} class="${alarm ? "blink" : ""}">${lcd}</text>
      ${[36, 64].map((x, i) => `
        <g transform="translate(${x} 113)">
          <circle r="7" fill="#2b2f34" stroke="#6b7480"/>
          <g class="fan" style="--d:${dur}s;animation-play-state:${fanOn ? "running" : "paused"}">
            ${[0, 120, 240].map((r) => `<path d="M0 0 C3 -2 3 -5.5 0 -6 C-2 -4.5 -2 -2 0 0Z" fill="${fanOn ? "#4fc3f7" : "#6b7480"}" transform="rotate(${r})"/>`).join("")}
          </g>
          <circle r="1.2" fill="#9aa3ad"/>
        </g>`).join("")}
      <rect x="24" y="134" width="8" height="5" rx="1.5" fill="#22262a"/><rect x="68" y="134" width="8" height="5" rx="1.5" fill="#22262a"/>
      ${low ? `<text x="50" y="148" text-anchor="middle" font-size="6" fill="#e53935" class="blink">${this._t("pellets_low")}</text>` : ""}
    </svg>`;
  }

  _dd(kind, label, options, cur, disp, entity) {
    return `<label class="dd"><small>${eccE(label)}</small><span>${eccE(disp ? disp(cur) : cur ?? "—")}</span><ha-icon icon="mdi:chevron-down"></ha-icon>
      <select data-dd="${eccE(kind)}" ${entity ? `data-entity="${eccE(entity)}"` : ""}>${options.map((o) => `<option value="${eccE(o)}" ${o === cur ? "selected" : ""}>${eccE(disp ? disp(o) : o)}</option>`).join("")}</select></label>`;
  }

  /* Image personnelle du poêle : les flammes sont dessinées dans la vitre (image_window, en % de l'image) */
  _stoveImage(src, ph, veille, low, presetWindow) {
    const w = Object.assign({ x: 25, y: 25, width: 50, height: 40 }, presetWindow || this._config.image_window || {});
    const p = Math.min(5, Math.max(1, Number(this._realPower()) || 1));
    const relax = this._v("relax") === "on";
    const a = this._s("climate")?.attributes || {};
    const alarm = ph === "alarm";
    const k = veille ? 0 : ph === "on" ? (relax ? 0.55 : 0.45 + p * 0.11) : ph === "ignition" ? 0.35 : 0;
    const lit = k > 0;
    const flames = lit ? `
      <rect width="100" height="100" fill="#120804" opacity=".9"/>
      <rect class="glowp" width="100" height="100" fill="url(#eccG2)" style="opacity:${0.35 + k * 0.6}"/>
      <g transform="translate(50 92) scale(${0.85 + k * 0.25} ${k}) translate(-50 -92)">
        <g class="fl">
          <path d="M32 92 C20 88 22 72 29 62 C31 73 37 74 35 63 C45 74 45 89 32 92Z" fill="url(#eccF2)" style="animation-delay:-.3s"/>
          <path d="M68 92 C80 88 78 72 71 62 C69 73 63 74 65 63 C55 74 55 89 68 92Z" fill="url(#eccF2)" style="animation-delay:-.7s"/>
          <path d="M50 92 C28 86 32 60 43 44 C43 58 54 58 50 30 C70 50 73 84 50 92Z" fill="url(#eccF2)"/>
          <path d="M50 92 C39 89 41 74 47 66 C48 75 53 74 52 63 C61 74 61 89 50 92Z" fill="#ffe082" style="animation-delay:-.5s"/>
        </g>
      </g>` : "";
    const spark = ph === "ignition" ? `<circle class="blink" cx="50" cy="88" r="3" fill="#fff59d"/>` : "";
    const waves = ph === "on" ? [25, 50, 75].map((x, i) => `<path class="wave" d="M${x} 12 q3 -3 0 -6 q-3 -3 0 -6" fill="none" stroke="#ff8a65" stroke-width="1.6" stroke-linecap="round" style="animation-delay:${i * 0.6}s"/>`).join("") : "";
    const fan = (n) => {
      const rf = Number(this._v(n === 1 ? "real_fan1" : "real_fan2"));
      const on = !relax && ph !== "off" && ph !== "unavailable" && rf !== 0;
      const v = (rf / 20) || (parseInt(n === 1 ? a.fan_mode : this._v("fan2")) / 20) || 3;
      const d = Math.max(0.35, 1.9 - v * 0.25);
      const col = on ? "#4fc3f7" : "#6b7480";
      return `<svg viewBox="-10 -10 20 27" width="18" height="25">
        <circle r="8" fill="#2b2f34" stroke="#6b7480"/>
        <g class="fan" style="--d:${d}s;animation-play-state:${on ? "running" : "paused"}">
          ${[0, 120, 240].map((r) => `<path d="M0 0 C3 -2 3 -6 0 -7 C-2 -5 -2 -2 0 0Z" fill="${col}" transform="rotate(${r})"/>`).join("")}
        </g>
        <circle r="1.4" fill="#9aa3ad"/>
        <text y="15.5" text-anchor="middle" font-size="6" fill="var(--secondary-text-color)">V${n}</text>
      </svg>`;
    };
    let lcd = this._t("off").toUpperCase();
    if (alarm) lcd = this._t("alarm").toUpperCase();
    else if (veille) lcd = "STAND-BY";
    else if (ph !== "off") lcd = `${this._fmt(a.current_temperature)}°>${this._fmt(a.temperature)}° P${this._realPower() || "-"}`;
    lcd = eccE(lcd);
    const filter = alarm ? "drop-shadow(0 0 6px #e53935)" : lit ? "drop-shadow(0 0 8px rgba(255,120,0,.45))" : "none";
    const frame = this._config.image_calibration ? "outline:1px dashed red;" : "";
    return `
    <div class="imgw">
      <img src="${eccE(src)}" alt="" style="filter:${filter}" class="${alarm ? "blink" : ""}">
      <svg viewBox="0 0 100 12" preserveAspectRatio="none" class="imgwaves">${waves}</svg>
      <div class="imgwin" style="left:${Number(w.x) || 0}%;top:${Number(w.y) || 0}%;width:${Number(w.width) || 0}%;height:${Number(w.height) || 0}%;${frame}">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none">
          <defs>
            <linearGradient id="eccF2" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#ff6f00"/><stop offset=".6" stop-color="#ffa000"/><stop offset="1" stop-color="#ffd54f"/></linearGradient>
            <radialGradient id="eccG2" cx=".5" cy=".9" r=".8"><stop offset="0" stop-color="#ff9800" stop-opacity=".85"/><stop offset="1" stop-color="#ff9800" stop-opacity="0"/></radialGradient>
          </defs>
          ${flames}${spark}
        </svg>
      </div>
    </div>
    <div class="imgbar">${fan(1)}<div class="lcd ${alarm ? "blink" : ""}" style="color:${alarm ? "#ff5252" : "#7cffb2"}">${lcd}</div>${fan(2)}</div>
    ${low ? `<div class="red blink lowtxt">${this._t("pellets_low")}</div>` : ""}`;
  }

  _modes() {
    const a = this._s("climate")?.attributes || {};
    const fanModes = a.fan_modes || ["Auto", "20%", "40%", "60%", "80%", "100%"];
    const presets = (a.preset_modes || ["Auto", "Man. P1", "Man. P2", "Man. P3", "Man. P4", "Man. P5"]).filter((p) => p !== "none");
    const fan2 = this._s("fan2");
    const rp = this._realPower();
    const pdisp = (o) => (o === "Auto" ? "Auto" : String(o).replace("Man. ", ""));
    const tog = (key, icon, label) => {
      const st = this._s(key);
      if (!st) return "";
      const on = st.state === "on";
      return `<button class="btn ${on ? "act" : ""}" data-act="toggle" data-entity="${eccE(this._resolved[key])}"><ha-icon icon="${icon}"></ha-icon><span>${label}</span><span class="dot ${on ? "on" : ""}"></span></button>`;
    };
    const cur = a.preset_mode || "Auto";
    return `
    <div class="sec-title">${this._t("fans")}</div>
    <div class="dd3 ${fan2 ? "" : "two"}">
      ${this._dd("preset", this._t("power"), presets, cur, (o) => pdisp(o) + (o === "Auto" && o === cur && rp ? ` · P${rp}` : ""))}
      ${this._dd("fan1", this._t("fan1s"), fanModes, a.fan_mode)}
      ${fan2 ? this._dd("fan2", this._t("fan2s"), fan2.attributes.options || [], fan2.state) : ""}
    </div>
    <div class="row2">${tog("standby", "mdi:sleep", this._t("standby"))}${tog("relax", "mdi:volume-off", this._t("silence"))}</div>`;
  }

  _nextSlot() {
    const now = new Date(), m = now.getHours() * 60 + now.getMinutes();
    let best = null;
    for (const p of this._resolved.profiles) {
      if (this._hass.states[p.active]?.state !== "on") continue;
      for (const k of ["start", "end"]) {
        const v = this._hass.states[p[k]]?.state;
        if (!v || !v.includes(":")) continue;
        const [h, mi] = v.split(":").map(Number);
        let d = (h * 60 + mi - m + 1440) % 1440;
        if (d === 0) d = 1440;
        if (!best || d < best.d) best = { d, t: v.slice(0, 5) };
      }
    }
    return best ? best.t : null;
  }

  _planning(list = true) {
    const r = this._resolved, out = [];
    const planning = this._s("planning");
    out.push(`<div class="sec-title">${this._t("planning")}
      ${planning ? `<button class="mini ${planning.state === "on" ? "on" : ""}" data-act="toggle" data-entity="${eccE(r.planning)}">
        <ha-icon icon="${planning.state === "on" ? "mdi:calendar-check" : "mdi:calendar-remove"}"></ha-icon>${this._t(planning.state === "on" ? "planning_on" : "planning_off")}</button>` : ""}</div>`);
    // Fenêtre ouverte : coupure en attente ou poêle coupé
    const win = this._s("window_cut");
    if (win && (win.state === "on" || win.attributes?.cut_at)) {
      const wa = win.attributes || {};
      const hm = (iso) => new Date(iso).toLocaleTimeString(this._hass?.locale?.language || "fr", { hour: "2-digit", minute: "2-digit" });
      const names = (wa.open_windows || []).join(", ");
      const cut = win.state === "on";
      const line = cut ? (wa.resume_at ? `${this._t("win_resume_at")} ${hm(wa.resume_at)}` : this._t("win_resume_close"))
        : `${this._t("win_cut_at")} ${hm(wa.cut_at)}`;
      out.push(`<div class="banner"><ha-icon icon="mdi:window-open-variant"></ha-icon>
        <div><b>${this._t(!cut ? "win_wait" : wa.resume_at ? "win_closed" : "win_cut")}</b><br><span>${names ? eccE(names) + " · " : ""}${eccE(line)}</span></div>
        <button data-act="more" data-entity="${eccE(r.window_cut)}"><ha-icon icon="mdi:information-outline"></ha-icon></button></div>`);
    }
    const ov = this._s("override");
    if (ov?.state === "on") {
      out.push(`<div class="banner"><ha-icon icon="mdi:hand-back-right"></ha-icon>
        <div><b>${this._t("override")} ${this._fmt(this._s("climate")?.attributes?.temperature)} °C</b><br><span>${this._t("override_txt")}${this._nextSlot() ? " (" + eccE(this._nextSlot()) + ")" : ""}</span></div>
        <button data-act="off" data-entity="${eccE(r.override)}">${this._t("cancel")}</button></div>`);
    }
    // Réglages manuels : ventilations, puissance, stand-by (jusqu'à la prochaine plage)
    // et silence (Relax) activé à la main (jusqu'à minuit), dans le même bandeau
    const manOn = this._s("manual")?.state === "on", rxOn = this._s("relax_prio")?.state === "on";
    if (manOn || rxOn) {
      const nx = this._nextSlot();
      const lines = [];
      if (manOn) lines.push(`${this._t("manual_txt")} ${eccE(nx || this._t("next_slot"))}`);
      if (rxOn) lines.push(this._t("relax_txt"));
      const ents = [manOn ? r.manual : null, rxOn ? r.relax_prio : null].filter(Boolean).join(",");
      out.push(`<div class="banner"><ha-icon icon="${manOn ? "mdi:hand-back-right-outline" : "mdi:volume-off"}"></ha-icon>
        <div><b>${this._t("manual")}</b><br><span>${lines.join("<br>")}</span></div>
        <button data-act="off" data-entity="${eccE(ents)}">${this._t("give_back")}</button></div>`);
    }
    const cur = this._v("current_profile");
    // « Gérer les programmations » : dans la partie Poêle quand elle est affichée, sinon ici
    const manage = this._config.show_header === false;
    out.push(`${list ? `<div class="profiles">${r.profiles.map((p) => this._profileRow(p, cur)).join("")}</div>` : ""}
      ${manage ? `<button class="add" data-act="page" data-page="list"><ha-icon icon="mdi:calendar-edit"></ha-icon><span>${this._t("manage")}</span></button>` : ""}`);
    return out.join("");
  }

  _days(days) {
    const D = this._t("days");
    if (!Array.isArray(days) || days.length === 0 || days.length === 7) return this._t("every_day");
    const k = [...days].sort().join(",");
    if (k === "0,1,2,3,4") return this._t("weekdays");
    if (k === "5,6") return this._t("weekend");
    return [...days].sort().map((d) => D[d]).join(" ");
  }

  _profileRow(p, cur) {
    const st = (e) => (e ? this._hass.states[e] : undefined);
    const active = st(p.active)?.state === "on";
    const name = st(p.name)?.state || `${this._t("profile")} ${p.n}`;
    const d = (st(p.start)?.state || "").slice(0, 5), f = (st(p.end)?.state || "").slice(0, 5);
    const sp = st(p.setpoint)?.state;
    const mode = st(p.mode)?.state || "";
    const days = st(p.active)?.attributes?.days;
    const isCur = this._curN() === p.n;
    const hours = d && d === f ? this._t("all_day") : `${d} → ${f}`;
    const tags = this._tags(this._vals(p.n), p.n);
    return `
    <div class="pwrap ${isCur ? "cur" : ""}">
    <div class="prof ${active ? "" : "dis"}">
      <button class="sw ${active ? "on" : ""}" data-act="toggle" data-entity="${eccE(p.active)}" title="${eccE(name)}"><span></span></button>
      <div class="pn" data-act="page" data-page="${p.n}"><b>${eccE(name)}</b><span>${eccE(hours)} · ${eccE(this._days(days))}</span>${tags}</div>
      <div class="pc">
        <button class="round sm" data-act="num-" data-entity="${eccE(p.setpoint)}"><ha-icon icon="mdi:minus"></ha-icon></button>
        <span>${this._fmt(sp)}°</span>
        <button class="round sm" data-act="num+" data-entity="${eccE(p.setpoint)}"><ha-icon icon="mdi:plus"></ha-icon></button>
      </div>
    </div>
    </div>`;
  }

  /* ------------------------------------------------------------ menu programmations */
  _vals(n) {
    if (n === "new") return this._draft;
    const p = this._resolved.profiles.find((x) => x.n === n);
    if (!p) return null;
    const st = (k) => (p[k] ? this._hass.states[p[k]] : undefined);
    const days = st("active")?.attributes?.days;
    return {
      p, name: st("name")?.state || `${this._t("profile")} ${n}`, start: (st("start")?.state || "").slice(0, 5), end: (st("end")?.state || "").slice(0, 5),
      days: Array.isArray(days) && days.length ? days : [0, 1, 2, 3, 4, 5, 6], setpoint: Number(st("setpoint")?.state),
      mode: eccIsSb(st("mode")?.state ?? "standby") ? "standby" : "run", absent: st("absent")?.state, power: st("power")?.state, fan1: st("fan1")?.state, fan2: st("fan2")?.state,
      relax: st("relax")?.state === "on", active: st("active")?.state === "on",
      opts: { power: st("power")?.attributes?.options, fan1: st("fan1")?.attributes?.options, fan2: st("fan2")?.attributes?.options, absent: st("absent")?.attributes?.options },
    };
  }

  _defOpts() {
    const a = this._s("climate")?.attributes || {};
    return {
      power: (a.preset_modes || ["Auto", "Man. P1", "Man. P2", "Man. P3", "Man. P4", "Man. P5"]).filter((x) => x !== "none"),
      fan1: a.fan_modes || ["Auto", "20%", "40%", "60%", "80%", "100%"],
      fan2: this._s("fan2")?.attributes?.options || null,
    };
  }

  _newDraft() {
    const o = this._defOpts();
    return { name: this._t("new_name"), start: "07:00", end: "09:00", days: [0, 1, 2, 3, 4, 5, 6], setpoint: 20, mode: "standby",
      power: "Auto", fan1: "Auto", fan2: o.fan2 ? (o.fan2.includes("Auto") ? "Auto" : o.fan2[0]) : null, relax: false, active: true };
  }

  _manager(overlay) {
    const pg = this._page ?? "list";
    if (pg === "pellet") return this._pelletSheet(overlay);
    if (pg === "ignitions") return this._ignitionSheet(overlay);
    const close = overlay ? `<button class="round" data-act="page" data-page="close"><ha-icon icon="mdi:close"></ha-icon></button>` : "";
    if (pg === "list") {
      const cur = this._v("current_profile");
      const rows = this._resolved.profiles.map((p) => {
        const v = this._vals(p.n);
        const isCur = this._curN() === p.n;
        return `<div class="mrow ${v.active ? "" : "dis"} ${isCur ? "cur" : ""}">
          <button class="sw ${v.active ? "on" : ""}" data-act="toggle" data-entity="${eccE(p.active)}"><span></span></button>
          <div class="pn" data-act="page" data-page="${p.n}"><b>${eccE(v.name)}</b><span>${v.start === v.end ? this._t("all_day") : eccE(v.start + " → " + v.end)} · ${eccE(this._days(v.days))} · ${this._fmt(v.setpoint)} °C</span>${this._tags(v, p.n)}</div>
          <div class="ord">
            <button class="round xs" data-act="move" data-n="${p.n}" data-val="-1" title="${this._t("move_up")}" ${p.n === 1 ? "disabled" : ""}><ha-icon icon="mdi:chevron-up"></ha-icon></button>
            <button class="round xs" data-act="move" data-n="${p.n}" data-val="1" title="${this._t("move_down")}" ${p.n === this._resolved.profiles.length ? "disabled" : ""}><ha-icon icon="mdi:chevron-down"></ha-icon></button>
          </div></div>`;
      }).join("");
      return `<div class="mhead"><ha-icon icon="mdi:calendar-clock" class="hicon"></ha-icon><b>${this._t("schedules")}</b>${close}</div>
        <div class="mlist">${rows}</div>
        <button class="primary" data-act="page" data-page="new"><ha-icon icon="mdi:plus"></ha-icon>${this._t("new_schedule")}</button>
        <div class="hint">${this._t("priority")}</div>`;
    }
    if (pg === "new" && !this._draft) this._draft = this._newDraft();
    const n = pg === "new" ? "new" : Number(pg);
    const v = this._vals(n);
    if (!v) { this._page = "list"; return this._manager(overlay); }
    const o = Object.assign(this._defOpts(), Object.fromEntries(Object.entries(v.opts || {}).filter(([, x]) => x)));
    const D = this._t("days");
    const dd = (f, label, disp) => (v[f] == null || !o[f] ? "" :
      `<label class="dd"><small>${eccE(label)}</small><span>${eccE(disp ? disp(v[f]) : v[f])}</span><ha-icon icon="mdi:chevron-down"></ha-icon>
        <select data-f="${f}" data-n="${n}">${o[f].map((x) => `<option value="${eccE(x)}" ${x === v[f] ? "selected" : ""}>${eccE(disp ? disp(x) : x)}</option>`).join("")}</select></label>`);
    const sb = v.mode === "standby";
    const delConf = this._confirm === "del" + n;
    return `<div class="mhead"><button class="round" data-act="page" data-page="list"><ha-icon icon="mdi:arrow-left"></ha-icon></button>
        <b>${n === "new" ? this._t("new_schedule") : eccE(v.name)}</b>${close}</div>
      <div class="pedit">
        <label class="fld"><small>${this._t("name")}</small><input data-f="name" data-n="${n}" value="${eccE(v.name)}"></label>
        <div class="frow">
          ${this._timeStepper(n, "start", this._t("start"), v.start)}
          ${this._timeStepper(n, "end", this._t("end"), v.end)}
          <div class="fld"><small>${this._t("setpoint")}</small><div class="pc">
            <button class="round sm" data-act="fsp" data-n="${n}" data-val="-"><ha-icon icon="mdi:minus"></ha-icon></button>
            <span>${this._fmt(v.setpoint)}°</span>
            <button class="round sm" data-act="fsp" data-n="${n}" data-val="+"><ha-icon icon="mdi:plus"></ha-icon></button></div></div>
        </div>
        <div class="daysel">${D.map((l, i) => `<button class="${v.days.includes(i) ? "on" : ""}" data-act="day" data-n="${n}" data-d="${i}">${l}</button>`).join("")}</div>
        <div class="dd3 ${o.fan2 && v.fan2 != null ? "" : "two"}">
          ${dd("power", this._t("power"), (x) => (x === "Auto" ? "Auto" : String(x).replace("Man. ", "")))}
          ${dd("fan1", this._t("fan1s"))}
          ${dd("fan2", this._t("fan2s"))}
        </div>
        ${n !== "new" && o.absent && v.absent != null ? `<div class="dd1">${dd("absent", this._t("if_away"))}</div>` : ""}
        <div class="row2">
          <button class="btn ${sb ? "act" : ""}" data-act="fbool" data-f="mode" data-n="${n}"><ha-icon icon="mdi:sleep"></ha-icon><span>${this._t("standby")}</span><span class="dot ${sb ? "on" : ""}"></span></button>
          <button class="btn ${v.relax ? "act" : ""}" data-act="fbool" data-f="relax" data-n="${n}"><ha-icon icon="mdi:volume-off"></ha-icon><span>${this._t("silence")}</span><span class="dot ${v.relax ? "on" : ""}"></span></button>
        </div>
        ${n === "new"
          ? `<button class="primary" data-act="create"><ha-icon icon="mdi:check"></ha-icon>${this._t("create")}</button>`
          : `<div class="pfoot"><button class="del ${delConf ? "confirm" : ""}" data-act="del" data-n="${n}"><ha-icon icon="mdi:delete-outline"></ha-icon>${this._t(delConf ? "confirm_del" : "del")}</button></div>`}
      </div>`;
  }

  // Étiquettes : ligne 1 Puissance · V1 · V2, ligne 2 Stand-by/Marche · Silence. Un appui change la valeur.
  _curN() {
    const s = this._s("current_profile");
    const a = Number(s?.attributes?.profile);
    if (a) return a;
    const p = this._resolved.profiles.find((x) => this._hass.states[x.name]?.state === s?.state);
    return p ? p.n : null;
  }

  // Heure réglée par boutons − / + (5 min, appui long = défilement) ; un appui sur l'heure ouvre le sélecteur
  _timeStepper(n, f, label, value) {
    const pend = this._pend && this._pend.n === n && this._pend.f === f ? this._pend.v : value;
    return `<div class="fld"><small>${label}</small><div class="tstep">
      <button class="round sm" data-hold="-5" data-n="${n}" data-f2="${f}"><ha-icon icon="mdi:minus"></ha-icon></button>
      <label class="tval"><span>${eccE(pend)}</span><input type="time" data-f="${f}" data-n="${n}" value="${eccE(pend)}"></label>
      <button class="round sm" data-hold="5" data-n="${n}" data-f2="${f}"><ha-icon icon="mdi:plus"></ha-icon></button></div></div>`;
  }

  _holdStart(el) {
    const n = el.dataset.n === "new" ? "new" : Number(el.dataset.n), f = el.dataset.f2, d = Number(el.dataset.hold);
    const base = this._pend && this._pend.n === n && this._pend.f === f ? this._pend.v : this._vals(n)[f];
    const step = () => {
      const cur = this._pend.v.split(":").map(Number);
      const m = cur[0] * 60 + cur[1];
      // pas de 5 min, aligné sur les 5 minutes
      const k = Math.abs(d);
      const next = d > 0 ? Math.floor(m / k) * k + k : Math.ceil(m / k) * k - k;
      const mm = ((next % 1440) + 1440) % 1440;
      this._pend.v = `${String(Math.floor(mm / 60)).padStart(2, "0")}:${String(mm % 60).padStart(2, "0")}`;
      this._sig = ""; this._render();
    };
    this._pend = { n, f, v: base };
    step();
    clearTimeout(this._holdT); clearInterval(this._holdI);
    this._holdT = setTimeout(() => { this._holdI = setInterval(step, 110); }, 450);
    const end = () => {
      clearTimeout(this._holdT); clearInterval(this._holdI);
      window.removeEventListener("pointerup", end); window.removeEventListener("pointercancel", end);
      const pv = this._pend; this._pend = null;
      if (pv && pv.v !== this._vals(pv.n)[pv.f]) this._setField(pv.n, pv.f, pv.v);
      else { this._sig = ""; this._render(); }
    };
    window.addEventListener("pointerup", end); window.addEventListener("pointercancel", end);
  }

  _tags(v, n) {
    if (!v) return "";
    const t = (f, label, cls) => `<button class="tag ${cls || ""}" data-act="tag" data-n="${n}" data-f="${f}">${eccE(label)}</button>`;
    const l1 = [
      v.power != null ? t("power", v.power === "Auto" ? "P Auto" : String(v.power).replace("Man. ", "")) : "",
      v.fan1 != null ? t("fan1", "V1 " + v.fan1) : "",
      v.fan2 != null ? t("fan2", "V2 " + v.fan2) : "",
    ].join("");
    const sb = v.mode === "standby";
    const l2 = t("mode", sb ? this._t("standby") : this._t("mode_run"), sb ? "sb" : "run") + t("relax", this._t("silence"), v.relax ? "rx" : "off");
    return `<div class="tags">${l1}</div><div class="tags">${l2}</div>`;
  }

  // Écrit un champ : brouillon (nouvelle programmation) ou entité de l'intégration
  _setField(n, f, value) {
    if (n === "new") { this._draft[f] = value; this._sig = ""; this._render(); return; }
    const p = this._resolved.profiles.find((x) => x.n === n);
    if (!p) return;
    switch (f) {
      case "name": this._call("text", "set_value", { entity_id: p.name, value }); break;
      case "start": case "end": this._call("time", "set_value", { entity_id: p[f], time: value.length === 5 ? value + ":00" : value }); break;
      case "setpoint": this._call("number", "set_value", { entity_id: p.setpoint, value }); break;
      case "days": this._call(ECC_DOMAIN, "set_profile_days", { profile: n, days: value }); break;
      case "relax": this._call("switch", value ? "turn_on" : "turn_off", { entity_id: p.relax }); break;
      case "mode": {
        const opts = this._hass.states[p.mode]?.attributes?.options || ["run", "standby"];
        const opt = opts.find((o) => eccIsSb(o) === (value === "standby")) || value;
        this._call("select", "select_option", { entity_id: p.mode, option: opt });
        break;
      }
      default: if (p[f]) this._call("select", "select_option", { entity_id: p[f], option: value });
    }
  }

  _tracking() {
    const tile = (icon, label, value, color, entity) => `
      <div class="tile" data-act="more" data-entity="${eccE(entity)}">
        <ha-icon icon="${icon}" style="color:${color}"></ha-icon><span class="tl">${eccE(label)}</span><span class="tv">${eccE(value)}</span></div>`;
    const ign = this._v("ignitions");
    const al = this._v("alarm") === "on";
    const lab = this._v("alarm_label");
    const low = this._v("pellet") === "Empty";
    const graph = this._config.show_graph ? `<div class="graph">${this._graph()}</div>` : "";
    return `
    <div class="sec-title">${this._t("tracking")}</div>
    ${graph}
    <div class="tiles">
      ${this._resolved.ignitions || this._resolved.ign_hist ? `<div class="tile" data-act="page" data-page="ignitions">
        <ha-icon icon="mdi:fire-circle" style="color:#f06b21"></ha-icon><span class="tl">${this._t("ignitions")}</span><span class="tv">${eccE(ign ?? "—")}</span></div>` : ""}
      ${this._resolved.alarm ? tile(al ? "mdi:alert" : "mdi:check-circle", this._t("alarm_now"), al ? (lab || this._t("alarm")) : this._t("none"), al ? "#e53935" : "#2ea55f", this._resolved.alarm_label || this._resolved.alarm) : ""}
      ${this._resolved.pellet || this._resolved.res_hours ? this._pelletTile(low) : ""}
    </div>`;
  }

  _pelletTile(low) {
    const h = Number(this._v("res_hours"));
    const warn = low || this._v("res_low") === "on";
    const val = low ? this._t("reserve_low") : Number.isFinite(h) && this._resolved.res_hours ? `${Math.round(h)} h` : this._t("ok");
    const col = warn ? "#e67e22" : "#2ea55f";
    return `<div class="tile" data-act="page" data-page="pellet">
      <ha-icon icon="${warn ? "mdi:alert-circle-outline" : "mdi:grain"}" style="color:${col}"></ha-icon><span class="tl">${this._t("pellets")}</span>
      <span class="tv" style="${warn ? "color:#e67e22" : ""}">${val}</span></div>`;
  }

  /* Menu « Allumages » : allumages des 3 derniers jours, arrêt, durée, total et moyenne */
  _ignitionSheet(overlay) {
    const hist = this._s("ign_hist")?.attributes?.history || [];
    const lang = this._hass?.locale?.language || "fr";
    const hm = (d) => d.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
    const dur = (m) => (m == null ? "—" : m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}` : `${m} min`);
    const dayKey = (d) => d.toLocaleDateString("sv");
    const today = new Date(), yest = new Date(Date.now() - 86400000);
    const dayLabel = (d) => dayKey(d) === dayKey(today) ? this._t("today") : dayKey(d) === dayKey(yest) ? this._t("yesterday")
      : d.toLocaleDateString(lang, { weekday: "long", day: "numeric", month: "long" });
    const days = new Map();
    let tot = 0, n = 0;
    for (const r of hist) {
      const s = new Date(r.start);
      if (isNaN(s)) continue;
      let e = null, endTxt;
      if (r.end === null || r.end === undefined) { e = new Date(); endTxt = `<i>${this._t("running")}</i>`; }
      else if (r.end === "?") { endTxt = "?"; }
      else { e = new Date(r.end); endTxt = hm(e); }
      const m = e ? Math.max(0, Math.round((e - s) / 60000)) : null;
      if (m != null) { tot += m; n++; }
      const k = dayKey(s);
      if (!days.has(k)) days.set(k, { label: dayLabel(s), rows: [], tot: 0 });
      const g = days.get(k);
      g.rows.push(`<tr><td>${hm(s)}</td><td>${endTxt}</td><td>${dur(m)}</td></tr>`);
      g.tot += m || 0;
    }
    const close = overlay ? `<button class="round" data-act="page" data-page="close"><ha-icon icon="mdi:close"></ha-icon></button>` : "";
    const cnt = this._v("ignitions");
    let body = "";
    if (!days.size) body = `<div class="hint">${this._t("no_ign")}</div>`;
    for (const g of days.values()) {
      const k = g.rows.length;
      body += `<div class="dayh"><b>${g.label}</b><span>${k} ${this._t(k > 1 ? "ign_many" : "ign_one")} · ${dur(g.tot)}</span></div>
        <table class="igt"><thead><tr><th>${this._t("ign_on")}</th><th>${this._t("ign_off")}</th><th>${this._t("duration")}</th></tr></thead><tbody>${g.rows.join("")}</tbody></table>`;
    }
    const foot = days.size ? `<div class="igsum"><span>${this._t("total")}</span><b>${dur(tot)}</b><span>${this._t("average")}</span><b>${dur(n ? Math.round(tot / n) : 0)}</b>
      ${cnt !== undefined ? `<span>${this._t("counter")}</span><b>${eccE(cnt)}</b>` : ""}</div>` : "";
    return `<div class="mhead"><ha-icon icon="mdi:fire-circle" class="hicon"></ha-icon><b>${this._t("ign_title")}</b>${close}</div>${body}${foot}`;
  }

  /* Menu « Réservoir de granulés » : mêmes informations que le menu du poêle */
  _pelletSheet(overlay) {
    const r = this._resolved, st = (k) => (r[k] ? this._hass.states[r[k]] : undefined);
    const hrs = (v) => (v === undefined || v === null || v === "" || isNaN(Number(v)) ? "—" : `${this._fmt(v, Number(v) >= 100 ? 0 : 1)} h`);
    const avgS = st("res_avg"), durations = avgS?.attributes?.durations || [];
    const load = avgS?.attributes?.last_load_kg;
    const stockS = st("stock_auto");
    const rows = [];
    const row = (icon, label, value, extra = "") => rows.push(`<div class="prow"><ha-icon icon="${icon}"></ha-icon><span>${label}</span><b>${value}</b>${extra}</div>`);
    if (r.res_hours) row("mdi:fire", this._t("res_hours"), hrs(st("res_hours")?.state));
    if (load != null) row("mdi:sack", this._t("last_load"), `${this._fmt(load)} kg`);
    if (r.res_avg) row("mdi:history", this._t("last_res"), durations.length ? hrs(durations[0]) : "—");
    if (r.res_avg) row("mdi:chart-bell-curve-cumulative", this._t("avg_res"), hrs(avgS?.state));
    if (r.res_auto) row("mdi:gauge", this._t("res_auto"), st("res_auto")?.state && !["unknown", "unavailable"].includes(st("res_auto").state) ? hrs(st("res_auto").state) : this._t("pending2"));
    if (r.res_alert) {
      const a = st("res_alert");
      row("mdi:timer-alert-outline", this._t("alert_after"), "", `<div class="pc">
        <button class="round sm" data-act="num-" data-entity="${eccE(r.res_alert)}"><ha-icon icon="mdi:minus"></ha-icon></button>
        <span>${a ? (Number(a.state) ? this._fmt(a.state) + " h" : "—") : "—"}</span>
        <button class="round sm" data-act="num+" data-entity="${eccE(r.res_alert)}"><ha-icon icon="mdi:plus"></ha-icon></button></div>`);
    }
    if (r.pellet) row("mdi:grain", this._t("stove_reserve"), this._v("pellet") === "Empty" ? `<span class="red">${this._t("reserve_low")}</span>` : this._t("ok"));
    if (stockS) {
      const bags = stockS.attributes?.stock_bags, kg = stockS.attributes?.stock_kg;
      if (bags != null || kg != null) row("mdi:silo", this._t("stock_left"), bags != null ? `${this._fmt(bags, 0)} ${this._t("bag_unit")}` : `${this._fmt(kg, 0)} kg`);
      row("mdi:clock-outline", this._t("stock_auto"), stockS.state && !["unknown", "unavailable"].includes(stockS.state) ? hrs(stockS.state) : this._t("pending2"));
    }
    const per = st("res_hours")?.attributes?.bags_per_fill;
    const fillLabel = stockS && per ? `${this._t("poured")} ${this._fmt(per, per % 1 ? 1 : 0)} ${this._t(Number(per) > 1 ? "bag_unit" : "bag_one")}` : this._t("filled");
    const conf = this._confirm === "fill";
    const close = overlay ? `<button class="round" data-act="page" data-page="close"><ha-icon icon="mdi:close"></ha-icon></button>` : "";
    return `<div class="mhead"><ha-icon icon="mdi:grain" class="hicon"></ha-icon><b>${this._t("reservoir")}</b>${close}</div>
      <div class="plist">${rows.join("")}</div>
      ${r.res_filled ? `<button class="primary ${conf ? "warn" : ""}" data-act="fill"><ha-icon icon="mdi:basket-fill"></ha-icon>${conf ? this._t("confirm_fill") : fillLabel}</button>` : ""}`;
  }

  /* ------------------------------------------------------------ graphique 24 h */
  async _loadHistory() {
    if (this._histLoading || Date.now() - this._histAt < 300000 || !this._hass.callWS) return;
    this._histLoading = true;
    try {
      const end = new Date(), start = new Date(end - 24 * 3600 * 1000);
      const ids = [this._resolved.climate, this._resolved.real_power].filter(Boolean);
      const res = await this._hass.callWS({ type: "history/history_during_period", start_time: start.toISOString(),
        end_time: end.toISOString(), entity_ids: ids, minimal_response: false, no_attributes: false, significant_changes_only: false });
      this._hist = { start: +start, end: +end, data: res };
      this._histAt = Date.now();
      this._sig = "";
      this._render();
    } catch (e) { this._histAt = Date.now(); }
    this._histLoading = false;
  }

  _graph() {
    if (!this._hist) return `<div class="gload">${this._t("last24")}…</div>`;
    const { start, end, data } = this._hist;
    const W = 320, H = 110, L = 26, R = 20, T = 14, B = 16;
    const cl = data[this._resolved.climate] || [], pw = data[this._resolved.real_power] || [];
    const ts = (x) => (x.lu || x.lc || 0) * 1000;
    const temp = [], spt = [], pow = [];
    for (const x of cl) {
      const t = ts(x), a = x.a || {};
      if (a.current_temperature != null) temp.push([t, Number(a.current_temperature)]);
      if (a.temperature != null) spt.push([t, Number(a.temperature)]);
    }
    for (const x of pw) if (!isNaN(Number(x.s))) pow.push([ts(x), Number(x.s)]);
    const vals = temp.concat(spt).map((p) => p[1]);
    if (!vals.length) return `<div class="gload">—</div>`;
    let lo = Math.floor(Math.min(...vals) - 0.5), hi = Math.ceil(Math.max(...vals) + 0.5);
    const X = (t) => L + ((t - start) / (end - start)) * (W - L - R);
    const Y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    const YP = (v) => T + (1 - v / 5) * (H - T - B);
    const step = (pts, y, close) => {
      if (!pts.length) return "";
      let d = `M${X(Math.max(pts[0][0], start)).toFixed(1)} ${y(pts[0][1]).toFixed(1)}`;
      for (let i = 1; i < pts.length; i++) d += ` H${X(pts[i][0]).toFixed(1)} V${y(pts[i][1]).toFixed(1)}`;
      d += ` H${X(end).toFixed(1)}`;
      if (close) d += ` V${(H - B).toFixed(1)} H${X(Math.max(pts[0][0], start)).toFixed(1)} Z`;
      return d;
    };
    const line = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${X(Math.max(p[0], start)).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join(" ") + (pts.length ? ` L${X(end).toFixed(1)} ${Y(pts[pts.length - 1][1]).toFixed(1)}` : "");
    const grid = [lo, (lo + hi) / 2, hi].map((v) => `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" class="gl"/><text x="${L - 3}" y="${Y(v) + 3}" text-anchor="end" class="gt">${this._fmt(v, 0)}</text>`).join("");
    const hours = [];
    for (let h = 0; h <= 24; h += 6) {
      const t = start + h * 3600 * 1000, dt = new Date(t);
      hours.push(`<text x="${X(t)}" y="${H - 3}" text-anchor="middle" class="gt">${String(dt.getHours()).padStart(2, "0")}h</text>`);
    }
    return `
    <svg viewBox="0 0 ${W} ${H}" class="gsvg">
      ${grid}${hours.join("")}
      <path d="${step(pow, YP, true)}" fill="rgba(46,165,95,.18)" stroke="#2ea55f" stroke-width="1"/>
      <path d="${step(spt, Y, false)}" fill="none" stroke="#3498db" stroke-width="1.6"/>
      <path d="${line(temp)}" fill="none" stroke="#e67e22" stroke-width="1.8"/>
      <text x="${W - R + 3}" y="${YP(5) + 3}" class="gt">P5</text><text x="${W - R + 3}" y="${YP(1) + 3}" class="gt">P1</text>
    </svg>
    <div class="legend"><span><i style="background:#e67e22"></i>${this._t("temp")}</span><span><i style="background:#3498db"></i>${this._t("setpoint")}</span><span><i style="background:#2ea55f"></i>${this._t("power")}</span></div>`;
  }

  /* ------------------------------------------------------------ actions */
  _onAction(ev, el) {
    ev.stopPropagation();
    const act = el.dataset.act, ent = el.dataset.entity, val = el.dataset.val, clim = this._resolved.climate;
    const a = this._s("climate")?.attributes || {};
    switch (act) {
      case "sp-": case "sp+": {
        const step = a.target_temp_step || 0.5;
        const t = Math.min(a.max_temp ?? 30, Math.max(a.min_temp ?? 15, Number(a.temperature) + (act === "sp+" ? step : -step)));
        this._call("climate", "set_temperature", { entity_id: clim, temperature: t });
        break;
      }
      case "power":
        if (this._confirm === "power") {
          this._confirm = null;
          this._call("climate", "set_hvac_mode", { entity_id: clim, hvac_mode: this._isOn() ? "off" : "heat" });
        } else {
          this._confirm = "power";
          clearTimeout(this._ct);
          this._ct = setTimeout(() => { this._confirm = null; this._sig = ""; this._render(); }, 4000);
        }
        this._sig = ""; this._render();
        break;
      case "preset": this._call("climate", "set_preset_mode", { entity_id: clim, preset_mode: val }); break;
      case "fan1": this._call("climate", "set_fan_mode", { entity_id: clim, fan_mode: val }); break;
      case "fan2": this._call("select", "select_option", { entity_id: this._resolved.fan2, option: val }); break;
      case "toggle": this._call("homeassistant", "toggle", { entity_id: ent }); break;
      case "off": this._call("homeassistant", "turn_off", { entity_id: ent.split(",") }); break;
      case "num-": case "num+": {
        const s = this._hass.states[ent]; if (!s) break;
        const st = Number(s.attributes.step) || 0.5;
        const v = Math.min(Number(s.attributes.max ?? 30), Math.max(Number(s.attributes.min ?? 5), Number(s.state) + (act === "num+" ? st : -st)));
        this._call("number", "set_value", { entity_id: ent, value: v });
        break;
      }
      case "more": if (ent) this._moreInfo(ent); break;
      case "page": {
        const pg = el.dataset.page;
        if (pg === "close") { this._page = null; this._draft = null; }
        else { this._page = /^\d+$/.test(pg) ? Number(pg) : pg; if (pg !== "new") this._draft = null; }
        this._confirm = null; this._sig = ""; this._render();
        break;
      }
      case "close-bg": if (ev.target === el) { this._page = null; this._draft = null; this._sig = ""; this._render(); } break;
      case "pmode": this._call("select", "select_option", { entity_id: ent, option: val }); break;
      case "day": {
        const n = el.dataset.n === "new" ? "new" : Number(el.dataset.n), d = Number(el.dataset.d);
        const set = new Set(this._vals(n).days);
        set.has(d) ? set.delete(d) : set.add(d);
        if (set.size) this._setField(n, "days", [...set].sort());
        break;
      }
      case "fsp": {
        const n = el.dataset.n === "new" ? "new" : Number(el.dataset.n), v = this._vals(n);
        const ns = n === "new" ? null : this._hass.states[v.p.setpoint];
        const step = Number(ns?.attributes?.step) || 0.5, lo = Number(ns?.attributes?.min ?? 10), hi = Number(ns?.attributes?.max ?? 28);
        this._setField(n, "setpoint", Math.min(hi, Math.max(lo, (Number(v.setpoint) || 20) + (val === "+" ? step : -step))));
        break;
      }
      case "fill": {
        if (this._confirm === "fill") {
          this._confirm = null;
          this._call("button", "press", { entity_id: this._resolved.res_filled });
        } else {
          this._confirm = "fill";
          clearTimeout(this._ct);
          this._ct = setTimeout(() => { this._confirm = null; this._sig = ""; this._render(); }, 4000);
        }
        this._sig = ""; this._render();
        break;
      }
      case "move": {
        const n = Number(el.dataset.n), to = n + Number(el.dataset.val);
        if (to >= 1 && to <= this._resolved.profiles.length) this._call(ECC_DOMAIN, "move_profile", { profile: n, position: to });
        break;
      }
      case "tag": {
        const n = Number(el.dataset.n), f = el.dataset.f, v = this._vals(n);
        if (f === "mode") { this._setField(n, "mode", v.mode === "standby" ? "run" : "standby"); break; }
        if (f === "relax") { this._setField(n, "relax", !v.relax); break; }
        const o = Object.assign(this._defOpts(), Object.fromEntries(Object.entries(v.opts || {}).filter(([, x]) => x)))[f] || [];
        if (o.length) this._setField(n, f, o[(o.indexOf(v[f]) + 1) % o.length]);
        break;
      }
      case "fbool": {
        const n = el.dataset.n === "new" ? "new" : Number(el.dataset.n), v = this._vals(n), f = el.dataset.f;
        this._setField(n, f, f === "mode" ? (v.mode === "standby" ? "run" : "standby") : !v.relax);
        break;
      }
      case "create": {
        const d = this._draft;
        this._call(ECC_DOMAIN, "add_profile", { name: d.name, start: d.start, end: d.end, days: d.days, setpoint: d.setpoint, mode: d.mode,
          power: d.power, fan1: d.fan1, ...(d.fan2 != null ? { fan2: d.fan2 } : {}), relax: d.relax, active: true });
        this._draft = null; this._page = "list"; this._resolved = null;
        break;
      }
      case "del": {
        const n = Number(el.dataset.n);
        if (this._confirm === "del" + n) {
          this._confirm = null; this._page = "list";
          this._call(ECC_DOMAIN, "remove_profile", { profile: n });
          this._resolved = null;
        } else {
          this._confirm = "del" + n;
          clearTimeout(this._ct);
          this._ct = setTimeout(() => { this._confirm = null; this._sig = ""; this._render(); }, 4000);
        }
        this._sig = ""; if (this._resolved) this._render();
        break;
      }
    }
  }

  _onDD(el) {
    const v = el.value, clim = this._resolved.climate;
    switch (el.dataset.dd) {
      case "preset": this._call("climate", "set_preset_mode", { entity_id: clim, preset_mode: v }); break;
      case "fan1": this._call("climate", "set_fan_mode", { entity_id: clim, fan_mode: v }); break;
      case "fan2": this._call("select", "select_option", { entity_id: this._resolved.fan2, option: v }); break;
    }
  }

  _onInput(el) {
    const ent = el.dataset.entity, v = el.value;
    if (!ent || !v) return;
    if (el.dataset.in === "time") this._call("time", "set_value", { entity_id: ent, time: v.length === 5 ? v + ":00" : v });
    else this._call("text", "set_value", { entity_id: ent, value: v });
  }

  _onSelect(el) {
    const ent = this._resolved[el.dataset.sel];
    if (ent) this._call("select", "select_option", { entity_id: ent, option: el.value });
  }
}

const ECC_CSS = `
:host { --ecc-accent: #f06b21; --ecc-soft: rgba(127,127,127,.10); }
ha-card { padding: 14px 14px 12px; overflow: hidden; }
ha-icon { --mdc-icon-size: 18px; display: inline-flex; }
button { font: inherit; color: inherit; border: none; background: none; cursor: pointer; }
.sep { height: 1px; background: var(--divider-color, rgba(127,127,127,.2)); margin: 12px -14px; }
.head { display: grid; grid-template-columns: 120px 1fr; grid-template-areas: "title right" "state state" "anim thermo" "anim infos"; column-gap: 12px; row-gap: 2px; }
.title { grid-area: title; font-size: 16px; font-weight: 600; align-self: center; min-width: 0; }
.hdr-right { grid-area: right; justify-self: end; }
.state { grid-area: state; font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.anim { grid-area: anim; }
.thermo { grid-area: thermo; display: flex; flex-direction: column; align-items: center; padding-top: 2px; }
.tsub { display: flex; align-items: center; gap: 4px; font-size: 13px; font-weight: 500; color: var(--secondary-text-color); margin-top: 2px; cursor: pointer; min-width: 0; }
.tsub ha-icon { --mdc-icon-size: 16px; } .tsub span { color: var(--primary-text-color); white-space: nowrap; }
.tsub small { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.curt { display: flex; flex-direction: column; align-items: center; line-height: 1.25; margin-bottom: 2px; }
.curt small { font-size: 12px; color: var(--secondary-text-color); } .curt b { font-size: 15px; font-weight: 600; }
.dial { position: relative; width: 100%; max-width: 190px; aspect-ratio: 1; }
.dial svg { width: 100%; height: 100%; display: block; }
.dial path { fill: none; stroke-linecap: round; stroke-width: 14; }
.dial .track { stroke: rgba(127,127,127,.18); }
.dial .fill { opacity: .45; }
.dial .handle { fill: #fff; stroke-width: 5; }
.dial .curdot { fill: #fff; opacity: .85; }
.dc { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; padding-bottom: 8%; pointer-events: none; }
.dlabel { font-size: 13px; font-weight: 600; }
.dval { display: flex; align-items: flex-start; line-height: 1; margin-top: 2px; }
.dint { font-size: 44px; font-weight: 400; }
.dside { display: flex; flex-direction: column; justify-content: space-between; height: 40px; margin-left: 2px; font-size: 16px; }
.dside span:last-child { font-size: 20px; }
.dbtn { position: absolute; left: 0; right: 0; bottom: 2%; display: flex; justify-content: center; gap: 18px; }
.dbtn .round { background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, rgba(127,127,127,.35)); }
.infos { grid-area: infos; text-align: center; font-size: 12px; line-height: 1.55; color: var(--secondary-text-color); margin-top: 2px; }
.room { display: flex; align-items: flex-start; }
.big { font-size: 40px; font-weight: 400; line-height: 1; }
.unit { font-size: 16px; margin-left: 2px; opacity: .7; }
.lbl { font-size: 12px; color: var(--secondary-text-color); margin-bottom: 8px; }
.sp { display: flex; align-items: center; gap: 10px; }
.spv { display: flex; flex-direction: column; align-items: center; min-width: 56px; }
.spv span { font-size: 20px; font-weight: 600; color: var(--ecc-accent); }
.spv small { font-size: 11px; color: var(--secondary-text-color); }
.round { width: 36px; height: 36px; border-radius: 50%; background: var(--ecc-soft); display: inline-flex; align-items: center; justify-content: center; }
.round:active, .btn:active, .seg button:active, .dd:active, .daysel button:active { transform: scale(.96); }
.round.sm { width: 28px; height: 28px; }
.chip { display: inline-flex; align-items: center; gap: 4px; padding: 4px 8px 4px 10px; border-radius: 14px; background: var(--ecc-soft); font-size: 12px; font-weight: 600; position: relative; max-width: 180px; }
.chip span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.chip select { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.green { color: #66bb6a; } .red { color: #e53935; }
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
.btn { display: flex; align-items: center; gap: 8px; height: 48px; padding: 0 12px; border-radius: 12px; background: var(--ecc-soft); font-size: 13px; font-weight: 600; text-align: left; }
.btn ha-icon { color: var(--secondary-text-color); }
.btn.hot { background: rgba(240,107,33,.12); color: var(--ecc-accent); } .btn.hot ha-icon { color: var(--ecc-accent); }
.btn.confirm { background: rgba(229,57,53,.15); color: #e53935; } .btn.confirm ha-icon { color: #e53935; }
.btn.act { background: rgba(240,107,33,.12); } .btn.act ha-icon { color: var(--ecc-accent); }
.btn .dot { margin-left: auto; width: 10px; height: 10px; border-radius: 50%; background: rgba(127,127,127,.35); }
.btn .dot.on { background: var(--ecc-accent); }
.sec-title { display: flex; align-items: center; justify-content: space-between; font-size: 15px; font-weight: 600; margin-bottom: 8px; }
.lbl2 { font-size: 12px; color: var(--secondary-text-color); margin: 8px 0 4px; }
.seg { display: flex; gap: 4px; background: var(--ecc-soft); padding: 3px; border-radius: 12px; }
.seg button { flex: 1; padding: 7px 0; border-radius: 9px; font-size: 12px; font-weight: 600; color: var(--secondary-text-color); white-space: nowrap; }
.seg button.on { background: var(--card-background-color, #fff); color: var(--ecc-accent); box-shadow: 0 1px 3px rgba(0,0,0,.15); }
.mini { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 14px; background: var(--ecc-soft); color: var(--secondary-text-color); }
.mini.on { background: rgba(46,165,95,.14); color: #2ea55f; }
.banner { display: grid; grid-template-columns: 22px 1fr auto; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 14px; background: rgba(240,107,33,.10); border: 1px solid rgba(240,107,33,.35); margin-bottom: 8px; font-size: 12px; line-height: 16px; }
.banner ha-icon { color: var(--ecc-accent); }
.banner span { opacity: .8; }
.banner button { padding: 6px 12px; border-radius: 14px; background: rgba(240,107,33,.18); color: var(--ecc-accent); font-size: 12px; font-weight: 600; }
.dd3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.dd3.two { grid-template-columns: repeat(2, 1fr); }
.dd1 { display: grid; }
.dd { position: relative; display: flex; flex-direction: column; padding: 6px 26px 7px 10px; border-radius: 12px; background: var(--ecc-soft); min-width: 0; cursor: pointer; }
.dd small { font-size: 11px; color: var(--secondary-text-color); white-space: nowrap; }
.dd span { font-size: 14px; font-weight: 600; color: var(--ecc-accent); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dd ha-icon { position: absolute; right: 6px; top: 50%; transform: translateY(-50%); color: var(--secondary-text-color); }
.dd select { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; }
.profiles { display: flex; flex-direction: column; gap: 6px; }
.pwrap { border-radius: 12px; background: var(--ecc-soft); border: 1px solid transparent; }
.pwrap.cur { border-color: rgba(240,107,33,.55); background: rgba(240,107,33,.08); }
.tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.tag { font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 9px; background: rgba(127,127,127,.14); color: var(--secondary-text-color); white-space: nowrap; }
.tag:active { transform: scale(.94); }
.tag.sb { background: rgba(255,171,64,.20); color: #e08a00; }
.tag.run { background: rgba(240,107,33,.16); color: var(--ecc-accent); }
.tag.rx { background: rgba(46,165,95,.16); color: #2ea55f; }
.tag.off { background: rgba(127,127,127,.10); color: var(--secondary-text-color); opacity: .55; }
.overlay { position: fixed; inset: 0; z-index: 9; background: rgba(0,0,0,.45); display: flex; align-items: flex-end; justify-content: center; }
.sheet { width: 100%; max-width: 520px; max-height: 92vh; overflow-y: auto; box-sizing: border-box; background: var(--card-background-color, #fff); color: var(--primary-text-color); border-radius: 20px 20px 0 0; padding: 12px 14px calc(16px + env(safe-area-inset-bottom)); }
@media (min-width: 700px) { .overlay { align-items: center; } .sheet { border-radius: 20px; } }
.mgr-card { padding: 12px 14px 14px; }
.mhead { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.mhead b { flex: 1; font-size: 17px; }
.mhead .hicon { --mdc-icon-size: 22px; color: var(--ecc-accent); }
.mlist { display: flex; flex-direction: column; gap: 6px; }
.ord { display: flex; flex-direction: column; gap: 4px; }
.round.xs { width: 26px; height: 26px; }
.round:disabled { opacity: .3; cursor: default; }
.tstep { display: flex; align-items: center; gap: 4px; height: 36px; }
.tval { position: relative; min-width: 50px; text-align: center; font-weight: 600; font-size: 15px; cursor: pointer; }
.tval input { position: absolute; inset: 0; opacity: 0; width: 100%; cursor: pointer; }
.plist { display: flex; flex-direction: column; }
.dayh { display: flex; justify-content: space-between; align-items: baseline; margin: 12px 2px 4px; font-size: 14px; }
.dayh b::first-letter { text-transform: uppercase; }
.dayh span { font-size: 12px; color: var(--secondary-text-color); }
.igt { width: 100%; border-collapse: collapse; font-size: 14px; }
.igt th { font-size: 11px; font-weight: 600; color: var(--secondary-text-color); text-align: center; padding: 4px; }
.igt td { text-align: center; padding: 7px 4px; border-top: 1px solid var(--divider-color, rgba(127,127,127,.2)); font-variant-numeric: tabular-nums; }
.igt td i { color: var(--ecc-accent); font-style: normal; font-weight: 600; }
.igsum { display: grid; grid-template-columns: 1fr auto; gap: 6px 12px; margin-top: 14px; padding: 12px; border-radius: 12px; background: var(--ecc-soft); font-size: 14px; }
.prow { display: grid; grid-template-columns: 24px 1fr auto auto; align-items: center; gap: 10px; padding: 10px 2px; border-bottom: 1px solid var(--divider-color, rgba(127,127,127,.2)); font-size: 14px; }
.prow ha-icon { color: var(--secondary-text-color); }
.prow b { font-weight: 600; }
.primary.warn { background: #e53935; }
.mrow { display: grid; grid-template-columns: 40px 1fr 26px; align-items: center; gap: 10px; padding: 9px 10px; border-radius: 12px; background: var(--ecc-soft); border: 1px solid transparent; }
.mrow.cur { border-color: rgba(240,107,33,.55); background: rgba(240,107,33,.08); }
.mrow.dis .pn { opacity: .45; }
.chev { color: var(--secondary-text-color); cursor: pointer; }
.primary { display: flex; align-items: center; justify-content: center; gap: 6px; width: 100%; height: 44px; margin-top: 10px; border-radius: 12px; background: var(--ecc-accent); color: #fff; font-size: 14px; font-weight: 600; }
.hint { font-size: 11px; color: var(--secondary-text-color); text-align: center; margin-top: 8px; }
.pedit { display: flex; flex-direction: column; gap: 10px; }
.frow { display: flex; gap: 8px; }
.fld { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.fld.grow { flex: 1; }
.fld small { font-size: 11px; color: var(--secondary-text-color); }
.fld input { font: inherit; font-size: 14px; font-weight: 600; color: var(--primary-text-color); background: var(--ecc-soft); border: 1px solid var(--divider-color, rgba(127,127,127,.3)); border-radius: 10px; padding: 7px 8px; min-width: 0; width: 100%; box-sizing: border-box; color-scheme: light dark; }
.fld input[type=time] { min-width: 96px; }
.fld .pc { height: 36px; }
.daysel { display: flex; gap: 4px; }
.daysel button { flex: 1; height: 34px; border-radius: 10px; background: var(--ecc-soft); border: 1px solid var(--divider-color, rgba(127,127,127,.3)); font-size: 12px; font-weight: 600; color: var(--secondary-text-color); }
.daysel button.on { background: var(--ecc-accent); border-color: var(--ecc-accent); color: #fff; }
.pedit .row2 { margin-top: 0; }
.pfoot { display: flex; justify-content: space-between; align-items: center; }
.del { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 600; color: #e53935; padding: 4px 8px; border-radius: 14px; }
.del.confirm { background: rgba(229,57,53,.15); }
.add { display: flex; align-items: center; justify-content: center; gap: 6px; width: 100%; margin-top: 8px; height: 40px; border-radius: 12px; border: 1.5px dashed rgba(240,107,33,.5); color: var(--ecc-accent); font-size: 13px; font-weight: 600; }
.prof { display: grid; grid-template-columns: 40px 1fr auto; align-items: center; gap: 10px; padding: 8px 10px; }
.prof.dis .pn, .prof.dis .pc { opacity: .45; }
.pn { display: flex; flex-direction: column; cursor: pointer; min-width: 0; }
.pn b { font-size: 13px; } .pn span { font-size: 11px; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pc { display: flex; align-items: center; gap: 6px; font-weight: 600; font-size: 14px; }
.pc span { min-width: 38px; text-align: center; color: var(--ecc-accent); }
.sw { width: 36px; height: 20px; border-radius: 10px; background: rgba(127,127,127,.35); position: relative; transition: background .2s; }
.sw span { position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%; background: #fff; transition: left .2s; box-shadow: 0 1px 2px rgba(0,0,0,.3); }
.sw.on { background: var(--ecc-accent); } .sw.on span { left: 18px; }
.graph { margin-bottom: 8px; }
.gsvg { width: 100%; height: auto; display: block; }
.gl { stroke: var(--divider-color, rgba(127,127,127,.25)); stroke-width: .6; stroke-dasharray: 2 3; }
.gt { font-size: 8px; fill: var(--secondary-text-color); }
.gload { font-size: 12px; color: var(--secondary-text-color); padding: 20px 0; text-align: center; }
.legend { display: flex; justify-content: center; gap: 14px; font-size: 11px; color: var(--secondary-text-color); }
.legend i { display: inline-block; width: 10px; height: 3px; border-radius: 2px; margin-right: 4px; vertical-align: middle; }
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.tile { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 10px 4px; border-radius: 12px; background: var(--ecc-soft); cursor: pointer; text-align: center; }
.tile ha-icon { --mdc-icon-size: 22px; }
.tl { font-size: 11px; color: var(--secondary-text-color); } .tv { font-size: 13px; font-weight: 600; }
.stove { width: 120px; height: auto; display: block; overflow: visible; }
.imgw { position: relative; width: 120px; margin-top: 12px; }
.imgw { aspect-ratio: 140 / 212; }
.imgw img { width: 100%; height: 100%; object-fit: contain; display: block; }
.imgwaves { position: absolute; left: 0; top: -14px; width: 100%; height: 14px; overflow: visible; }
.imgwin { position: absolute; overflow: hidden; }
.imgwin svg { width: 100%; height: 100%; display: block; }
.imgbar { display: flex; align-items: center; justify-content: space-between; width: 120px; margin-top: 4px; }
.imgbar .fan { transform-box: fill-box; transform-origin: center; }
.lcd { background: #0c1720; border: 1px solid #8f98a2; border-radius: 3px; padding: 1px 4px; font: 8px monospace; white-space: nowrap; overflow: hidden; max-width: 80px; }
.lowtxt { font-size: 10px; text-align: center; width: 120px; margin-top: 2px; }
.glowp { animation: ecc-glow 2.6s ease-in-out infinite; }
@keyframes ecc-glow { 0%,100% { opacity: .45; } 50% { opacity: .9; } }
.stove.lit { filter: drop-shadow(0 0 8px rgba(255,120,0,.45)); }
.fl path { transform-box: fill-box; transform-origin: 50% 100%; animation: ecc-fl 1.1s ease-in-out infinite alternate; }
@keyframes ecc-fl { from { transform: scaleY(.88) skewX(-3deg); } to { transform: scaleY(1.08) skewX(3deg); } }
.fan { animation: ecc-spin var(--d) linear infinite; }
@keyframes ecc-spin { to { transform: rotate(360deg); } }
.wave { animation: ecc-wave 2s ease-in-out infinite; opacity: 0; }
@keyframes ecc-wave { 0% { opacity: 0; transform: translateY(4px); } 50% { opacity: .9; } 100% { opacity: 0; transform: translateY(-6px); } }
.blink { animation: ecc-blink 1s steps(2) infinite; }
@keyframes ecc-blink { 50% { opacity: .35; } }
@media (max-width: 380px) { .head { grid-template-columns: 100px 1fr; } .stove, .imgw, .imgbar, .lowtxt { width: 100px; } .big { font-size: 34px; } }
`;


/* Éditeur visuel : thermostat, titre, dessin intégré ou image personnelle (avec position de la vitre) */
const ECC_ED_I18N = {
  fr: { climate: "Thermostat du poêle", title: "Titre", image_mode: "Image du poêle", bild9: "Edilkamin Bild 9+", builtin: "Dessin simple", custom: "Image personnelle",
    image: "Adresse de l'image (ex. /local/poele/poele.svg)", win_x: "Vitre : gauche (%)", win_y: "Vitre : haut (%)", win_w: "Vitre : largeur (%)",
    win_h: "Vitre : hauteur (%)", image_calibration: "Afficher le cadre de la vitre (réglage)", mode: "Affichage", full: "Carte complète", planning: "Menu des programmations seul", temperature_entity: "Thermomètre (affiché sous le titre)", temperature_name: "Nom du thermomètre (vide = nom de l'entité)",
    show_header: "Poêle (image, thermostat, allumage et « Gérer les programmations »)",
    show_modes: "Réglages manuels (puissance, ventilations, stand-by, silence)",
    show_planning: "Programmation (liste des programmations)",
    show_tracking: "Suivi (graphique, allumages, granulés, alarme)",
    open_options: "Options de l'intégration", open_options_hint: "Fenêtres, présence, historique, planning de secours… Réglages communs à toutes les cartes. Pensez à enregistrer la carte avant." },
  en: { climate: "Stove thermostat", title: "Title", image_mode: "Stove picture", bild9: "Edilkamin Bild 9+", builtin: "Simple drawing", custom: "Own picture",
    image: "Picture URL (e.g. /local/stove/stove.svg)", win_x: "Glass: left (%)", win_y: "Glass: top (%)", win_w: "Glass: width (%)",
    win_h: "Glass: height (%)", image_calibration: "Show the glass frame (calibration)", mode: "Display", full: "Full card", planning: "Schedule menu only", temperature_entity: "Thermometer (shown under the title)", temperature_name: "Thermometer name (empty = entity name)",
    show_header: "Stove (picture, thermostat, on/off and “Manage schedules”)",
    show_modes: "Manual settings (power, fans, standby, silent)",
    show_planning: "Schedules (schedule list)",
    show_tracking: "Tracking (graph, ignitions, pellets, alarm)",
    open_options: "Integration options", open_options_hint: "Windows, presence, history, fallback schedule… Settings shared by all cards. Save the card first." },
};

class EdilkaminControlCardEditor extends HTMLElement {
  setConfig(config) { this._config = { ...config }; this._render(); }
  set hass(hass) { this._hass = hass; if (this._form) this._form.hass = hass; else this._render(); }

  _t(k) { const l = (this._hass?.locale?.language || "fr").slice(0, 2); return (ECC_ED_I18N[l] || ECC_ED_I18N.en)[k] || k; }

  _data() {
    const c = this._config || {}, w = c.image_window || {};
    const im = c.image || "bild9";
    const kind = im === "default" ? "generic" : (ECC_IMAGES[im] || im === "generic") ? im : "custom";
    const custom = kind === "custom";
    return { climate: c.climate, title: c.title, temperature_entity: c.temperature_entity, temperature_name: c.temperature_name, image_mode: kind,
      show_header: c.show_header !== false, show_modes: c.show_modes !== false, show_planning: c.show_planning !== false, show_tracking: c.show_tracking !== false,
      image: custom ? c.image : "", win_x: w.x ?? 25, win_y: w.y ?? 25, win_w: w.width ?? 50, win_h: w.height ?? 40,
      image_calibration: !!c.image_calibration };
  }

  _schema(d) {
    const num = (name) => ({ name, selector: { number: { min: 0, max: 100, step: 0.1, mode: "box" } } });
    const s = [
      { name: "show_header", selector: { boolean: {} } },
      { name: "show_modes", selector: { boolean: {} } },
      { name: "show_planning", selector: { boolean: {} } },
      { name: "show_tracking", selector: { boolean: {} } },
      { name: "climate", required: true, selector: { entity: { domain: "climate" } } },
      { name: "title", selector: { text: {} } },
      { name: "temperature_entity", selector: { entity: { filter: { domain: "sensor", device_class: "temperature" } } } },
      ...(d.temperature_entity ? [{ name: "temperature_name", selector: { text: {} } }] : []),
      { name: "image_mode", selector: { select: { mode: "dropdown", options: [{ value: "bild9", label: this._t("bild9") }, { value: "generic", label: this._t("builtin") }, { value: "custom", label: this._t("custom") }] } } },
    ];
    if (d.image_mode === "custom") {
      s.push({ name: "image", selector: { text: {} } },
        { type: "grid", name: "", schema: [num("win_x"), num("win_y"), num("win_w"), num("win_h")] },
        { name: "image_calibration", selector: { boolean: {} } });
    }
    return s;
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._opt) {
      // Raccourci vers les options de l'intégration (fenêtres, présence…), réglages communs à toutes les cartes
      this._opt = document.createElement("div");
      this._opt.style.cssText = "display:flex;align-items:center;gap:12px;margin:0 0 16px;padding:10px 12px;border-radius:12px;background:var(--secondary-background-color)";
      const btn = document.createElement("ha-button");
      btn.addEventListener("click", () => this._openOptions());
      const hint = document.createElement("span");
      hint.style.cssText = "font-size:12px;color:var(--secondary-text-color);line-height:1.35";
      this._opt.append(btn, hint);
      this.appendChild(this._opt);
    }
    this._opt.firstChild.textContent = this._t("open_options");
    this._opt.lastChild.textContent = this._t("open_options_hint");
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (sc) => this._t(sc.name);
      this._form.addEventListener("value-changed", (ev) => this._changed(ev.detail.value));
      this.appendChild(this._form);
    }
    const d = this._data();
    this._form.hass = this._hass;
    this._form.data = d;
    this._form.schema = this._schema(d);
  }

  // Ouvre la page de l'intégration sur cette entrée, puis sa fenêtre d'options dès qu'elle est affichée
  async _openOptions() {
    let id = null;
    try {
      const es = await this._hass.callWS({ type: "config_entries/get", domain: ECC_DOMAIN });
      const mine = es.find((e) => e.unique_id === this._config?.climate) || es.find((e) => e.state === "loaded") || es[0];
      id = mine?.entry_id || null;
    } catch (_e) { /* pas administrateur : la page de l'intégration suffit */ }
    history.pushState(null, "", `/config/integrations/integration/${ECC_DOMAIN}${id ? `?config_entry=${id}` : ""}`);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
    if (!id) return;
    const findRow = (root) => {
      for (const e of root.querySelectorAll("*")) {
        if (e.tagName === "HA-CONFIG-ENTRY-ROW" && (e.dataset?.entryId === id || e.entry?.entry_id === id)) return e;
        if (e.shadowRoot) { const r = findRow(e.shadowRoot); if (r) return r; }
      }
      return null;
    };
    // Bouton « Configurer » de la ligne : icône engrenage (repérée par son tracé ou son libellé)
    const isCog = (b) => /^M12,8A4,4 0 0,1 16,1|^M12,15\.5A3\.5,3\.5/.test(String(b.path || "")) || /configur|konfigur/i.test(String(b.label || ""));
    for (let i = 0; i < 40; i++) {
      await new Promise((r) => setTimeout(r, 250));
      const row = findRow(document);
      const btn = row?.shadowRoot && [...row.shadowRoot.querySelectorAll("ha-icon-button")].find(isCog);
      if (btn) { btn.click(); return; }
    }
  }

  _changed(v) {
    const c = { ...this._config, climate: v.climate };
    for (const k of ["title", "temperature_entity", "temperature_name"]) { if (v[k]) c[k] = v[k]; else delete c[k]; }
    // Sections : enregistrées seulement quand elles sont masquées (affichées par défaut)
    for (const k of ["show_header", "show_modes", "show_planning", "show_tracking"]) { if (v[k] === false) c[k] = false; else delete c[k]; }
    if (v.image_mode === "custom") {
      c.image = v.image || "/local/poele.svg";
      c.image_window = { x: Number(v.win_x), y: Number(v.win_y), width: Number(v.win_w), height: Number(v.win_h) };
      if (v.image_calibration) c.image_calibration = true; else delete c.image_calibration;
    } else {
      if (v.image_mode === "bild9") delete c.image; else c.image = v.image_mode;
      delete c.image_window; delete c.image_calibration;
    }
    this._config = c;
    this._render();
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: c }, bubbles: true, composed: true }));
  }
}

// La carte est chargée très tôt par l'intégration : dans Home Assistant, attendre que l'interface ait
// installé son registre d'éléments personnalisés avant de déclarer la carte.
const eccDefine = () => {
  if (!customElements.get("edilkamin-control-card")) customElements.define("edilkamin-control-card", EdilkaminControlCard);
  if (!customElements.get("edilkamin-control-card-editor")) customElements.define("edilkamin-control-card-editor", EdilkaminControlCardEditor);
};
if (document.querySelector("home-assistant") || "hassConnection" in window) customElements.whenDefined("home-assistant").then(eccDefine);
else eccDefine();
window.customCards = window.customCards || [];
window.customCards.push({
  type: "edilkamin-control-card",
  name: "Edilkamin Control",
  description: "Pilotage et programmation d'un poêle Edilkamin (Edilkamin Control)",
  preview: true,
  documentationURL: "https://github.com/akoonet-homeassistant/edilkamin_control",
});
console.info(`%c EDILKAMIN-CONTROL-CARD %c ${ECC_VERSION} `, "color:#fff;background:#f06b21;font-weight:700", "color:#f06b21");
