const map = L.map('map-viewport', { zoomControl: false, attributionControl: false }).setView([0, 0], 2);
L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', { maxZoom: 19, opacity: 0.65 }).addTo(map);

let aircraftMarkers = {};
let controllerMarkers = {};
let blindConeCircles = {};
let assignmentLines = [];
let gpsMarker = null;
let localControllers = [];
let currentSelectedIcao = null;
let latestAircraftList = [];

let hasAutoCenteredInit = false;
let hasCenteredOnGPSFirstFix = false;
let isTimeoutInputLoaded = false;

// PER EVITARE LA RICOSTRUZIONE DEL DOM A OGNI WEBSOCKET TICK
let lastControllersJson = "";

let chartHistory = new Array(20).fill(0);

const socket = io();

map.on('click', () => { deselectAircraft(); });

function deselectAircraft() {
  currentSelectedIcao = null;
  document.getElementById('target-focus-card').innerHTML = `
    <div style="text-align: center; color: var(--text-sub); font-size: 13px; padding: 12px 0;">
      Seleziona un aereo sulla mappa o dal feed
    </div>
  `;
  Object.keys(aircraftMarkers).forEach(icao => {
    const marker = aircraftMarkers[icao];
    if (marker && marker.getElement()) {
      marker.getElement().classList.remove('selected-plane-icon');
    }
  });
  renderAircraftFeed(latestAircraftList);
}

