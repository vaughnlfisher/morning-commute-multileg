// Morning Commute Multileg Card v1.2.0
// Layout: matches my-rail-commute-card exactly
// Each train: LEG1 row (full) + walk divider + LEG2 row (full, southbound Thameslink)
// History panel: reliability tiles + daily breakdown + best/worst

const VER = '1.2.0';
const SC = {
  on_time:    {color:'#4caf50', icon:'✓', label:'On time'},
  delayed:    {color:'#f44336', icon:'⚠', label:'Delayed'},
  minor:      {color:'#ff9800', icon:'⚠', label:'Minor delay'},
  cancelled:  {color:'#d32f2f', icon:'✕', label:'Cancelled'},
  no_service: {color:'#9e9e9e', icon:'–', label:'No service'},
  expected:   {color:'#2196f3', icon:'~', label:'Expected'},
};

function sc(state, delay) {
  if (!state) return SC.no_service;
  const s = state.toLowerCase();
  if (s==='cancelled'||s==='critical') return SC.cancelled;
  if (s==='no service'||s==='no trains') return SC.no_service;
  if (s.includes('expected')) return SC.expected;
  if (delay>=10) return SC.delayed;
  if (delay>=3)  return SC.minor;
  return SC.on_time;
}

function pct_color(p) {
  if (p===null||p===undefined) return '#555';
  if (p>=98) return '#2e7d32';
  if (p>=95) return '#4caf50';
  if (p>=90) return '#ff9800';
  if (p>=80) return '#f44336';
  return '#b71c1c';
}

function day_abbr(dateStr) {
  try {
    const d = new Date(dateStr+'T12:00:00');
    return d.toLocaleDateString('en-GB',{weekday:'short'});
  } catch { return ''; }
}

class MorningCommuteMultilegCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:'open'});
    this._config = {};
    this._hass = null;
  }

  static getStubConfig() {
    return {
      entity: 'sensor.morning_commute_summary',
      title: 'Morning Commute',
      show_platform: true, show_operator: true,
      show_calling_points: true, show_journey_time: true,
      show_last_updated: true, show_leg2: true,
      show_history_panel: true, compact_height: false,
    };
  }

  setConfig(config) {
    if (!config.entity) throw new Error('entity is required');
    this._config = {
      title: 'Morning Commute',
      show_header: true, show_route: true,
      show_platform: true, show_operator: true,
      show_calling_points: false, show_delay_reason: true,
      show_journey_time: false, show_last_updated: false,
      show_leg2: true, show_history_panel: true,
      max_calling_points: 3, compact_height: false,
      font_size: 'medium', hide_on_time_trains: false,
      min_delay_to_show: 0,
      ...config
    };
  }

  set hass(h) { this._hass = h; this._render(); }
  getCardSize() { return 8; }

  // ── DATA ─────────────────────────────────────────────────────────────

  _s(eid) {
    const s = this._hass.states[eid];
    return s ? {state: s.state, attrs: s.attributes} : null;
  }

  _prefix() {
    const mc = this._hass.states['sensor.morning_commute_train_1'];
    if (mc && mc.state !== 'unknown' && mc.state !== 'unavailable') return 'morning_commute';
    return 'twyford_to_farringdon';
  }

  _summaryAttrs() {
    const cfg = this._s(this._config.entity);
    if (cfg && cfg.state !== 'unknown' && cfg.state !== 'unavailable') return cfg.attrs;
    const fb = this._s('sensor.twyford_to_farringdon_summary');
    return fb ? fb.attrs : null;
  }

  _trainData(n) {
    const p = this._prefix();
    const s = this._hass.states[`sensor.${p}_train_${n}`];
    if (!s || s.state==='unknown'||s.state==='unavailable') return null;
    return {state: s.state, ...s.attributes};
  }

  _trains() {
    const trains = [];
    for (let i=1; i<=10; i++) {
      const t = this._trainData(i);
      if (!t) break;
      const st = (t.state||t.status||'').toLowerCase();
      if (st==='no service') break;
      trains.push({...t, train_number:i});
    }
    return trains;
  }

  _histAttrs() {
    const rel = this._hass.states[`sensor.${this._prefix()}_historical_reliability`];
    const del = this._hass.states[`sensor.${this._prefix()}_historical_delays`];
    return {
      rel: rel ? rel.attributes : null,
      del: del ? del.attributes : null,
    };
  }

  // ── STYLES ────────────────────────────────────────────────────────────

  _styles() {
    const fs = {small:'12px', medium:'14px', large:'16px'}[this._config.font_size]||'14px';
    const rp = this._config.compact_height ? '8px 16px' : '12px 16px';
    return `
      :host{display:block}
      ha-card{overflow:hidden;font-family:var(--paper-font-body1_-_font-family,'Roboto',sans-serif);font-size:${fs}}

      /* ── HEADER ── */
      .hdr{display:flex;align-items:center;padding:12px 16px 6px;border-bottom:1px solid var(--divider-color,#e0e0e0);gap:10px}
      .hdr-icon{font-size:20px}
      .hdr-title{font-size:15px;font-weight:600;color:var(--primary-text-color)}
      .hdr-route{font-size:11px;color:var(--secondary-text-color);margin-top:1px}

      /* ── TRAIN BLOCK (contains both legs + walk) ── */
      .train-block{border-bottom:1px solid var(--divider-color,rgba(0,0,0,.08))}
      .train-block:last-of-type{border-bottom:none}

      /* ── LEG LABEL BAR ── */
      .leg-bar{display:flex;align-items:center;gap:6px;padding:3px 16px;
        font-size:10px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;
        color:var(--secondary-text-color);background:var(--secondary-background-color,#f5f5f5)}
      .leg-bar.l1{border-top:1px solid var(--divider-color,rgba(0,0,0,.08))}
      .leg-bar.l2{border-top:none}
      .leg-pill{border-radius:10px;padding:1px 7px;font-size:9px;font-weight:800;color:#fff}
      .p1{background:#0098D4}  /* Elizabeth line blue */
      .p2{background:#003688}  /* Thameslink dark blue */

      /* ── TRAIN ROW ── */
      .train-row{padding:${rp};background:transparent}
      .train-row:hover{background:var(--secondary-background-color,rgba(0,0,0,.03))}
      .t-top{display:flex;align-items:baseline;justify-content:space-between;gap:6px;margin-bottom:3px}
      .t-time{font-size:1.25em;font-weight:700;color:var(--primary-text-color);letter-spacing:-.3px;flex-shrink:0}
      .t-meta{display:flex;align-items:center;gap:8px;flex:1;flex-wrap:wrap}
      .t-plat{font-size:.82em;color:var(--secondary-text-color);
        background:var(--secondary-background-color,#f0f0f0);border-radius:4px;padding:1px 6px}
      .t-plat.changed{color:#ff9800;border:1px solid #ff9800}
      .t-status{font-size:.8em;font-weight:600;flex-shrink:0}
      .t-sub{font-size:.79em;color:var(--secondary-text-color);margin-top:2px}
      .t-calling{font-size:.76em;color:var(--secondary-text-color);margin-top:2px}
      .t-delay{font-size:.76em;color:#f44336;margin-top:2px;font-style:italic}

      /* ── WALK DIVIDER ── */
      .walk-div{display:flex;align-items:center;gap:8px;padding:5px 16px;
        font-size:.76em;color:var(--secondary-text-color);
        background:var(--secondary-background-color,rgba(0,0,0,.03));
        border-top:1px dashed var(--divider-color,rgba(0,0,0,.15))}
      .walk-line{flex:1;border-top:1px dashed var(--divider-color,rgba(0,0,0,.2))}

      /* ── HISTORY PANEL ── */
      .hist-panel{padding:10px 16px 12px;border-top:1px solid var(--divider-color,rgba(0,0,0,.08))}
      .hist-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px}
      .hist-stat{text-align:center;background:var(--secondary-background-color,rgba(0,0,0,.04));
        border-radius:6px;padding:6px 4px}
      .hist-stat-val{font-size:1.15em;font-weight:700;color:var(--primary-text-color)}
      .hist-stat-lbl{font-size:.7em;color:var(--secondary-text-color);margin-top:1px}
      .hist-days{display:flex;gap:3px;justify-content:stretch;margin-bottom:6px}
      .hist-day{flex:1;text-align:center;border-radius:4px;padding:4px 2px;min-width:0}
      .hist-day-lbl{font-size:.65em;color:var(--primary-text-color);font-weight:600;
        mix-blend-mode:normal;opacity:.9}
      .hist-day-pct{font-size:.7em;font-weight:700;margin-top:1px;
        color:var(--primary-text-color);opacity:.95}
      .hist-bw{display:flex;justify-content:space-between;font-size:.75em;
        color:var(--secondary-text-color);margin-top:4px}

      /* ── FOOTER ── */
      .footer{padding:5px 16px;font-size:.74em;color:var(--secondary-text-color);
        border-top:1px solid var(--divider-color,rgba(0,0,0,.08));
        display:flex;justify-content:space-between}

      .no-trains{padding:18px 16px;text-align:center;color:var(--secondary-text-color)}
    `;
  }

  // ── RENDER ONE TRAIN ROW ──────────────────────────────────────────────

  _trainRow(train, legNum) {
    const cfg = this._config;
    const delay = parseInt(train.delay_minutes||0, 10);
    const status = sc(train.state||train.status, delay);
    const dep = train.departure_time||train.scheduled_departure||'--:--';
    const arr = train.scheduled_arrival||'';

    let jMins = null;
    if (cfg.show_journey_time && arr && dep!=='--:--') {
      try {
        const [dh,dm]=dep.split(':').map(Number);
        const [ah,am]=arr.split(':').map(Number);
        jMins=(ah*60+am)-(dh*60+dm);
        if (jMins<0) jMins+=1440;
      } catch{}
    }

    const platHtml = cfg.show_platform && train.platform
      ? `<span class="t-plat${train.platform_changed?' changed':''}">Platform ${train.platform}${train.platform_changed?' ↻':''}</span>` : '';
    const jHtml = jMins>0 ? `<span style="font-size:.76em;color:var(--secondary-text-color)">Journey time: ${jMins} mins</span>` : '';
    const callHtml = cfg.show_calling_points && train.calling_points?.length
      ? `<div class="t-calling">Calling at: ${train.calling_points.slice(0,cfg.max_calling_points).join(', ')}${train.calling_points.length>cfg.max_calling_points?` +${train.calling_points.length-cfg.max_calling_points} more`:''}</div>` : '';
    const delayHtml = cfg.show_delay_reason && train.delay_reason
      ? `<div class="t-delay">⚠ ${train.delay_reason}</div>` : '';
    const cancelHtml = cfg.show_delay_reason && train.cancellation_reason
      ? `<div class="t-delay">✕ ${train.cancellation_reason}</div>` : '';
    const opHtml = cfg.show_operator && train.operator
      ? `<div class="t-sub">${train.operator}</div>` : '';

    return `<div class="train-row">
      <div class="t-top">
        <span class="t-time">${dep}</span>
        <div class="t-meta">${platHtml}${jHtml}</div>
        <span class="t-status" style="color:${status.color}">${status.icon} ${delay>0?`+${delay}m`:status.label}</span>
      </div>
      ${opHtml}${callHtml}${delayHtml}${cancelHtml}
    </div>`;
  }

  _leg2Row(train) {
    const cfg = this._config;
    const earliest = train.leg2_earliest_after_arrival;
    const dest = train.leg2_earliest_destination || '';
    const waitMins = train.leg2_connection_mins;
    const walkMins = train.leg2_walk_mins || 5;
    const isEst = earliest && earliest.startsWith('~');

    if (train.is_cancelled) {
      return `<div class="train-row" style="opacity:.6">
        <div class="t-top">
          <span class="t-time" style="color:#9e9e9e">--:--</span>
          <div class="t-meta"></div>
          <span class="t-status" style="color:#9e9e9e">– No connection</span>
        </div>
        <div class="t-sub" style="font-style:italic">Train cancelled — no Thameslink connection</div>
      </div>`;
    }

    if (!earliest) {
      return `<div class="train-row">
        <div class="t-top">
          <span class="t-time" style="color:#9e9e9e">--:--</span>
          <div class="t-meta"></div>
          <span class="t-status" style="color:#9e9e9e">– No data</span>
        </div>
        <div class="t-sub" style="font-style:italic">Connection data not yet available</div>
      </div>`;
    }

    const clean = earliest.replace(/^~/,'');
    const [connTime] = clean.split(' → ');
    const connDest = dest.replace(' (est.)','');
    const statusColor = isEst ? '#ff9800' : '#003688';
    const statusLabel = isEst ? '~ Estimated' : '✓ Live';
    const waitLabel = waitMins !== null && waitMins !== undefined
      ? `${walkMins}m walk + ${waitMins}m wait` : `${walkMins}m walk`;

    return `<div class="train-row">
      <div class="t-top">
        <span class="t-time" style="color:${statusColor}">${connTime}</span>
        <div class="t-meta">
          <span class="t-sub" style="margin:0">${waitLabel}</span>
        </div>
        <span class="t-status" style="color:${statusColor}">${statusLabel}</span>
      </div>
      <div class="t-sub">Towards ${connDest}</div>
    </div>`;
  }

  // ── HISTORY PANEL ─────────────────────────────────────────────────────

  _histPanel() {
    const {rel, del} = this._histAttrs();
    if (!rel) return '';

    const today = rel.on_time_pct_today;
    const d7 = rel.on_time_pct_7day;
    const d30 = rel.on_time_pct_30day;
    const avgDelay = del ? del.avg_delay_7day : null;

    const fmt = v => v !== null && v !== undefined ? `${parseFloat(v).toFixed(1)}%` : 'N/A';
    const fmtD = v => v !== null && v !== undefined ? `${parseFloat(v).toFixed(1)} min` : 'N/A';

    // Daily breakdown — last 7 days with data
    const breakdown = (rel.daily_breakdown || [])
      .filter(d => d.on_time_pct !== null)
      .slice(-7);

    const daysHtml = breakdown.map(d => {
      const pct = d.on_time_pct;
      const bg = pct_color(pct);
      const lbl = day_abbr(d.date);
      return `<div class="hist-day" style="background:${bg}20;border:1px solid ${bg}40">
        <div class="hist-day-lbl" style="color:${bg}">${lbl}</div>
        <div class="hist-day-pct" style="color:${bg}">${pct.toFixed(0)}%</div>
      </div>`;
    }).join('');

    // Best/worst from summary
    const summAttrs = this._summaryAttrs() || {};
    const best = summAttrs.best_day;
    const worst = summAttrs.worst_day;
    const bestStr = best ? `👍 Best: ${day_abbr(best.date||'')} ${best.date||''} (${best.on_time_pct !== undefined ? best.on_time_pct.toFixed(2) : '?'}%)` : '';
    const worstStr = worst ? `👎 Worst: ${day_abbr(worst.date||'')} ${worst.date||''} (${worst.on_time_pct !== undefined ? worst.on_time_pct.toFixed(2) : '?'}%)` : '';

    return `<div class="hist-panel">
      <div class="hist-stats">
        <div class="hist-stat">
          <div class="hist-stat-val" style="color:${pct_color(today)}">${fmt(today)}</div>
          <div class="hist-stat-lbl">Today</div>
        </div>
        <div class="hist-stat">
          <div class="hist-stat-val" style="color:${pct_color(d7)}">${fmt(d7)}</div>
          <div class="hist-stat-lbl">7-day</div>
        </div>
        <div class="hist-stat">
          <div class="hist-stat-val" style="color:${pct_color(d30)}">${fmt(d30)}</div>
          <div class="hist-stat-lbl">30-day</div>
        </div>
        <div class="hist-stat">
          <div class="hist-stat-val">${fmtD(avgDelay)}</div>
          <div class="hist-stat-lbl">Avg delay</div>
        </div>
      </div>
      ${daysHtml ? `<div class="hist-days">${daysHtml}</div>` : ''}
      <div class="hist-bw">
        <span>${bestStr}</span>
        <span>${worstStr}</span>
      </div>
    </div>`;
  }

  // ── MAIN RENDER ───────────────────────────────────────────────────────

  _render() {
    if (!this._hass || !this._config.entity) return;

    const attrs = this._summaryAttrs();
    const trains = this._trains();
    const cfg = this._config;

    const origin = attrs?.origin_name || 'Twyford';
    const dest   = attrs?.destination_name || 'Farringdon';
    const lastUpdated = attrs?.last_updated
      ? new Date(attrs.last_updated).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'})
      : null;

    const visible = trains.filter(t => {
      if (cfg.hide_on_time_trains && !t.is_cancelled && parseInt(t.delay_minutes||0,10)===0) return false;
      if (cfg.min_delay_to_show && parseInt(t.delay_minutes||0,10)<cfg.min_delay_to_show) return false;
      return true;
    });

    const hdrHtml = cfg.show_header ? `
      <div class="hdr">
        <span class="hdr-icon">🚆</span>
        <div>
          <div class="hdr-title">${cfg.title}</div>
          ${cfg.show_route ? `<div class="hdr-route">${origin} → ${dest}</div>` : ''}
        </div>
      </div>` : '';

    const trainBlocksHtml = visible.length ? visible.map(t => `
      <div class="train-block">
        <div class="leg-bar l1">
          <span class="leg-pill p1">LEG 1</span>
          ${origin} → ${dest} · Elizabeth line
        </div>
        ${this._trainRow(t, 1)}
        ${cfg.show_leg2 ? `
        <div class="walk-div">
          <span class="walk-line"></span>
          🚶 ${t.leg2_walk_mins||5} min walk · Farringdon → City Thameslink
          <span class="walk-line"></span>
        </div>
        <div class="leg-bar l2">
          <span class="leg-pill p2">LEG 2</span>
          City Thameslink · Thameslink southbound
        </div>
        ${this._leg2Row(t)}` : ''}
      </div>`).join('') : '<div class="no-trains">No trains found</div>';

    const histHtml = cfg.show_history_panel ? this._histPanel() : '';
    const footerHtml = cfg.show_last_updated && lastUpdated
      ? `<div class="footer"><span>Last updated: ${lastUpdated}</span><span>🚉</span></div>` : '';

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card>
        ${hdrHtml}
        ${trainBlocksHtml}
        ${histHtml}
        ${footerHtml}
      </ha-card>`;
  }
}

customElements.define('morning-commute-multileg-card', MorningCommuteMultilegCard);
window.customCards=(window.customCards||[]).filter(c=>c.type!=='morning-commute-multileg-card');
window.customCards.push({
  type:'morning-commute-multileg-card',
  name:'Morning Commute Multileg Card',
  description:'Twyford→Farringdon (Elizabeth) + City Thameslink southbound, per train, with history',
  preview:true
});
console.info(
  `%c MORNING-COMMUTE-MULTILEG-CARD %c v${VER} `,
  'background:#003688;color:#fff;font-weight:700;padding:2px 4px;border-radius:3px 0 0 3px',
  'background:#0098D4;color:#fff;font-weight:700;padding:2px 4px;border-radius:0 3px 3px 0'
);
