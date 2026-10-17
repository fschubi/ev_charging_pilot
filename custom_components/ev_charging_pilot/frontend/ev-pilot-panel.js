/*
 * EV Charging Pilot – Sidebar-Panel (Masterplan §12.5).
 *
 * Keine Steuerlogik: Das Panel liest über die WebSocket-API und löst jede
 * Aktion über einen Service der Integration aus. Fünf Ansichten:
 * Cockpit · Ladeplan · Hausstrom · Drive & Energy · Diagnose.
 */

const DOMAIN = "ev_charging_pilot";
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
  safety_lock: "Sicherheitssperre", override: "Override", rfid: "RFID", one_shot: "Einmalig",
  target_soc_reached: "Ziel-SOC erreicht", climate: "Vorklimatisierung", schedule: "Wochenplan",
  default_off: "Standard aus", automation_off: "Automatik aus",
};
const HEALTH_LABELS = { HEALTHY: "Gesund", DEGRADED: "Eingeschränkt", ERROR: "Fehler" };
const QUALITY_CLASS = {
  GOOD: "ok", LAST_KNOWN_VALID: "info", ESTIMATED: "info", STALE: "warn",
  CONFLICT: "bad", INVALID: "bad", UNAVAILABLE: "muted",
};
const VIEWS = [
  ["cockpit", "Cockpit"], ["plan", "Ladeplan"], ["home", "Hausstrom"],
  ["drive", "Drive & Energy"], ["diag", "Diagnose"], ["settings", "Einstellungen"],
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
// Charging current choices: "" keeps the wallbox setting (or the default from the settings).
const AMPS = [6, 8, 10, 12, 14, 16];
const ampsKw = (a, phases) => `${(a * (phases || 3) * 0.23).toLocaleString("de-DE", { maximumFractionDigits: 1 })} kW`;
const ampsOptions = (selected, settings, standardLabel) => {
  const st = settings || {};
  const std = standardLabel || (st.default_current_a ? `Standard (${st.default_current_a} A)` : "Standard (Wallbox-Einstellung)");
  return [`<option value="" ${selected ? "" : "selected"}>${std}</option>`,
    ...AMPS.map((a) => `<option value="${a}" ${Number(selected) === a ? "selected" : ""}>${a} A · ca. ${ampsKw(a, st.phases)}</option>`)].join("");
};
const dateOnly = (iso) => (iso ? new Date(iso).toLocaleDateString("de-DE") : "–");

// ------------------------------------------------------------------ graphics

const HEALTH_TEXT = {
  CP_STATE_UNKNOWN: "Shelly (CP-Relais) nicht erreichbar – Zustand der CP-Leitung unbekannt. Aus Sicherheitsgründen schaltet die Automatik nichts.",
  CP_OPEN: "CP-Leitung ist offen (Shelly-Relais aus). Die Automatik versucht, sie zu schließen.",
  CP_NOT_RESTORED: "CP-Relais nach dem Puls nicht zurückgestellt – bitte Shelly prüfen und dann „Fehler zurücksetzen“.",
  CHARGER_UNAVAILABLE: "Wallbox nicht erreichbar (Cloud/Internet?).",
  REPEATED_START_FAILURE: "Mehrere Ladestarts hintereinander fehlgeschlagen – nach Prüfung „Fehler zurücksetzen“.",
  HALO_SCHEDULE_ON: "Der interne Zeitplan der Wallbox ist an – bitte in der Wallbox-App ausschalten.",
  SHELLY_CONFIG_DRIFT: "Shelly-Konfiguration weicht ab (auto_on / Einschaltzustand / Pulsdauer).",
  OVMS_OFFLINE: "OVMS liefert keine Daten.",
  SOC_STALE: "SOC ist veraltet – SOC-Funktionen pausieren.",
  TEMPERATURE_MISSING: "Keine Außentemperatur – automatische Klimaprofile pausieren.",
};
const CLIMATE_BLOCKED = {
  CLIMATE_DISABLED: "Vorklimatisierung ist in den Optionen aus",
  OVMS_DISABLED: "OVMS ist noch nicht aktiv – Klima wird erst mit OVMS ausgeführt",
  HEALTH_NOT_HEALTHY: "pausiert, solange das System eingeschränkt ist",
  SOC_UNKNOWN: "kein gültiger SOC",
  SOC_TOO_LOW: "SOC zu niedrig für Klima",
};
const SHELLY_LABELS = { initial_state: "Einschaltzustand", auto_on: "Auto-On", auto_on_delay: "Auto-On-Verzögerung" };
const fmtShelly = (v) => v === true ? "an" : v === false ? "aus" : v === null || v === undefined ? "–" : typeof v === "number" ? `${v} s` : String(v);
const shellyRows = (devs) => (devs || []).map((d) =>
  `<div class="row"><span>${esc(SHELLY_LABELS[d.key] || d.key)}</span><span><span class="pill bad">${esc(fmtShelly(d.actual))}</span> → <span class="pill ok">${esc(fmtShelly(d.expected))}</span></span></div>`).join("");
// Routine steps that clutter the log; "Wichtiges" hides them.
const ROUTINE_EVENTS = new Set(["CHARGER_CONFIRMED", "CHARGER_OFF_CONFIRMED", "POWER_DETECTED",
  "EXECUTOR_STARTED", "DRY_RUN", "SWITCH_CYCLE_VIOLATION", "CP_PULSE_DONE", "WAIT_FOR_CHARGE",
  "POWER_LOST", "PLAN_CONFIRMED"]);
const EVENT_FILTERS = [["important", "Wichtiges"], ["", "alle"], ["charging", "Laden"],
  ["wakeup", "Wecken"], ["cp", "CP"], ["climate", "Klima"], ["health", "System"],
  ["config", "Konfiguration"], ["user", "Bedienung"]];
const SEASON_LABELS = { winter: "Winter", spring: "Frühling", summer: "Sommer", autumn: "Herbst" };

const socColor = (soc) =>
  soc === null ? "var(--disabled-text-color, #888)"
    : soc < 20 ? "var(--error-color, #db4437)"
    : soc < 50 ? "var(--warning-color, #ffa600)"
    : "var(--success-color, #43a047)";

/** Gradient colours of the battery fill by charge level. */
const socGradient = (soc) =>
  soc === null ? ["#7a7f87", "#9aa0a8"]
    : soc < 20 ? ["#ff416c", "#ff8a5c"]
    : soc < 50 ? ["#f7971e", "#ffd200"]
    : ["#11998e", "#38ef7d"];

/** Modern capsule battery: gradient fill, glass highlight, cell lines, shimmer while charging,
 *  minimum and target as labelled markers. */
function batterySvg({ charging, error, soc, min = null, pref = null }) {
  const level = soc === null ? 0 : Math.max(0, Math.min(100, soc));
  const X0 = 18, W = 300, Y0 = 24, H = 60;
  const w = W * level / 100;
  const [c1, c2] = socGradient(soc);
  const xAt = (p) => X0 + W * p / 100;
  const cells = Array.from({ length: 9 }, (_, i) => `<line x1="${xAt((i + 1) * 10)}" y1="${Y0}" x2="${xAt((i + 1) * 10)}" y2="${Y0 + H}" stroke="rgba(0,0,0,.16)" stroke-width="1.5"/>`).join("");
  const markers = [];
  const close = min !== null && pref !== null && Math.abs(pref - min) < 14;
  if (min !== null) markers.push([min, `min ${min}`, "var(--warning-color, #ffa600)", close ? "end" : "middle"]);
  if (pref !== null) markers.push([pref, `Ziel ${pref}`, "var(--primary-color, #03a9f4)", close ? "start" : "middle"]);
  const marks = markers.map(([p, label, color, anchor]) => {
    const x = xAt(p);
    const tx = anchor === "end" ? x - 4 : anchor === "start" ? x + 4 : x;
    return `<line x1="${x}" y1="${Y0 - 4}" x2="${x}" y2="${Y0 + H + 4}" stroke="${color}" stroke-width="2.5" stroke-linecap="round" opacity=".95"/>
      <path d="M${x - 5} ${Y0 + H + 13} L${x + 5} ${Y0 + H + 13} L${x} ${Y0 + H + 6} Z" fill="${color}"/>
      <text x="${tx}" y="${Y0 + H + 27}" text-anchor="${anchor}" class="bmark" style="fill:${color}">${label} %</text>`;
  }).join("");
  const frame = error ? "var(--error-color, #db4437)" : "rgba(255,255,255,.22)";
  return `
  <svg class="battery" viewBox="0 0 352 118" role="img" aria-label="Akku ${soc === null ? "unbekannt" : Math.round(soc) + " Prozent"}">
    <defs>
      <linearGradient id="evp-fill" x1="0" x2="1"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></linearGradient>
      <linearGradient id="evp-gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".45"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/></linearGradient>
      <linearGradient id="evp-shine" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".45"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
      <clipPath id="evp-clip"><rect x="${X0}" y="${Y0}" width="${W}" height="${H}" rx="20"/></clipPath>
    </defs>
    <rect x="${X0 - 6}" y="${Y0 - 6}" width="${W + 12}" height="${H + 12}" rx="26" fill="rgba(127,127,127,.10)" stroke="${frame}" stroke-width="2"/>
    <rect x="${X0 + W + 10}" y="${Y0 + 18}" width="10" height="${H - 36}" rx="5" fill="${level >= 100 ? c2 : "rgba(127,127,127,.45)"}"/>
    <g clip-path="url(#evp-clip)">
      <rect x="${X0}" y="${Y0}" width="${W}" height="${H}" fill="rgba(127,127,127,.14)"/>
      ${w > 0 ? `<rect x="${X0}" y="${Y0}" width="${w.toFixed(1)}" height="${H}" fill="url(#evp-fill)" class="${charging ? "breathe" : ""}"/>` : ""}
      ${charging && w > 0 ? `<rect y="${Y0}" width="70" height="${H}" fill="url(#evp-shine)"><animate attributeName="x" from="${X0 - 70}" to="${(X0 + w).toFixed(1)}" dur="2.4s" repeatCount="indefinite"/></rect>` : ""}
      ${cells}
      <rect x="${X0}" y="${Y0}" width="${W}" height="${H / 2}" fill="url(#evp-gloss)"/>
    </g>
    ${marks}
    <g class="bsoc">
      ${charging ? `<path transform="translate(${X0 + W / 2 - 62} ${Y0 + 13}) scale(1.4)" d="M9 0 L0 13 L7 13 L4 24 L14 9 L7 9 L10 0 Z" fill="#fff"/>` : ""}
      <text x="${X0 + W / 2 + (charging ? 10 : 0)}" y="${Y0 + H / 2 + 11}" text-anchor="middle" class="batt">${soc === null ? "– %" : Math.round(soc) + " %"}</text>
    </g>
  </svg>`;
}

/** Half-circle power gauge 0 … max kW. */
function powerGauge(kw, max) {
  const frac = Math.max(0, Math.min(1, kw / (max || 1)));
  const a = Math.PI * (1 - frac);
  const x = 70 + Math.cos(a) * 52, y = 82 - Math.sin(a) * 52;
  return `<svg viewBox="0 0 140 110" class="gauge" role="img" aria-label="Ladeleistung">
    <path d="M18 82 A52 52 0 0 1 122 82" fill="none" stroke="var(--divider-color, #444)" stroke-width="12" stroke-linecap="round"/>
    ${frac > 0.005 ? `<path d="M18 82 A52 52 0 0 1 ${x.toFixed(1)} ${y.toFixed(1)}" fill="none" stroke="var(--primary-color, #03a9f4)" stroke-width="12" stroke-linecap="round"/>` : ""}
    <text x="70" y="78" text-anchor="middle" class="gbig">${num(kw, 1)}<tspan class="gunit"> kW</tspan></text>
    <text x="18" y="102" text-anchor="middle" class="gsub">0</text>
    <text x="122" y="102" text-anchor="middle" class="gsub">${num(max, 1)}</text>
  </svg>`;
}

/** The night ahead: price curve, charging window / cheap blocks, now and departure. */
function timelineSvg(s) {
  const now = Date.now();
  const w = s.next_window;
  const startT = w ? Math.min(now, new Date(w.start).getTime() - 3600e3) : now;
  const endT = w ? new Date(w.departure).getTime() + 1800e3 : now + 12 * 3600e3;
  const span = Math.max(3600e3, endT - startT);
  const W = 800, top = 18, bottom = 92, left = 6, right = 794;
  const X = (t) => left + ((t - startT) / span) * (right - left);
  const slots = (s.prices.slots || []).filter((p) => new Date(p.end).getTime() > startT && new Date(p.start).getTime() < endT);
  let priceArea = "";
  if (slots.length) {
    const prices = slots.map((p) => p.eur_per_kwh);
    const lo = Math.min(...prices), hi = Math.max(...prices);
    const Y = (p) => bottom - 8 - ((p - lo) / ((hi - lo) || 1)) * (bottom - top - 26);
    const pts = slots.flatMap((p) => [[X(Math.max(startT, new Date(p.start).getTime())), Y(p.eur_per_kwh)],
      [X(Math.min(endT, new Date(p.end).getTime())), Y(p.eur_per_kwh)]]);
    priceArea = `<path d="M${pts.map((p) => p.map((v) => v.toFixed(1)).join(" ")).join(" L")} L${pts[pts.length - 1][0].toFixed(1)} ${bottom} L${pts[0][0].toFixed(1)} ${bottom} Z"
      fill="var(--warning-color, #ffa600)" opacity=".16"/>
      <path d="M${pts.map((p) => p.map((v) => v.toFixed(1)).join(" ")).join(" L")}" fill="none" stroke="var(--warning-color, #ffa600)" stroke-width="1.5" opacity=".8"/>`;
  }
  const finish = w && w.estimate && w.estimate.finish_at && !w.blocks.length ? w.estimate.finish_at : null;
  const blocks = w ? (w.blocks.length ? w.blocks : [[w.start, finish || w.departure]]) : [];
  const charge = blocks.map(([a, b]) => `<rect x="${X(new Date(a).getTime()).toFixed(1)}" y="${bottom - 14}" width="${Math.max(2, X(new Date(b).getTime()) - X(new Date(a).getTime())).toFixed(1)}" height="14" rx="3" fill="var(--primary-color, #03a9f4)"/>`).join("");
  const ticks = [];
  const hour = 3600e3;
  for (let t = Math.ceil(startT / hour) * hour; t <= endT; t += hour * (span > 14 * hour ? 2 : 1)) {
    ticks.push(`<line x1="${X(t).toFixed(1)}" y1="${bottom}" x2="${X(t).toFixed(1)}" y2="${bottom + 4}" stroke="var(--secondary-text-color)"/>
      <text x="${X(t).toFixed(1)}" y="${bottom + 16}" text-anchor="middle" class="tl">${new Date(t).getHours()}</text>`);
  }
  // Labels sit beside their line: "fertig" to the left, everything else to the right.
  const marker = (t, label, color, dash, side = "start") => {
    const x = X(t);
    const anchor = side === "end" || x > right - 60 ? "end" : "start";
    const tx = anchor === "end" ? x - 4 : x + 4;
    return `<line x1="${x.toFixed(1)}" y1="${top}" x2="${x.toFixed(1)}" y2="${bottom}" stroke="${color}" stroke-width="2" ${dash ? 'stroke-dasharray="4 3"' : ""}/>
    <text x="${tx.toFixed(1)}" y="${top + 10}" text-anchor="${anchor}" class="tl" style="fill:${color}">${label}</text>`;
  };
  const blockText = blocks.map(([a, b]) => {
    const x = (X(new Date(a).getTime()) + X(new Date(b).getTime())) / 2;
    return `<text x="${x.toFixed(1)}" y="${bottom - 18}" text-anchor="middle" class="tl" style="fill:var(--primary-color)">${time(a)}–${time(b)}</text>`;
  }).join("");
  const climate = s.climate && !s.climate.blocked && w
    ? marker(new Date(s.climate.start_at).getTime(), "Klima", "var(--info-color, #039be5)", true) : "";
  return `<svg viewBox="0 0 ${W} 112" class="timeline" role="img" aria-label="Ladeplan der Nacht">
    <line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}" stroke="var(--divider-color)"/>
    ${priceArea}${charge}${blockText}${ticks.join("")}${climate}
    ${w ? marker(new Date(w.ready_at).getTime(), "fertig", "var(--success-color, #43a047)", true, "end") : ""}
    ${w ? marker(new Date(w.departure).getTime(), "Abfahrt", "var(--primary-text-color)", false) : ""}
    ${now >= startT && now <= endT ? marker(now, "jetzt", "var(--error-color, #db4437)", false) : ""}
  </svg>`;
}

/** Last 24 h: charging power (area) and SOC (line). */
function historySvg(history, maxKw) {
  const W = 800, top = 10, bottom = 100, left = 6, right = 794;
  if (!history || history.length < 2) {
    return `<p class="sub">Der Verlauf füllt sich ab jetzt minütlich (die letzten 24 Stunden).</p>`;
  }
  const t0 = new Date(history[0][0]).getTime();
  const t1 = new Date(history[history.length - 1][0]).getTime();
  const X = (t) => left + ((t - t0) / ((t1 - t0) || 1)) * (right - left);
  const YP = (w) => bottom - (Math.min(w / 1000, maxKw) / maxKw) * (bottom - top);
  const YS = (soc) => bottom - (soc / 100) * (bottom - top);
  const power = history.filter((h) => h[1] !== null);
  const socs = history.filter((h) => h[2] !== null);
  const area = power.length ? `<path d="M${X(new Date(power[0][0]).getTime()).toFixed(1)} ${bottom} ${power.map((h) => `L${X(new Date(h[0]).getTime()).toFixed(1)} ${YP(h[1]).toFixed(1)}`).join(" ")} L${X(new Date(power[power.length - 1][0]).getTime()).toFixed(1)} ${bottom} Z"
    fill="var(--primary-color, #03a9f4)" opacity=".35"/>` : "";
  const line = socs.length > 1 ? `<path d="${socs.map((h, i) => `${i ? "L" : "M"}${X(new Date(h[0]).getTime()).toFixed(1)} ${YS(h[2]).toFixed(1)}`).join(" ")}"
    fill="none" stroke="var(--success-color, #43a047)" stroke-width="2"/>` : "";
  return `<svg viewBox="0 0 ${W} 118" class="timeline" role="img" aria-label="Verlauf">
    <line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}" stroke="var(--divider-color)"/>
    ${area}${line}
    <text x="${left}" y="${bottom + 14}" class="tl">${time(history[0][0])}</text>
    <text x="${right}" y="${bottom + 14}" text-anchor="end" class="tl">${time(history[history.length - 1][0])}</text>
  </svg>
  <div class="legend"><span class="dot" style="background:var(--primary-color)"></span>Ladeleistung
    <span class="dot" style="background:var(--success-color)"></span>SOC</div>`;
}

/** Downscale large photos in the browser before upload; PNG keeps its transparency. */
async function shrinkImage(file, maxWidth) {
  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap || bitmap.width <= maxWidth) return file;
  const canvas = document.createElement("canvas");
  canvas.width = maxWidth;
  canvas.height = Math.round(bitmap.height * maxWidth / bitmap.width);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const type = file.type === "image/png" ? "image/png" : file.type === "image/webp" ? "image/webp" : "image/jpeg";
  return new Promise((resolve) => canvas.toBlob((b) => resolve(b || file), type, 0.9));
}

