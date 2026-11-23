/**
 * solar-mask-card — Lovelace custom card
 * solar_mask integration — github.com/38decibel/solar_mask
 */

class SolarMaskCard extends HTMLElement {

  setConfig(config) {
    if (!config.entity) throw new Error('solar-mask-card: entity is required');
    this._config = config;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: 'open' });
      this.shadowRoot.innerHTML = `
        <style>
          :host { display: block; }
          ha-card { padding: 12px 16px 16px; box-sizing: border-box; }
          .card-header {
            font-size: 1.1em; font-weight: 500;
            color: var(--primary-text-color); padding-bottom: 8px;
          }
          #chart-container { width: 100%; }
          #chart-container svg { width: 100%; display: block; }
          .legend {
            display: flex; flex-wrap: wrap; gap: 6px 14px;
            margin-top: 8px; font-size: 0.78em;
            color: var(--secondary-text-color);
          }
          .legend-item { display: flex; align-items: center; gap: 5px; }
          .info-bar {
            display: flex; justify-content: space-around; align-items: center;
            margin-top: 12px; padding: 10px 8px 4px;
            border-top: 1px solid var(--divider-color, #444);
          }
          .info-cell {
            display: flex; flex-direction: column; align-items: center; gap: 3px;
            flex: 1;
          }
          .info-cell + .info-cell {
            border-left: 1px solid var(--divider-color, #444);
          }
          .info-value {
            font-size: 0.95em; font-weight: 500;
            color: var(--primary-text-color);
          }
        </style>
        <ha-card>
          <div class="card-header" id="title"></div>
          <div id="chart-container"></div>
          <div class="legend" id="legend"></div>
          <div class="info-bar" id="info-bar"></div>
        </ha-card>`;
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 4; }

  static getStubConfig() {
    return {
      entity: 'sensor.maison_solar_diagram',
      sun_entity: 'sensor.maison_sun_effective_elevation'
    };
  }

  _render() {
    const cfg      = this._config;
    const stateObj = this._hass.states[cfg.entity];
    const sunObj   = cfg.sun_entity ? this._hass.states[cfg.sun_entity] : null;

    this.shadowRoot.getElementById('title').textContent =
      cfg.title || stateObj?.attributes?.friendly_name || 'Diagramme solaire';

    if (!stateObj) {
      this.shadowRoot.getElementById('chart-container').innerHTML =
        `<p style="color:var(--error-color)">Entité introuvable : ${cfg.entity}</p>`;
      return;
    }

    const attr   = stateObj.attributes;
    const height = cfg.height || 320;
    const W = 600, H = height;
    const ml = 38, mr = 12, mt = 10, mb = 36;
    const cW = W - ml - mr, cH = H - mt - mb;

    const toX = az => ml + az / 360 * cW;
    const toY = el => mt + cH - Math.max(el, 0) / 75 * cH;

    // Équinoxe : moyenne mars + septembre (trajectoires très proches, on prend mars)
    const SERIES = [
      { key: 'path_solstice_ete',   label: 'Solstice d\'été',  color: '#FDD835', width: 2,   dash: '7,4' },
      { key: 'path_equinoxe_mars',  label: 'Équinoxe',         color: '#FFB74D', width: 2,   dash: '7,4' },
      { key: 'path_solstice_hiver', label: 'Solstice d\'hiver', color: '#64B5F6', width: 2,   dash: '7,4' },
      { key: 'path_aujourdhui',     label: "Aujourd'hui",       color: '#43A047', width: 3.5, dash: '' },
    ];

    let s = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;

    // Background
    s += `<rect x="${ml}" y="${mt}" width="${cW}" height="${cH}"
            fill="var(--card-background-color,#1c1c1e)" rx="4"/>`;

    // Grid
    s += `<g stroke="var(--divider-color,#444)" stroke-width="0.5" opacity="0.6">`;
    for (let el = 0; el <= 75; el += 15) {
      const y = toY(el);
      s += `<line x1="${ml}" y1="${y}" x2="${ml+cW}" y2="${y}"/>`;
      s += `<text x="${ml-4}" y="${y+4}" text-anchor="end" font-size="9"
              fill="var(--secondary-text-color,#888)">${el}°</text>`;
    }
    for (const [az, label] of [[0,'N'],[45,'NE'],[90,'E'],[135,'SE'],[180,'S'],[225,'SO'],[270,'O'],[315,'NO'],[360,'N']]) {
      const x = toX(az);
      s += `<line x1="${x}" y1="${mt}" x2="${x}" y2="${mt+cH}"/>`;
      s += `<text x="${x}" y="${mt+cH+14}" text-anchor="middle" font-size="9"
              fill="var(--secondary-text-color,#888)">${label}</text>`;
    }
    s += `</g>`;

    // Axis labels
    s += `<text x="${ml+cW/2}" y="${H-2}" text-anchor="middle" font-size="10"
            fill="var(--secondary-text-color,#888)">Azimut</text>`;
    s += `<text x="10" y="${mt+cH/2}" text-anchor="middle" font-size="10"
            fill="var(--secondary-text-color,#888)"
            transform="rotate(-90,10,${mt+cH/2})">Élévation (°)</text>`;

    // Horizon line
    s += `<line x1="${ml}" y1="${toY(0)}" x2="${ml+cW}" y2="${toY(0)}"
            stroke="var(--secondary-text-color,#888)" stroke-width="1" opacity="0.5"/>`;

    // Mask — orange, fond 66% opacité
    const maskPts = attr.mask || [];
    if (maskPts.length >= 2) {
      const poly = maskPts.map(p => `${toX(p.x).toFixed(1)},${toY(p.y).toFixed(1)}`).join(' ');
      const bR   = `${toX(maskPts[maskPts.length-1].x).toFixed(1)},${toY(0).toFixed(1)}`;
      const bL   = `${toX(maskPts[0].x).toFixed(1)},${toY(0).toFixed(1)}`;
      s += `<polygon points="${poly} ${bR} ${bL}" fill="#FF6F00" opacity="0.25"/>`;
      s += `<polyline points="${poly}" fill="none" stroke="#FF6F00"
              stroke-width="2" stroke-linejoin="round"/>`;
    }

    // Sun paths — aujourd'hui dessiné en dernier (au-dessus)
    const order = [
      ...SERIES.filter(s => s.key !== 'path_aujourdhui'),
      SERIES.find(s => s.key === 'path_aujourdhui'),
    ];

    for (const serie of order) {
      const pts = (attr[serie.key] || []).filter(p => p.y >= -1);
      if (pts.length < 2) continue;
      const d    = this._smoothPath(pts, toX, toY);
      const dash = serie.dash ? `stroke-dasharray="${serie.dash}"` : '';
      s += `<path d="${d}" fill="none" stroke="${serie.color}"
              stroke-width="${serie.width}" stroke-linecap="round"
              stroke-linejoin="round" opacity="0.95" ${dash}/>`;
    }

    // Current sun dot
    if (sunObj) {
      const az      = parseFloat(sunObj.attributes.sun_azimuth)  || 0;
      const elev    = parseFloat(sunObj.attributes.sun_elevation) || 0;
      const effElev = parseFloat(sunObj.state) || 0;
      if (elev > 0) {
        const cx = toX(az), cy = toY(elev);
        const dotColor = effElev > 0 ? '#FF6F00' : '#9E9E9E';
        s += `<circle cx="${cx}" cy="${cy}" r="9" fill="${dotColor}" opacity="0.22"/>`;
        s += `<circle cx="${cx}" cy="${cy}" r="5.5" fill="${dotColor}"
                stroke="white" stroke-width="2"/>`;
      }
    }

    s += `</svg>`;
    this.shadowRoot.getElementById('chart-container').innerHTML = s;

    // Legend
    let legend = `
      <div class="legend-item">
        <svg width="26" height="12">
          <rect x="0" y="1" width="26" height="10" fill="#FF6F00" opacity="0.25" rx="2"/>
          <line x1="0" y1="6" x2="26" y2="6" stroke="#FF6F00" stroke-width="2"/>
        </svg>
        <span>Horizon (masque)</span>
      </div>`;

    for (const serie of SERIES) {
      const dash = serie.dash ? `stroke-dasharray="${serie.dash}"` : '';
      legend += `
        <div class="legend-item">
          <svg width="26" height="10">
            <line x1="0" y1="5" x2="26" y2="5"
              stroke="${serie.color}" stroke-width="${Math.min(serie.width + 0.5, 3.5)}" ${dash}/>
          </svg>
          <span>${serie.label}</span>
        </div>`;
    }

    if (sunObj) {
      const effElev  = parseFloat(sunObj.state) || 0;
      const dotColor = effElev > 0 ? '#FF6F00' : '#9E9E9E';
      legend += `
        <div class="legend-item">
          <svg width="14" height="14">
            <circle cx="7" cy="7" r="5" fill="${dotColor}" stroke="white" stroke-width="1.5"/>
          </svg>
          <span>${effElev > 0 ? 'Soleil (visible)' : 'Soleil (masqué)'}</span>
        </div>`;
    }

    this.shadowRoot.getElementById('legend').innerHTML = legend;

    // ── Info bar ───────────────────────────────────────────────────────────
    const diagAttr  = stateObj.attributes;
    const startVal  = this._hass.states[cfg.entity.replace('solar_diagram', 'sun_start')];
    const endVal    = this._hass.states[cfg.entity.replace('solar_diagram', 'sun_end')];

    const fmtTime = (entityId) => {
      const obj = this._hass.states[entityId];
      if (!obj || ['unknown','unavailable'].includes(obj.state)) return '--:--';
      try {
        const d = new Date(obj.state);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      } catch { return '--:--'; }
    };

    const sunElevVal = sunObj ? parseFloat(sunObj.attributes.sun_elevation) : null;
    const effElevVal = sunObj ? parseFloat(sunObj.state) : null;
    const elevStr    = sunElevVal !== null && !isNaN(sunElevVal)
      ? `${sunElevVal.toFixed(1)}°`
      : '--';
    const elevColor  = (effElevVal !== null && effElevVal > 0)
      ? '#FF6F00' : 'var(--secondary-text-color, #888)';

    const startEntityId = cfg.entity.replace('solar_diagram', 'sun_start');
    const endEntityId   = cfg.entity.replace('solar_diagram', 'sun_end');

    this.shadowRoot.getElementById('info-bar').innerHTML = `
      <div class="info-cell">
        
        <div class="info-label">Lever du soleil</div>
        <div class="info-value">${fmtTime(startEntityId)}</div>
      </div>
      <div class="info-cell">
        
        <div class="info-label">Élévation actuelle</div>
        <div class="info-value" style="color:${elevColor}">${elevStr}</div>
      </div>
      <div class="info-cell">
        
        <div class="info-label">Coucher du soleil</div>
        <div class="info-value">${fmtTime(endEntityId)}</div>
      </div>`;
  }

  _smoothPath(pts, toX, toY) {
    const m = pts.map(p => [toX(p.x), toY(p.y)]);
    if (m.length < 2) return '';
    let d = `M ${m[0][0].toFixed(1)} ${m[0][1].toFixed(1)}`;
    for (let i = 1; i < m.length; i++) {
      const p0 = m[Math.max(i-2,0)], p1 = m[i-1];
      const p2 = m[i],               p3 = m[Math.min(i+1,m.length-1)];
      const t  = 0.3;
      const cp1x = p1[0]+(p2[0]-p0[0])*t, cp1y = p1[1]+(p2[1]-p0[1])*t;
      const cp2x = p2[0]-(p3[0]-p1[0])*t, cp2y = p2[1]-(p3[1]-p1[1])*t;
      d += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)},${cp2x.toFixed(1)} ${cp2y.toFixed(1)},${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
    }
    return d;
  }
}

customElements.define('solar-mask-card', SolarMaskCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'solar-mask-card',
  name: 'Solar Mask Card',
  description: 'Sun paths over a horizon mask — solar_mask integration.',
});
