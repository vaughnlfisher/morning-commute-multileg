// Morning Commute Multileg Card v1.5.0
// Collapsible history: LEG 1 (Elizabeth line) + LEG 2 (Thameslink CTK->EPH)

const VER = '1.5.0';
const SC = {
  on_time:    {color:'#4caf50', icon:'\u2713', label:'On time'},
  delayed:    {color:'#f44336', icon:'\u26a0', label:'Delayed'},
  minor:      {color:'#ff9800', icon:'\u26a0', label:'Minor delay'},
  cancelled:  {color:'#d32f2f', icon:'\u2715', label:'Cancelled'},
  no_service: {color:'#9e9e9e', icon:'\u2013', label:'No service'},
  expected:   {color:'#2196f3', icon:'~', label:'Expected'},
};
function sc(state, delay) {
  if (!state) return SC.no_service;
  const s = state.toLowerCase();
  if (s==='cancelled'||s==='critical') return SC.cancelled;
  if (s==='no service'||s==='no trains') return SC.no_service;
  if (s.includes('expected')) return SC.expected;
  if (delay>=10) return SC.delayed;
  if (delay>=3) return SC.minor;
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
  try { return new Date(dateStr+'T12:00:00').toLocaleDateString('en-GB',{weekday:'short'}); }
  catch { return ''; }
}

class MorningCommuteMultilegCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:'open'});
    this._config = {};
    this._hass = null;
    this._histOpen = false;
  }
  static getStubConfig() {
    return {entity:'sensor.morning_commute_summary',title:'Morning Commute',show_platform:true,show_operator:true,show_calling_points:true,show_journey_time:true,show_last_updated:true,show_leg2:true,show_history_panel:true,compact_height:false};
  }
  setConfig(config) {
    if (!config.entity) throw new Error('entity is required');
    this._config = {title:'Morning Commute',show_header:true,show_route:true,show_platform:true,show_operator:true,show_calling_points:false,show_delay_reason:true,show_journey_time:false,show_last_updated:false,show_leg2:true,show_history_panel:true,max_calling_points:3,compact_height:false,font_size:'medium',hide_on_time_trains:false,min_delay_to_show:0,...config};
  }
  set hass(h) { this._hass = h; this._render(); }
  getCardSize() { return 8; }

  _s(eid) { const s=this._hass.states[eid]; return s?{state:s.state,attrs:s.attributes}:null; }
  _prefix() {
    const mc=this._hass.states['sensor.morning_commute_train_1'];
    if (mc&&mc.state!=='unknown'&&mc.state!=='unavailable') return 'morning_commute';
    return 'twyford_to_farringdon';
  }
  _summaryAttrs() {
    const c=this._s(this._config.entity);
    if (c&&c.state!=='unknown'&&c.state!=='unavailable') return c.attrs;
    const f=this._s('sensor.twyford_to_farringdon_summary');
    return f?f.attrs:null;
  }
  _trainData(n) {
    const p=this._prefix();
    const s=this._hass.states[`sensor.${p}_train_${n}`];
    if (!s||s.state==='unknown'||s.state==='unavailable') return null;
    return {state:s.state,...s.attributes};
  }
  _trains() {
    const trains=[];
    for (let i=1;i<=10;i++) {
      const t=this._trainData(i);
      if (!t) break;
      if ((t.state||t.status||'').toLowerCase()==='no service') break;
      trains.push({...t,train_number:i});
    }
    return trains;
  }
  _histAttrs() {
    const p=this._prefix();
    const rel=this._hass.states[`sensor.${p}_historical_reliability`];
    const del=this._hass.states[`sensor.${p}_historical_delays`];
    const leg2=this._hass.states["sensor.morning_commute_leg_2_historical_reliability"];
    return {rel:rel?rel.attributes:null,del:del?del.attributes:null,leg2:leg2?leg2.attributes:null};
  }
  _computeLeg2(scheduledArrival) {
    const tfl=this._hass.states['sensor.london_tfl_thameslink_910gctmslnk'];
    if (!tfl||!tfl.attributes.departures) return null;
    const southbound=tfl.attributes.departures.filter(d=>d.line&&d.line.designation==='2');
    if (!southbound.length) return null;
    const now=new Date();
    let arrDt=null;
    if (scheduledArrival) {
      try {
        const [h,m]=scheduledArrival.split(':').map(Number);
        arrDt=new Date(now); arrDt.setHours(h,m,0,0);
        if (arrDt<now&&(now-arrDt)>6*3600000) arrDt.setDate(arrDt.getDate()+1);
      } catch {arrDt=null;}
    }
    const earliestBoard=arrDt?new Date(arrDt.getTime()+5*60000):null;
    for (const dep of southbound) {
      try {
        const depDt=new Date(dep.expected);
        if (!earliestBoard||depDt>=earliestBoard) {
          const dest=(dep.destination||'').replace(' Rail Station','');
          const hh=String(depDt.getHours()).padStart(2,'0');
          const mm=String(depDt.getMinutes()).padStart(2,'0');
          const waitMins=arrDt?Math.round((depDt-arrDt)/60000)-5:null;
          return {time:`${hh}:${mm}`,dest,waitMins,estimated:false};
        }
      } catch {continue;}
    }
    const last=southbound[southbound.length-1];
    try {
      const lastDt=new Date(last.expected);
      const dests=southbound.map(d=>(d.destination||'').replace(' Rail Station',''));
      let proj=new Date(lastDt); let steps=0;
      while (proj<(earliestBoard||now)&&steps<20){proj=new Date(proj.getTime()+20*60000);steps++;}
      const hh=String(proj.getHours()).padStart(2,'0'); const mm=String(proj.getMinutes()).padStart(2,'0');
      return {time:`~${hh}:${mm}`,dest:dests[steps%dests.length],waitMins:null,estimated:true};
    } catch {return null;}
  }

  _styles() {
    const fs={small:'12px',medium:'14px',large:'16px'}[this._config.font_size]||'14px';
    const rp=this._config.compact_height?'8px 16px':'12px 16px';
    return `
      :host{display:block}
      ha-card{overflow:hidden;font-family:var(--paper-font-body1_-_font-family,'Roboto',sans-serif);font-size:${fs}}
      .hdr{display:flex;align-items:center;padding:12px 16px 6px;border-bottom:1px solid var(--divider-color,#e0e0e0);gap:10px}
      .hdr-title{font-size:15px;font-weight:600;color:var(--primary-text-color)}
      .hdr-route{font-size:11px;color:var(--secondary-text-color);margin-top:1px}
      .train-block{border-bottom:1px solid var(--divider-color,rgba(0,0,0,.08))}
      .train-block:last-of-type{border-bottom:none}
      .leg-bar{display:flex;align-items:center;gap:6px;padding:3px 16px;font-size:10px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--secondary-text-color);background:var(--secondary-background-color,#f5f5f5)}
      .leg-bar.l1{border-top:1px solid var(--divider-color,rgba(0,0,0,.08))}
      .leg-pill{border-radius:10px;padding:1px 7px;font-size:9px;font-weight:800;color:#fff}
      .p1{background:#0098D4} .p2{background:#003688}
      .train-row{padding:${rp}}
      .leg2-row{padding-left:28px;border-left:3px solid #003688;margin-left:13px}
      .train-row:hover{background:var(--secondary-background-color,rgba(0,0,0,.03))}
      .t-top{display:flex;align-items:baseline;justify-content:space-between;gap:6px;margin-bottom:3px}
      .t-time{font-size:1.25em;font-weight:700;color:var(--primary-text-color);letter-spacing:-.3px;flex-shrink:0}
      .t-meta{display:flex;align-items:center;gap:8px;flex:1;flex-wrap:wrap}
      .t-plat{font-size:.82em;color:var(--secondary-text-color);background:var(--secondary-background-color,#f0f0f0);border-radius:4px;padding:1px 6px}
      .t-plat.changed{color:#ff9800;border:1px solid #ff9800}
      .t-status{font-size:.8em;font-weight:600;flex-shrink:0}
      .t-sub{font-size:.79em;color:var(--secondary-text-color);margin-top:2px}
      .t-calling{font-size:.76em;color:var(--secondary-text-color);margin-top:2px}
      .t-delay{font-size:.76em;color:#f44336;margin-top:2px;font-style:italic}
      .walk-div{display:flex;align-items:center;gap:8px;padding:5px 16px;font-size:.76em;color:var(--secondary-text-color);background:var(--secondary-background-color,rgba(0,0,0,.03));border-top:1px dashed var(--divider-color,rgba(0,0,0,.15))}
      .walk-line{flex:1;border-top:1px dashed var(--divider-color,rgba(0,0,0,.2))}
      .hist-toggle{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;cursor:pointer;border-top:1px solid var(--divider-color,rgba(0,0,0,.08));background:var(--secondary-background-color,#f5f5f5);user-select:none}
      .hist-toggle:hover{background:var(--secondary-background-color,rgba(0,0,0,.06))}
      .hist-toggle-lbl{font-size:11px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;color:var(--secondary-text-color)}
      .hist-toggle-icon{font-size:14px;color:var(--secondary-text-color);transition:transform .2s}
      .hist-toggle-icon.open{transform:rotate(180deg)}
      .hist-section{padding:10px 16px 12px;border-top:1px solid var(--divider-color,rgba(0,0,0,.06))}
      .hist-section-title{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--secondary-text-color);margin-bottom:6px}
      .hist-section-title.l1{color:#0098D4} .hist-section-title.l2{color:#003688}
      .hist-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px}
      .hist-stat{text-align:center;background:var(--secondary-background-color,rgba(0,0,0,.04));border-radius:6px;padding:6px 4px}
      .hist-stat-val{font-size:1.15em;font-weight:700}
      .hist-stat-lbl{font-size:.7em;color:var(--secondary-text-color);margin-top:1px}
      .hist-days{display:flex;gap:3px;margin-bottom:6px}
      .hist-day{flex:1;text-align:center;border-radius:4px;padding:4px 2px;min-width:0}
      .hist-day-lbl{font-size:.65em;font-weight:600;opacity:.9}
      .hist-day-pct{font-size:.7em;font-weight:700;margin-top:1px;opacity:.95}
      .hist-bw{display:flex;justify-content:space-between;font-size:.72em;color:var(--secondary-text-color);margin-top:2px}
      .hist-divider{border:none;border-top:1px solid var(--divider-color,rgba(0,0,0,.08));margin:10px 0 8px}
      .footer{padding:5px 16px;font-size:.74em;color:var(--secondary-text-color);border-top:1px solid var(--divider-color,rgba(0,0,0,.08));display:flex;justify-content:space-between}
      .no-trains{padding:18px 16px;text-align:center;color:var(--secondary-text-color)}
    `;
  }

  _trainRow(train) {
    const cfg=this._config;
    const delay=parseInt(train.delay_minutes||0,10);
    const status=sc(train.state||train.status,delay);
    const dep=train.departure_time||train.scheduled_departure||'--:--';
    const arr=train.scheduled_arrival||'';
    let jMins=null;
    if (cfg.show_journey_time&&arr&&dep!=='--:--') {
      try{const[dh,dm]=dep.split(':').map(Number);const[ah,am]=arr.split(':').map(Number);jMins=(ah*60+am)-(dh*60+dm);if(jMins<0)jMins+=1440;}catch{}
    }
    const platHtml=cfg.show_platform&&train.platform?`<span class="t-plat${train.platform_changed?' changed':''}">Platform ${train.platform}${train.platform_changed?' \u21bb':''}</span>`:'';
    const jHtml=jMins>0?`<span style="font-size:.76em;color:var(--secondary-text-color)">Journey time: ${jMins} mins</span>`:'';
    const callHtml=cfg.show_calling_points&&train.calling_points?.length?`<div class="t-calling">Calling at: ${train.calling_points.slice(0,cfg.max_calling_points).join(', ')}${train.calling_points.length>cfg.max_calling_points?` +${train.calling_points.length-cfg.max_calling_points} more`:''}</div>`:'';
    const delayHtml=cfg.show_delay_reason&&train.delay_reason?`<div class="t-delay">\u26a0 ${train.delay_reason}</div>`:'';
    const cancelHtml=cfg.show_delay_reason&&train.cancellation_reason?`<div class="t-delay">\u2715 ${train.cancellation_reason}</div>`:'';
    const opHtml=cfg.show_operator&&train.operator?`<div class="t-sub">${train.operator}</div>`:'';
    return `<div class="train-row"><div class="t-top"><span class="t-time">${dep}</span><div class="t-meta">${platHtml}${jHtml}</div><span class="t-status" style="color:${status.color}">${status.icon} ${delay>0?`+${delay}m`:status.label}</span></div>${opHtml}${callHtml}${delayHtml}${cancelHtml}</div>`;
  }

  _leg2Rows(train) {
    const walkMins=train.leg2_walk_mins||5;
    if (train.is_cancelled) return `<div class="train-row"><div class="t-top"><span class="t-time" style="color:#9e9e9e">--:--</span><div class="t-meta"></div><span class="t-status" style="color:#9e9e9e">\u2013 No connection</span></div><div class="t-sub" style="font-style:italic">Train cancelled</div></div>`;
    let conns=Array.isArray(train.leg2_connections)?train.leg2_connections:[];
    if (conns.length) {
      return conns.map(c=>{
        const waitLbl=(c.wait_mins!==null&&c.wait_mins!==undefined)?`${walkMins}m walk + ${c.wait_mins}m wait`:`${walkMins}m walk`;
        return `<div class="train-row leg2-row"><div class="t-top"><span class="t-time" style="color:#003688">${c.time}</span><div class="t-meta"><span style="font-size:.79em;color:var(--secondary-text-color)">${waitLbl}</span></div><span class="t-status" style="color:#003688">\u2713 Live</span></div><div class="t-sub">Towards ${c.destination}</div></div>`;
      }).join('');
    }
    // Fallback: single earliest or TfL-derived estimate
    let conn=null;
    const earliest=train.leg2_earliest_after_arrival;
    if (earliest&&earliest!=='None') {
      const isEst=earliest.startsWith('~');
      const[connTime]=earliest.replace(/^~/,'').split(' \u2192 ');
      conn={time:connTime,dest:(train.leg2_earliest_destination||'').replace(' (est.)',''),waitMins:train.leg2_connection_mins,estimated:isEst};
    } else {
      conn=this._computeLeg2(train.scheduled_arrival);
    }
    if (!conn) return `<div class="train-row"><div class="t-top"><span class="t-time" style="color:#9e9e9e">--:--</span><div class="t-meta"></div><span class="t-status" style="color:#9e9e9e">\u2013 No data</span></div><div class="t-sub" style="font-style:italic;color:var(--secondary-text-color)">Awaiting Thameslink data</div></div>`;
    const color=conn.estimated?'#ff9800':'#003688';
    const statusLbl=conn.estimated?'~ Estimated':'\u2713 Live';
    const waitLbl=conn.waitMins!==null&&conn.waitMins!==undefined?`${walkMins}m walk + ${conn.waitMins}m wait`:`${walkMins}m walk`;
    return `<div class="train-row leg2-row"><div class="t-top"><span class="t-time" style="color:${color}">${conn.time}</span><div class="t-meta"><span style="font-size:.79em;color:var(--secondary-text-color)">${waitLbl}</span></div><span class="t-status" style="color:${color}">${statusLbl}</span></div><div class="t-sub">Towards ${conn.dest}</div></div>`;
  }

  _renderHistSection(attrs, delAttrs, label, pillClass) {
    if (!attrs || attrs.on_time_pct_7day===null||attrs.on_time_pct_7day===undefined) return `<div class="hist-section"><div class="hist-section-title ${pillClass}">${label}</div><div style="font-size:.76em;color:var(--secondary-text-color);font-style:italic">No data available</div></div>`;
    const fmt=v=>v!==null&&v!==undefined?`${parseFloat(v).toFixed(1)}%`:'N/A';
    const fmtD=v=>v!==null&&v!==undefined?`${parseFloat(v).toFixed(1)} min`:'N/A';
    const breakdown=(attrs.daily_breakdown||[]).filter(d=>d.on_time_pct!==null).slice(-7);
    const daysHtml=breakdown.map(d=>{
      const bg=pct_color(d.on_time_pct);
      return `<div class="hist-day" style="background:${bg}20;border:1px solid ${bg}60"><div class="hist-day-lbl" style="color:${bg}">${day_abbr(d.date)}</div><div class="hist-day-pct" style="color:${bg}">${d.on_time_pct.toFixed(0)}%</div></div>`;
    }).join('');
    const best=attrs.best_day;
    const worst=attrs.worst_day;
    const bestStr=best?`\ud83d\udc4d ${day_abbr(best.date||'')} ${best.date||''} (${best.on_time_pct!==undefined?parseFloat(best.on_time_pct).toFixed(1):'?'}%)`:''; 
    const worstStr=worst?`\ud83d\udc4e ${day_abbr(worst.date||'')} ${worst.date||''} (${worst.on_time_pct!==undefined?parseFloat(worst.on_time_pct).toFixed(1):'?'}%)`:''; 
    const avgDelay=delAttrs?delAttrs.avg_delay_7day:attrs.avg_delay_7day;
    return `<div class="hist-section">
      <div class="hist-section-title ${pillClass}">${label}</div>
      <div class="hist-stats">
        <div class="hist-stat"><div class="hist-stat-val" style="color:${pct_color(attrs.on_time_pct_today)}">${fmt(attrs.on_time_pct_today)}</div><div class="hist-stat-lbl">Today</div></div>
        <div class="hist-stat"><div class="hist-stat-val" style="color:${pct_color(attrs.on_time_pct_7day)}">${fmt(attrs.on_time_pct_7day)}</div><div class="hist-stat-lbl">7-day</div></div>
        <div class="hist-stat"><div class="hist-stat-val" style="color:${pct_color(attrs.on_time_pct_30day)}">${fmt(attrs.on_time_pct_30day)}</div><div class="hist-stat-lbl">30-day</div></div>
        <div class="hist-stat"><div class="hist-stat-val">${fmtD(avgDelay)}</div><div class="hist-stat-lbl">Avg delay</div></div>
      </div>
      ${daysHtml?`<div class="hist-days">${daysHtml}</div>`:''}
      <div class="hist-bw"><span>${bestStr}</span><span>${worstStr}</span></div>
    </div>`;
  }

  _histPanel() {
    const {rel, del, leg2} = this._histAttrs();
    const leg1Html = this._renderHistSection(rel, del, '\ud83d\ude86 Leg 1 \u00b7 Twyford \u2192 Farringdon (Elizabeth line)', 'l1');
    const leg2Html = this._renderHistSection(leg2, null, '\ud83d\ude86 Leg 2 \u00b7 City Thameslink \u2192 Elephant & Castle (Thameslink)', 'l2');
    return `${leg1Html}<hr class="hist-divider">${leg2Html}`;
  }

  _render() {
    if (!this._hass||!this._config.entity) return;
    const attrs=this._summaryAttrs();
    const trains=this._trains();
    const cfg=this._config;
    const origin=attrs?.origin_name||'Twyford';
    const dest=attrs?.destination_name||'Farringdon';
    const lastUpdated=attrs?.last_updated?new Date(attrs.last_updated).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}):null;
    const visible=trains.filter(t=>{
      if (cfg.hide_on_time_trains&&!t.is_cancelled&&parseInt(t.delay_minutes||0,10)===0) return false;
      if (cfg.min_delay_to_show&&parseInt(t.delay_minutes||0,10)<cfg.min_delay_to_show) return false;
      return true;
    });
    const hdrHtml=cfg.show_header?`<div class="hdr"><span style="font-size:20px">\ud83d\ude86</span><div><div class="hdr-title">${cfg.title}</div>${cfg.show_route?`<div class="hdr-route">${origin} \u2192 ${dest}</div>`:''}</div></div>`:'';
    const blocksHtml=visible.length?visible.slice(0,3).map(t=>`<div class="train-block"><div class="leg-bar l1"><span class="leg-pill p1">LEG 1</span>${origin} \u2192 ${dest} \u00b7 Elizabeth line</div>${this._trainRow(t)}${cfg.show_leg2?`<div class="walk-div"><span class="walk-line"></span>\ud83d\udeb6 ${t.leg2_walk_mins||5} min walk \u00b7 Farringdon \u2192 City Thameslink<span class="walk-line"></span></div><div class="leg-bar"><span class="leg-pill p2">LEG 2</span>City Thameslink \u00b7 next ${Array.isArray(t.leg2_connections)&&t.leg2_connections.length?t.leg2_connections.length:''} southbound</div>${this._leg2Rows(t)}`:''}</div>`).join(''):'<div class="no-trains">No trains found</div>';
    const histHtml=cfg.show_history_panel?`<div class="hist-toggle" id="hist-toggle"><span class="hist-toggle-lbl">\ud83d\udcca Reliability History</span><span class="hist-toggle-icon${this._histOpen?' open':''}">\u25bc</span></div>${this._histOpen?this._histPanel():''}`:'';
    const footerHtml=cfg.show_last_updated&&lastUpdated?`<div class="footer"><span>Last updated: ${lastUpdated}</span><span>\ud83d\ude49</span></div>`:'';
    this.shadowRoot.innerHTML=`<style>${this._styles()}</style><ha-card>${hdrHtml}${blocksHtml}${histHtml}${footerHtml}</ha-card>`;
    const toggleEl=this.shadowRoot.getElementById('hist-toggle');
    if (toggleEl) toggleEl.addEventListener('click',()=>{this._histOpen=!this._histOpen;this._render();});
  }
}

customElements.define('morning-commute-multileg-card',MorningCommuteMultilegCard);
window.customCards=(window.customCards||[]).filter(c=>c.type!=='morning-commute-multileg-card');
window.customCards.push({type:'morning-commute-multileg-card',name:'Morning Commute Multileg Card',description:'Twyford->Farringdon (Elizabeth) + CTK southbound per train, dual history panels',preview:true});
console.info(`%c MORNING-COMMUTE-MULTILEG-CARD %c v${VER} `,'background:#003688;color:#fff;font-weight:700;padding:2px 4px;border-radius:3px 0 0 3px','background:#0098D4;color:#fff;font-weight:700;padding:2px 4px;border-radius:0 3px 3px 0');