const STYLE = `
  .testcenter { grid-column: 1 / -1; }
  .testcenter > summary { font-size: 16px; padding: 10px 4px; }
  .testcenter > .grid { padding: 0; }
  /* Price dialog: a page of its own (opaque), so the cockpit does not shine through. */
  .overlay { position: fixed; inset: 0; z-index: 100; overflow: auto;
             background: var(--primary-background-color);
             display: flex; align-items: flex-start; justify-content: center;
             padding: max(24px, env(safe-area-inset-top)) 16px 16px; box-sizing: border-box; }
  .overlay .dialog { width: 100%; max-width: 440px; box-sizing: border-box; padding: 20px; }
  .overlay .dialog h2 { font-size: 1.3em; margin: 0 0 4px; }
  .overlay .dialog label { display: block; font-size: 0.95em; }
  .overlay .dialog input[name=price] { display: block; box-sizing: border-box; width: 100%;
             font-size: 1.8em; padding: 10px 14px; margin-top: 6px; text-align: center; }
  .overlay .quick { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 16px 0; }
  .overlay .quick .act { font-size: 1.1em; padding: 12px 0; }
  .overlay .pbar { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .overlay .pbar .act { padding: 12px 0; font-size: 1.05em; }
  details > summary { cursor: pointer; font-weight: 500; padding: 6px 0; color: var(--primary-color); }
  details[open] > summary { margin-bottom: 8px; }
  :host { display: block; background: var(--primary-background-color); min-height: 100vh;
          color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, inherit); }
  header { display: flex; align-items: center; gap: 12px; padding: 0 16px; height: 56px;
           background: var(--app-header-background-color, var(--primary-color));
           color: var(--app-header-text-color, #fff); position: sticky; top: 0; z-index: 2; }
  header h1 { font-size: 20px; font-weight: 400; margin: 0; flex: 1; white-space: nowrap;
              overflow: hidden; text-overflow: ellipsis; }
  .menu { background: none; border: none; color: inherit; font-size: 22px; cursor: pointer; }
  .version { font-size: 12px; font-weight: 400; opacity: .75; margin-left: 10px; vertical-align: middle; }
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
  .act { border: 1px solid var(--divider-color); background: var(--card-background-color);
               color: var(--primary-text-color); border-radius: 18px; padding: 8px 14px; cursor: pointer; font: inherit; }
  .act.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; }
  .act.danger { color: var(--error-color); }
  .act:disabled { opacity: .45; cursor: default; }
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
  .notice .reason { margin: 4px 0 0; }
  svg text { fill: var(--secondary-text-color); font-size: 10px; }
  .toast { position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%); padding: 10px 16px;
           border-radius: 8px; background: var(--primary-text-color); color: var(--card-background-color); z-index: 5; }
  .hero { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 12px; align-items: center; }
  .hero .col { text-align: center; }
  .hero .label { font-size: 13px; color: var(--secondary-text-color); margin-top: 2px; }
  svg.battery { width: 100%; max-width: 460px; }
  .photo { position: relative; border-radius: 14px; overflow: hidden; }
  .photo img { width: 100%; max-height: 300px; object-fit: contain; display: block; }
  .photo.charging::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 4px;
     background: linear-gradient(90deg, transparent, var(--success-color, #43a047), transparent);
     background-size: 50% 100%; background-repeat: no-repeat; animation: sweep 1.6s linear infinite; }
  @keyframes sweep { from { background-position: -50% 0; } to { background-position: 150% 0; } }
  .pulse-soft { animation: pulse 2.4s ease-in-out infinite; }
  .batt { font-size: 30px; font-weight: 700; fill: #fff; paint-order: stroke; stroke: rgba(0,0,0,.35); stroke-width: 4px; letter-spacing: .5px; }
  .bmark { font-size: 12px; font-weight: 600; }
  .breathe { animation: breathe 2.4s ease-in-out infinite; }
  @keyframes breathe { 50% { opacity: .82; } }
  @media (prefers-reduced-motion: reduce) { .breathe { animation: none; } }
  .kwsmall { font-size: 11px; font-weight: 600; fill: var(--success-color, #43a047); }
  .hint { font-size: 12px; color: var(--secondary-text-color); }
  input[type=range] { width: 100%; padding: 0; accent-color: var(--primary-color); }
  .slider { display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; align-items: center; margin: 8px 0; }
  .slider b { min-width: 48px; text-align: right; }
  .settings { max-width: 860px; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; padding-bottom: 80px; }
  .stop { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
  .status { margin: 6px 0 2px; }
  .status .big { font-size: 22px; line-height: 1.25; }
  .status .sdetail { font-size: 14px; color: var(--secondary-text-color); margin-top: 4px; }
  .status.tone-bad .big { color: var(--error-color, #db4437); }
  .status.tone-warn .big { color: var(--warning-color, #ffa600); }
  .plan.off { opacity: .7; }
  .phead { display: flex; align-items: center; gap: 12px; }
  .pname { flex: 1; font-size: 18px; font-weight: 500; border: 1px solid transparent; background: none; padding: 6px 8px; margin-left: -8px; }
  .pname:hover, .pname:focus { border-color: var(--divider-color); }
  .psum { font-size: 13px; color: var(--secondary-text-color); margin: 2px 0 10px; }
  .psec { margin-top: 14px; }
  .plabel { display: block; font-size: 13px; color: var(--secondary-text-color); margin-bottom: 6px; }
  .pgrid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); margin-top: 12px; }
  .pgrid.two { grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); margin-top: 6px; }
  .pmode { margin-top: 8px; display: flex; flex-direction: column; gap: 6px; }
  .pmode .inline { flex-direction: row; align-items: center; gap: 8px; color: var(--primary-text-color); }
  .pmode .inline input { width: auto; }
  .daychips { display: flex; gap: 6px; flex-wrap: wrap; }
  .day { min-width: 42px; padding: 8px 0; border-radius: 18px; border: 1px solid var(--divider-color); background: none; color: var(--secondary-text-color); font: inherit; cursor: pointer; }
  .day.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .socbar { position: relative; height: 14px; border-radius: 7px; background: var(--divider-color); overflow: visible; }
  .socbar .fill { height: 100%; border-radius: 7px; background: var(--primary-color); opacity: .75; }
  .socbar i { position: absolute; top: -4px; bottom: -4px; width: 3px; background: var(--warning-color, #ffa600); border-radius: 2px; transform: translateX(-1px); }
  .pfoot { margin-top: 14px; display: flex; justify-content: flex-end; }
  label .unitbox { width: max-content; }
  @media (max-width: 420px) { .daychips { gap: 4px; } .day { min-width: 0; flex: 1; } }
  td.nowrap { white-space: nowrap; }
  .checks { display: grid; gap: 8px; margin-top: 12px; }
  .crow { display: flex; gap: 10px; align-items: flex-start; }
  .crow .pill { min-width: 54px; text-align: center; margin-top: 2px; }
  .seg { display: inline-flex; border: 1px solid var(--divider-color); border-radius: 20px; overflow: hidden; }
  .seg button { background: none; border: none; padding: 8px 16px; font: inherit; color: var(--secondary-text-color); cursor: pointer; }
  .seg button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .sgroup { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px);
            box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); overflow: hidden; }
  .shead { width: 100%; display: flex; align-items: center; gap: 14px; padding: 16px; background: none; border: none;
           color: var(--primary-text-color); font: inherit; text-align: left; cursor: pointer; }
  .shead ha-icon { color: var(--primary-color); --mdc-icon-size: 26px; flex: none; }
  .stitle { flex: 1; font-size: 16px; font-weight: 500; }
  .stitle small { display: block; font-size: 13px; font-weight: 400; color: var(--secondary-text-color); margin-top: 2px; }
  .chev { color: var(--secondary-text-color); font-size: 14px; }
  .sbody { border-top: 1px solid var(--divider-color); }
  .srow { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px;
          border-bottom: 1px solid var(--divider-color); }
  .srow:last-child { border-bottom: none; }
  .srow.changed { box-shadow: inset 3px 0 0 var(--warning-color, #ffa600); }
  .stext { flex: 1; min-width: 0; }
  .slabel { font-size: 15px; }
  .shelp { font-size: 12.5px; color: var(--secondary-text-color); margin-top: 3px; line-height: 1.35; }
  .sctl { flex: none; display: flex; align-items: center; gap: 8px; }
  .sctl.wrap { flex: 1; flex-wrap: wrap; justify-content: flex-end; }
  .sctl select, .sctl input[type=text], .sctl input[type=date], .sctl input[type=time] { min-width: 180px; padding: 8px 10px; }
  .photoctl img { height: 48px; border-radius: 8px; }
  .unitbox { display: flex; align-items: center; border: 1px solid var(--divider-color); border-radius: 6px; overflow: hidden; }
  .unitbox input { border: none; width: 90px; text-align: right; padding: 8px 6px; }
  .unitbox span { padding: 0 10px; color: var(--secondary-text-color); font-size: 13px; background: rgba(127,127,127,.12); align-self: stretch; display: flex; align-items: center; }
  .switch { position: relative; display: inline-block; width: 46px; height: 26px; cursor: pointer; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .switch .track { position: absolute; inset: 0; background: var(--divider-color); border-radius: 13px; transition: background .2s; }
  .switch .track::after { content: ""; position: absolute; left: 3px; top: 3px; width: 20px; height: 20px; border-radius: 50%; background: #fff; transition: transform .2s; }
  .switch input:checked + .track { background: var(--primary-color); }
  .switch input:checked + .track::after { transform: translateX(20px); }
  .switch input:focus-visible + .track { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .savebar { position: sticky; bottom: 12px; display: flex; align-items: center; gap: 10px; justify-content: flex-end;
             padding: 12px 16px; border-radius: 12px; background: var(--card-background-color);
             box-shadow: 0 4px 16px rgba(0,0,0,.35); border: 1px solid var(--warning-color, #ffa600); }
  .savebar span { flex: 1; font-size: 14px; }
  @media (max-width: 600px) {
    .srow { flex-direction: column; align-items: stretch; gap: 8px; }
    .sctl { justify-content: flex-start; }
    .sctl select, .sctl input[type=text], .sctl input[type=date], .sctl input[type=time] { width: 100%; min-width: 0; }
    .srow:has(.switch) { flex-direction: row; align-items: center; }
  }
  .field { display: flex; flex-direction: column; gap: 4px; }
  .field .help { font-size: 11px; color: var(--secondary-text-color); }
  .check { flex-direction: row; align-items: center; gap: 8px; color: var(--primary-text-color); }
  svg.gauge { width: 100%; max-width: 170px; }
  svg.timeline { width: 100%; height: auto; display: block; }
  .kw { font-size: 13px; font-weight: 600; fill: var(--success-color, #43a047); }
  .gbig { font-size: 28px; font-weight: 500; fill: var(--primary-text-color); }
  .gunit { font-size: 13px; fill: var(--secondary-text-color); }
  .gsub { font-size: 10px; fill: var(--secondary-text-color); }
  .tl { font-size: 11px; fill: var(--secondary-text-color); }
  .flow { animation: flow 0.9s linear infinite; }
  @keyframes flow { to { stroke-dashoffset: -12; } }
  .pulse { animation: pulse 1.6s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: .35; } }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin-top: 4px; }
  .legend { font-size: 12px; color: var(--secondary-text-color); display: flex; gap: 14px; align-items: center; margin-top: 4px; }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; }
  .reason { font-size: 13px; margin: 6px 0 0; }
  @media (prefers-reduced-motion: reduce) { .flow, .pulse { animation: none; } }
  @media (max-width: 760px) { .hero { grid-template-columns: 1fr; } }
  @media (max-width: 600px) { main { padding: 8px; } .grid { gap: 8px; } }
`;

class EvPilotPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._view = localStorage.getItem("ev-pilot-view") || "cockpit";
    this._state = null;
    this._cache = {};
    this._plans = null;
    this._year = new Date().getFullYear();
    this._month = new Date().getMonth() + 1;
    this._eventFilter = "important";
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
      return true;
    } catch (err) {
      this._toast(`Fehler: ${err.message || err}`);
      return false;
    }
  }

  // Submit a form; its typed values are kept until the call succeeded.
  async _submit(form, service, data, label) {
    const draft = this._formDrafts && this._formDrafts[form];
    if (this._formDrafts) delete this._formDrafts[form];
    if (!(await this._call(service, data, label)) && draft) {
      this._formDrafts[form] = draft;
      this._render(true);
    }
  }

  _toast(text) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = text;
    this.shadowRoot.appendChild(el);
    setTimeout(() => el.remove(), 3000);
  }

  /** A push about an external charge opens the panel with ?external_price=<id>. */
  async _checkPriceLink() {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("external_price");
    if (!id) return;
    params.delete("external_price");
    const rest = params.toString();
    history.replaceState(history.state, "", window.location.pathname + (rest ? `?${rest}` : ""));
    let charge = null;
    if (!id.startsWith("test-")) {
      try {
        const list = await this._ws("get_external_charges", { limit: 50 });
        charge = (list.items || []).find((e) => e.id === id) || null;
      } catch (err) { /* the dialog works without the details */ }
    }
    this._priceDialog = { id, charge };
  }

  _priceDialogHtml(s) {
    const d = this._priceDialog;
    if (!d) return "";
    const c = d.charge;
    const info = d.id.startsWith("test-") ? "Nur ein Test – es wird nichts gespeichert."
      : c ? `${dateOnly(c.date)} · ca. ${num(c.energy_kwh, 1, "kWh")}${c.note ? ` · ${esc(c.note)}` : ""}` : "Erkannte Fremdladung";
    const buttons = ((s && s.settings.external_price_buttons) || []).map((p) =>
      `<button class="act" data-action="price-pick" data-price="${p}">${num(p, 2, "€/kWh")}</button>`).join("");
    return `<div class="overlay"><div class="card dialog">
      <h2>Preis der Fremdladung</h2>
      <p class="sub">${info}</p>
      <div class="pform" data-form="pricedialog">
        <label>Bezahlter Preis in € pro kWh<input type="text" inputmode="decimal" autocomplete="off" name="price" placeholder="z. B. 0,49"></label>
      </div>
      ${buttons ? `<div class="sub">oder direkt wählen:</div><div class="quick">${buttons}</div>` : ""}
      <div class="pbar"><button class="act" data-action="price-cancel">Abbrechen</button>
        <button class="act primary" data-action="price-save">Speichern</button></div>
    </div></div>`;
  }

  async _savePrice(price) {
    const d = this._priceDialog;
    if (!d || !String(price || "").trim()) { this._toast("Bitte einen Preis eingeben"); return; }
    if (await this._call("set_external_price", { id: d.id, price: String(price) }, "Preis gespeichert")) {
      this._priceDialog = null;
      if (this._formDrafts) delete this._formDrafts.pricedialog;
      this._render(true);
    }
  }

  async _refresh() {
    await this._checkPriceLink();
    try {
      this._state = await this._ws("state");
      this._error = null;
    } catch (err) {
      this._error = err.message || String(err);
    }
    await this._loadPhoto();
    await this._loadView();
    // Re-render only when something visible changed (ages tick every poll).
    const signature = JSON.stringify([this._view, this._state, this._cache, this._plans, this._photoUrl, this._error, this._priceDialog],
      (key, value) => (key === "age_s" ? undefined : value));
    if (signature === this._signature) return;
    this._signature = signature;
    this._render();
  }

  async _loadPhoto() {
    const url = this._state && this._state.vehicle_image;
    if (url === this._photoSrc) return;
    this._photoSrc = url;
    if (this._photoUrl) URL.revokeObjectURL(this._photoUrl);
    this._photoUrl = null;
    if (!url) return;
    try {
      const response = await this._hass.fetchWithAuth(url);
      if (response.ok) this._photoUrl = URL.createObjectURL(await response.blob());
    } catch (err) {
      this._photoUrl = null;
    }
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
        if (!c.events || Date.now() - (c.eventsAt || 0) > 30000) {
          const category = this._eventFilter && this._eventFilter !== "important" ? { category: this._eventFilter } : {};
          c.events = await this._ws("get_events", { limit: 300, ...category });
          c.eventsAt = Date.now();
        }
        if (!c.replay) c.replay = await this._ws("get_replay");
      } else if (this._view === "settings" && !c.settings) {
        c.settings = await this._ws("get_settings");
      } else if (this._view === "plan" && this._plans === null && this._state) {
        this._plans = JSON.parse(JSON.stringify(this._state.plans));
      }
    } catch (err) {
      this._error = err.message || String(err);
    }
  }

  /** Integration version: WS state first, then panel config, then ?v= of the script URL. */
  _version() {
    const fromState = this._state && this._state.version;
    if (fromState) return String(fromState);
    const fromConfig = this._panel && this._panel.config && this._panel.config.ev_pilot_version;
    if (fromConfig) return String(fromConfig);
    try {
      for (const script of document.querySelectorAll("script[src]")) {
        const src = script.getAttribute("src") || "";
        if (!src.includes("ev_charging_pilot")) continue;
        const v = new URL(src, window.location.href).searchParams.get("v");
        if (v) return v;
      }
    } catch (err) { /* ignore */ }
    return "";
  }

  _setView(view) {
    if (this._settingsDraft && view !== this._view
        && !confirm("Geänderte Einstellungen sind noch nicht gespeichert. Verwerfen?")) return;
    this._settingsDraft = null;
    if (this._planSaveTimer) this._savePlans();  // flush a pending plan change
    this._view = view;
    localStorage.setItem("ev-pilot-view", view);
    this._cache = {};
    this._plans = null;
    this._refresh();
  }

  // ------------------------------------------------------------------ render

  _render(force = false) {
    const s = this._state;
    const mode = s ? s.mode : "";
    const modeLabel = { dry_run: "DRY-RUN", live: "LIVE", replay: "REPLAY" }[mode] || "";
    const body = !s
      ? `<div class="card">${this._error ? `Fehler: ${esc(this._error)}` : "Lade …"}</div>`
      : { cockpit: () => this._cockpit(s), plan: () => this._planView(s), home: () => this._home(),
          drive: () => this._drive(), diag: () => this._diag(s), settings: () => this._settingsView(s) }[this._view]();
    const focused = this.shadowRoot.activeElement;
    if (!force && focused && ["INPUT", "SELECT"].includes(focused.tagName)) {
      // Never re-render under the user's cursor while a form field is being edited.
      return;
    }
    const scrolls = [...this.shadowRoot.querySelectorAll(".scroll")].map((el) => [el.scrollTop, el.scrollLeft]);
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <header>
        <button class="menu" data-menu title="Menü">☰</button>
        <h1>${esc(s ? s.name : "EV Charging Pilot")}${this._version() ? `<span class="version">v${esc(this._version())}</span>` : ""}</h1>
        ${modeLabel ? `<span class="badge ${mode === "live" ? "live" : ""}">${modeLabel}</span>` : ""}
      </header>
      <nav>${VIEWS.map(([id, label]) => `<button data-view="${id}" class="${this._view === id ? "active" : ""}">${id === "home" && s ? `Hausstrom → ${esc(s.vehicle_name)}` : label}</button>`).join("")}</nav>
      <main>${body}</main>${this._priceDialogHtml(s)}`;
    this.shadowRoot.querySelectorAll(".scroll").forEach((el, i) => {
      if (scrolls[i]) [el.scrollTop, el.scrollLeft] = scrolls[i];
    });
    // Live data re-renders the page every few seconds: keep what the user typed.
    this.shadowRoot.querySelectorAll("[data-form] [name]").forEach((el) => {
      const draft = this._formDrafts && this._formDrafts[el.closest("[data-form]").dataset.form];
      if (draft && el.name in draft) el.value = draft[el.name];
    });
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
    root.querySelectorAll("details[data-details]").forEach((el) =>
      el.addEventListener("toggle", () => {
        this._openDetails = this._openDetails || new Set();
        el.open ? this._openDetails.add(el.dataset.details) : this._openDetails.delete(el.dataset.details);
      }));
    root.querySelectorAll("[data-form] [name]").forEach((el) =>
      ["input", "change"].forEach((type) => el.addEventListener(type, () => {
        const form = el.closest("[data-form]").dataset.form;
        this._formDrafts = this._formDrafts || {};
        this._formDrafts[form] = { ...(this._formDrafts[form] || {}), [el.name]: el.value };
      })));
    root.querySelectorAll('input[type=range]').forEach((el) =>
      el.addEventListener("input", () => {
        const label = el.closest("label") && el.closest("label").querySelector("b.val");
        if (label) label.textContent = el.dataset.action === "manual-target" && Number(el.value) >= 100 ? "voll (100 %)" : `${el.value} %`;
      }));
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
        this._queuePlanSave();
        if (field === "enabled") this._render(true);
        break;
      }
      case "plan-day": {
        const plan = plans[Number(el.dataset.index)];
        const days = new Set(plan.weekdays);
        days.has(el.dataset.day) ? days.delete(el.dataset.day) : days.add(el.dataset.day);
        plan.weekdays = WEEKDAYS.map(([d]) => d).filter((d) => days.has(d));
        this._queuePlanSave();
        this._render(true);
        break;
      }
      case "plan-mode":
        plans[Number(el.dataset.index)].mode = el.dataset.mode;
        this._queuePlanSave();
        this._render(true);
        break;
      case "plan-add":
        plans.push({ id: `plan-${Date.now().toString(36)}`, name: "Neuer Plan", enabled: true,
          weekdays: ["sat", "sun"], mode: "departure_based", charge_start_time: "03:00",
          departure_time: "09:00", ready_buffer_min: 30, minimum_departure_soc_pct: 80,
          preferred_departure_soc_pct: 90, climate: "auto" });
        this._savePlans("Plan hinzugefügt"); break;
      case "plan-delete": {
        const plan = plans[Number(el.dataset.index)];
        if (!confirm(`Plan „${plan.name}“ löschen?`)) break;
        plans.splice(Number(el.dataset.index), 1);
        this._savePlans(`Plan „${plan.name}“ gelöscht`); break;
      }
      case "external-add":
        this._addExternal(); break;
      case "odometer-add":
        this._addOdometer(); break;
      case "event-filter":
        this._eventFilter = el.value; this._cache.events = null; this._refresh(); break;
      case "system-check":
        this._toast("Systemtest läuft …");
        this._ws("run_system_check", { send_test_push: el.dataset.push === "1" })
          .then((result) => { this._cache.check = result; this._render(true); })
          .catch((err) => this._toast(`Fehler: ${err.message || err}`));
        break;
      case "oneshot-add": {
        const data = this._form("oneshot");
        if (!data.departure_at) { this._toast("Bitte Datum und Uhrzeit wählen"); break; }
        // "Standard" is an explicit choice here (0), not "take the plan's current".
        const amps = this.shadowRoot.querySelector('[data-form="oneshot"] [name=charge_current_a]');
        if (amps) data.charge_current_a = Number(amps.value || 0);
        this._submit("oneshot", "start_one_shot", data, "Einmalige Abfahrt geplant");
        break;
      }
      case "events-reload":
        this._cache.events = null; this._refresh(); break;
      case "replay-run":
        this._runReplay(); break;
      case "report":
        this._createReport(el.dataset.month ? Number(el.dataset.month) : null); break;
      case "open-report":
        this._openReport(el.dataset.url); break;
      case "price-pick":
        this._savePrice(el.dataset.price); break;
      case "price-save": {
        const input = this.shadowRoot.querySelector('[data-form="pricedialog"] [name=price]');
        this._savePrice(input && input.value); break;
      }
      case "price-cancel":
        this._priceDialog = null; this._render(true); break;
      case "manual-current":
        this._ws("set_manual_current", { value: Number(el.value || 0) })
          .then((r) => { this._toast(r.value ? `Ladestrom „Jetzt laden“: ${r.value} A` : "Ladestrom „Jetzt laden“: Standard"); this._refresh(); })
          .catch((err) => this._toast(`Fehler: ${err.message || err}`));
        break;
      case "manual-target":
        this._ws("set_manual_target", { value: Number(el.value) })
          .then(() => { this._toast(`Manuelles Ladeziel ${el.value} %`); this._refresh(); })
          .catch((err) => this._toast(`Fehler: ${err.message || err}`));
        break;
      case "setting":
        this._settingsDraft = { ...(this._settingsDraft || {}), [el.dataset.key]:
          el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value };
        if (this._cache.settings && this._settingsDraft[el.dataset.key] === this._cache.settings.values[el.dataset.key]) {
          delete this._settingsDraft[el.dataset.key];  // changed back → no longer dirty
          if (!Object.keys(this._settingsDraft).length) this._settingsDraft = null;
        }
        this._render(true);
        break;
      case "group-toggle": {
        const open = this._openGroups || new Set(["general"]);
        open.has(el.dataset.group) ? open.delete(el.dataset.group) : open.add(el.dataset.group);
        this._openGroups = open;
        this._render(true);
        break;
      }
      case "expert-toggle":
        try { localStorage.setItem("ev-pilot-expert", el.dataset.value); } catch (err) { /* private mode */ }
        this._render(true);
        break;
      case "settings-save":
        this._saveSettings(); break;
      case "settings-discard":
        this._settingsDraft = null; this._render(true); break;
      case "photo-upload":
        this._uploadPhoto(el); break;
      case "photo-delete":
        this._deletePhoto(); break;
      case "configure-shelly":
        this._configureShelly(); break;
      case "external-cost":
        this._completeExternal(el.dataset.id); break;
      default: break;
    }
  }

  /** Plan edits save themselves shortly after the last change – no save button to forget. */
  _queuePlanSave() {
    clearTimeout(this._planSaveTimer);
    this._planSaveTimer = setTimeout(() => this._savePlans(), 800);
  }

  async _savePlans(message = "Ladeplan gespeichert") {
    clearTimeout(this._planSaveTimer);
    this._planSaveTimer = null;
    if (!this._plans) return;
    try {
      const result = await this._ws("set_plans", { plans: this._plans });
      if (this._view === "plan") this._plans = result.plans;
      this._toast(message);
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
    this._submit("external", "add_external_charge", data, "Fremdladung erfasst");
  }

  _addOdometer() {
    const data = this._form("odometer");
    if (!data.odometer_km) { this._toast("Kilometerstand angeben"); return; }
    this._submit("odometer", "add_manual_odometer", data, "Kilometerstand erfasst");
  }

  _settingsView(s) {
    const cfg = this._cache.settings;
    if (!cfg) return `<div class="card">Lade Einstellungen …</div>`;
    const draft = this._settingsDraft || {};
    const admin = cfg.is_admin;
    const expert = this._expert();
    const value = (key) => (key in draft ? draft[key] : cfg.values[key]);
    const shown = (f) => {
      if (f.hidden || (f.advanced && !expert)) return false;
      return Object.entries(f.show_if || {}).every(([k, want]) =>
        Array.isArray(want) ? want.includes(value(k)) : value(k) === want);
    };
    const open = this._openGroups || new Set(["general"]);
    const dirtyKeys = Object.keys(draft);

    const control = (f) => {
      const v = value(f.key);
      const attrs = `data-action="setting" data-key="${f.key}" ${admin ? "" : "disabled"}`;
      if (f.type === "bool") {
        return `<label class="switch"><input type="checkbox" ${v ? "checked" : ""} ${attrs}><span class="track"></span></label>`;
      }
      if (f.type === "select") {
        return `<select ${attrs}>${f.options.map((o) => `<option value="${esc(o.value)}" ${o.value === v ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select>`;
      }
      if (f.type === "number") {
        return `<div class="unitbox"><input type="number" inputmode="decimal" min="${f.min}" max="${f.max}" step="${f.step}" value="${esc(v)}" ${attrs}>${f.unit ? `<span>${esc(f.unit)}</span>` : ""}</div>`;
      }
      if (f.type === "date") return `<input type="date" value="${esc(v)}" ${attrs}>`;
      if (f.type === "time") return `<input type="time" value="${esc(String(v || "").slice(0, 5))}" ${attrs}>`;
      return `<input type="text" value="${esc(v ?? "")}" ${attrs} ${f.type === "entity" ? 'placeholder="sensor.…"' : ""}>`;
    };
    const row = (f) => `<div class="srow ${f.key in draft ? "changed" : ""}">
        <div class="stext"><div class="slabel">${esc(f.label)}</div>${f.help ? `<div class="shelp">${esc(f.help)}</div>` : ""}</div>
        <div class="sctl">${control(f)}</div></div>`;

    const photoRows = `<div class="srow">
        <div class="stext"><div class="slabel">Fahrzeugfoto</div>
          <div class="shelp">Seitenansicht, am schönsten als PNG mit transparentem Hintergrund, mind. 1200 px breit.</div></div>
        <div class="sctl photoctl">
          ${this._photoUrl ? `<img src="${this._photoUrl}" alt="Fahrzeug">` : ""}
          <label class="act" style="cursor:pointer">${this._photoUrl ? "Ändern" : "Foto wählen"}<input type="file" accept="image/png,image/jpeg,image/webp" data-action="photo-upload" style="display:none" ${admin ? "" : "disabled"}></label>
          ${this._photoUrl ? `<button class="act danger" data-action="photo-delete" ${admin ? "" : "disabled"}>Entfernen</button>` : ""}
        </div></div>`;
    const history = (cfg.price_history || []).slice().reverse().map((p) =>
      `<span class="pill muted">${dateOnly(p.valid_from)}: ${num(p.eur_per_kwh, 3, "€/kWh")}</span>`).join(" ");

    const groups = cfg.groups.filter((g) => (expert || !g.advanced) && g.fields.some(shown)).map((g) => {
      const isOpen = open.has(g.id);
      const changed = g.fields.some((f) => f.key in draft) || (g.id === "prices" && ("price_eur_kwh" in draft || "price_valid_from" in draft));
      return `<section class="sgroup ${isOpen ? "open" : ""}">
        <button class="shead" data-action="group-toggle" data-group="${g.id}" aria-expanded="${isOpen}">
          <ha-icon icon="${esc(g.icon || "mdi:cog")}"></ha-icon>
          <span class="stitle">${esc(g.title)}${changed ? ` <span class="pill warn">geändert</span>` : ""}<small>${esc(g.description || "")}</small></span>
          <span class="chev">${isOpen ? "▴" : "▾"}</span>
        </button>
        ${isOpen ? `<div class="sbody">
          ${g.id === "general" ? photoRows : ""}
          ${g.fields.filter(shown).map(row).join("")}
          ${g.id === "prices" && history ? `<div class="srow"><div class="stext"><div class="slabel">Bisherige Preise</div></div><div class="sctl wrap">${history}</div></div>` : ""}
        </div>` : ""}
      </section>`;
    }).join("");

    return `<div class="settings">
      <div class="card stop">
        <div><b>Einstellungen</b><div class="hint">${expert ? "Alle Einstellungen inkl. Feinabstimmung." : "Die wichtigsten Einstellungen. Feinabstimmung unter „Experte“."}</div></div>
        <div class="seg" role="group" aria-label="Ansicht">
          <button class="${expert ? "" : "on"}" data-action="expert-toggle" data-value="0">Einfach</button>
          <button class="${expert ? "on" : ""}" data-action="expert-toggle" data-value="1">Experte</button>
        </div>
      </div>
      ${admin ? "" : `<div class="notice warn">Nur Administratoren können Einstellungen ändern.</div>`}
      ${groups}
      ${dirtyKeys.length ? `<div class="savebar">
        <span>${dirtyKeys.length} Änderung${dirtyKeys.length === 1 ? "" : "en"} – noch nicht gespeichert</span>
        <button class="act" data-action="settings-discard">Verwerfen</button>
        <button class="act primary" data-action="settings-save" ${admin ? "" : "disabled"}>Speichern</button>
      </div>` : ""}
    </div>`;
  }

  _expert() {
    try { return localStorage.getItem("ev-pilot-expert") === "1"; } catch (err) { return false; }
  }

  async _saveSettings() {
    try {
      await this._ws("set_settings", { values: this._settingsDraft || {} });
      this._settingsDraft = null;
      this._cache.settings = null;
      this._toast("Einstellungen gespeichert – Integration lädt neu");
      setTimeout(() => this._refresh(), 2500);
    } catch (err) {
      this._toast(`Fehler: ${err.message || err}`);
    }
  }

  async _uploadPhoto(input) {
    const file = input.files && input.files[0];
    if (!file) return;
    try {
      const blob = await shrinkImage(file, 1600);
      const form = new FormData();
      form.append("file", blob, file.name);
      const response = await this._hass.fetchWithAuth("/api/ev_charging_pilot/vehicle_image", { method: "POST", body: form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) { this._toast(`Fehler: ${data.error || response.status}`); return; }
      this._toast("Foto gespeichert");
      await this._refresh();
    } catch (err) {
      this._toast(`Fehler: ${err.message || err}`);
    }
  }

  async _deletePhoto() {
    if (!confirm("Fahrzeugfoto entfernen?")) return;
    await this._hass.fetchWithAuth("/api/ev_charging_pilot/vehicle_image", { method: "DELETE" });
    this._toast("Foto entfernt");
    await this._refresh();
  }

  async _configureShelly() {
    if (!confirm("Am Shelly werden die Failsafe-Werte gesetzt:\n• Einschaltzustand: an\n• Auto-On: an\n• Auto-On-Verzögerung = CP-Pulsdauer\n\nDamit schließt der Shelly die CP-Leitung immer von selbst. Fortfahren?")) return;
    try {
      // callService(domain, service, data, target, notifyOnError, returnResponse)
      const result = await this._hass.callService(DOMAIN, "configure_shelly", {}, undefined, false, true);
      const ok = result && result.response && result.response.ok;
      this._toast(ok ? "Shelly konfiguriert – Prüfung bestanden" : "Shelly gesetzt, die Prüfung zeigt noch Abweichungen");
    } catch (err) {
      this._toast(`Fehler: ${err.message || err}`);
    }
    await this._refresh();
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
    const powerW = s.values.charge_power && s.values.charge_power.value !== null ? s.values.charge_power.value : 0;
    const kw = powerW / 1000;
    const health = s.health.status;
    const ex = s.executor;
    const desired = s.desired || {};
    const e = w ? w.estimate : {};
    const healthClass = { HEALTHY: "ok", DEGRADED: "warn", ERROR: "bad" }[health];
    const has = (key) => key in s.entities;
    const plugged = !["DISCONNECTED", null, undefined].includes(ex.state);
    const charging = ex.state === "CHARGING" || ex.state === "CHARGE_STABILIZING";
    // Scale of gauge and chart: what can flow at home – the measured power wins over a
    // too small configured on-board charger (smart 453 with the 22 kW option).
    const peakKw = Math.max(0, ...(s.history || []).map((h) => (h[1] || 0) / 1000));
    const maxKw = Math.min(s.settings.max_power_kw || 11, Math.max(s.settings.vehicle_charger_kw || 4.6,
      (s.learned && s.learned.power_kw) || 0, kw, peakKw));
    const reasons = s.health.reasons.map((r) => `<p class="reason">${esc(HEALTH_TEXT[r] || r)}</p>`).join("");
    // The status sentence already says "Probebetrieb"; the header badge shows the mode.
    const notice = "";
    const errorBox = health === "ERROR"
      ? `<div class="notice bad"><b>Automatik gesperrt.</b>${reasons}</div>` : "";
    return `${notice}${errorBox}
    <div class="grid">
      <div class="card wide">
        <div class="hero">
          <div class="col carcol">
            ${this._photoUrl ? `<div class="photo ${charging ? "charging" : ""}"><img src="${this._photoUrl}" alt="Fahrzeug"></div>` : ""}
            ${batterySvg({ charging, error: health === "ERROR" || !!ex.failure_code, soc: soc ? soc.value : null,
              min: w ? w.minimum_soc_pct : null, pref: w ? w.preferred_soc_pct : null })}
            ${this._sohChip(s)}
            ${soc && soc.quality !== "GOOD" ? `<div class="hint"><span class="pill ${QUALITY_CLASS[soc.quality]}">${soc.quality === "LAST_KNOWN_VALID" ? "letzter bekannter Ladestand – Auto schläft" : esc(soc.quality)}</span></div>` : ""}
            ${!this._photoUrl ? `<div class="hint">Eigenes Fahrzeugfoto: Reiter „Einstellungen“</div>` : ""}
            ${s.summary ? `<div class="status tone-${esc(s.summary.tone)}"><div class="big">${esc(s.summary.headline)}</div>
              ${s.summary.detail ? `<div class="sdetail">${esc(s.summary.detail)}</div>` : ""}</div>`
              : `<div class="big">${esc(STATE_LABELS[ex.state] || ex.state || "–")}</div>`}
            <div class="chips">
              <span class="pill ${plugged ? "info" : "muted"}">${plugged ? "eingesteckt" : "nicht eingesteckt"}</span>
              <span class="pill ${healthClass}">${esc(HEALTH_LABELS[health] || health)}</span>
              ${s.override ? `<span class="pill info">Override: ${esc(s.override.mode)}</span>` : ""}
              ${s.one_shot ? `<span class="pill info">Einmalig: Abfahrt ${dateTime(s.one_shot.departure_at)}</span>` : ""}
              ${!s.automation_enabled ? `<span class="pill warn">Automatik aus</span>` : ""}
              ${ex.failure_code ? `<span class="pill bad">${esc(ex.failure_code)}</span>` : ""}
            </div>
            <div class="sub">Zustand: ${esc(STATE_LABELS[ex.state] || ex.state || "–")} · Soll: ${esc(REASON_LABELS[desired.reason] || desired.reason || "–")}
              (${desired.charger_enabled === true ? "Wallbox an" : desired.charger_enabled === false ? "Wallbox aus" : "nicht eingreifen"}) · seit ${time(ex.since)}</div>
          </div>
          <div class="col">
            ${powerGauge(kw, maxKw)}
            ${w ? `<div class="label"><b>Abfahrt ${dateTime(w.departure)}</b></div>` : ""}
            <div class="label">${s.session ? `Session ${num(s.session.energy_kwh, 2, "kWh")}` : "keine laufende Session"}</div>
            <div class="label">${num(s.prices.current_eur_kwh * 100, 1, "ct/kWh")} ${s.prices.dynamic ? "(dynamisch)" : "(Festpreis)"}</div>
          </div>
        </div>
      </div>
      <div class="card wide">
        <h2>Nächste Ladung ${w ? `<span class="sub">· ${esc(w.name)} · Abfahrt ${dateTime(w.departure)}</span>` : ""}</h2>
        ${w ? timelineSvg(s) : `<p class="sub">Kein aktiver Ladeplan.</p>`}
        <div class="legend"><span class="dot" style="background:var(--primary-color)"></span>${w && w.blocks.length ? "Ladeblöcke (günstigste Zeit)" : "Ladefenster"}
          ${(s.prices.slots || []).length ? (() => {
            const p = s.prices.slots.map((x) => x.eur_per_kwh * 100);
            return `<span class="dot" style="background:var(--warning-color)"></span>Strompreis ${num(Math.min(...p), 0)}–${num(Math.max(...p), 0)} ct/kWh`;
          })() : ""}</div>
      </div>
      <div class="card">
        <h2>Prognose <span class="sub">(Schätzung)</span></h2>
        <div class="row"><span>Erwarteter SOC bei Abfahrt</span><b>${num(e.expected_soc_at_departure, 0, "%")}</b></div>
        <div class="row"><span>Mindest-SOC ${w ? w.minimum_soc_pct + " %" : ""}</span>${this._yesNo(e.minimum_reachable)}</div>
        <div class="row"><span>Wunsch-SOC ${w ? w.preferred_soc_pct + " %" : ""}</span>${this._yesNo(e.preferred_reachable)}</div>
        <div class="row"><span>Start</span><span>${w ? dateTime(w.start) : "–"}${w && w.fallback_without_soc ? " (fest, kein SOC)" : ""}</span></div>
        <div class="row"><span>Voraussichtlich fertig</span><span>${time(e.finish_at)}</span></div>
        <div class="row"><span>Kosten</span><span>${num(e.cost_eur, 2, "€")}</span></div>
        <p class="hint">${s.learned && s.learned.active
          ? `Gelernt aus ${s.learned.sessions} Ladungen: ${s.learned.power_kw ? num(s.learned.power_kw, 1, "kW") : "Nennleistung"}${s.learned.grid_kwh_per_pct ? ` · ${num(s.learned.grid_kwh_per_pct, 2, "kWh")} je %` : ""}`
          : "Die Prognose lernt aus den eigenen Ladungen (ab 3 Ladungen genauer)."}</p>
      </div>
      <div class="card">
        <h2>System</h2>
        <div class="big"><span class="pill ${healthClass}">${esc(HEALTH_LABELS[health] || health)}</span></div>
        ${reasons || `<p class="sub">alles erreichbar</p>`}
        ${s.data_conflict ? `<p><span class="pill bad">Datenkonflikt Wallbox/Fahrzeug</span></p>` : ""}
        ${s.health.shelly_deviations && s.health.shelly_deviations.length ? `${shellyRows(s.health.shelly_deviations)}
          <div class="actions" style="margin-top:8px"><button class="act primary" data-action="configure-shelly">Shelly konfigurieren</button></div>` : ""}
        ${s.climate ? `<p class="sub">Klima ${s.climate.duration_min} min ab ${time(s.climate.start_at)}${s.climate.blocked ? ` – ${esc(CLIMATE_BLOCKED[s.climate.blocked] || s.climate.blocked)}` : ""}</p>` : ""}
        ${s.prices.error ? `<p><span class="pill warn">${esc(s.prices.error)}</span></p>` : ""}
      </div>
      <div class="card">
        <h2>Letzte Ladung</h2>
        ${s.last_result ? `<div class="big">${s.last_result.success ? num(s.last_result.energy_kwh, 2, "kWh") : `<span class="pill bad">${esc(s.last_result.failure_code)}</span>`}</div>
          <div class="sub">${dateTime(s.last_result.at)}</div>` : `<p class="sub">Noch keine Ladung aufgezeichnet.</p>`}
      </div>
      <div class="card wide">
        <h2>Verlauf (24 h)</h2>
        ${historySvg(s.history, maxKw)}
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
          ${ex.failure_code ? `<button class="act primary" data-service="reset_error" data-label="Neuer Ladeversuch">Erneut versuchen</button>`
            : `<button class="act danger" data-service="reset_error" ${health === "ERROR" ? "" : "disabled"}>Fehler zurücksetzen</button>`}
        </div>
      </div>
    </div>`;
  }

  _sohChip(s) {
    const soh = s.values.ovms_soh;
    const range = s.values.ovms_range;
    const parts = [];
    if (soh && soh.value !== null) {
      const cls = soh.value >= 90 ? "ok" : soh.value >= 80 ? "info" : "warn";
      parts.push(`<span class="pill ${cls}" title="Akkugesundheit (State of Health)">Akkugesundheit (SOH) ${num(soh.value, 0, "%")}</span>`);
    } else if ("ovms_soh" in s.entities) {
      parts.push(`<span class="pill muted" title="Akkugesundheit">SOH –</span>`);
    }
    if (range && range.value !== null) parts.push(`<span class="pill muted">${num(range.value, 0, "km")} Reichweite</span>`);
    return parts.length ? `<div class="chips">${parts.join("")}</div>` : "";
  }

  _vehicleLinkRows(s) {
    const v = s.vehicle_link || {};
    const dataOk = v.data_quality === "GOOD" || v.data_quality === "LAST_KNOWN_VALID";
    const path = { ovms_service: "OVMS-Integration", mqtt: "MQTT-Topic", script: "Script" }[v.command_path];
    return `<div class="row"><span>Fahrzeugdaten</span>${!v.data_configured
        ? `<span class="pill muted">nicht eingerichtet</span>`
        : `<span class="pill ${dataOk ? "ok" : "warn"}">${dataOk ? "verbunden" : esc(v.data_quality || "–")}</span>`}</div>
      ${v.data_configured && v.data_updated_at ? `<div class="hint">zuletzt ${dateTime(v.data_updated_at)}</div>` : ""}
      <div class="row"><span>Zugriff</span>${v.read_write
        ? `<span class="pill ${v.commands_ready ? "ok" : "warn"}">Lesen & Schreiben</span>`
        : `<span class="pill info">nur Lesen</span>`}</div>
      <div class="hint">${v.read_write
        ? (path ? `Befehle (Wakeup, Klima) gehen über ${path}.` : "Kein Befehlsweg gefunden – die OVMS-Integration (HACS) einrichten.")
        : `Umschalten unter Einstellungen → Allgemein.${path ? ` Befehlsweg ist bereit (${path}).` : ""}`}</div>`;
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
    const cards = plans.map((p, i) => {
      const win = (s.windows || []).find((w) => w.source_id === p.id);
      const fixed = p.mode === "fixed_start";
      const field = (name) => `data-action="plan-field" data-index="${i}" data-field="${name}"`;
      const summary = !p.enabled ? "Plan ist ausgeschaltet."
        : !p.weekdays.length ? "Keine Abfahrtstage gewählt."
        : win ? `Nächste Abfahrt ${dateTime(win.departure)} · Start ${dateTime(win.start)} · erwartet ${num(win.estimate.expected_soc_at_departure, 0, "%")}`
        : "Keine Abfahrt in den nächsten Tagen.";
      return `
      <div class="card wide plan ${p.enabled ? "" : "off"}">
        <div class="phead">
          <input class="pname" ${field("name")} value="${esc(p.name)}" aria-label="Name des Plans">
          <label class="switch" title="${p.enabled ? "Plan aktiv" : "Plan aus"}"><input type="checkbox" ${field("enabled")} ${p.enabled ? "checked" : ""}><span class="track"></span></label>
        </div>
        <div class="psum">${esc(summary)}</div>
        <div class="psec"><span class="plabel">Abfahrt an diesen Tagen</span>
          <div class="daychips">${WEEKDAYS.map(([d, l]) => `<button class="day ${p.weekdays.includes(d) ? "on" : ""}" data-action="plan-day" data-index="${i}" data-day="${d}" aria-pressed="${p.weekdays.includes(d)}">${l}</button>`).join("")}</div></div>
        <div class="pgrid">
          <label>Abfahrt um<input type="time" ${field("departure_time")} value="${esc(p.departure_time)}"></label>
          <label>Fertig vor Abfahrt<span class="unitbox"><input type="number" min="0" max="240" step="5" ${field("ready_buffer_min")} value="${p.ready_buffer_min}"><span>min</span></span></label>
          <label>Vorklimatisierung<select ${field("climate")}>
            ${[["off", "aus"], ["auto", "automatisch (nach Temperatur)"], ["5", "5 min"], ["10", "10 min"], ["15", "15 min"]]
              .map(([v, l]) => `<option value="${v}" ${p.climate === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
          ${s.settings.current_settable ? `<label>Ladestrom<select ${field("charge_current_a")}>${ampsOptions(p.charge_current_a, s.settings)}</select></label>` : ""}
        </div>
        <div class="psec"><span class="plabel">Wann laden?</span>
          <div class="seg">
            <button class="${fixed ? "" : "on"}" data-action="plan-mode" data-index="${i}" data-mode="departure_based">Rechtzeitig zur Abfahrt</button>
            <button class="${fixed ? "on" : ""}" data-action="plan-mode" data-index="${i}" data-mode="fixed_start">Ab fester Uhrzeit</button>
          </div>
          <div class="pmode">${fixed
            ? `<label class="inline">Start um <input type="time" ${field("charge_start_time")} value="${esc(p.charge_start_time)}"></label>`
            : `<span class="hint">Startet so spät wie möglich${s.prices.dynamic ? " bzw. in den günstigsten Stunden" : ""}, damit das Auto zur Abfahrt fertig ist.</span>
               <label class="inline">Ohne aktuellen Ladestand ab <input type="time" ${field("charge_start_time")} value="${esc(p.charge_start_time)}"></label>`}</div></div>
        <div class="psec"><span class="plabel">Ladestand bei Abfahrt</span>
          <div class="socbar" aria-hidden="true"><div class="fill" style="width:${p.preferred_departure_soc_pct}%"></div><i style="left:${p.minimum_departure_soc_pct}%"></i></div>
          <div class="pgrid two">
            <label>Mindestens: <b class="val">${p.minimum_departure_soc_pct} %</b><input type="range" min="10" max="100" step="5" ${field("minimum_departure_soc_pct")} value="${p.minimum_departure_soc_pct}"></label>
            <label>Laden bis (Ziel): <b class="val">${p.preferred_departure_soc_pct} %</b><input type="range" min="10" max="100" step="5" ${field("preferred_departure_soc_pct")} value="${p.preferred_departure_soc_pct}"></label>
          </div></div>
        <div class="pfoot"><button class="act danger" data-action="plan-delete" data-index="${i}">Plan löschen</button></div>
      </div>`;
    }).join("");
    const manual = s.settings.manual_target_soc ?? 100;
    return `<div class="grid">
      <div class="card wide">
        <h2>Manuelles Laden <span class="sub">· „Jetzt laden“ ohne Zeitplan</span></h2>
        <div class="slider"><label>Laden bis: <b class="val">${manual >= 100 ? "voll (100 %)" : manual + " %"}</b>
          <input type="range" min="20" max="100" step="5" value="${manual}" data-action="manual-target"></label></div>
        ${s.settings.current_settable ? `<label class="inline">Ladestrom <select data-action="manual-current">${ampsOptions(s.settings.manual_current_a, s.settings)}</select></label>` : ""}
        <p class="hint">Gilt für „Jetzt laden“ (Cockpit, Push beim Einstecken, Service). Ohne Fahrzeugdaten wird bis zum Abstecken geladen.</p>
      </div>
      ${this._oneShotCard(s, plans)}
      <div class="card wide"><h2>Kommende Ladefenster</h2>
        ${s.next_window ? timelineSvg(s) : ""}
        ${windows ? `<div class="scroll"><table><tr><th>Plan</th><th>Start</th><th>Abfahrt</th><th class="n">SOC erwartet</th><th>Art</th><th class="n">Kosten*</th></tr>${windows}</table></div>` : `<p class="sub">Kein Plan aktiv.</p>`}
        <p class="sub">* Schätzung. Ist das Ziel erreicht, bleibt die Wallbox bis zur Abfahrt aus – das Auto wird dafür nie geweckt.</p>
      </div>
      ${cards}
      <div class="card wide actions">
        <button class="act" data-action="plan-add">Plan hinzufügen</button>
        <span class="sub">Änderungen werden automatisch gespeichert.</span>
      </div>
    </div>`;
  }

  _oneShotCard(s, plans) {
    const shot = s.one_shot;
    const tomorrow = new Date(Date.now() + 864e5);
    const pad = (n) => String(n).padStart(2, "0");
    const proposal = `${tomorrow.getFullYear()}-${pad(tomorrow.getMonth() + 1)}-${pad(tomorrow.getDate())}T07:00`;
    const target = (plans[0] && plans[0].preferred_departure_soc_pct) || 90;
    return `<div class="card wide"><h2>Einmalige Abfahrt <span class="sub">· z. B. Urlaub, Termin</span></h2>
      ${shot ? `<div class="row"><span>Geplant: <b>${dateTime(shot.departure_at)}</b> · Ziel ${shot.preferred_departure_soc_pct} %${shot.charge_current_a ? ` · ${shot.charge_current_a} A` : ""}</span>
        <button class="act" data-service="cancel_one_shot" data-label="Einmalige Abfahrt gelöscht">Löschen</button></div>` : ""}
      <div class="form" data-form="oneshot">
        <label>Abfahrt<input type="datetime-local" name="departure_at" value="${proposal}"></label>
        <label>Laden bis<span class="unitbox"><input type="number" name="target_soc" min="20" max="100" step="5" value="${target}"><span>%</span></span></label>
        ${s.settings.current_settable ? `<label>Ladestrom<select name="charge_current_a">${ampsOptions(plans[0] && plans[0].charge_current_a, s.settings)}</select></label>` : ""}
        <button class="act primary" data-action="oneshot-add">${shot ? "Ersetzen" : "Einplanen"}</button>
      </div>
      <p class="hint">Gilt zusätzlich zu den Wochenplänen und löscht sich nach der Abfahrt selbst.</p></div>`;
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
        <div class="sub">Wallbox-Zähler, maßgeblich für die Hausabrechnung</div></div>
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
      ${Object.entries(entries).map(([k, g]) => `<tr><td>${esc(SEASON_LABELS[k] || (k + " °C"))}</td><td class="n">${num(g.distance_km, 0)}</td><td class="n">${num(g.vehicle_kwh_100km, 1)}</td>
        <td class="n">${num(g.grid_kwh_100km, 1)}</td><td class="n">${num(g.recuperation_share_pct, 0)}</td><td class="n">${num(g.auxiliary_kwh, 1)}</td><td class="n">${num(g.cost_eur, 2)}</td></tr>`).join("")}
      </table></div><p class="sub">Fahrzeugverbrauch netto (verbraucht minus Rekuperation), nur Fahrten ab 1 km mit Energiedaten. * Netz geschätzt mit dem gemessenen Ladeverlust, Kosten mit deinem tatsächlichen Heimstrompreis.</p></div>`;
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
      <div class="card wide"><h2>Fremdladungen</h2>
        <p class="sub">Ladungen außer Haus erkennt der Pilot automatisch über OVMS (Auto lädt, ist aber nicht an der eigenen Wallbox). Den bezahlten Preis fragt er per Push ab, oder du ergänzt ihn hier.</p>
        <details data-details="external" ${this._open("external")}><summary>Fremdladung manuell erfassen</summary>
        <div class="form" data-form="external">
          <label>Datum<input type="date" name="date"></label>
          <label>kWh<input type="number" step="0.01" min="0" name="energy_kwh"></label>
          <label>Ort<select name="source"><option value="public">Öffentlich</option><option value="workplace">Arbeitgeber</option><option value="other_home">Andere Wallbox</option></select></label>
          <label>Kosten €<input type="number" step="0.01" min="0" name="cost_eur"></label>
          <label>oder €/kWh<input type="number" step="0.001" min="0" name="price_eur_kwh"></label>
          <label>Anbieter<input name="provider"></label>
          <label>Kilometerstand<input type="number" min="0" name="odometer_km"></label>
          <button class="act primary" data-action="external-add">Speichern</button>
        </div></details>
        <div class="scroll"><table><tr><th>Datum</th><th>Ort</th><th class="n">kWh</th><th class="n">€</th><th>Anbieter</th><th></th></tr>
          ${external.map((e) => `<tr><td>${dateOnly(e.date)}</td><td>${esc(e.source)}</td><td class="n">${num(e.energy_kwh, 2)}</td>
            <td class="n">${num(e.cost_eur ?? (e.price_eur_kwh ? e.price_eur_kwh * e.energy_kwh : null), 2)}</td>
            <td>${esc(e.provider || "")} ${e.detected ? `<span class="pill warn">erkannt · geschätzt</span>` : ""}</td>
            <td>${e.detected ? `<button class="act" data-action="external-cost" data-id="${esc(e.id)}">Ergänzen</button> ` : ""}<button class="act danger" data-service="delete_external_charge" data-payload='${esc(JSON.stringify({ id: e.id }))}' data-confirm="Fremdladung löschen?">×</button></td></tr>`).join("") || `<tr><td colspan="6" class="sub">Keine Fremdladungen.</td></tr>`}
        </table></div></div>
      <div class="card wide"><details data-details="odometer" ${this._open("odometer")}><summary>Kilometerstand manuell eintragen</summary>
        <p class="sub">Nur nötig ohne OVMS bzw. mit Kilometerquelle „manuell“ – mit OVMS kommen die Kilometer automatisch. Stand am Monatsanfang und -ende reicht.</p>
        <div class="form" data-form="odometer">
          <label>km<input type="number" min="0" name="odometer_km"></label>
          <button class="act" data-action="odometer-add">Erfassen</button>
        </div></details></div>
    </div>`;
  }

  /** Collapsible sections keep their state across the frequent re-renders. */
  _open(id) {
    return this._openDetails && this._openDetails.has(id) ? "open" : "";
  }

  _pricePushCard(s) {
    const t = s.price_push_test;
    let result = "";
    if (t && !t.received_at) {
      result = `<span class="pill info">wartet auf Antwort …</span>`;
    } else if (t) {
      result = t.price_eur_kwh != null
        ? `<span class="pill ok">angekommen</span> <b>${num(t.price_eur_kwh, 2, "€/kWh")}</b> erkannt`
        : `<span class="pill bad">nicht erkannt</span> Eingabe „${esc(t.reply || "")}“`;
    }
    return `<div class="card wide"><h2>Push-Test: Preisabfrage Fremdladung</h2>
      <p class="sub">Schickt die Frage nach dem Preis pro kWh aufs Handy, wie nach einer erkannten Fremdladung – nur als Test, es wird nichts gespeichert. Lange drücken zeigt die Preis-Knöpfe, ein Tipp auf die Mitteilung öffnet hier ein Fenster mit Ziffernblock.</p>
      <div class="actions"><button class="act primary" data-service="test_price_push" data-label="Test-Push gesendet">Test-Push senden</button>${result}</div>
      ${t ? `<div class="hint">Gesendet ${dateTime(t.sent_at)}${t.received_at ? ` · Antwort ${dateTime(t.received_at)}` : ""}</div>` : ""}</div>`;
  }

  _chargeTestCard(s) {
    const t = s.charge_test;
    const running = t && t.phase !== "done";
    const verdict = !t ? "" : running
      ? `<span class="pill info">${t.phase === "stopping" ? "Wallbox wird gesperrt …" : "läuft …"}</span>`
      : `<span class="pill ${t.ok ? "ok" : "bad"}">${t.ok ? "erfolgreich" : "fehlgeschlagen"}</span>`;
    const steps = t ? t.steps.map((x) => `<div class="row"><span>${esc(x.text)}</span><span class="sub">+${x.after_s} s</span></div>`).join("") : "";
    return `<div class="card wide"><h2>Ladetest</h2>
      <p class="sub">Schaltet wirklich: Wallbox an, bei Bedarf Auto wecken (erst OVMS, dann CP-Puls), kurz stabil laden, Wallbox wieder aus. Dauert höchstens 8 Minuten. Das Auto muss eingesteckt sein.</p>
      <div class="actions"><button class="act primary" data-service="charge_test" data-label="Ladetest gestartet"
        data-confirm="Ladetest jetzt starten? Die Wallbox wird freigegeben und das Auto bei Bedarf geweckt."
        ${running ? "disabled" : ""}>Ladetest starten</button>${verdict}</div>
      ${t && t.summary ? `<p><b>${esc(t.summary)}</b></p>` : ""}
      ${steps}
      ${t ? `<div class="hint">Gestartet ${dateTime(t.started_at)}</div>` : ""}</div>`;
  }

  _diag(s) {
    const c = this._cache;
    // A running test keeps the Test-Center open even if it was collapsed.
    const testRunning = (s.charge_test && s.charge_test.phase !== "done")
      || (s.price_push_test && !s.price_push_test.received_at
        && Date.now() - new Date(s.price_push_test.sent_at) < 10 * 60e3);
    const all = (c.events && c.events.items) || [];
    const events = this._eventFilter === "important"
      ? all.filter((e) => e.severity !== "debug" && !ROUTINE_EVENTS.has(e.code)) : all;
    const replay = c.replay || {};
    const last = replay.last;
    const values = Object.entries(s.values).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(s.entities[k] || "")}</td>
      <td class="n">${esc(v.value ?? "–")} ${esc(v.unit || "")}</td><td class="n">${v.age_s ?? "–"} s</td>
      <td><span class="pill ${QUALITY_CLASS[v.quality]}">${esc(v.quality)}</span></td></tr>`).join("");
    const sevClass = { critical: "bad", error: "bad", warning: "warn", info: "info", debug: "muted" };
    const check = c.check;
    const checkRows = check ? (check.results || []).map((r) => `<div class="crow"><span class="pill ${{ ok: "ok", info: "info", warn: "warn", bad: "bad" }[r.status]}">${{ ok: "ok", info: "Info", warn: "Hinweis", bad: "Fehler" }[r.status]}</span>
        <div><b>${esc(r.title)}</b><div class="sub">${esc(r.detail)}</div></div></div>`).join("") : "";
    return `<div class="grid">
      <div class="card"><h2>Health</h2>
        <div class="big"><span class="pill ${{ HEALTHY: "ok", DEGRADED: "warn", ERROR: "bad" }[s.health.status]}">${esc(HEALTH_LABELS[s.health.status])}</span></div>
        ${s.health.reasons.map((r) => `<p class="reason">${esc(HEALTH_TEXT[r] || r)}</p>`).join("") || `<div class="sub">keine Auffälligkeiten</div>`}</div>
      <div class="card"><h2>CP / Failsafe</h2>
        <div class="row"><span>Checkliste §3.6</span>${this._yesNo(s.settings.cp_failsafe_verified)}</div>
        <div class="row"><span>Shelly-Konfiguration</span>${this._yesNo(s.health.shelly_config_ok)}</div>
        ${shellyRows(s.health.shelly_deviations)}
        ${s.health.shelly_config_ok === null && s.health.shelly_host ? `<p class="sub">Shelly-Konfiguration nicht lesbar (Shelly offline oder passwortgeschützt).</p>` : ""}
        ${s.health.shelly_host ? `<div class="actions" style="margin-top:8px"><button class="act ${s.health.shelly_config_ok === false ? "primary" : ""}" data-action="configure-shelly">Shelly konfigurieren</button></div>` : ""}
        <div class="row"><span>Puls-Maskierung aktiv</span><span>${s.executor.cp_masked ? "ja" : "nein"}</span></div></div>
      <div class="card"><h2>Fahrzeug</h2>
        ${this._vehicleLinkRows(s)}
        <div class="row"><span>HV-Zyklen heute</span><span>${s.hv_cycles_today ?? "–"}</span></div>
        <div class="row"><span>12 V</span><span>${s.values.ovms_12v ? num(s.values.ovms_12v.value, 1, "V") : "–"}</span></div>
        <div class="row"><span>Außentemperatur</span><span>${num(s.outside_temperature.value, 1, "°C")} (${esc(s.outside_temperature.source)})</span></div></div>
      <div class="card wide"><h2>Datenqualität je Wert</h2><div class="scroll"><table>
        <tr><th>Wert</th><th>Entität</th><th class="n">Wert</th><th class="n">Alter</th><th>Qualität</th></tr>${values}</table></div></div>
      <div class="card wide"><h2>Event Log</h2>
        <div class="actions"><label style="max-width:220px">Anzeigen<select data-action="event-filter">
          ${EVENT_FILTERS.map(([k, l]) => `<option value="${k}" ${this._eventFilter === k ? "selected" : ""}>${l}</option>`).join("")}
        </select></label><button class="act" data-action="events-reload">Aktualisieren</button></div>
        <div class="scroll"><table><tr><th>Zeit</th><th>Meldung</th><th>Code</th></tr>
          ${events.map((e) => `<tr><td class="nowrap">${dateTime(e.timestamp)}</td><td>${esc(e.message)}</td>
            <td><span class="pill ${sevClass[e.severity]}">${esc(e.code)}</span></td></tr>`).join("") || `<tr><td colspan="3" class="sub">Keine Einträge.</td></tr>`}
        </table></div></div>
      <div class="card wide"><h2>Replay</h2>
        <p class="sub">Datensätze liegen in <code>/config/ev_charging_pilot/replay</code>; erstellen mit dem Service <code>create_replay_dataset</code>.</p>
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
      <details class="testcenter" data-details="tests" ${this._open("tests") || (testRunning ? "open" : "")}>
        <summary>Test-Center <span class="sub">· Systemtest, Ladetest, Push-Test Preisabfrage</span></summary>
        <div class="grid">
          <div class="card wide"><h2>Systemtest</h2>
            <p class="sub">Prüft Wallbox, CP-Relais, Fahrzeugdaten, Befehlsweg, Push und Strompreis – ohne etwas zu schalten und ohne das Auto zu wecken.</p>
            <div class="actions"><button class="act primary" data-action="system-check">Systemtest starten</button>
              <button class="act" data-action="system-check" data-push="1">… mit Test-Push</button></div>
            ${check ? `<div class="checks">${checkRows}</div><div class="hint">Stand ${dateTime(check.at)}</div>` : ""}</div>
          ${this._chargeTestCard(s)}
          ${this._pricePushCard(s)}
        </div>
      </details>
    </div>`;
  }
}

if (!customElements.get("ev-pilot-panel")) {
  customElements.define("ev-pilot-panel", EvPilotPanel);
}