function selectAircraft(ac) {
  currentSelectedIcao = ac.icao;
  
  const callsign = ac.current_data[10] || ac.icao;
  const alt = ac.current_data[11] || '0';
  const speed = ac.current_data[12] || '0';
  const heading = ac.current_data[13] || '0';
  const vrate = ac.current_data[16] || '0';

  document.getElementById('target-focus-card').innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
      <div>
        <div style="font-size: 20px; font-weight: 700; color: var(--accent-purple);">${callsign}</div>
        <div style="font-size: 12px; color: var(--text-sub);">ICAO: ${ac.icao}</div>
      </div>
      <span class="status-badge" style="background: rgba(175, 82, 222, 0.2); color: var(--accent-purple);">SELEZIONATO</span>
    </div>
    <div class="data-row"><span class="data-label">Altitudine</span><span class="data-value">${alt} ft</span></div>
    <div class="data-row"><span class="data-label">Ground Speed</span><span class="data-value">${speed} kts</span></div>
    <div class="data-row"><span class="data-label">Heading</span><span class="data-value">${heading}°</span></div>
    <div class="data-row"><span class="data-label">Vertical Rate</span><span class="data-value">${vrate} ft/m</span></div>
    <div class="data-row"><span class="data-label">Assegnazione</span><span class="data-value" style="color: var(--accent-blue);">${ac.assigned_ctrl || 'Nessuno'}</span></div>
  `;

  const lat = parseFloat(ac.current_data[14]);
  const lon = parseFloat(ac.current_data[15]);
  if (lat && lon) { map.panTo([lat, lon]); }

  renderAircraftFeed(latestAircraftList);
}

function toggleRadioChart() {
  const chartBox = document.getElementById('radio-chart-container');
  const btn = document.getElementById('btn-toggle-chart');
  if (chartBox.style.display === 'none') {
    chartBox.style.display = 'block';
    btn.innerText = '▲';
  } else {
    chartBox.style.display = 'none';
    btn.innerText = '▼';
  }
}

function updateRFChart(pps) {
  chartHistory.push(pps);
  if (chartHistory.length > 20) chartHistory.shift();

  const maxVal = Math.max(5, ...chartHistory);
  const width = 300;
  const height = 50;

  let linePoints = [];
  let areaPoints = [`0,55`];

  chartHistory.forEach((val, idx) => {
    const x = (idx / (chartHistory.length - 1)) * width;
    const y = 55 - ((val / maxVal) * height);
    linePoints.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    areaPoints.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  });

  areaPoints.push(`300,55`);

  const lineEl = document.getElementById('chart-line');
  const areaEl = document.getElementById('chart-area');
  if (lineEl) lineEl.setAttribute('points', linePoints.join(' '));
  if (areaEl) areaEl.setAttribute('points', areaPoints.join(' '));
}

function updateAircraftTimeout() {
  const inp = document.getElementById('input-ac-timeout');
  if (!inp) return;
  const timeout = parseInt(inp.value);
  if (isNaN(timeout) || timeout < 5) return;

  fetch('/api/set_aircraft_timeout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ timeout })
  });
}

function fetchCleanSerialPorts() {
  fetch('/api/list_serial_ports')
    .then(r => r.json())
    .then(d => {
      const gpsSel = document.getElementById('select-gps-port');
      const heltecSel = document.getElementById('select-heltec-port');
      let html = '<option value="">-- Seleziona Porta --</option>';
      (d.ports || []).forEach(p => {
        html += `<option value="${p.port}">${p.port} (${p.desc})</option>`;
      });
      if (gpsSel) gpsSel.innerHTML = html;
      if (heltecSel) heltecSel.innerHTML = html;
    });
}

fetchCleanSerialPorts();

socket.on('telemetry_update', (data) => {
  const sys = data.system || {};
  const aircraft = data.aircraft || [];
  latestAircraftList = aircraft;

  if (!hasAutoCenteredInit) {
    if (sys.gps && sys.gps.connected && sys.gps.lat && sys.gps.lon) {
      map.setView([sys.gps.lat, sys.gps.lon], 12);
      hasAutoCenteredInit = true;
      hasCenteredOnGPSFirstFix = true;
    } else if (sys.reference_datum && sys.reference_datum.lat && sys.reference_datum.lon) {
      map.setView([sys.reference_datum.lat, sys.reference_datum.lon], 12);
      hasAutoCenteredInit = true;
    }
  }

  if (!hasCenteredOnGPSFirstFix && sys.gps && sys.gps.connected && sys.gps.lat && sys.gps.lon) {
    map.flyTo([sys.gps.lat, sys.gps.lon], 13, { duration: 1.8 });
    hasCenteredOnGPSFirstFix = true;
    hasAutoCenteredInit = true;
  }

  updateTxButtonUI(sys.tx_active);

  const dotDump = document.getElementById('dot-dump1090');
  const txtDump = document.getElementById('txt-dump1090');
  if (dotDump && txtDump) {
    if (sys.dump1090_connected) { dotDump.classList.add('online'); txtDump.innerText = 'dump1090: CONNECTED'; }
    else { dotDump.classList.remove('online'); txtDump.innerText = 'dump1090: DISCONNECTED'; }
  }

  const dotSer = document.getElementById('dot-serial');
  const txtSer = document.getElementById('txt-serial');
  if (dotSer && txtSer) {
    if (sys.serial_status && sys.serial_status.connected) { dotSer.classList.add('online'); txtSer.innerText = `Heltec: ${sys.serial_status.port} ⚙️`; }
    else { dotSer.classList.remove('online'); txtSer.innerText = 'Heltec: DISCONNECTED ⚙️'; }
  }

  const dotGps = document.getElementById('dot-gps');
  const txtGps = document.getElementById('txt-gps');
  if (dotGps && txtGps) {
    if (sys.gps && sys.gps.connected) { dotGps.classList.add('online'); txtGps.innerText = `GPS: ${sys.gps.fix} ⚙️`; }
    else { dotGps.classList.remove('online'); txtGps.innerText = 'GPS: NO FIX ⚙️'; }
  }

  document.getElementById('lbl-utc').innerText = (sys.gps && sys.gps.utc) ? sys.gps.utc : '--:--:-- UTC';

  if (sys.gps) {
    document.getElementById('val-gps-lat').innerText = (sys.gps.lat || 0).toFixed(5) + '°';
    document.getElementById('val-gps-lon').innerText = (sys.gps.lon || 0).toFixed(5) + '°';
    document.getElementById('val-gps-alt').innerText = (sys.gps.alt || 0) + ' m';
    document.getElementById('val-gps-sats').innerText = sys.gps.satellites || 0;
    renderGPSMarker(sys.gps);
  }

  if (sys.rf_stats) {
    const pps = sys.rf_stats.packets_sec !== undefined ? sys.rf_stats.packets_sec : 0.0;
    document.getElementById('val-rf-pps').innerText = pps;
    document.getElementById('val-rf-airtime').innerText = (sys.rf_stats.airtime_util !== undefined ? sys.rf_stats.airtime_util : '0.0') + '%';
    document.getElementById('val-rf-bitrate').innerText = sys.rf_stats.payload_bitrate || '0.00 KB/s';
    
    updateRFChart(pps);
  }

  if (!isTimeoutInputLoaded && sys.aircraft_timeout_sec) {
    const inpTimeout = document.getElementById('input-ac-timeout');
    if (inpTimeout) {
      inpTimeout.value = sys.aircraft_timeout_sec;
      isTimeoutInputLoaded = true;
    }
  }

  const ref = sys.reference_datum || { name: 'POINT_ALPHA', lat: 45.4642, lon: 9.1901 };
  const inpName = document.getElementById('input-ref-name');
  const inpLat = document.getElementById('input-ref-lat');
  const inpLon = document.getElementById('input-ref-lon');

  if (inpName && document.activeElement !== inpName) inpName.value = ref.name || 'POINT_ALPHA';
  if (inpLat && document.activeElement !== inpLat) inpLat.value = (ref.lat !== undefined) ? ref.lat : 45.4642;
  if (inpLon && document.activeElement !== inpLon) inpLon.value = (ref.lon !== undefined) ? ref.lon : 9.1901;

  localControllers = sys.controllers || [];
  renderControllers(localControllers);
  renderAircraft(aircraft, localControllers);
  renderAircraftFeed(aircraft);
});

function updateTxButtonUI(isActive) {
  const btnTx = document.getElementById('btn-tx-toggle');
  const txtTx = document.getElementById('txt-tx-status');
  if (isActive) { btnTx.classList.add('active'); txtTx.innerText = 'TX TRANSMITTER ACTIVE'; }
  else { btnTx.classList.remove('active'); txtTx.innerText = 'TX TRANSMITTER OFF'; }
}

function toggleTX() { fetch('/api/toggle_tx', { method: 'POST' }); }

function renderAircraftFeed(aircraftList) {
  const container = document.getElementById('aircraft-feed-container');
  const countEl = document.getElementById('ac-count');
  if (!container) return;

  countEl.innerText = aircraftList.length;

  if (aircraftList.length === 0) {
    container.innerHTML = '<div style="font-size: 12px; color: var(--text-sub); text-align: center; padding: 12px;">Nessun aereo rilevato</div>';
    return;
  }

  let html = '';
  aircraftList.forEach(ac => {
    const callsign = ac.current_data[10] || ac.icao;
    const alt = ac.current_data[11] || '0';
    const speed = ac.current_data[12] || '0';
    const isSelected = ac.icao === currentSelectedIcao;

    html += `
      <div class="glass-card clickable-item ${isSelected ? 'selected-item' : ''}" onclick="event.stopPropagation(); selectAircraftByIcao('${ac.icao}')">
        <div style="display:flex; justify-content:space-between; font-weight:700; font-size:13px;">
          <span>✈ ${callsign}</span>
          <span style="font-family:var(--font-mono); font-weight:600;">${alt} ft</span>
        </div>
        <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-sub); margin-top:4px;">
          <span>Speed: ${speed} kts</span>
          <span>Ctrl: ${ac.assigned_ctrl || 'Nessuno'}</span>
        </div>
      </div>
    `;
  });
  container.innerHTML = html;
}

function selectAircraftByIcao(icao) {
  const ac = latestAircraftList.find(a => a.icao === icao);
  if (ac) selectAircraft(ac);
}

function renderGPSMarker(gps) {
  if (!gps.connected || !gps.lat || !gps.lon) {
    if (gpsMarker) { map.removeLayer(gpsMarker); gpsMarker = null; }
    return;
  }

  const customGpsIcon = L.divIcon({
    className: 'leaflet-gps-icon',
    html: `
      <div style="position:relative; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;">
        <div style="position: absolute; inset: 0; background: rgba(52, 199, 89, 0.25); border-radius: 50%; animation: pulse 2s infinite;"></div>
        <div style="width: 14px; height: 14px; background: var(--accent-green); border: 2px solid white; border-radius: 50%; box-shadow: 0 0 10px rgba(52,199,89,0.8);"></div>
        <div class="label-capsule" style="position: absolute; left: 36px; top: -6px; border-color: rgba(52, 199, 89, 0.5);">
          <strong>📍 GPS STN LOCALE</strong><br>
          <span style="color: var(--accent-green);">${gps.fix}</span>
        </div>
      </div>
    `,
    iconSize: [160, 40],
    iconAnchor: [16, 16]
  });

  if (!gpsMarker) {
    gpsMarker = L.marker([gps.lat, gps.lon], { icon: customGpsIcon }).addTo(map);
  } else {
    gpsMarker.setLatLng([gps.lat, gps.lon]);
    gpsMarker.setIcon(customGpsIcon);
  }
}

function openGPSModal() { fetchCleanSerialPorts(); document.getElementById('modal-gps').style.display = 'flex'; }
function closeGPSModal() { document.getElementById('modal-gps').style.display = 'none'; }
function openHeltecModal() { fetchCleanSerialPorts(); document.getElementById('modal-heltec').style.display = 'flex'; }
function closeHeltecModal() { document.getElementById('modal-heltec').style.display = 'none'; }

function connectGPS() {
  const port = document.getElementById('select-gps-port').value;
  const baud = document.getElementById('select-gps-baud').value;
  if (!port) return alert("Seleziona una porta seriale per il GPS!");
  fetch('/api/connect_gps', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ port, baud }) })
    .then(r => r.json()).then(d => { if (d.status === "error") alert("Errore GPS: " + d.message); else closeGPSModal(); });
}

function disconnectGPS() {
  fetch('/api/connect_gps', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ port: "DISCONNECT" }) }).then(() => closeGPSModal());
}

function connectHeltec() {
  const port = document.getElementById('select-heltec-port').value;
  const baud = document.getElementById('select-heltec-baud').value;
  if (!port) return alert("Seleziona una porta seriale per Heltec!");
  fetch('/api/connect_heltec', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ port, baud }) })
    .then(r => r.json()).then(d => { if (d.status === "error") alert("Errore Heltec: " + d.message); else closeHeltecModal(); });
}

function disconnectHeltec() {
  fetch('/api/connect_heltec', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ port: "DISCONNECT" }) }).then(() => closeHeltecModal());
}

function openAddControllerModal() { document.getElementById('modal-add-controller').style.display = 'flex'; }
function closeAddControllerModal() { document.getElementById('modal-add-controller').style.display = 'none'; }

function submitAddController() {
  const name = document.getElementById('m-ctrl-name').value;
  const lat = parseFloat(document.getElementById('m-ctrl-lat').value);
  const lon = parseFloat(document.getElementById('m-ctrl-lon').value);
  const zenith_blind_angle = parseFloat(document.getElementById('m-ctrl-zenith').value);
  const radius_km = parseFloat(document.getElementById('m-ctrl-radius').value);

  // Reset dello stato del render per forzare l'aggiornamento
  lastControllersJson = "";

  fetch('/api/add_controller', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, lat, lon, zenith_blind_angle, radius_km })
  }).then(r => r.json()).then(d => closeAddControllerModal());
}

// CANCELLAZIONE REALE E ISTANTANEA AL PRIMO CLICK
function deleteController(id) {
  lastControllersJson = ""; // Forzo il ridisegno immediato del DOM
  localControllers = localControllers.filter(c => String(c.id) !== String(id));
  
  if (controllerMarkers[id]) { map.removeLayer(controllerMarkers[id]); delete controllerMarkers[id]; }
  if (blindConeCircles[id]) { map.removeLayer(blindConeCircles[id]); delete blindConeCircles[id]; }
  
  renderControllers(localControllers);

  fetch('/api/delete_controller', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id })
  });
}

// RENDER CONTROLLORI OTTIMIZZATO (SENZA DISTRUZIONE DOM SE LA LISTA NON CAMBIA)
function renderControllers(controllers) {
  const container = document.getElementById('controllers-container');
  if (!container) return;

  // Se la lista è identica a prima, NON ricreare i pulsanti e NON toccare il DOM
  const currentJson = JSON.stringify((controllers || []).map(c => `${c.id}_${c.name}_${c.zenith_blind_angle}_${c.radius_km}`));
  if (currentJson === lastControllersJson) {
    return;
  }
  lastControllersJson = currentJson;

  container.innerHTML = '';

  if (!controllers || controllers.length === 0) {
    container.innerHTML = '<div style="font-size: 12px; color: var(--text-sub); text-align: center; padding: 10px;">Nessun controllore presente. Clicca <b>+ Add</b>.</div>';
    return;
  }

  controllers.forEach(ctrl => {
    const zenithAngle = ctrl.zenith_blind_angle || 30;
    container.innerHTML += `
      <div class="glass-card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px;">
          <div style="font-weight: 600; font-size: 14px;">${ctrl.name}</div>
          <button onclick="event.stopPropagation(); deleteController('${ctrl.id}')" style="border:none; background:none; color:var(--accent-red); cursor:pointer; font-weight:700; padding:4px 8px; font-size:16px; pointer-events:auto;" title="Elimina Controllore">✕</button>
        </div>
        <div class="data-row"><span class="data-label">Cono Zenith</span><span class="data-value">± ${zenithAngle}°</span></div>
        <div class="data-row"><span class="data-label">Raggio Op.</span><span class="data-value">${ctrl.radius_km} km</span></div>
      </div>
    `;

    if (!controllerMarkers[ctrl.id]) {
      controllerMarkers[ctrl.id] = L.circleMarker([ctrl.lat, ctrl.lon], { color: '#007aff', fillColor: '#007aff', fillOpacity: 0.9, radius: 8 }).addTo(map).bindTooltip(ctrl.name, { permanent: true, direction: 'top' });
    } else {
      controllerMarkers[ctrl.id].setLatLng([ctrl.lat, ctrl.lon]);
    }

    const radiusGroundMeters = 3000.0 * Math.tan(zenithAngle * Math.PI / 180.0);
    if (blindConeCircles[ctrl.id]) map.removeLayer(blindConeCircles[ctrl.id]);
    blindConeCircles[ctrl.id] = L.circle([ctrl.lat, ctrl.lon], { radius: radiusGroundMeters, color: '#ff9500', fillColor: '#ff9500', fillOpacity: 0.15, weight: 1.5, dashArray: '3, 3' }).addTo(map);
  });

  Object.keys(controllerMarkers).forEach(cid => {
    if (!controllers.find(c => String(c.id) === String(cid))) {
      map.removeLayer(controllerMarkers[cid]); delete controllerMarkers[cid];
      if (blindConeCircles[cid]) { map.removeLayer(blindConeCircles[cid]); delete blindConeCircles[cid]; }
    }
  });
}

function renderAircraft(aircraftList, controllers) {
  assignmentLines.forEach(l => map.removeLayer(l));
  assignmentLines = [];

  aircraftList.forEach(ac => {
    const lat = parseFloat(ac.current_data[14]);
    const lon = parseFloat(ac.current_data[15]);
    if (!lat || !lon) return;

    const callsign = ac.current_data[10] || ac.icao;
    const alt = ac.current_data[11] || '0';
    const heading = parseFloat(ac.current_data[13] || 0);
    const isBlind = ac.in_blind_cone;
    const isSelected = ac.icao === currentSelectedIcao;
    const ctrlId = ac.assigned_ctrl || 'NESSUNO';
    
    let color = isBlind ? '#ff9500' : '#007aff';
    if (isSelected) color = '#af52de';

    if (!aircraftMarkers[ac.icao]) {
      const customIcon = L.divIcon({
        className: 'leaflet-plane-icon ' + (isSelected ? 'selected-plane-icon' : ''),
        html: `
          <div class="plane-wrapper" style="position: relative; cursor: pointer; display: flex; align-items: center;">
            <div class="plane-svg" style="transform: rotate(${heading}deg); width: 26px; height: 26px; transition: transform 0.3s ease;">
              <svg viewBox="0 0 24 24" width="26" height="26" fill="${color}">
                <path d="M21,16L21,14L13,9L13,3.5A1.5,1.5 0 0,0 11.5,2A1.5,1.5 0 0,0 10,3.5L10,9L2,14L2,16L10,13.5L10,19L8,20.5L8,22L11.5,21L15,22L15,20.5L13,19L13,13.5L21,16Z"/>
              </svg>
            </div>
            <div class="label-capsule" style="position: absolute; left: 30px; top: -12px; ${isBlind ? 'border-color: rgba(255, 149, 0, 0.4);' : ''}">
              <strong class="ac-cs">${callsign}</strong> • <span class="ac-alt">${alt}</span>ft<br>
              <span class="ac-ctrl" style="color: ${isBlind ? 'var(--accent-orange)' : (isSelected ? 'var(--accent-purple)' : 'var(--accent-blue)')};">
                ${isBlind ? '⚠️ In Cono Verticale' : 'Ctrl: ' + ctrlId}
              </span>
            </div>
          </div>
        `,
        iconSize: [160, 40],
        iconAnchor: [13, 13]
      });

      const marker = L.marker([lat, lon], { icon: customIcon }).addTo(map);
      marker.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        selectAircraft(ac);
      });
      aircraftMarkers[ac.icao] = marker;
    } else {
      const marker = aircraftMarkers[ac.icao];
      marker.setLatLng([lat, lon]);
      
      const el = marker.getElement();
      if (el) {
        if (isSelected) el.classList.add('selected-plane-icon');
        else el.classList.remove('selected-plane-icon');

        const svg = el.querySelector('.plane-svg');
        if (svg) svg.style.transform = `rotate(${heading}deg)`;
        
        const path = el.querySelector('.plane-svg svg path');
        if (path) path.setAttribute('fill', color);

        const cs = el.querySelector('.ac-cs');
        if (cs) cs.innerText = callsign;

        const altEl = el.querySelector('.ac-alt');
        if (altEl) altEl.innerText = alt;

        const ctrlEl = el.querySelector('.ac-ctrl');
        if (ctrlEl) {
          ctrlEl.innerText = isBlind ? '⚠️ In Cono Verticale' : 'Ctrl: ' + ctrlId;
          ctrlEl.style.color = isBlind ? 'var(--accent-orange)' : (isSelected ? 'var(--accent-purple)' : 'var(--accent-blue)');
        }
      }
    }

    if (ac.assigned_ctrl && controllers) {
      const ctrl = controllers.find(c => String(c.id) === String(ac.assigned_ctrl));
      if (ctrl) {
        const line = L.polyline([[lat, lon], [ctrl.lat, ctrl.lon]], {
          color: color, weight: isSelected ? 2.5 : 1.5, dashArray: '4, 4'
        }).addTo(map);
        assignmentLines.push(line);
      }
    }
  });

  Object.keys(aircraftMarkers).forEach(icao => {
    if (!aircraftList.find(a => a.icao === icao)) {
      map.removeLayer(aircraftMarkers[icao]);
      delete aircraftMarkers[icao];
    }
  });
}

function updateReferenceDatum() {
  const name = document.getElementById('input-ref-name').value;
  const lat = parseFloat(document.getElementById('input-ref-lat').value);
  const lon = parseFloat(document.getElementById('input-ref-lon').value);
  fetch('/api/update_reference', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, lat, lon })
  });
}

function setRefToCurrentGPS() { fetch('/api/use_current_gps_ref', { method: 'POST' }); }