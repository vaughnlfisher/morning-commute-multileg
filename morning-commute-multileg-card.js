// Morning Commute Multileg Card v1.0.0
// Matches my-rail-commute-card design + adds Leg 2 (Farringdon → City Thameslink)
// Entity: sensor.morning_commute_summary (from morning_commute_multileg integration)

const CARD_VERSION = '1.0.0';

const STATUS_CONFIG = {
  on_time:     { color: '#4caf50', icon: '✓', label: 'On time' },
  minor_delay: { color: '#ff9800', icon: '⚠', label: 'Minor delay' },
  delayed:     { color: '#f44336', icon: '⚠', label: 'Delayed' },
  cancelled:   { color: '#d32f2f', icon: '✕', label: 'Cancelled' },
  no_service:  { color: '#9e9e9e', icon: '–', label: 'No service' },
  expected:    { color: '#2196f3', icon: '~', label: 'Expected' },
};

function getStatusConfig(state, delayMins) {
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
      view: 'full',
      show_platform: true,
      show_operator: true,
      show_calling_points: true,
      show_last_updated: true,
      show_journey_time: true,
      show_leg2: true,
      compact_height: false,
    };
  }

  setConfig(config) {
    if (!config.entity) throw new Error('entity is required');
    this._config = {
      title: 'Morning Commute',
      view: 'full',
      show_header: true,
      show_route: true,
      show_platform: true,
      show_operator: true,
      show_calling_points: false,
      show_delay_reason: true,
      show_journey_time: false,
      show_last_updated: false,
      show_leg2: true,
      show_leg2_departures: true,
      max_calling_points: 3,
      compact_height: false,
      font_size: 'medium',
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 6; }

  // ── DATA HELPERS ────────────────────────────────────────────────────

  _summaryState() {
    const s = this._hass.states[this._config.entity];
    return s ? { state: s.state, attrs: s.attributes } : null;
  }

  _trainState(n) {
    // Try morning_commute_train_N first, fall back to twyford_to_farringdon_train_N
    const mc = this._hass.states[`sensor.morning_commute_train_${n}`];
    if (mc) return { state: mc.state, attrs: mc.attributes };
    const tf = this._hass.states[`sensor.twyford_to_farringdon_train_${n}`];
    if (tf) return { state: tf.state, attrs: tf.attributes };
    return null;
  }

  _trains() {
    const summary = this._summaryState();
    if (!summary) return [];
    // Prefer all_trains attribute (pre-assembled by integration)
    if (summary.attrs.all_trains && Array.isArray(summary.attrs.all_trains)) {
      return summary.attrs.all_trains;
    }
    // Fall back: read individual train sensors
    const trains = [];
    for (let i = 1; i <= 10; i++) {
      const t = this._trainState(i);
      if (!t || t.state === 'No service' || t.state === 'unavailable') break;
      trains.push({ ...t.attrs, state: t.state, train_number: i });
    }
    return trains;
  }

  _leg2() {
    // Leg2 data is on the summary sensor attrs (from morning_commute_multileg)
    const summary = this._summaryState();
    if (!summary) return null;
    const a = summary.attrs;
    if (!a.leg2_station) return null;
    return {
      station: a.leg2_station || 'City Thameslink',
      walk_mins: a.leg2_walk_mins || 5,
      next_departure: a.leg2_next_departure,
      next_destination: a.leg2_next_destination,
      northbound: a.leg2_northbound_departures || [],
      earliest: a.leg2_earliest_after_arrival,
    };
  }

  // ── STYLES ──────────────────────────────────────────────────────────

  _styles() {
    const fs = { small: '12px', medium: '14px', large: '16px' }[this._config.font_size] || '14px';
    const rowPad = this._config.compact_height ? '8px 16px' : '12px 16px';
    return `
      :host { display: block; }
      ha-card {
        overflow: hidden;
        font-family: var(--paper-font-body1_-_font-family, 'Roboto', sans-serif);
        font-size: ${fs};
      }
      /* ── HEADER ── */
      .card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 16px 4px;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
      }
      .header-left { display: flex; align-items: center; gap: 8px; }
      .header-icon { color: var(--primary-color, #03a9f4); font-size: 20px; }
      .card-title { font-size: 16px; font-weight: 600; color: var(--primary-text-color); }
      .card-route { font-size: 12px; color: var(--secondary-text-color); margin-top: 1px; }
      /* ── LEG LABEL ── */
      .leg-label {
        display: flex; align-items: center; gap: 6px;
        padding: 6px 16px 4px;
        font-size: 11px; font-weight: 700; letter-spacing: .6px;
        text-transform: uppercase; color: var(--secondary-text-color);
        background: var(--secondary-background-color, #f5f5f5);
        border-top: 1px solid var(--divider-color, #e0e0e0);
      }
      .leg-label.leg2 { color: #6950A1; }
      .leg-pill {
        background: var(--primary-color, #03a9f4);
        color: #fff; border-radius: 10px;
        padding: 1px 7px; font-size: 10px; font-weight: 700;
      }
      .leg-pill.p2 { background: #6950A1; }
      /* ── TRAIN ROW ── */
      .train-row {
        padding: ${rowPad};
        border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.08));
        transition: background .15s;
      }
      .train-row:last-of-type { border-bottom: none; }
      .train-row:hover { background: var(--secondary-background-color, #f5f5f5); }
      .train-top {
        display: flex; align-items: baseline;
        justify-content: space-between; gap: 8px;
        margin-bottom: 3px;
      }
      .departure-time {
        font-size: 1.3em; font-weight: 700;
        color: var(--primary-text-color);
        letter-spacing: -.3px; flex-shrink: 0;
      }
      .train-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; flex: 1; }
      .platform {
        font-size: .85em; color: var(--secondary-text-color);
        background: var(--secondary-background-color, #f0f0f0);
        border-radius: 4px; padding: 1px 6px;
      }
      .platform.changed { color: #ff9800; border: 1px solid #ff9800; }
      .status-badge {
        font-size: .82em; font-weight: 600;
        display: flex; align-items: center; gap: 3px;
        flex-shrink: 0;
      }
      .train-detail {
        font-size: .82em; color: var(--secondary-text-color);
        margin-top: 2px; line-height: 1.5;
      }
      .calling-pts { font-size: .78em; color: var(--secondary-text-color); margin-top: 2px; }
      .delay-reason { font-size: .78em; color: #f44336; margin-top: 2px; font-style: italic; }
      .journey-time { font-size: .78em; color: var(--secondary-text-color); }
      /* ── LEG 2 SECTION ── */
      .leg2-section { padding: ${rowPad}; }
      .leg2-connection {
        display: flex; align-items: center; justify-content: space-between;
        gap: 8px; margin-bottom: 8px;
      }
      .leg2-earliest {
        font-size: 1.1em; font-weight: 700;
        color: #6950A1;
      }
      .leg2-dest { font-size: .85em; color: var(--secondary-text-color); }
      .leg2-walk {
        font-size: .78em; color: var(--secondary-text-color);
        display: flex; align-items: center; gap: 4px;
      }
      .leg2-departures { margin-top: 6px; }
      .leg2-dep-row {
        display: flex; align-items: center; gap: 8px;
        padding: 3px 0;
        border-bottom: 1px dashed var(--divider-color, rgba(0,0,0,.08));
        font-size: .82em; color: var(--secondary-text-color);
      }
      .leg2-dep-row:last-child { border-bottom: none; }
      .leg2-dep-time { font-weight: 600; color: var(--primary-text-color); flex-shrink: 0; width: 42px; }
      .leg2-dep-dest { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .leg2-dep-first { color: #6950A1; font-weight: 700; }
      .no-trains {
        padding: 20px 16px; text-align: center;
        color: var(--secondary-text-color); font-size: .9em;
      }
      /* ── FOOTER ── */
      .card-footer {
        padding: 6px 16px; font-size: .75em;
        color: var(--secondary-text-color);
        border-top: 1px solid var(--divider-color, rgba(0,0,0,.08));
        display: flex; justify-content: space-between; align-items: center;
      }
      /* ── DIVIDER ── */
      .walk-divider {
        display: flex; align-items: center; gap: 8px;
        padding: 6px 16px;
        background: var(--secondary-background-color, #f5f5f5);
        border-top: 1px dashed var(--divider-color);
        font-size: .78em; color: var(--secondary-text-color);
      }
      .walk-line { flex: 1; border-top: 2px dashed var(--divider-color); }
    `;
  }

  // ── RENDER HELPERS ──────────────────────────────────────────────────

  _renderTrainRow(train, isFirst) {
    const cfg = this._config;
    const delay = parseInt(train.delay_minutes || 0, 10);
    const sc = getStatusConfig(train.state || train.status, delay);
    const dep = train.departure_time || train.scheduled_departure || '--:--';
    const platChanged = train.platform_changed;
    const plat = train.platform;
    const operator = train.operator || '';
    const calling = train.calling_points || [];
    const journeyMins = train.scheduled_arrival && dep !== '--:--' ? (() => {
      try {
        const [dh, dm] = dep.split(':').map(Number);
        const [ah, am] = (train.scheduled_arrival || '').split(':').map(Number);
        return (ah * 60 + am) - (dh * 60 + dm);
      } catch { return null; }
    })() : null;

    const platHtml = cfg.show_platform && plat
      ? `<span class="platform ${platChanged ? 'changed' : ''}">Platform ${plat}${platChanged ? ' ⟳' : ''}</span>`
      : '';

    const callingHtml = cfg.show_calling_points && calling.length
      ? `<div class="calling-pts">Calling at: ${calling.slice(0, cfg.max_calling_points).join(', ')}${calling.length > cfg.max_calling_points ? ` +${calling.length - cfg.max_calling_points} more` : ''}</div>`
      : '';

    const delayHtml = cfg.show_delay_reason && train.delay_reason
      ? `<div class="delay-reason">⚠ ${train.delay_reason}</div>`
      : '';

    const cancelHtml = cfg.show_delay_reason && train.cancellation_reason
      ? `<div class="delay-reason">✕ ${train.cancellation_reason}</div>`
      : '';

    const journeyHtml = cfg.show_journey_time && journeyMins && journeyMins > 0
      ? `<span class="journey-time">Journey time: ${journeyMins} mins</span>`
      : '';

    const delayLabel = delay > 0 ? `+${delay} min` : '';

    return `
      <div class="train-row">
        <div class="train-top">
          <span class="departure-time">${dep}</span>
          <div class="train-meta">
            ${platHtml}
            ${journeyHtml}
          </div>
          <span class="status-badge" style="color:${sc.color}">
            ${sc.icon} ${delay > 0 ? delayLabel : sc.label}
          </span>
        </div>
        <div class="train-detail">
          ${cfg.show_operator && operator ? `<span>${operator}</span>` : ''}
        </div>
        ${callingHtml}
        ${delayHtml}
        ${cancelHtml}
      </div>`;
  }

  _renderLeg2(leg2) {
    if (!leg2 || !this._config.show_leg2) return '';

    // Parse northbound departures: "HH:MM → Destination"
    const deps = (leg2.northbound && leg2.northbound.length)
      ? leg2.northbound
      : (leg2.next_departure ? [`${leg2.next_departure} → ${leg2.next_destination || ''}`] : []);

    const connTime = leg2.earliest
      ? leg2.earliest.split(' → ')[0]
      : (leg2.next_departure || '--:--');
    const connDest = leg2.earliest
      ? leg2.earliest.split(' → ').slice(1).join(' → ')
      : (leg2.next_destination || '');

    const depsHtml = this._config.show_leg2_departures && deps.length
      ? `<div class="leg2-departures">
          ${deps.map((d, i) => {
            const [t, ...rest] = d.split(' → ');
            return `<div class="leg2-dep-row ${i === 0 ? 'leg2-dep-first' : ''}">
              <span class="leg2-dep-time">${t}</span>
              <span class="leg2-dep-dest">${rest.join(' → ')}</span>
            </div>`;
          }).join('')}
        </div>`
      : '';

    return `
      <div class="leg-label leg2">
        <span class="leg-pill p2">LEG 2</span>
        ${leg2.station} · Thameslink
      </div>
      <div class="leg2-section">
        <div class="leg2-connection">
          <div>
            <div class="leg2-earliest" style="color:#6950A1">${connTime}</div>
            <div class="leg2-dest">${connDest}</div>
          </div>
          <div class="leg2-walk">
            🚶 ${leg2.walk_mins} min walk from Farringdon
          </div>
        </div>
        ${depsHtml}
      </div>`;
  }

  // ── MAIN RENDER ─────────────────────────────────────────────────────

  _render() {
    if (!this._hass || !this._config.entity) return;

    const summary = this._summaryState();
    const trains = this._trains();
    const leg2 = this._leg2();
    const cfg = this._config;

    const origin = summary?.attrs?.origin_name || 'Twyford';
    const dest = summary?.attrs?.destination_name || 'Farringdon';
    const lastUpdated = summary?.attrs?.last_updated
      ? new Date(summary.attrs.last_updated).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
      : null;

    // Filter trains
    const visibleTrains = trains.filter(t => {
      const s = (t.state || t.status || '').toLowerCase();
      if (s === 'no service' || s === 'unavailable') return false;
      if (cfg.hide_on_time_trains && !t.is_cancelled && (parseInt(t.delay_minutes || 0, 10) === 0)) return false;
      if (cfg.min_delay_to_show && parseInt(t.delay_minutes || 0, 10) < cfg.min_delay_to_show) return false;
      return true;
    });

    const headerHtml = cfg.show_header ? `
      <div class="card-header">
        <div class="header-left">
          <span class="header-icon">🚆</span>
          <div>
            <div class="card-title">${cfg.title}</div>
            ${cfg.show_route ? `<div class="card-route">${origin} → ${dest}</div>` : ''}
          </div>
        </div>
      </div>` : '';

    const leg1Label = `
      <div class="leg-label">
        <span class="leg-pill">LEG 1</span>
        ${origin} → ${dest} · Elizabeth line
      </div>`;

    const trainRowsHtml = visibleTrains.length
      ? visibleTrains.map((t, i) => this._renderTrainRow(t, i === 0)).join('')
      : `<div class="no-trains">No trains found</div>`;

    const walkDividerHtml = leg2 && cfg.show_leg2
      ? `<div class="walk-divider">
          <span class="walk-line"></span>
          🚶 ${leg2.walk_mins} min walk → Farringdon → City Thameslink
          <span class="walk-line"></span>
        </div>`
      : '';

    const footerHtml = cfg.show_last_updated && lastUpdated
      ? `<div class="card-footer">
          <span>Last updated: ${lastUpdated}</span>
          <span style="font-size:1.2em">🚉</span>
        </div>`
      : '';

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card>
        ${headerHtml}
        ${leg1Label}
        ${trainRowsHtml}
        ${walkDividerHtml}
        ${this._renderLeg2(leg2)}
        ${footerHtml}
      </ha-card>`;
  }
}

// ── EDITOR ──────────────────────────────────────────────────────────────

class MorningCommuteMultilegCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; }
  set hass(h) { this._hass = h; }
  get _schema() {
    return [
      { name: 'entity',             selector: { entity: { domain: 'sensor' } } },
      { name: 'title',              selector: { text: {} } },
      { name: 'view',               selector: { select: { options: ['full','compact','next-only','board'] } } },
      { name: 'show_platform',      selector: { boolean: {} } },
      { name: 'show_operator',      selector: { boolean: {} } },
      { name: 'show_calling_points',selector: { boolean: {} } },
      { name: 'show_journey_time',  selector: { boolean: {} } },
      { name: 'show_last_updated',  selector: { boolean: {} } },
      { name: 'show_leg2',          selector: { boolean: {} } },
      { name: 'show_leg2_departures',selector: { boolean: {} } },
      { name: 'compact_height',     selector: { boolean: {} } },
    ];
  }
}

customElements.define('morning-commute-multileg-card', MorningCommuteMultilegCard);
customElements.define('morning-commute-multileg-card-editor', MorningCommuteMultilegCardEditor);

window.customCards = window.customCards || [];
window.customCards = window.customCards.filter(c => c.type !== 'morning-commute-multileg-card');
window.customCards.push({
  type: 'morning-commute-multileg-card',
  name: 'Morning Commute Multileg Card',
  description: 'Twyford → Farringdon (Elizabeth line) + City Thameslink leg with connection times',
  preview: true,
});

console.info(`%c MORNING-COMMUTE-MULTILEG-CARD %c v${CARD_VERSION} `, 
  'background:#6950A1;color:#fff;font-weight:700;padding:2px 4px;border-radius:3px 0 0 3px',
  'background:#003688;color:#fff;font-weight:700;padding:2px 4px;border-radius:0 3px 3px 0');
