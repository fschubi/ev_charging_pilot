/*
 * Smart EQ Charging Center – Sidebar-Panel (Masterplan §12.5).
 *
 * Keine Steuerlogik: Das Panel liest über die WebSocket-API und löst jede
 * Aktion über einen Service der Integration aus. Fünf Ansichten:
 * Cockpit · Ladeplan · Hausstrom · Drive & Energy · Diagnose.
 */

const DOMAIN = "smart_eq_charging";
const REFRESH_MS = 5000;
const WEEKDAYS = [
  ["mon", "Mo"], ["tue", "Di"], ["wed", "Mi"], ["thu", "Do"], ["fri", "Fr"], ["sat", "Sa"], ["sun", "So"],
];
const MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
const STATE_LABELS = {
  DISCONNECTED: "Nicht gesteckt", IDLE: "Bereit", ENABLING: "Freigabe läuft",
  WAITING_FOR_CHARGE: "Warte auf Ladung", CHARGE_STABILIZING: "Ladung stabilisiert",
  WAKEUP_OVMS: "Wakeup OVMS", WAKEUP_CP: "Wakeup CP", CHARGING: "Lädt",
  CHARGE_ENDED: "Ladung beendet", INTERRUPTED: "Unterbrochen", DISABLING: "Abschaltung läuft",
  COOLDOWN: "Pause", START_FAILED: "Start fehlgeschlagen",
};
const REASON_LABELS = {
  safety_lock: "Sicherheitssperre", override: "Override", rfid: "RFID", one_shot: "Heute Nacht",
  target_soc_reached: "Ziel-SOC erreicht", climate: "Vorklimatisierung", schedule: "Wochenplan",
  default_off: "Standard aus", automation_off: "Automatik aus",
};
const HEALTH_LABELS = { HEALTHY: "Gesund", DEGRADED: "Eingeschränkt", ERROR: "Fehler" };
const QUALITY_CLASS = {
  GOOD: "ok", LAST_KNOWN_VALID: "info", ESTIMATED: "info", STALE: "warn",
  CONFLICT: "bad", INVALID: "bad", UNAVAILABLE: "muted",
};
const VIEWS = [
  ["cockpit", "Cockpit"], ["plan", "Ladeplan"], ["home", "Hausstrom → Smart EQ"],
  ["drive", "Drive & Energy"], ["diag", "Diagnose"],
];

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const num = (value, digits = 1, unit = "") =>
  value === null || value === undefined || Number.isNaN(Number(value))
    ? "–"
    : `${Number(value).toLocaleString("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits })}${unit ? " " + unit : ""}`;
const time = (iso) =>
  iso ? new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" }) : "–";
const dateTime = (iso) =>
  iso ? new Date(iso).toLocaleString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "–";
const dateOnly = (iso) => (iso ? new Date(iso).toLocaleDateString("de-DE") : "–");

const STYLE = `
  :host { display: block; background: var(--primary-background-color); min-height: 100vh;
          color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, inherit); }
  header { display: flex; align-items: center; gap: 12px; padding: 0 16px; height: 56px;
           background: var(--app-header-background-color, var(--primary-color));
           color: var(--app-header-text-color, #fff); position: sticky; top: 0; z-index: 2; }
  header h1 { font-size: 20px; font-weight: 400; margin: 0; flex: 1; white-space: nowrap;
              overflow: hidden; text-overflow: ellipsis; }
  .menu { background: none; border: none; color: inherit; font-size: 22px; cursor: pointer; }
  .badge { font-size: 12px; padding: 3px 8px; border-radius: 10px; background: rgba(255,255,255,.2); }
  .badge.live { background: var(--success-color, #2e7d32); }
  nav { display: flex; gap: 4px; padding: 8px 16px 0; overflow-x: auto;
        border-bottom: 1px solid var(--divider-color); background: var(--card-background-color); }
  nav button { background: none; border: none; padding: 10px 14px; cursor: pointer; font: inherit;
               color: var(--secondary-text-color); border-bottom: 2px solid transparent; white-space: nowrap; }
  nav button.active { color: var(--primary-color); border-bottom-color: var(--primary-color); }
  main { padding: 16px; max-width: 1200px; margin: 0 auto; box-sizing: border-box; }
  .grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
  .card { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); padding: 16px; }
  .card h2 { font-size: 16px; font-weight: 500; margin: 0 0 12px; }
  .wide { grid-column: 1 / -1; }
  .big { font-size: 28px; font-weight: 500; }
  .sub { color: var(--secondary-text-color); font-size: 13px; }
  .row { display: flex; justify-content: space-between; gap: 8px; padding: 4px 0; font-size: 14px; }
  .row span:first-child { color: var(--secondary-text-color); }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; }
  button.act { border: 1px solid var(--divider-color); background: var(--card-background-color);
               color: var(--primary-text-color); border-radius: 18px; padding: 8px 14px; cursor: pointer; font: inherit; }
  button.act.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; }
  button.act.danger { color: var(--error-color); }
  button.act:disabled { opacity: .45; cursor: default; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
  .ok { background: rgba(46,125,50,.15); color: var(--success-color, #2e7d32); }
  .info { background: rgba(2,136,209,.15); color: var(--info-color, #0288d1); }
  .warn { background: rgba(245,124,0,.15); color: var(--warning-color, #f57c00); }
  .bad { background: rgba(198,40,40,.15); color: var(--error-color, #c62828); }
  .muted { background: rgba(127,127,127,.15); color: var(--secondary-text-color); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--divider-color); vertical-align: top; }
  th { color: var(--secondary-text-color); font-weight: 500; }
  td.n, th.n { text-align: right; white-space: nowrap; }
  .scroll { overflow-x: auto; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
  input, select { font: inherit; padding: 6px 8px; border-radius: 6px; border: 1px solid var(--divider-color);
                  background: var(--card-background-color); color: var(--primary-text-color); }
  .form { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); align-items: end; }
  .days { display: flex; gap: 6px; flex-wrap: wrap; }
  .days label { flex-direction: row; align-items: center; gap: 4px; color: var(--primary-text-color); }
  .bar { height: 8px; border-radius: 4px; background: var(--divider-color); overflow: hidden; }
  .bar > div { height: 100%; background: var(--primary-color); }
  .notice { padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; }
  svg text { fill: var(--secondary-text-color); font-size: 10px; }
  .toast { position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%); padding: 10px 16px;
           border-radius: 8px; background: var(--primary-text-color); color: var(--card-background-color); z-index: 5; }
  @media (max-width: 600px) { main { padding: 8px; } .grid { gap: 8px; } }
`;

class SmartEqPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._view = localStorage.getItem("smart-eq-view") || "cockpit";
    this._state = null;
    this._cache = {};
    this._plans = null;
    this._year = new Date().getFullYear();
    this._month = new Date().getMonth() + 1;
    this._eventFilter = "";
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._start();
  }

  set narrow(value) { this._narrow = value; }
  set panel(value) { this._panel = value; }

  connectedCallback() { if (this._hass) this._start(); }

  disconnectedCallback() { clearInterval(this._timer); this._timer = null; }

  _start() {
    if (this._timer) return;
    this._refresh();
    this._timer = setInterval(() => this._refresh(), REFRESH_MS);
  }

  async _ws(type, extra = {}) {
    return this._hass.callWS({ type: `${DOMAIN}/${type}`, ...extra });
  }

  async _call(service, data = {}, label = "") {
    try {
      await this._hass.callService(DOMAIN, service, data);
      this._toast(label || "Erledigt");
      this._cache = {};
      await this._refresh();
    } catch (err) {
      this._toast(`Fehler: ${err.message || err}`);
    }
  }

  _toast(text) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = text;
    this.shadowRoot.appendChild(el);
    setTimeout(() => el.remove(), 3000);
  }

  async _refresh() {
    try {
      this._state = await this._ws("state");
      this._error = null;
    } catch (err) {
      this._error = err.message || String(err);
    }
    await this._loadView();
    this._render();
  }

  async _loadView() {
    const c = this._cache;
    try {
      if (this._view === "home") {
        const key = `${this._year}-${this._month}`;
        if (c.monthKey !== key) {
          c.month = await this._ws("get_month_statistics", { year: this._year, month: this._month });
          c.year = await this._ws("get_year_statistics", { year: this._year });
          c.sessions = await this._ws("get_sessions", { limit: 500 });
          c.reports = (await this._ws("list_reports")).items;
          c.monthKey = key;
        }
      } else if (this._view === "drive") {
        if (!c.trips) {
          c.trips = await this._ws("get_trips", { limit: 200 });
          c.external = await this._ws("get_external_charges", { limit: 200 });
          c.temps = await this._ws("get_temperature_statistics", { year: this._year });
          c.yearDrive = await this._ws("get_year_statistics", { year: this._year });
        }
      } else if (this._view === "diag") {
        c.events = await this._ws("get_events", { limit: 200, ...(this._eventFilter ? { category: this._eventFilter } : {}) });
        if (!c.replay) c.replay = await this._ws("get_replay");
      } else if (this._view === "plan" && this._plans === null && this._state) {
        this._plans = JSON.parse(JSON.stringify(this._state.plans));
      }
    } catch (err) {
      this._error = err.message || String(err);
    }
  }

  _setView(view) {
    this._view = view;
    localStorage.setItem("smart-eq-view", view);
    this._cache = {};
    this._plans = null;
    this._refresh();
  }

  // ------------------------------------------------------------------ render

  _render() {
    const s = this._state;
    const mode = s ? s.mode : "";
    const modeLabel = { dry_run: "DRY-RUN", live: "LIVE", replay: "REPLAY" }[mode] || "";
    const body = !s
      ? `<div class="card">${this._error ? `Fehler: ${esc(this._error)}` : "Lade …"}</div>`
      : { cockpit: () => this._cockpit(s), plan: () => this._planView(s), home: () => this._home(),
          drive: () => this._drive(), diag: () => this._diag(s) }[this._view]();
    const focused = this.shadowRoot.activeElement;
    if (focused && ["INPUT", "SELECT"].includes(focused.tagName)) {
      // Never re-render under the user's cursor while a form field is being edited.
      return;
    }
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <header>
        <button class="menu" data-menu title="Menü">☰</button>
        <h1>${esc(s ? s.name : "Smart EQ")}</h1>
        ${modeLabel ? `<span class="badge ${mode === "live" ? "live" : ""}">${modeLabel}</span>` : ""}
      </header>
      <nav>${VIEWS.map(([id, label]) => `<button data-view="${id}" class="${this._view === id ? "active" : ""}">${label}</button>`).join("")}</nav>
      <main>${body}</main>`;
    this._bind();
  }

  _bind() {
    const root = this.shadowRoot;
    root.querySelector("[data-menu]")?.addEventListener("click", () =>
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true })));
    root.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => this._setView(b.dataset.view)));
    root.querySelectorAll("[data-service]").forEach((b) =>
      b.addEventListener("click", () => {
        if (b.dataset.confirm && !confirm(b.dataset.confirm)) return;
        this._call(b.dataset.service, b.dataset.payload ? JSON.parse(b.dataset.payload) : {}, b.dataset.label);
      }));
    root.querySelectorAll("[data-action]").forEach((el) =>
      el.addEventListener(el.tagName === "BUTTON" ? "click" : "change", (ev) => this._action(el.dataset.action, el, ev)));
  }

  _action(action, el) {
    const plans = this._plans;
    switch (action) {
      case "month-prev":
        this._month -= 1;
        if (this._month < 1) { this._month = 12; this._year -= 1; }
        this._cache = {}; this._refresh(); break;
      case "month-next":
        this._month += 1;
        if (this._month > 12) { this._month = 1; this._year += 1; }
        this._cache = {}; this._refresh(); break;
      case "plan-field": {
        const plan = plans[Number(el.dataset.index)];
        const field = el.dataset.field;
        if (el.type === "checkbox" && field === "weekday") {
          const days = new Set(plan.weekdays);
          el.checked ? days.add(el.value) : days.delete(el.value);
          plan.weekdays = WEEKDAYS.map(([d]) => d).filter((d) => days.has(d));
        } else if (el.type === "checkbox") {
          plan[field] = el.checked;
        } else if (el.type === "number") {
          plan[field] = Number(el.value);
        } else {
          plan[field] = el.value;
        }
        break;
      }
      case "plan-add":
        plans.push({ id: `plan-${Date.now().toString(36)}`, name: "Neuer Plan", enabled: true,
          weekdays: ["sat", "sun"], mode: "departure_based", charge_start_time: "03:00",
          departure_time: "09:00", ready_buffer_min: 30, minimum_departure_soc_pct: 80,
          preferred_departure_soc_pct: 90, climate: "auto" });
        this._render(); break;
      case "plan-delete":
        plans.splice(Number(el.dataset.index), 1); this._render(); break;
      case "plan-reset":
        this._plans = null; this._refresh(); break;
      case "plan-save":
        this._savePlans(); break;
      case "external-add":
        this._addExternal(); break;
      case "odometer-add":
        this._addOdometer(); break;
      case "event-filter":
        this._eventFilter = el.value; this._refresh(); break;
      case "replay-run":
        this._runReplay(); break;
      case "report":
        this._createReport(el.dataset.month ? Number(el.dataset.month) : null); break;
      case "open-report":
        this._openReport(el.dataset.url); break;
      case "external-cost":
        this._completeExternal(el.dataset.id); break;
      default: break;
    }
  }

  async _savePlans() {
    try {
      const result = await this._ws("set_plans", { plans: this._plans });
      this._plans = result.plans;
      this._toast("Ladepläne gespeichert");
      await this._refresh();
    } catch (err) {
      this._toast(`Fehler: ${err.message || err}`);
    }
  }

  _form(id) {
    const data = {};
    this.shadowRoot.querySelectorAll(`[data-form="${id}"] [name]`).forEach((el) => {
      if (el.value === "") return;
      data[el.name] = el.type === "number" ? Number(el.value) : el.value;
    });
    return data;
  }

  _addExternal() {
    const data = this._form("external");
    if (!data.date || !data.energy_kwh) { this._toast("Datum und kWh angeben"); return; }
    this._call("add_external_charge", data, "Fremdladung erfasst");
  }

  _addOdometer() {
    const data = this._form("odometer");
    if (!data.odometer_km) { this._toast("Kilometerstand angeben"); return; }
    this._call("add_manual_odometer", data, "Kilometerstand erfasst");
  }

  async _createReport(month) {
    try {
      this._toast("Bericht wird erstellt …");
      const report = await this._ws("create_report", { year: this._year, ...(month ? { month } : {}) });
      this._cache.monthKey = null;
      await this._openReport(report.url);
      await this._refresh();
    } catch (err) {
      this._toast(`Fehler: ${err.message || err}`);
    }
  }

  async _openReport(url) {
    // Reports need a login: fetch with the user's token, open as blob.
    const response = await this._hass.fetchWithAuth(url);
    if (!response.ok) { this._toast(`Download fehlgeschlagen (${response.status})`); return; }
    const blob = await response.blob();
    window.open(URL.createObjectURL(blob), "_blank");
  }

  _completeExternal(id) {
    const item = ((this._cache.external && this._cache.external.items) || []).find((e) => e.id === id);
    if (!item) return;
    const cost = prompt(`Kosten in € für ${item.energy_kwh} kWh am ${dateOnly(item.date)}:`, item.cost_eur ?? "");
    if (cost === null) return;
    const kwh = prompt("Geladene kWh (Schätzung korrigieren):", item.energy_kwh);
    if (kwh === null) return;
    const provider = prompt("Anbieter (optional):", item.provider || "") || undefined;
    const data = { id: item.id, date: item.date, source: item.source,
      energy_kwh: Number(String(kwh).replace(",", ".")), cost_eur: Number(String(cost).replace(",", ".")) };
    if (provider) data.provider = provider;
    if (item.note) data.note = item.note;
    this._call("add_external_charge", data, "Fremdladung ergänzt");
  }

  async _runReplay() {
    const file = this.shadowRoot.querySelector("[name=replay_file]")?.value;
    if (!file) { this._toast("Datensatz wählen"); return; }
    try {
      this._toast("Replay läuft …");
      await this._hass.callService(DOMAIN, "start_replay", { file });
      this._cache.replay = await this._ws("get_replay");
      this._render();
    } catch (err) {
      this._toast(`Fehler: ${err.message || err}`);
    }
  }

  // ---------------------------------------------------------------- views

  _cockpit(s) {
    const w = s.next_window;
    const soc = s.soc && s.soc.value !== null ? s.soc : null;
    const power = s.values.charge_power;
    const health = s.health.status;
    const ex = s.executor;
    const desired = s.desired || {};
    const e = w ? w.estimate : {};
    const healthClass = { HEALTHY: "ok", DEGRADED: "warn", ERROR: "bad" }[health];
    const has = (key) => key in s.entities;
    const notice = s.mode !== "live"
      ? `<div class="notice info">Modus <b>${esc(s.mode)}</b>: Die Integration protokolliert nur, was sie schalten würde. Live erst nach Messphase, Dry-Run und Einzeltest (Grundsatz 11).</div>` : "";
    return `${notice}
    <div class="grid">
      <div class="card">
        <h2>Status</h2>
        <div class="big">${esc(STATE_LABELS[ex.state] || ex.state || "–")}</div>
        <div class="sub">seit ${time(ex.since)} · Soll: ${esc(REASON_LABELS[desired.reason] || desired.reason || "–")}
          (${desired.charger_enabled === true ? "Halo an" : desired.charger_enabled === false ? "Halo aus" : "nicht eingreifen"})</div>
        ${ex.failure_code ? `<p><span class="pill bad">${esc(ex.failure_code)}</span></p>` : ""}
        ${s.override ? `<p><span class="pill info">Override: ${esc(s.override.mode)}</span></p>` : ""}
        ${s.one_shot ? `<p><span class="pill info">Heute Nacht bis ${dateTime(s.one_shot.departure_at)}</span></p>` : ""}
        ${!s.automation_enabled ? `<p><span class="pill warn">Automatik aus</span></p>` : ""}
      </div>
      <div class="card">
        <h2>Akku</h2>
        <div class="big">${soc ? num(soc.value, 0, "%") : "–"}</div>
        ${soc ? `<div class="bar"><div style="width:${Math.min(100, soc.value)}%"></div></div>` : ""}
        <div class="sub">${soc ? `<span class="pill ${QUALITY_CLASS[soc.quality]}">${esc(soc.quality)}</span> · ${dateTime(soc.updated_at)}` : "kein SOC (OVMS fehlt)"}</div>
      </div>
      <div class="card">
        <h2>Leistung</h2>
        <div class="big">${power ? num(power.value / 1000, 2, "kW") : "–"}</div>
        <div class="sub">${s.session ? `Session ${num(s.session.energy_kwh, 2, "kWh")} seit ${time(s.session.started_at)}` : "keine laufende Session"}</div>
      </div>
      <div class="card">
        <h2>Nächste Abfahrt</h2>
        <div class="big">${w ? dateTime(w.departure) : "–"}</div>
        <div class="sub">${w ? `${esc(w.name)} · Start ${dateTime(w.start)}${w.fallback_without_soc ? " (fester Start, kein SOC)" : ""}` : "kein aktiver Plan"}</div>
      </div>
      <div class="card">
        <h2>Prognose <span class="sub">(Schätzung)</span></h2>
        <div class="row"><span>Erwarteter SOC</span><b>${num(e.expected_soc_at_departure, 0, "%")}</b></div>
        <div class="row"><span>Mindest-SOC ${w ? w.minimum_soc_pct + " %" : ""}</span>${this._yesNo(e.minimum_reachable)}</div>
        <div class="row"><span>Wunsch-SOC ${w ? w.preferred_soc_pct + " %" : ""}</span>${this._yesNo(e.preferred_reachable)}</div>
        <div class="row"><span>Voraussichtlich fertig</span><span>${time(e.finish_at)}</span></div>
      </div>
      <div class="card">
        <h2>System</h2>
        <div class="big"><span class="pill ${healthClass}">${esc(HEALTH_LABELS[health] || health)}</span></div>
        <div class="sub">${s.health.reasons.length ? s.health.reasons.map(esc).join(", ") : "alles erreichbar"}</div>
        ${s.data_conflict ? `<p><span class="pill bad">Datenkonflikt Halo/OVMS</span></p>` : ""}
        ${s.climate ? `<p class="sub">Klima ${s.climate.duration_min} min ab ${time(s.climate.start_at)}${s.climate.blocked ? ` – gesperrt: ${esc(s.climate.blocked)}` : ""}</p>` : ""}
      </div>
      <div class="card">
        <h2>Strompreis</h2>
        <div class="big">${num(s.prices.current_eur_kwh * 100, 1, "ct/kWh")}</div>
        <div class="sub">${s.prices.dynamic ? `dynamisch (${esc(s.prices.source)})` : "Festpreis"}${s.prices.error ? ` · <span class="pill warn">${esc(s.prices.error)}</span>` : ""}</div>
        ${w && w.estimate.cost_eur !== null ? `<div class="row"><span>Nächste Ladung (Schätzung)</span><b>${num(w.estimate.cost_eur, 2, "€")}</b></div>` : ""}
        ${w && w.blocks.length ? `<div class="sub">Günstigste Zeit: ${w.blocks.map((b) => `${time(b[0])}–${time(b[1])}`).join(", ")}</div>` : ""}
      </div>
      <div class="card wide">
        <h2>Schnellaktionen</h2>
        <div class="actions">
          <button class="act primary" data-service="start_charging" data-label="Jetzt laden">Jetzt laden</button>
          <button class="act" data-service="stop_charging" data-label="Laden gestoppt">Laden stoppen</button>
          <button class="act" data-service="start_one_shot" data-label="Heute Nacht laden">Heute Nacht laden</button>
          <button class="act" data-service="clear_override" ${s.override ? "" : "disabled"}>Override aufheben</button>
          <button class="act" data-service="cancel_one_shot" ${s.one_shot ? "" : "disabled"}>One-Shot löschen</button>
          ${has("ovms_soc") ? `<button class="act" data-service="start_climate" data-payload='{"minutes":10}'>Klima 10 min</button>
          <button class="act" data-service="stop_climate">Klima stopp</button>
          <button class="act" data-service="vehicle_wakeup" data-confirm="Fahrzeug wirklich wecken? Jeder Wakeup kostet HV-Zyklen.">Fahrzeug wecken</button>` : ""}
          ${has("cp_relay") ? `<button class="act" data-service="cp_wakeup" data-confirm="CP-Puls auslösen?" ${s.settings.cp_failsafe_verified ? "" : "disabled title='Failsafe nicht verifiziert'"}>CP-Wakeup</button>` : ""}
          <button class="act danger" data-service="reset_error" ${ex.failure_code || health === "ERROR" ? "" : "disabled"}>Fehler zurücksetzen</button>
        </div>
      </div>
      ${s.last_result ? `<div class="card wide"><h2>Letztes Ladeergebnis</h2>
        <div class="row"><span>${dateTime(s.last_result.at)}</span><span>${s.last_result.success ? `<span class="pill ok">ok</span> ${num(s.last_result.energy_kwh, 2, "kWh")}` : `<span class="pill bad">${esc(s.last_result.failure_code)}</span>`}</span></div></div>` : ""}
    </div>`;
  }

  _yesNo(value) {
    if (value === true) return `<span class="pill ok">ja</span>`;
    if (value === false) return `<span class="pill bad">nein</span>`;
    return `<span class="pill muted">unbekannt</span>`;
  }

  _planView(s) {
    const plans = this._plans || [];
    const windows = (s.windows || []).map((w) => `<tr><td>${esc(w.name)}</td><td>${dateTime(w.start)}</td><td>${dateTime(w.departure)}</td>
      <td class="n">${num(w.estimate.expected_soc_at_departure, 0, "%")}</td>
      <td>${w.blocks.length ? `günstig: ${w.blocks.map((b) => `${time(b[0])}–${time(b[1])}`).join(", ")}` : w.fallback_without_soc ? "fester Start" : "abfahrtsbasiert"}</td>
      <td class="n">${num(w.estimate.cost_eur, 2, "€")}</td></tr>`).join("");
    const cards = plans.map((p, i) => `
      <div class="card wide">
        <h2>${esc(p.name)} ${p.enabled ? "" : `<span class="pill muted">aus</span>`}</h2>
        <div class="form">
          <label>Name<input data-action="plan-field" data-index="${i}" data-field="name" value="${esc(p.name)}"></label>
          <label>Modus<select data-action="plan-field" data-index="${i}" data-field="mode">
            <option value="departure_based" ${p.mode === "departure_based" ? "selected" : ""}>Abfahrtsbasiert</option>
            <option value="fixed_start" ${p.mode === "fixed_start" ? "selected" : ""}>Fester Start</option></select></label>
          <label>Abfahrt<input type="time" data-action="plan-field" data-index="${i}" data-field="departure_time" value="${esc(p.departure_time)}"></label>
          <label>Fester Start / Rückfall<input type="time" data-action="plan-field" data-index="${i}" data-field="charge_start_time" value="${esc(p.charge_start_time)}"></label>
          <label>Fertig vor Abfahrt (min)<input type="number" min="0" max="240" data-action="plan-field" data-index="${i}" data-field="ready_buffer_min" value="${p.ready_buffer_min}"></label>
          <label>Mindest-SOC %<input type="number" min="10" max="100" step="5" data-action="plan-field" data-index="${i}" data-field="minimum_departure_soc_pct" value="${p.minimum_departure_soc_pct}"></label>
          <label>Wunsch-SOC %<input type="number" min="10" max="100" step="5" data-action="plan-field" data-index="${i}" data-field="preferred_departure_soc_pct" value="${p.preferred_departure_soc_pct}"></label>
          <label>Klima<select data-action="plan-field" data-index="${i}" data-field="climate">
            ${[["off", "aus"], ["auto", "automatisch (Profil)"], ["5", "5 min"], ["10", "10 min"], ["15", "15 min"]]
              .map(([v, l]) => `<option value="${v}" ${p.climate === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        </div>
        <p class="days">${WEEKDAYS.map(([d, l]) => `<label><input type="checkbox" data-action="plan-field" data-index="${i}" data-field="weekday" value="${d}" ${p.weekdays.includes(d) ? "checked" : ""}>${l}</label>`).join("")}
          <label><input type="checkbox" data-action="plan-field" data-index="${i}" data-field="enabled" ${p.enabled ? "checked" : ""}>aktiv</label></p>
        <button class="act danger" data-action="plan-delete" data-index="${i}">Plan löschen</button>
      </div>`).join("");
    return `<div class="grid">
      <div class="card wide"><h2>Kommende Ladefenster</h2>
        ${windows ? `<div class="scroll"><table><tr><th>Plan</th><th>Start</th><th>Abfahrt</th><th class="n">SOC erwartet</th><th>Art</th><th class="n">Kosten*</th></tr>${windows}</table></div>` : `<p class="sub">Kein Plan aktiv.</p>`}
        <p class="sub">Abfahrtstage = Tage der Abfahrt. Ohne SOC fällt ein abfahrtsbasierter Plan auf den festen Start zurück.
          Mit dynamischem Preis (Tibber) lädt ein abfahrtsbasierter Plan in den günstigsten Stunden. * Schätzung</p>
      </div>
      ${cards}
      <div class="card wide actions">
        <button class="act" data-action="plan-add">Plan hinzufügen</button>
        <button class="act primary" data-action="plan-save">Speichern</button>
        <button class="act" data-action="plan-reset">Verwerfen</button>
      </div>
    </div>`;
  }

  _home() {
    const c = this._cache;
    const m = c.month || {};
    const months = (c.year && c.year.months) || [];
    const max = Math.max(1, ...months.map((x) => x.home_energy_kwh || 0));
    const bars = months.map((x, i) => {
      const h = Math.round(((x.home_energy_kwh || 0) / max) * 100);
      return `<rect x="${i * 30 + 6}" y="${110 - h}" width="20" height="${h}" rx="3"
        fill="var(--primary-color)" opacity="${x.month === this._month ? 1 : 0.45}"><title>${MONTHS[i]}: ${num(x.home_energy_kwh, 1, "kWh")}</title></rect>
        <text x="${i * 30 + 16}" y="124" text-anchor="middle">${MONTHS[i]}</text>`;
    }).join("");
    const start = new Date(this._year, this._month - 1, 1);
    const end = new Date(this._year, this._month, 1);
    const sessions = ((c.sessions && c.sessions.items) || []).filter((x) => {
      const t = new Date(x.started_at); return t >= start && t < end;
    });
    return `<div class="grid">
      <div class="card wide actions" style="align-items:center">
        <button class="act" data-action="month-prev">‹</button>
        <b>${MONTHS[this._month - 1]} ${this._year}</b>
        <button class="act" data-action="month-next">›</button>
        <span class="sub">${m.complete ? "vollständig" : "unvollständig"} · ${esc(m.quality || "")}</span>
        <span style="flex:1"></span>
        <button class="act" data-action="report" data-month="${this._month}">PDF Monat</button>
        <button class="act" data-action="report">PDF Jahr</button>
      </div>
      ${(c.reports || []).length ? `<div class="card wide"><h2>PDF-Berichte</h2><div class="actions">
        ${c.reports.map((r) => `<button class="act" data-action="open-report" data-url="${esc(r.url)}">${esc(r.file)}</button>`).join("")}</div></div>` : ""}
      <div class="card"><h2>Heimladen</h2><div class="big">${num(m.home_energy_kwh, 1, "kWh")}</div>
        <div class="sub">Halo-Zähler, maßgeblich für die Hausabrechnung</div></div>
      <div class="card"><h2>Kosten Heimladen</h2><div class="big">${num(m.home_cost_eur, 2, "€")}</div>
        <div class="sub">${num(this._state?.prices.current_eur_kwh, 3, "€/kWh")} aktuell${this._state?.prices.dynamic ? " (dynamisch)" : ""}</div></div>
      <div class="card"><h2>Sessions</h2><div class="big">${m.sessions ?? "–"}</div>
        <div class="sub">${m.failed_sessions ? `${m.failed_sessions} fehlgeschlagen` : "keine Fehlstarts"}</div></div>
      <div class="card wide"><h2>Monatsvergleich ${this._year}</h2>
        <svg viewBox="0 0 366 130" width="100%" height="160" role="img" aria-label="Heim-kWh pro Monat">${bars}</svg></div>
      <div class="card wide"><h2>Lade-Sessions</h2><div class="scroll"><table>
        <tr><th>Start</th><th>Ende</th><th class="n">kWh</th><th class="n">€</th><th class="n">max kW</th><th>Grund</th><th>Wakeup</th><th>Ergebnis</th></tr>
        ${sessions.map((x) => `<tr><td>${dateTime(x.started_at)}</td><td>${time(x.ended_at)}</td><td class="n">${num(x.grid_energy_kwh, 2)}</td>
          <td class="n">${num(x.cost_eur, 2)}</td><td class="n">${num(x.max_power_w / 1000, 1)}</td><td>${esc(REASON_LABELS[x.reason] || x.reason)}</td>
          <td>${x.ovms_wakeup_used ? "OVMS " : ""}${x.cp_wakeup_used ? "CP" : ""}</td>
          <td>${x.success ? `<span class="pill ok">ok</span>` : `<span class="pill bad">${esc(x.failure_code)}</span>`}</td></tr>`).join("") || `<tr><td colspan="8" class="sub">Keine Sessions in diesem Monat.</td></tr>`}
      </table></div></div>
    </div>`;
  }

  _drive() {
    const c = this._cache;
    const y = c.yearDrive || {};
    const temps = c.temps || { bands: {}, seasons: {} };
    const trips = (c.trips && c.trips.items) || [];
    const external = (c.external && c.external.items) || [];
    const group = (title, entries) => `<div class="card wide"><h2>${title}</h2><div class="scroll"><table>
      <tr><th></th><th class="n">km</th><th class="n">Fahrzeug kWh/100</th><th class="n">Netz kWh/100*</th><th class="n">Rekup. %</th><th class="n">Neben kWh</th><th class="n">€*</th></tr>
      ${Object.entries(entries).map(([k, g]) => `<tr><td>${esc(k)}</td><td class="n">${num(g.distance_km, 0)}</td><td class="n">${num(g.vehicle_kwh_100km, 1)}</td>
        <td class="n">${num(g.grid_kwh_100km, 1)}</td><td class="n">${num(g.recuperation_share_pct, 0)}</td><td class="n">${num(g.auxiliary_kwh, 1)}</td><td class="n">${num(g.cost_eur, 2)}</td></tr>`).join("")}
      </table></div><p class="sub">* geschätzt aus Fahrzeugverbrauch und gemessenem Ladeverlust</p></div>`;
    return `<div class="grid">
      <div class="card"><h2>${this._year}: Strecke</h2><div class="big">${num(y.distance_km, 0, "km")}</div>
        <div class="sub">${y.trips ?? 0} Fahrten · Qualität ${esc(y.quality || "–")}</div></div>
      <div class="card"><h2>Netzverbrauch</h2><div class="big">${num(y.grid_consumption_kwh_100km, 1, "kWh/100 km")}</div>
        <div class="sub">inkl. Ladeverlust, mit SOC-Ausgleich</div></div>
      <div class="card"><h2>Kosten</h2><div class="big">${num(y.cost_per_100km_eur, 2, "€/100 km")}</div>
        <div class="sub">Heim ${num(y.home_cost_eur, 2, "€")} · Fremd ${num(y.external_cost_eur, 2, "€")}</div></div>
      <div class="card"><h2>Ladeverlust</h2><div class="big">${num(y.charging_loss_pct, 1, "%")}</div>
        <div class="sub">nur Sessions mit gemessener Fahrzeugenergie</div></div>
      ${group("Temperaturgruppen", temps.bands)}
      ${group("Jahreszeiten", temps.seasons)}
      <div class="card wide"><h2>Fahrten</h2><div class="scroll"><table>
        <tr><th>Start</th><th class="n">km</th><th class="n">min</th><th class="n">kWh/100</th><th class="n">°C</th><th class="n">SOC</th><th>Qualität</th></tr>
        ${trips.slice(0, 50).map((t) => `<tr><td>${dateTime(t.started_at)}</td><td class="n">${num(t.distance_km, 1)}</td><td class="n">${num(t.duration_min, 0)}</td>
          <td class="n">${num(t.consumption_kwh_100km, 1)}</td><td class="n">${num(t.outside_temp_avg_c, 0)}</td>
          <td class="n">${num(t.soc_start_pct, 0)}→${num(t.soc_end_pct, 0)}</td><td><span class="pill ${t.quality === "GOOD" ? "ok" : "warn"}">${esc(t.quality)}</span></td></tr>`).join("") || `<tr><td colspan="7" class="sub">Noch keine Fahrten.</td></tr>`}
      </table></div></div>
      <div class="card wide"><h2>Fremdladen erfassen</h2>
        <div class="form" data-form="external">
          <label>Datum<input type="date" name="date"></label>
          <label>kWh<input type="number" step="0.01" min="0" name="energy_kwh"></label>
          <label>Ort<select name="source"><option value="public">Öffentlich</option><option value="workplace">Arbeitgeber</option><option value="other_home">Andere Wallbox</option></select></label>
          <label>Kosten €<input type="number" step="0.01" min="0" name="cost_eur"></label>
          <label>Anbieter<input name="provider"></label>
          <label>Kilometerstand<input type="number" min="0" name="odometer_km"></label>
          <button class="act primary" data-action="external-add">Speichern</button>
        </div>
        <div class="scroll"><table><tr><th>Datum</th><th>Ort</th><th class="n">kWh</th><th class="n">€</th><th>Anbieter</th><th></th></tr>
          ${external.map((e) => `<tr><td>${dateOnly(e.date)}</td><td>${esc(e.source)}</td><td class="n">${num(e.energy_kwh, 2)}</td>
            <td class="n">${num(e.cost_eur ?? (e.price_eur_kwh ? e.price_eur_kwh * e.energy_kwh : null), 2)}</td>
            <td>${esc(e.provider || "")} ${e.detected ? `<span class="pill warn">erkannt · geschätzt</span>` : ""}</td>
            <td>${e.detected ? `<button class="act" data-action="external-cost" data-id="${esc(e.id)}">Ergänzen</button> ` : ""}<button class="act danger" data-service="delete_external_charge" data-payload='${esc(JSON.stringify({ id: e.id }))}' data-confirm="Fremdladung löschen?">×</button></td></tr>`).join("") || `<tr><td colspan="6" class="sub">Keine Fremdladungen.</td></tr>`}
        </table></div></div>
      <div class="card wide"><h2>Kilometerstand manuell</h2>
        <div class="form" data-form="odometer">
          <label>km<input type="number" min="0" name="odometer_km"></label>
          <button class="act" data-action="odometer-add">Erfassen</button>
        </div><p class="sub">Für den Modus „Manuell“ (ohne OVMS): Stand am Monatsanfang und -ende reicht.</p></div>
    </div>`;
  }

  _diag(s) {
    const c = this._cache;
    const events = (c.events && c.events.items) || [];
    const replay = c.replay || {};
    const last = replay.last;
    const values = Object.entries(s.values).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(s.entities[k] || "")}</td>
      <td class="n">${esc(v.value ?? "–")} ${esc(v.unit || "")}</td><td class="n">${v.age_s ?? "–"} s</td>
      <td><span class="pill ${QUALITY_CLASS[v.quality]}">${esc(v.quality)}</span></td></tr>`).join("");
    const sevClass = { critical: "bad", error: "bad", warning: "warn", info: "info", debug: "muted" };
    return `<div class="grid">
      <div class="card"><h2>Health</h2>
        <div class="big"><span class="pill ${{ HEALTHY: "ok", DEGRADED: "warn", ERROR: "bad" }[s.health.status]}">${esc(HEALTH_LABELS[s.health.status])}</span></div>
        <div class="sub">${s.health.reasons.map(esc).join(", ") || "keine Auffälligkeiten"}</div></div>
      <div class="card"><h2>CP / Failsafe</h2>
        <div class="row"><span>Checkliste §3.6</span>${this._yesNo(s.settings.cp_failsafe_verified)}</div>
        <div class="row"><span>Shelly-Konfiguration</span>${this._yesNo(s.health.shelly_config_ok)}</div>
        <div class="row"><span>Puls-Maskierung aktiv</span><span>${s.executor.cp_masked ? "ja" : "nein"}</span></div></div>
      <div class="card"><h2>Fahrzeug</h2>
        <div class="row"><span>OVMS-Funktionen</span><span>${s.settings.ovms_enabled ? "aktiv" : "gesperrt"}</span></div>
        <div class="row"><span>HV-Zyklen heute</span><span>${s.hv_cycles_today ?? "–"}</span></div>
        <div class="row"><span>12 V</span><span>${s.values.ovms_12v ? num(s.values.ovms_12v.value, 1, "V") : "–"}</span></div>
        <div class="row"><span>Außentemperatur</span><span>${num(s.outside_temperature.value, 1, "°C")} (${esc(s.outside_temperature.source)})</span></div></div>
      <div class="card wide"><h2>Datenqualität je Wert</h2><div class="scroll"><table>
        <tr><th>Wert</th><th>Entität</th><th class="n">Wert</th><th class="n">Alter</th><th>Qualität</th></tr>${values}</table></div></div>
      <div class="card wide"><h2>Event Log</h2>
        <label style="max-width:220px">Kategorie<select data-action="event-filter">
          ${["", "charging", "wakeup", "cp", "climate", "health", "config", "user"].map((k) => `<option value="${k}" ${this._eventFilter === k ? "selected" : ""}>${k || "alle"}</option>`).join("")}
        </select></label>
        <div class="scroll"><table><tr><th>Zeit</th><th>Kategorie</th><th>Code</th><th>Meldung</th></tr>
          ${events.map((e) => `<tr><td>${dateTime(e.timestamp)}</td><td>${esc(e.category)}</td>
            <td><span class="pill ${sevClass[e.severity]}">${esc(e.code)}</span></td><td>${esc(e.message)}</td></tr>`).join("")}
        </table></div></div>
      <div class="card wide"><h2>Replay</h2>
        <p class="sub">Datensätze liegen in <code>/config/smart_eq_charging/replay</code>; erstellen mit dem Service <code>create_replay_dataset</code>.</p>
        <div class="form">
          <label>Datensatz<select name="replay_file">${(replay.files || []).map((f) => `<option>${esc(f)}</option>`).join("")}</select></label>
          <button class="act primary" data-action="replay-run" ${(replay.files || []).length ? "" : "disabled"}>Replay starten</button>
        </div>
        ${last ? `<div class="row"><span>${esc(last.name)}</span><b>Übereinstimmung ${last.agreement === null ? "–" : num(last.agreement * 100, 0, "%")}</b></div>
          <div class="scroll"><table><tr><th>Zeit</th><th>Zustand</th><th>Soll</th></tr>
            ${(last.states || []).slice(0, 60).map((x) => `<tr><td>${dateTime(x.at)}</td><td>${esc(STATE_LABELS[x.state] || x.state)}</td><td>${esc(REASON_LABELS[x.desired] || x.desired || "")}</td></tr>`).join("")}
          </table></div>
          ${(last.mismatches || []).length ? `<p><span class="pill bad">Abweichungen</span> ${last.mismatches.map((m) => `${dateTime(m.at)} ${m.on ? "an" : "aus"}`).join(", ")}</p>` : ""}` : ""}
      </div>
    </div>`;
  }
}

if (!customElements.get("smart-eq-panel")) {
  customElements.define("smart-eq-panel", SmartEqPanel);
}
