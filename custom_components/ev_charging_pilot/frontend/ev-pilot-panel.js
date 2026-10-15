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
const SEASON_LABELS = { winter: "Winter", spring: "Frühling", summer: "Sommer", autumn: "Herbst" };

const socColor = (soc) =>
  soc === null ? "var(--disabled-text-color, #888)"
    : soc < 20 ? "var(--error-color, #db4437)"
    : soc < 50 ? "var(--warning-color, #ffa600)"
    : "var(--success-color, #43a047)";

/** Battery with SOC fill, plug and wallbox – shown below the photo (or alone without one). */
function batterySvg({ plugged, charging, error, soc, kw }) {
  const led = error ? "var(--error-color, #db4437)" : charging ? "var(--success-color, #43a047)"
    : plugged ? "var(--info-color, #039be5)" : "var(--disabled-text-color, #777)";
  const fill = soc === null ? 0 : Math.max(0, Math.min(100, soc));
  const w = 212 * fill / 100;
  return `
  <svg class="battery" viewBox="0 0 380 110" role="img" aria-label="Akku ${soc === null ? "unbekannt" : Math.round(soc) + " Prozent"}">
    <rect x="8" y="20" width="230" height="70" rx="14" fill="none" stroke="var(--primary-text-color)" stroke-width="5" opacity=".85"/>
    <rect x="240" y="42" width="12" height="26" rx="4" fill="var(--primary-text-color)" opacity=".85"/>
    ${w > 0 ? `<rect x="17" y="29" width="${w.toFixed(1)}" height="52" rx="8" fill="${socColor(soc)}" class="${charging ? "pulse-soft" : ""}"/>` : ""}
    <text x="123" y="64" text-anchor="middle" class="batt">${soc === null ? "– %" : Math.round(soc) + " %"}</text>
    ${charging ? `<path d="M46 34 L32 58 L44 58 L38 78 L56 50 L44 50 L50 34 Z" fill="#ffd600" stroke="rgba(0,0,0,.4)" opacity=".9"/>` : ""}
    <!-- cable to the wallbox -->
    ${plugged ? `<path d="M252 55 C290 55 290 55 326 55" fill="none" stroke="var(--secondary-text-color)" stroke-width="5" stroke-linecap="round"/>
      ${charging ? `<path d="M252 55 L326 55" fill="none" stroke="var(--success-color, #43a047)" stroke-width="3" stroke-dasharray="3 9" stroke-linecap="round" class="flow"/>` : ""}`
      : `<path d="M300 55 L326 55" fill="none" stroke="var(--secondary-text-color)" stroke-width="5" stroke-linecap="round" opacity=".5"/>`}
    <rect x="326" y="18" width="40" height="74" rx="9" fill="#2a2f36" stroke="#4a5260"/>
    <circle cx="346" cy="45" r="11" fill="none" stroke="${led}" stroke-width="3.5" class="${charging ? "pulse" : ""}"/>
    ${charging ? `<text x="346" y="80" text-anchor="middle" class="kwsmall">${num(kw, 1)} kW</text>` : ""}
  </svg>`;
}

