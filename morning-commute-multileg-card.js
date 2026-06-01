// Morning Commute Multileg Card v1.1.0
// Per-train leg 2: Farringdon → City Thameslink (southbound Thameslink)

const CARD_VERSION = '1.1.0';

const STATUS_CONFIG = {
  on_time:     { color: '#4caf50', icon: '✓', label: 'On time' },
  minor_delay: { color: '#ff9800', icon: '⚠', label: 'Minor delay' },
  delayed:     { color: '#f44336', icon: '⚠', label: 'Delayed' },
  cancelled:   { color: '#d32f2f', icon: '✕', label: 'Cancelled' },
  no_service:  { color: '#9e9e9e', icon: '–', label: 'No service' },
  expected:    { color: '#2196f3', icon: '~', label: 'Expected' },
};

function getStatusCfg(state, delayMins) {
  if (!state) return STATUS_CONFIG.no_service;
  const s = state.toLowerCase();
  if (s === 'cancelled' || s === 'critical') return STATUS_CONFIG.cancelled;
  if (s === 'no service' || s === 'no trains') return STATUS_CONFIG.no_service;
  if (s.includes('expected')) return STATUS_CONFIG.expected;
  if (delayMins >= 10) return STATUS_CONFIG.delayed;
  if (delayMins >= 3)  return STATUS_CONFIG.minor_delay;
  return STATUS_CONFIG.on_time;
}

class MorningCommuteMultilegCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
  }

  static getStubConfig() {
    return {
      entity: 'sensor.morning_commute_summary',
      title: 'Morning Commute',
      show_platform: true,
      show_operator: true,
      show_calling_points: true,
      show_journey_time: true,
      show_last_updated: true,
      show_leg2: true,
      compact_height: false,
    };
  }

  setConfig(config) {
    if (!config.entity) throw new Error('entity is required');
    this._config = {
      title: 'Morning Commute',
      show_header: true,
      show_route: true,
      show_platform: true,
      show_operator: true,
      show_calling_points: false,
      show_delay_reason: true,
      show_journey_time: false,
      show_last_updated: false,
      show_leg2: true,
      max_calling_points: 3,
      compact_height: false,
      font_size: 'medium',
      hide_on_time_trains: false,
      min_delay_to_show: 0,
      ...config,
    };
  }

  set hass(hass) { this._hass = hass; this._render(); }
  getCardSize() { return 7; }

  // ── DATA ────────────────────────────────────────────────────────────

  _summaryAttrs() {
    const s = this._hass.states[this._config.entity];
    return s ? s.attributes : null;
  }

  _trainData(n) {
    // Prefer morning_commute_train_N (has leg2 attrs), fall back to source
    const mc = this._hass.states[`sensor.morning_commute_train_${n}`];
    if (mc) return mc.attributes ? { state: mc.state, ...mc.attributes } : null;
    const tf = this._hass.states[`sensor.twyford_to_farringdon_train_${n}`];
    if (tf) return tf.attributes ? { state: tf.state, ...tf.attributes } : null;
    return null;
  }

  _trains() {
    const summary = this._summaryAttrs();
    // If all_trains is populated use it but supplement with per-sensor leg2 data
    const trains = [];
    for (let i = 1; i <= 10; i++) {
      const t = this._trainData(i);
      if (!t) break;
      const s = (t.state || t.status || '').toLowerCase();
      if (s === 'no service' || s === 'unavailable' || s === 'unknown') break;
      trains.push({ ...t, train_number: i });
    }
    return trains;
  }

  // ── STYLES ──────────────────────────────────────────────────────────

  _styles() {
    const fs = { small: '12px', medium: '14px', large: '16px' }[this._config.font_size] || '14px';
    const rp = this._config.compact_height ? '8px 16px' : '11px 16px';
    return `
      :host { display: block; }
      ha-card { overflow: hidden; font-family: var(--paper-font-body1_-_font-family,'Roboto',sans-serif); font-size: ${fs}; }

      /* Header */
      .card-header { display:flex; align-items:center; padding:11px 16px 6px; border-bottom:1px solid var(--divider-color,#e0e0e0); gap:9px; }
      .card-title  { font-size:15px; font-weight:600; color:var(--primary-text-color); }
      .card-route  { font-size:11px; color:var(--secondary-text-color); margin-top:1px; }

      /* Leg label bar */
      .leg-bar { display:flex; align-items:center; gap:6px; padding:4px 16px;
        font-size:10px; font-weight:700; letter-spacing:.5px; text-transform:uppercase;
        color:var(--secondary-text-color); background:var(--secondary-background-color,#f5f5f5);
        border-top:1px solid var(--divider-color,#e0e0e0); }
      .leg-pill { border-radius:10px; padding:1px 7px; font-size:9px; font-weight:800; color:#fff; }
      .l1 { background:var(--primary-color,#0098D4); }  /* Elizabeth line blue */
      .l2 { background:#003688; }                        /* Thameslink dark blue */

      /* Train row */
      .train-row { padding:${rp}; border-bottom:1px solid var(--divider-color,rgba(0,0,0,.07)); }
      .train-row:last-of-type { border-bottom:none; }
      .train-row:hover { background:var(--secondary-background-color,#f5f5f5); }

      /* Leg 1 top line */
      .leg1-line { display:flex; align-items:baseline; justify-content:space-between; gap:6px; }
      .dep-time { font-size:1.25em; font-weight:700; color:var(--primary-text-color); letter-spacing:-.3px; flex-shrink:0; }
      .train-meta { display:flex; align-items:center; gap:8px; flex:1; flex-wrap:wrap; }
      .platform { font-size:.82em; color:var(--secondary-text-color);
        background:var(--secondary-background-color,#f0f0f0); border-radius:4px; padding:1px 5px; }
      .platform.changed { color:#ff9800; border:1px solid #ff9800; }
      .status-badge { font-size:.8em; font-weight:600; display:flex; align-items:center; gap:2px; flex-shrink:0; }
      .train-sub { font-size:.78em; color:var(--secondary-text-color); margin-top:2px; }
      .calling-pts { font-size:.76em; color:var(--secondary-text-color); margin-top:1px; }
      .delay-reason { font-size:.76em; color:#f44336; margin-top:1px; font-style:italic; }

      /* Leg 2 connection block — sits inside each train row */
      .leg2-block {
        margin-top:7px;
        padding:6px 10px;
        background:rgba(0,54,136,.06);
        border-left:3px solid #003688;
        border-radius:0 4px 4px 0;
        display:flex; align-items:center; justify-content:space-between; gap:8px;
      }
      .leg2-block.estimated { border-color:#ff9800; background:rgba(255,152,0,.06); }
      .leg2-left { flex:1; min-width:0; }
      .leg2-icon { font-size:.75em; color:#003688; font-weight:700; text-transform:uppercase;
        letter-spacing:.4px; margin-bottom:2px; display:flex; align-items:center; gap:4px; }
      .leg2-icon.estimated { color:#ff9800; }
      .leg2-time { font-size:1.1em; font-weight:700; color:#003688; }
      .leg2-time.estimated { color:#ff9800; }
      .leg2-dest { font-size:.78em; color:var(--secondary-text-color); margin-top:1px;
        overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      .leg2-wait { font-size:.75em; color:var(--secondary-text-color); text-align:right; flex-shrink:0; }
      .leg2-no-data { font-size:.76em; color:var(--secondary-text-color); font-style:italic; }

      /* Footer */
      .card-footer { padding:5px 16px; font-size:.74em; color:var(--secondary-text-color);
        border-top:1px solid var(--divider-color,rgba(0,0,0,.08));
        display:flex; justify-content:space-between; }
      .no-trains { padding:18px 16px; text-align:center; color:var(--secondary-text-color); }
    `;
  }

  // ── RENDER ONE TRAIN ROW ─────────────────────────────────────────────

  _renderTrainRow(train) {
    const cfg = this._config;
    const delay = parseInt(train.delay_minutes || 0, 10);
    const sc = getStatusCfg(train.state || train.status, delay);
    const dep = train.departure_time || train.scheduled_departure || '--:--';

    // Journey time leg 1
    let journeyMins = null;
    if (cfg.show_journey_time && train.scheduled_arrival && dep !== '--:--') {
      try {
        const [dh, dm] = dep.split(':').map(Number);
        const [ah, am] = train.scheduled_arrival.split(':').map(Number);
        journeyMins = (ah * 60 + am) - (dh * 60 + dm);
      } catch { /* ignore */ }
    }

    const platHtml = cfg.show_platform && train.platform
      ? `<span class="platform${train.platform_changed ? ' changed' : ''}">Plat ${train.platform}${train.platform_changed ? ' ↻' : ''}</span>` : '';

    const jHtml = journeyMins > 0
      ? `<span style="font-size:.76em;color:var(--secondary-text-color)">60 mins</span>` : '';

    const callHtml = cfg.show_calling_points && train.calling_points?.length
      ? `<div class="calling-pts">Calling at: ${train.calling_points.slice(0, cfg.max_calling_points).join(', ')}${train.calling_points.length > cfg.max_calling_points ? ` +${train.calling_points.length - cfg.max_calling_points} more` : ''}</div>` : '';

    const delayHtml = cfg.show_delay_reason && train.delay_reason
      ? `<div class="delay-reason">⚠ ${train.delay_reason}</div>` : '';
    const cancelHtml = cfg.show_delay_reason && train.cancellation_reason
      ? `<div class="delay-reason">✕ ${train.cancellation_reason}</div>` : '';

    const operatorHtml = cfg.show_operator && train.operator
      ? `<span>${train.operator}</span>` : '';

    // ── Leg 2 connection for THIS train ──
    const leg2Html = cfg.show_leg2 ? this._renderLeg2Block(train) : '';

    return `<div class="train-row">
      <div class="leg1-line">
        <span class="dep-time">${dep}</span>
        <div class="train-meta">${platHtml}${jHtml}</div>
        <span class="status-badge" style="color:${sc.color}">${sc.icon} ${delay > 0 ? `+${delay}m` : sc.label}</span>
      </div>
      <div class="train-sub">${operatorHtml}</div>
      ${callHtml}${delayHtml}${cancelHtml}
      ${leg2Html}
    </div>`;
  }

  _renderLeg2Block(train) {
    const earliest = train.leg2_earliest_after_arrival;
    const dest = train.leg2_earliest_destination;
    const waitMins = train.leg2_connection_mins;
    const walkMins = train.leg2_walk_mins || 5;
    const arr = train.scheduled_arrival;

    // If cancelled, no point showing connection
    if (train.is_cancelled) {
      return `<div class="leg2-block" style="border-color:#d32f2f;background:rgba(211,47,47,.05)">
        <div class="leg2-left"><div class="leg2-icon" style="color:#d32f2f">🚂 City Thameslink · Southbound</div>
        <div class="leg2-no-data">No connection — train cancelled</div></div></div>`;
    }

    if (!arr) {
      return `<div class="leg2-block">
        <div class="leg2-left"><div class="leg2-icon">🚂 City Thameslink · Southbound</div>
        <div class="leg2-no-data">Arrival time not yet available</div></div></div>`;
    }

    const isEstimated = earliest && earliest.startsWith('~');

    if (!earliest) {
      return `<div class="leg2-block">
        <div class="leg2-left">
          <div class="leg2-icon">🚂 City Thameslink · Southbound</div>
          <div class="leg2-no-data">Connection data not available</div>
        </div>
      </div>`;
    }

    // Parse time from "HH:MM → Destination" or "~HH:MM → Destination (est.)"
    const cleanEarliest = earliest.replace(/^~/, '');
    const [connTime, ...destParts] = cleanEarliest.split(' → ');
    const connDest = destParts.join(' → ').replace(' (est.)', '');

    const waitHtml = waitMins !== null && waitMins !== undefined
      ? `<div class="leg2-wait">${walkMins}m walk<br>${waitMins}m wait</div>`
      : `<div class="leg2-wait">${walkMins}m walk</div>`;

    return `<div class="leg2-block${isEstimated ? ' estimated' : ''}">
      <div class="leg2-left">
        <div class="leg2-icon${isEstimated ? ' estimated' : ''}">
          🚂 City Thameslink · Southbound${isEstimated ? ' · estimated' : ''}
        </div>
        <div class="leg2-time${isEstimated ? ' estimated' : ''}">${connTime}</div>
        <div class="leg2-dest">→ ${connDest}</div>
      </div>
      ${waitHtml}
    </div>`;
  }

  // ── MAIN RENDER ──────────────────────────────────────────────────────

  _render() {
    if (!this._hass || !this._config.entity) return;

    const attrs = this._summaryAttrs();
    const trains = this._trains();
    const cfg = this._config;

    const origin = attrs?.origin_name || 'Twyford';
    const dest = attrs?.destination_name || 'Farringdon';
    const lastUpdated = attrs?.last_updated
      ? new Date(attrs.last_updated).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
      : null;

    const visible = trains.filter(t => {
      if (cfg.hide_on_time_trains && !t.is_cancelled && parseInt(t.delay_minutes || 0, 10) === 0) return false;
      if (cfg.min_delay_to_show && parseInt(t.delay_minutes || 0, 10) < cfg.min_delay_to_show) return false;
      return true;
    });

    const headerHtml = cfg.show_header ? `
      <div class="card-header">
        <span style="font-size:20px">🚆</span>
        <div>
          <div class="card-title">${cfg.title}</div>
          ${cfg.show_route ? `<div class="card-route">${origin} → Farringdon → City Thameslink (southbound)</div>` : ''}
        </div>
      </div>` : '';

    const legBar = `<div class="leg-bar">
      <span class="leg-pill l1">LEG 1</span>${origin} → ${dest} · Elizabeth line
    </div>`;

    const trainRows = visible.length
      ? visible.map(t => this._renderTrainRow(t)).join('')
      : `<div class="no-trains">No trains found</div>`;

    const footer = cfg.show_last_updated && lastUpdated
      ? `<div class="card-footer"><span>Last updated: ${lastUpdated}</span><span>🚉</span></div>` : '';

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card>
        ${headerHtml}
        ${legBar}
        ${trainRows}
        ${footer}
      </ha-card>`;
  }
}

customElements.define('morning-commute-multileg-card', MorningCommuteMultilegCard);
window.customCards = (window.customCards || []).filter(c => c.type !== 'morning-commute-multileg-card');
window.customCards.push({
  type: 'morning-commute-multileg-card',
  name: 'Morning Commute Multileg Card',
  description: 'Twyford → Farringdon (Elizabeth line) + City Thameslink southbound connection per train',
  preview: true,
});
console.info(
  '%c MORNING-COMMUTE-MULTILEG-CARD %c v' + CARD_VERSION + ' ',
  'background:#003688;color:#fff;font-weight:700;padding:2px 4px;border-radius:3px 0 0 3px',
  'background:#0098D4;color:#fff;font-weight:700;padding:2px 4px;border-radius:0 3px 3px 0'
);