/** Circular SOC gauge with markers for minimum and preferred SOC. */
function socRing(soc, min, pref) {
  const r = 52, c = 2 * Math.PI * r;
  const val = soc === null ? 0 : Math.max(0, Math.min(100, soc));
  const marker = (pct, color) => {
    const a = (pct / 100) * 2 * Math.PI - Math.PI / 2;
    const x1 = 70 + Math.cos(a) * (r - 11), y1 = 70 + Math.sin(a) * (r - 11);
    const x2 = 70 + Math.cos(a) * (r + 11), y2 = 70 + Math.sin(a) * (r + 11);
    return `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${color}" stroke-width="3" stroke-linecap="round"/>`;
  };
  return `<svg viewBox="0 0 140 140" class="gauge" role="img" aria-label="Ladestand">
    <circle cx="70" cy="70" r="${r}" fill="none" stroke="var(--divider-color, #444)" stroke-width="12"/>
    ${val > 0 ? `<circle cx="70" cy="70" r="${r}" fill="none" stroke="${socColor(soc)}" stroke-width="12" stroke-linecap="round"
      stroke-dasharray="${(c * val / 100).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 70 70)"/>` : ""}
    ${min ? marker(min, "var(--warning-color, #ffa600)") : ""}
    ${pref ? marker(pref, "var(--primary-color, #03a9f4)") : ""}
    <text x="70" y="72" text-anchor="middle" class="gbig">${soc === null ? "–" : Math.round(soc)}<tspan class="gunit">${soc === null ? "" : "%"}</tspan></text>
    <text x="70" y="94" text-anchor="middle" class="gsub">${soc === null ? "kein SOC" : "Ladestand"}</text>
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
  const blocks = w ? (w.blocks.length ? w.blocks : [[w.start, w.departure]]) : [];
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
  return `<svg viewBox="0 0 ${W} 112" class="timeline" role="img" aria-label="Ladeplan der Nacht">
    <line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}" stroke="var(--divider-color)"/>
    ${priceArea}${charge}${ticks.join("")}
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
  .hero { display: grid; grid-template-columns: minmax(0, 2.2fr) minmax(0, 1fr) minmax(0, 1fr); gap: 12px; align-items: center; }
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
  .batt { font-size: 22px; font-weight: 600; fill: #fff; paint-order: stroke; stroke: rgba(0,0,0,.35); stroke-width: 3px; }
  .kwsmall { font-size: 11px; font-weight: 600; fill: var(--success-color, #43a047); }
  .hint { font-size: 12px; color: var(--secondary-text-color); }
  input[type=range] { width: 100%; padding: 0; accent-color: var(--primary-color); }
  .slider { display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; align-items: center; margin: 8px 0; }
  .slider b { min-width: 48px; text-align: right; }
  .setgroup { margin-bottom: 4px; }
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
  @media (max-width: 760px) { .hero { grid-template-columns: 1fr 1fr; } .hero .carcol { grid-column: 1 / -1; } }
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
    await this._loadPhoto();
    await this._loadView();
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
        c.events = await this._ws("get_events", { limit: 200, ...(this._eventFilter ? { category: this._eventFilter } : {}) });
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
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <header>
        <button class="menu" data-menu title="Menü">☰</button>
        <h1>${esc(s ? s.name : "EV Charging Pilot")}${this._version() ? `<span class="version">v${esc(this._version())}</span>` : ""}</h1>
        ${modeLabel ? `<span class="badge ${mode === "live" ? "live" : ""}">${modeLabel}</span>` : ""}
      </header>
      <nav>${VIEWS.map(([id, label]) => `<button data-view="${id}" class="${this._view === id ? "active" : ""}">${id === "home" && s ? `Hausstrom → ${esc(s.vehicle_name)}` : label}</button>`).join("")}</nav>
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
    root.querySelectorAll('input[type=range][data-action="target"]').forEach((el) =>
      el.addEventListener("input", () => { el.closest(".slider").querySelector("b").textContent = `${el.value} %`; }));
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
      case "target":
        this._targetDraft = { ...(this._targetDraft || {}),
          [el.dataset.field]: el.type === "range" ? Number(el.value) : el.value };
        this._render(true); break;
      case "target-save":
        this._saveTarget(); break;
      case "setting":
        this._settingsDraft = { ...(this._settingsDraft || {}), [el.dataset.key]:
          el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value };
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

  _settingsView(s) {
    const cfg = this._cache.settings;
    if (!cfg) return `<div class="card">Lade Einstellungen …</div>`;
    const draft = this._settingsDraft || {};
    const value = (key) => (key in draft ? draft[key] : cfg.values[key]);
    const admin = cfg.is_admin;
    const field = (f) => {
      const v = value(f.key);
      const help = f.help ? `<span class="help">${esc(f.help)}</span>` : "";
      const attrs = `data-action="setting" data-key="${f.key}" ${admin ? "" : "disabled"}`;
      if (f.type === "bool") {
        return `<label class="field check"><input type="checkbox" ${v ? "checked" : ""} ${attrs}>${esc(f.label)}</label>`;
      }
      let input;
      if (f.type === "select") {
        input = `<select ${attrs}>${f.options.map((o) => `<option value="${esc(o.value)}" ${o.value === v ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select>`;
      } else if (f.type === "number") {
        input = `<input type="number" min="${f.min}" max="${f.max}" step="${f.step}" value="${esc(v)}" ${attrs}>`;
      } else if (f.type === "date") {
        input = `<input type="date" value="${esc(v)}" ${attrs}>`;
      } else if (f.type === "time") {
        input = `<input type="time" value="${esc(String(v || "").slice(0, 5))}" ${attrs}>`;
      } else {
        input = `<input type="text" value="${esc(v ?? "")}" ${attrs} ${f.type === "entity" ? 'placeholder="sensor.…"' : ""}>`;
      }
      return `<label class="field">${esc(f.label)}${f.unit ? ` <span class="help">(${esc(f.unit)})</span>` : ""}${input}${help}</label>`;
    };
    const dirty = Object.keys(draft).length > 0;
    const history = (cfg.price_history || []).slice().reverse().map((p) =>
      `<tr><td>${dateOnly(p.valid_from)}</td><td class="n">${num(p.eur_per_kwh, 3, "€/kWh")}</td></tr>`).join("");
    return `<div class="grid">
      ${admin ? "" : `<div class="notice warn wide">Nur Administratoren können Einstellungen ändern.</div>`}
      <div class="card wide">
        <h2>Fahrzeugfoto</h2>
        <div class="hero" style="grid-template-columns:minmax(0,1fr) minmax(0,1fr)">
          <div>${this._photoUrl ? `<div class="photo"><img src="${this._photoUrl}" alt="Fahrzeug"></div>` : `<p class="sub">Noch kein Foto – im Cockpit erscheint dann die Akku-Grafik.</p>`}</div>
          <div>
            <p class="hint">Am schönsten: <b>Seitenansicht</b>, <b>PNG mit transparentem Hintergrund</b> (freigestellt), Querformat etwa 2:1, mindestens 1200 px breit. JPG und WebP gehen auch. Große Bilder werden beim Hochladen auf 1600 px verkleinert.</p>
            <div class="actions">
              <label class="act primary" style="cursor:pointer">Foto wählen …<input type="file" accept="image/png,image/jpeg,image/webp" data-action="photo-upload" style="display:none" ${admin ? "" : "disabled"}></label>
              ${this._photoUrl ? `<button class="act danger" data-action="photo-delete" ${admin ? "" : "disabled"}>Foto entfernen</button>` : ""}
            </div>
          </div>
        </div>
      </div>
      ${this._targetCard(s)}
      <div class="card">
        <h2>Strompreis-Historie</h2>
        <div class="scroll"><table><tr><th>gültig ab</th><th class="n">Preis</th></tr>${history}</table></div>
        <p class="hint">Neuen Preis unten unter „Strompreis“ eintragen – alte Monate bleiben unverändert.</p>
      </div>
      ${cfg.groups.map((g) => `<div class="card wide setgroup">
        <h2>${esc(g.title)}</h2>
        <div class="form">${g.fields.map(field).join("")}</div>
      </div>`).join("")}
      <div class="card wide actions" style="position:sticky;bottom:8px">
        <button class="act primary" data-action="settings-save" ${dirty && admin ? "" : "disabled"}>Speichern</button>
        <button class="act" data-action="settings-discard" ${dirty ? "" : "disabled"}>Verwerfen</button>
        <span class="hint">${dirty ? `${Object.keys(draft).length} Änderung(en) nicht gespeichert` : "Alle Einstellungen gespeichert"}</span>
      </div>
    </div>`;
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
    const maxKw = Math.min(s.settings.vehicle_charger_kw || 4.6, s.settings.max_power_kw || 11);
    const reasons = s.health.reasons.map((r) => `<p class="reason">${esc(HEALTH_TEXT[r] || r)}</p>`).join("");
    const notice = s.mode !== "live"
      ? `<div class="notice info">Modus <b>${esc(s.mode)}</b>: Die Integration protokolliert nur, was sie schalten würde. Live erst nach Messphase, Dry-Run und Einzeltest (Grundsatz 11).</div>` : "";
    const errorBox = health === "ERROR"
      ? `<div class="notice bad"><b>Automatik gesperrt.</b>${reasons}</div>` : "";
    return `${notice}${errorBox}
    <div class="grid">
      <div class="card wide">
        <div class="hero">
          <div class="col carcol">
            ${this._photoUrl ? `<div class="photo ${charging ? "charging" : ""}"><img src="${this._photoUrl}" alt="Fahrzeug"></div>` : ""}
            ${batterySvg({ plugged, charging, error: health === "ERROR" || !!ex.failure_code, soc: soc ? soc.value : null, kw })}
            ${!this._photoUrl ? `<div class="hint">Eigenes Fahrzeugfoto: Reiter „Einstellungen“</div>` : ""}
            <div class="big">${esc(STATE_LABELS[ex.state] || ex.state || "–")}</div>
            <div class="chips">
              <span class="pill ${plugged ? "info" : "muted"}">${plugged ? "eingesteckt" : "nicht eingesteckt"}</span>
              <span class="pill ${healthClass}">${esc(HEALTH_LABELS[health] || health)}</span>
              ${s.override ? `<span class="pill info">Override: ${esc(s.override.mode)}</span>` : ""}
              ${s.one_shot ? `<span class="pill info">Heute Nacht bis ${time(s.one_shot.departure_at)}</span>` : ""}
              ${!s.automation_enabled ? `<span class="pill warn">Automatik aus</span>` : ""}
              ${ex.failure_code ? `<span class="pill bad">${esc(ex.failure_code)}</span>` : ""}
            </div>
            <div class="sub">Soll: ${esc(REASON_LABELS[desired.reason] || desired.reason || "–")}
              (${desired.charger_enabled === true ? "Wallbox an" : desired.charger_enabled === false ? "Wallbox aus" : "nicht eingreifen"}) · seit ${time(ex.since)}</div>
          </div>
          <div class="col">
            ${socRing(soc ? soc.value : null, w ? w.minimum_soc_pct : null, w ? w.preferred_soc_pct : null)}
            <div class="label">${soc ? `<span class="pill ${QUALITY_CLASS[soc.quality]}">${esc(soc.quality)}</span>` : "kein Fahrzeug-SOC"}</div>
            ${w ? `<div class="label">Ziel ${w.preferred_soc_pct} % · min. ${w.minimum_soc_pct} %</div>` : ""}
          </div>
          <div class="col">
            ${powerGauge(kw, maxKw)}
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
      ${this._targetCard(s)}
      <div class="card">
        <h2>Prognose <span class="sub">(Schätzung)</span></h2>
        <div class="row"><span>Erwarteter SOC bei Abfahrt</span><b>${num(e.expected_soc_at_departure, 0, "%")}</b></div>
        <div class="row"><span>Mindest-SOC ${w ? w.minimum_soc_pct + " %" : ""}</span>${this._yesNo(e.minimum_reachable)}</div>
        <div class="row"><span>Wunsch-SOC ${w ? w.preferred_soc_pct + " %" : ""}</span>${this._yesNo(e.preferred_reachable)}</div>
        <div class="row"><span>Start</span><span>${w ? dateTime(w.start) : "–"}${w && w.fallback_without_soc ? " (fest, kein SOC)" : ""}</span></div>
        <div class="row"><span>Voraussichtlich fertig</span><span>${time(e.finish_at)}</span></div>
        <div class="row"><span>Kosten</span><span>${num(e.cost_eur, 2, "€")}</span></div>
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
          <button class="act danger" data-service="reset_error" ${ex.failure_code || health === "ERROR" ? "" : "disabled"}>Fehler zurücksetzen</button>
        </div>
      </div>
    </div>`;
  }

  _targetCard(s) {
    const p = (s.plans || [])[0];
    if (!p) return "";
    const d = this._targetDraft || {};
    const min = d.minimum_departure_soc_pct ?? p.minimum_departure_soc_pct;
    const pref = d.preferred_departure_soc_pct ?? p.preferred_departure_soc_pct;
    const dep = d.departure_time ?? p.departure_time;
    return `<div class="card">
      <h2>Ladeziel <span class="sub">· ${esc(p.name)}</span></h2>
      <div class="slider"><label>Mindest-SOC bei Abfahrt<input type="range" min="10" max="100" step="5" value="${min}" data-action="target" data-field="minimum_departure_soc_pct"></label><b>${min} %</b></div>
      <div class="slider"><label>Wunsch-SOC (Ladeziel)<input type="range" min="10" max="100" step="5" value="${pref}" data-action="target" data-field="preferred_departure_soc_pct"></label><b>${pref} %</b></div>
      <div class="slider"><label>Abfahrt<input type="time" value="${esc(dep)}" data-action="target" data-field="departure_time"></label><b></b></div>
      <div class="actions"><button class="act primary" data-action="target-save" ${this._targetDraft ? "" : "disabled"}>Übernehmen</button></div>
      <p class="hint">Gilt für den Plan „${esc(p.name)}“; weitere Pläne im Reiter Ladeplan.</p>
    </div>`;
  }

  async _saveTarget() {
    const plans = JSON.parse(JSON.stringify(this._state.plans));
    const d = this._targetDraft || {};
    if (d.minimum_departure_soc_pct > (d.preferred_departure_soc_pct ?? plans[0].preferred_departure_soc_pct)) {
      d.preferred_departure_soc_pct = d.minimum_departure_soc_pct;
    }
    Object.assign(plans[0], d);
    if (plans[0].preferred_departure_soc_pct < plans[0].minimum_departure_soc_pct) {
      plans[0].minimum_departure_soc_pct = plans[0].preferred_departure_soc_pct;
    }
    try {
      await this._ws("set_plans", { plans });
      this._targetDraft = null;
      this._toast("Ladeziel gespeichert");
      await this._refresh();
    } catch (err) {
      this._toast(`Fehler: ${err.message || err}`);
    }
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
          <label>oder €/kWh<input type="number" step="0.001" min="0" name="price_eur_kwh"></label>
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
        ${s.health.reasons.map((r) => `<p class="reason">${esc(HEALTH_TEXT[r] || r)}</p>`).join("") || `<div class="sub">keine Auffälligkeiten</div>`}</div>
      <div class="card"><h2>CP / Failsafe</h2>
        <div class="row"><span>Checkliste §3.6</span>${this._yesNo(s.settings.cp_failsafe_verified)}</div>
        <div class="row"><span>Shelly-Konfiguration</span>${this._yesNo(s.health.shelly_config_ok)}</div>
        ${shellyRows(s.health.shelly_deviations)}
        ${s.health.shelly_config_ok === null && s.health.shelly_host ? `<p class="sub">Shelly-Konfiguration nicht lesbar (Shelly offline oder passwortgeschützt).</p>` : ""}
        ${s.health.shelly_host ? `<div class="actions" style="margin-top:8px"><button class="act ${s.health.shelly_config_ok === false ? "primary" : ""}" data-action="configure-shelly">Shelly konfigurieren</button></div>` : ""}
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
    </div>`;
  }
}

if (!customElements.get("ev-pilot-panel")) {
  customElements.define("ev-pilot-panel", EvPilotPanel);
}
