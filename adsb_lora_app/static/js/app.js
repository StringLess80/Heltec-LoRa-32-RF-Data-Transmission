// INITIALIZATION MAPPA 2D LEAFLET
const map = L.map('map-viewport', { zoomControl: false, attributionControl: false }).setView([0, 0], 2);
L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', { maxZoom: 19, opacity: 0.65 }).addTo(map);

// VARS STATO E MAPPE CON PERSISTENZA LOCALSTORAGE
let currentMapMode = localStorage.getItem('tactical_map_mode') || '2D';
let cesiumViewer = null;

// Entità Cesium 3D
let cesiumEntities = {
  aircraft: {},
  controllers: {},
  blindCones: {},
  dropLines: {},
  assignmentLines: {},
  gpsMarker: null
};

let aircraftMarkers = {};
let controllerMarkers = {};
let blindConeCircles = {};
let assignmentLines = [];
let gpsMarker = null;
let localControllers = [];
let currentSelectedIcao = null;
let latestAircraftList = [];
let latestSystemState = {};

let hasAutoCenteredInit = false;
let hasCenteredOnGPSFirstFix = false;
let isTimeoutInputLoaded = false;

let lastControllersJson = "";
let lastFeedJson = "";
let chartHistory = new Array(20).fill(0);

const socket = io();

map.on('click', () => { deselectAircraft(); });

// APPLICA MODALITÀ SALVATA ALL'AVVIO
document.addEventListener('DOMContentLoaded', () => {
  if (currentMapMode === '3D') {
    switchMapMode('3D');
  }
});

// ESPOSIZIONE GLOBALE FUNZIONI MODALE GUIDA
window.openControlsGuideModal = function() {
  const modal = document.getElementById('modal-controls-guide');
  if (modal) modal.style.display = 'flex';
};

window.closeControlsGuideModal = function() {
  const modal = document.getElementById('modal-controls-guide');
  if (modal) modal.style.display = 'none';
};

// SWITCH MODALITÀ 2D / 3D CON PERPENDICOLARE DALL'ALTO (-90°)
async function switchMapMode(mode) {
  currentMapMode = mode;
  localStorage.setItem('tactical_map_mode', mode);

  const btn2d = document.getElementById('btn-mode-2d');
  const btn3d = document.getElementById('btn-mode-3d');
  const map2dDiv = document.getElementById('map-viewport');
  const map3dDiv = document.getElementById('cesium-viewport');

  if (mode === '3D') {
    if (btn2d) btn2d.classList.remove('active');
    if (btn3d) btn3d.classList.add('active');
    map2dDiv.style.display = 'none';
    map3dDiv.style.display = 'block';

    if (!cesiumViewer) {
      await initCesium3DGlobe();
    } else {
      cesiumViewer.resize();
    }

    lastControllersJson = ""; 
    renderControllers(localControllers);
    renderAircraft(latestAircraftList, localControllers);

    let centerLat = 45.4642;
    let centerLon = 9.1901;

    const inpLat = parseFloat(document.getElementById('input-ref-lat')?.value);
    const inpLon = parseFloat(document.getElementById('input-ref-lon')?.value);
    if (!isNaN(inpLat) && !isNaN(inpLon)) {
      centerLat = inpLat;
      centerLon = inpLon;
    }

    if (cesiumViewer) {
      cesiumViewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(centerLon, centerLat, 35000.0),
        orientation: {
          heading: Cesium.Math.toRadians(0.0),
          pitch: Cesium.Math.toRadians(-90.0), // Perpendicolare dall'alto
          roll: 0.0
        },
        duration: 1.2
      });
    }

  } else {
    if (btn3d) btn3d.classList.remove('active');
    if (btn2d) btn2d.classList.add('active');
    map3dDiv.style.display = 'none';
    map2dDiv.style.display = 'block';
    
    map.invalidateSize();
    renderAircraft(latestAircraftList, localControllers);
  }
}

// FUNZIONE RECENTER DALL'ALTO (-90°)
function snapCameraToLocation() {
  let targetLat = null;
  let targetLon = null;

  if (latestSystemState?.gps?.connected && latestSystemState?.gps?.lat && latestSystemState?.gps?.lon) {
    targetLat = latestSystemState.gps.lat;
    targetLon = latestSystemState.gps.lon;
  } else {
    const inpLat = parseFloat(document.getElementById('input-ref-lat')?.value);
    const inpLon = parseFloat(document.getElementById('input-ref-lon')?.value);
    if (!isNaN(inpLat) && !isNaN(inpLon) && (inpLat !== 0 || inpLon !== 0)) {
      targetLat = inpLat;
      targetLon = inpLon;
    }
  }

  if (!targetLat && localControllers && localControllers.length > 0) {
    targetLat = localControllers[0].lat;
    targetLon = localControllers[0].lon;
  }

  if (!targetLat) {
    targetLat = 45.4642;
    targetLon = 9.1901;
  }

  if (currentMapMode === '2D') {
    map.flyTo([targetLat, targetLon], 13, { duration: 1.2 });
  } else if (cesiumViewer) {
    cesiumViewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(targetLon, targetLat, 25000.0),
      orientation: {
        heading: Cesium.Math.toRadians(0.0),
        pitch: Cesium.Math.toRadians(-90.0),
        roll: 0.0
      },
      duration: 1.2
    });
  }
}

// INIZIALIZZAZIONE GLOBO 3D CON MAPPA VETTORIALE HD E CONTROLLI FISICI TELECAMERA
async function initCesium3DGlobe() {
  Cesium.Ion.defaultAccessToken = '';

  cesiumViewer = new Cesium.Viewer('cesium-viewport', {
    imageryProvider: false,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    infoBox: false,
    sceneModePicker: false,
    selectionIndicator: false,
    timeline: false,
    animation: false,
    navigationHelpButton: false,
    fullscreenButton: false,
    skyAtmosphere: false
  });

  const controller = cesiumViewer.scene.screenSpaceCameraController;
  controller.minimumZoomDistance = 500.0;
  controller.enableCollisionDetection = true;
  controller.minimumPitchAmount = Cesium.Math.toRadians(-88.0);
  controller.maximumPitchAmount = Cesium.Math.toRadians(-5.0);

  try {
    const topoBaseProvider = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
      'https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer'
    );
    cesiumViewer.imageryLayers.addImageryProvider(topoBaseProvider);

    const labelsOverlayProvider = await Cesium.UrlTemplateImageryProvider.fromUrl(
      'https://a.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png'
    );
    cesiumViewer.imageryLayers.addImageryProvider(labelsOverlayProvider);

  } catch (err) {
    console.error("Errore caricamento layer mappe 3D:", err);
  }

  cesiumViewer.scene.globe.enableLighting = false;
  cesiumViewer.scene.globe.showGroundAtmosphere = false;

  setTimeout(() => {
    if (cesiumViewer) cesiumViewer.resize();
  }, 150);

  const handler = new Cesium.ScreenSpaceEventHandler(cesiumViewer.scene.canvas);
  handler.setInputAction((click) => {
    const pickedObject = cesiumViewer.scene.pick(click.position);
    if (Cesium.defined(pickedObject) && pickedObject.id && pickedObject.id.icao) {
      const ac = latestAircraftList.find(a => a.icao === pickedObject.id.icao);
      if (ac) selectAircraft(ac);
    } else {
      deselectAircraft();
    }
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
}

// TOGGLE PRESET STINGER AUTOMATICO
function toggleStingerPreset(isStinger) {
  const nameInput = document.getElementById('m-ctrl-name');
  const zenithInput = document.getElementById('m-ctrl-zenith');
  const radiusInput = document.getElementById('m-ctrl-radius');
  const heightInput = document.getElementById('m-ctrl-height');
  const minRangeInput = document.getElementById('m-ctrl-min-range');

  if (isStinger) {
    if (nameInput) nameInput.value = "STINGER_UNIT_ALPHA";
    if (zenithInput) zenithInput.value = "30";   // Limite elevazione 60°
    if (radiusInput) radiusInput.value = "8.0";  // 8.0km Slant Range
    if (heightInput) heightInput.value = "3.8";  // 3.8km Tetto Operativo
    if (minRangeInput) minRangeInput.value = "0.2"; // 200m Arming range
  } else {
    if (nameInput) nameInput.value = "CTRL_TOWER_NORTH";
    if (zenithInput) zenithInput.value = "30";
    if (radiusInput) radiusInput.value = "40.0";
    if (heightInput) heightInput.value = "12.0";
    if (minRangeInput) minRangeInput.value = "0.0";
  }
}

// COPIA COORDINATE DAL GPS REALE O PUNTO NOTO NELLA MODALE
function copyGPSToControllerModal() {
  let lat = null;
  let lon = null;

  if (latestSystemState?.gps?.connected && latestSystemState?.gps?.lat && latestSystemState?.gps?.lon) {
    lat = latestSystemState.gps.lat;
    lon = latestSystemState.gps.lon;
  } else {
    const refLat = parseFloat(document.getElementById('input-ref-lat')?.value);
    const refLon = parseFloat(document.getElementById('input-ref-lon')?.value);
    if (!isNaN(refLat) && !isNaN(refLon)) {
      lat = refLat;
      lon = refLon;
    }
  }

  if (lat && lon) {
    document.getElementById('m-ctrl-lat').value = lat.toFixed(5);
    document.getElementById('m-ctrl-lon').value = lon.toFixed(5);
  } else {
    alert("Nessun dato GPS o Punto Noto disponibile al momento!");
  }
}

// INVIO COMPLETO PARAMETRI TATTICI CONTROLLORE / STINGER
function submitAddController() {
  const isStinger = document.getElementById('m-ctrl-is-stinger')?.checked || false;
  const name = document.getElementById('m-ctrl-name').value || (isStinger ? "STINGER_UNIT_ALPHA" : "CTRL_TOWER");
  const lat = parseFloat(document.getElementById('m-ctrl-lat').value);
  const lon = parseFloat(document.getElementById('m-ctrl-lon').value);
  const zenith_blind_angle = parseFloat(document.getElementById('m-ctrl-zenith').value) || 30.0;
  const radius_km = parseFloat(document.getElementById('m-ctrl-radius').value) || (isStinger ? 8.0 : 40.0);
  const cone_height_km = parseFloat(document.getElementById('m-ctrl-height').value) || (isStinger ? 3.8 : 12.0);
  const min_range_km = parseFloat(document.getElementById('m-ctrl-min-range').value) || (isStinger ? 0.2 : 0.0);

  lastControllersJson = "";

  fetch('/api/add_controller', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      lat,
      lon,
      unit_type: isStinger ? 'MANPADS_STINGER' : 'RADAR_TOWER',
      zenith_blind_angle,
      radius_km,
      cone_height_km,
      min_range_km
    })
  }).then(r => r.json()).then(d => closeAddControllerModal());
}

// RENDER CONTROLLORI TATTICI E CONO CIECO ROVESCIATO FIM-92 STINGER
function renderControllers(controllers) {
  const container = document.getElementById('controllers-container');
  if (!container) return;

  const currentJson = JSON.stringify((controllers || []).map(c => `${c.id}_${c.name}_${c.zenith_blind_angle}_${c.radius_km}_${c.cone_height_km}`));
  if (currentJson === lastControllersJson) return;
  lastControllersJson = currentJson;

  container.innerHTML = '';

  if (!controllers || controllers.length === 0) {
    container.innerHTML = '<div style="font-size: 12px; color: var(--text-sub); text-align: center; padding: 10px;">Nessun controllore presente. Clicca <b>+ Add</b>.</div>';
    return;
  }

  controllers.forEach(ctrl => {
    const zenithAngle = ctrl.zenith_blind_angle || 30;
    const coneHeightKm = ctrl.cone_height_km || 3.8;
    const coneHeightMeters = coneHeightKm * 1000.0;

    container.innerHTML += `
      <div class="glass-card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px;">
          <div style="font-weight: 600; font-size: 14px;">🚀 ${ctrl.name}</div>
          <button onclick="event.stopPropagation(); deleteController('${ctrl.id}')" style="border:none; background:none; color:var(--accent-red); cursor:pointer; font-weight:700; padding:4px 8px; font-size:16px; pointer-events:auto;" title="Elimina Controllore">✕</button>
        </div>
        <div class="data-row"><span class="data-label">Cono Zenith</span><span class="data-value">± ${zenithAngle}°</span></div>
        <div class="data-row"><span class="data-label">Tetto Cono</span><span class="data-value">${coneHeightKm} km</span></div>
        <div class="data-row"><span class="data-label">Slant Range</span><span class="data-value">${ctrl.radius_km} km</span></div>
      </div>
    `;

    // 1. 2D LEAFLET
    if (!controllerMarkers[ctrl.id]) {
      controllerMarkers[ctrl.id] = L.circleMarker([ctrl.lat, ctrl.lon], { color: '#007aff', fillColor: '#007aff', fillOpacity: 0.9, radius: 8 }).addTo(map).bindTooltip(`🚀 Stinger: ${ctrl.name}`, { permanent: true, direction: 'top' });
    } else {
      controllerMarkers[ctrl.id].setLatLng([ctrl.lat, ctrl.lon]);
    }

    const radiusGround2D = (coneHeightMeters * 0.8) * Math.tan(zenithAngle * Math.PI / 180.0);
    if (blindConeCircles[ctrl.id]) map.removeLayer(blindConeCircles[ctrl.id]);
    blindConeCircles[ctrl.id] = L.circle([ctrl.lat, ctrl.lon], {
      radius: radiusGround2D,
      color: '#ff9500',
      fillColor: '#ff9500',
      fillOpacity: 0.18,
      weight: 1.8,
      dashArray: '4, 4'
    }).addTo(map);

    // 2. 3D CESIUM (VERTICE A TERRA QUOTA ZERO)
    if (cesiumViewer) {
      if (!cesiumEntities.controllers[ctrl.id]) {
        cesiumEntities.controllers[ctrl.id] = cesiumViewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(ctrl.lon, ctrl.lat, 0),
          point: { pixelSize: 12, color: Cesium.Color.fromCssColorString('#007aff'), outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
          label: {
            text: `🚀 ${ctrl.name}`,
            font: 'bold 12px sans-serif',
            fillColor: Cesium.Color.fromCssColorString('#007aff'),
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 3,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            pixelOffset: new Cesium.Cartesian2(0, -22)
          }
        });
      } else {
        cesiumEntities.controllers[ctrl.id].position = Cesium.Cartesian3.fromDegrees(ctrl.lon, ctrl.lat, 0);
      }

      const topRadiusMeters = coneHeightMeters * Math.tan(zenithAngle * Math.PI / 180.0);
      const coneCenterPosition = Cesium.Cartesian3.fromDegrees(ctrl.lon, ctrl.lat, coneHeightMeters / 2.0);

      if (cesiumEntities.blindCones[ctrl.id]) {
        cesiumViewer.entities.remove(cesiumEntities.blindCones[ctrl.id]);
      }
      
      cesiumEntities.blindCones[ctrl.id] = cesiumViewer.entities.add({
        position: coneCenterPosition,
        cylinder: {
          length: coneHeightMeters,
          topRadius: topRadiusMeters,
          bottomRadius: 0.0,
          material: Cesium.Color.fromCssColorString('#ff9500').withAlpha(0.22),
          outline: true,
          outlineColor: Cesium.Color.fromCssColorString('#ff9500').withAlpha(0.75)
        }
      });
    }
  });
}

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
  
  if (currentMapMode === '3D') renderAircraft3D(latestAircraftList, localControllers);
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

// WEBSOCKET RECEIVER TELEMETRIA
socket.on('telemetry_update', (data) => {
  const sys = data.system || {};
  const aircraft = data.aircraft || [];
  latestSystemState = sys;
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

function selectAircraftByIcao(icao) {
  const ac = latestAircraftList.find(a => a.icao === icao);
  if (ac) selectAircraft(ac);
}

function renderGPSMarker(gps) {
  if (!gps.connected || !gps.lat || !gps.lon) {
    if (gpsMarker) { map.removeLayer(gpsMarker); gpsMarker = null; }
    if (cesiumEntities.gpsMarker && cesiumViewer) { cesiumViewer.entities.remove(cesiumEntities.gpsMarker); cesiumEntities.gpsMarker = null; }
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

  if (cesiumViewer) {
    if (!cesiumEntities.gpsMarker) {
      cesiumEntities.gpsMarker = cesiumViewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(gps.lon, gps.lat, 0),
        point: { pixelSize: 12, color: Cesium.Color.fromCssColorString('#34c759'), outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
        label: { text: '📍 GPS STN LOCALE', font: '12px sans-serif', fillColor: Cesium.Color.fromCssColorString('#34c759'), pixelOffset: new Cesium.Cartesian2(0, -20) }
      });
    } else {
      cesiumEntities.gpsMarker.position = Cesium.Cartesian3.fromDegrees(gps.lon, gps.lat, 0);
    }
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

function deleteController(id) {
  lastControllersJson = "";
  localControllers = localControllers.filter(c => String(c.id) !== String(id));
  
  if (controllerMarkers[id]) { map.removeLayer(controllerMarkers[id]); delete controllerMarkers[id]; }
  if (blindConeCircles[id]) { map.removeLayer(blindConeCircles[id]); delete blindConeCircles[id]; }
  
  if (cesiumViewer) {
    if (cesiumEntities.controllers[id]) { cesiumViewer.entities.remove(cesiumEntities.controllers[id]); delete cesiumEntities.controllers[id]; }
    if (cesiumEntities.blindCones[id]) { cesiumViewer.entities.remove(cesiumEntities.blindCones[id]); delete cesiumEntities.blindCones[id]; }
  }

  renderControllers(localControllers);

  fetch('/api/delete_controller', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id })
  });
}

function renderAircraft(aircraftList, controllers) {
  if (currentMapMode === '2D') {
    renderAircraft2D(aircraftList, controllers);
  } else {
    renderAircraft3D(aircraftList, controllers);
  }
}

// RENDER AEREI MAPPA 2D
function renderAircraft2D(aircraftList, controllers) {
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

// SELEZIONE TARGET SENZA RIMBALZI CON AGGIORNAMENTO FEED
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
  const altMeters = parseFloat(alt) * 0.3048;

  if (lat && lon) {
    if (currentMapMode === '2D') {
      map.panTo([lat, lon]);
    } else if (cesiumViewer) {
      cesiumViewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(lon, lat, Math.max(altMeters + 10000, 15000)),
        orientation: {
          heading: Cesium.Math.toRadians(0.0),
          pitch: Cesium.Math.toRadians(-90.0),
          roll: 0.0
        },
        duration: 1.2
      });
    }
  }

  lastFeedJson = "";
  renderAircraftFeed(latestAircraftList);
  renderAircraft(latestAircraftList, localControllers);
}

// RENDER FEED AEREI CON CACHE DIFFING (ZERO FLICKER / ZERO RIMBALZI MID-CLICK)
function renderAircraftFeed(aircraftList) {
  const container = document.getElementById('aircraft-feed-container');
  const countEl = document.getElementById('ac-count');
  if (!container) return;

  if (countEl) countEl.innerText = aircraftList.length;

  if (aircraftList.length === 0) {
    container.innerHTML = '<div style="font-size: 12px; color: var(--text-sub); text-align: center; padding: 12px;">Nessun aereo rilevato</div>';
    lastFeedJson = "";
    return;
  }

  const currentFeedJson = JSON.stringify(aircraftList.map(a => `${a.icao}_${a.current_data[10]}_${a.current_data[11]}_${a.current_data[12]}_${a.assigned_ctrl}_${a.icao === currentSelectedIcao}`));
  
  if (currentFeedJson === lastFeedJson) {
    return;
  }
  lastFeedJson = currentFeedJson;

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

function renderAircraft3D(aircraftList, controllers) {
  if (!cesiumViewer) return;

  aircraftList.forEach(ac => {
    const lat = parseFloat(ac.current_data[14]);
    const lon = parseFloat(ac.current_data[15]);
    const altFeet = parseFloat(ac.current_data[11] || 0);
    const heading = parseFloat(ac.current_data[13] || 0);
    const altMeters = altFeet * 0.3048;
    if (!lat || !lon) return;

    const callsign = ac.current_data[10] || ac.icao;
    const isBlind = ac.in_blind_cone;
    const isSelected = ac.icao === currentSelectedIcao;

    let colorHex = isBlind ? '#ff9500' : '#007aff';
    if (isSelected) colorHex = '#af52de';
    const cesiumColor = Cesium.Color.fromCssColorString(colorHex);

    const position3D = Cesium.Cartesian3.fromDegrees(lon, lat, altMeters);
    const groundPosition3D = Cesium.Cartesian3.fromDegrees(lon, lat, 0);

    const headingRad = Cesium.Math.toRadians(heading);
    const modelHeadingOffset = Cesium.Math.toRadians(-90.0);
    const modelPitchOffset   = Cesium.Math.toRadians(90.0);
    const modelRollOffset    = Cesium.Math.toRadians(-90.0);
    
    const hpr = new Cesium.HeadingPitchRoll(
      headingRad + modelHeadingOffset,
      modelPitchOffset,
      modelRollOffset
    );
    const orientation = Cesium.Transforms.headingPitchRollQuaternion(position3D, hpr);

    // 1. UPDATE O CREA MODELLINO AEREO 3D (DIMENSIONE RIDOTTA A 22px)
    if (!cesiumEntities.aircraft[ac.icao]) {
      const entity = cesiumViewer.entities.add({
        position: position3D,
        orientation: orientation,
        model: {
          uri: '/static/assets/11803_Airplane_v1_l1.glb',
          minimumPixelSize: 22, // Ridotta dimensione minimia
          maximumScale: 200,    // Ridotta scala massima
          color: cesiumColor,
          colorBlendMode: Cesium.ColorBlendMode.MIX,
          colorBlendAmount: 0.75
        },
        label: {
          text: `${callsign}\n${altFeet} ft`,
          font: 'bold 11px sans-serif',
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          outlineWidth: 2,
          outlineColor: Cesium.Color.BLACK,
          fillColor: cesiumColor,
          pixelOffset: new Cesium.Cartesian2(0, -22)
        }
      });
      entity.icao = ac.icao;
      cesiumEntities.aircraft[ac.icao] = entity;
    } else {
      const entity = cesiumEntities.aircraft[ac.icao];
      entity.position = position3D;
      entity.orientation = orientation;
      if (entity.model) {
        entity.model.color = cesiumColor;
      }
      entity.label.text = `${callsign}\n${altFeet} ft`;
      entity.label.fillColor = cesiumColor;
    }

    // 2. UPDATE O CREA LINEA DI CADUTA VERTICALE A TERRA
    const dropPositions = [position3D, groundPosition3D];
    if (!cesiumEntities.dropLines[ac.icao]) {
      const dropEntity = cesiumViewer.entities.add({
        polyline: {
          positions: dropPositions,
          width: 1,
          material: cesiumColor.withAlpha(0.35)
        }
      });
      dropEntity._lastColorHex = colorHex;
      cesiumEntities.dropLines[ac.icao] = dropEntity;
    } else {
      const dropEntity = cesiumEntities.dropLines[ac.icao];
      dropEntity.polyline.positions = dropPositions;
      if (dropEntity._lastColorHex !== colorHex) {
        if (dropEntity.polyline.material && dropEntity.polyline.material.color) {
          dropEntity.polyline.material.color.setValue(cesiumColor.withAlpha(0.35));
        }
        dropEntity._lastColorHex = colorHex;
      }
    }

    // 3. VETTORE TRATTEGGIATO 3D VERSO IL CONTROLLORE (ZERO FLICKER CON CACHE PROPRIETÀ)
    if (ac.assigned_ctrl && controllers) {
      const ctrl = controllers.find(c => String(c.id) === String(ac.assigned_ctrl));
      if (ctrl) {
        const ctrlPos3D = Cesium.Cartesian3.fromDegrees(ctrl.lon, ctrl.lat, 0);
        const assignPositions = [position3D, ctrlPos3D];
        const targetWidth = isSelected ? 2.5 : 1.2;

        if (!cesiumEntities.assignmentLines[ac.icao]) {
          const assignEntity = cesiumViewer.entities.add({
            polyline: {
              positions: assignPositions,
              width: targetWidth,
              material: new Cesium.PolylineDashMaterialProperty({
                color: cesiumColor,
                dashLength: 12.0
              })
            }
          });
          assignEntity._lastColorHex = colorHex;
          assignEntity._lastWidth = targetWidth;
          cesiumEntities.assignmentLines[ac.icao] = assignEntity;
        } else {
          const assignEntity = cesiumEntities.assignmentLines[ac.icao];
          
          assignEntity.polyline.positions = assignPositions;

          // Aggiorna lo spessore SOLO se effettivamente cambiato
          if (assignEntity._lastWidth !== targetWidth) {
            assignEntity.polyline.width = targetWidth;
            assignEntity._lastWidth = targetWidth;
          }

          // Aggiorna il colore SOLO se effettivamente cambiato
          if (assignEntity._lastColorHex !== colorHex) {
            if (assignEntity.polyline.material && assignEntity.polyline.material.color) {
              assignEntity.polyline.material.color.setValue(cesiumColor);
            }
            assignEntity._lastColorHex = colorHex;
          }
        }
      } else if (cesiumEntities.assignmentLines[ac.icao]) {
        cesiumViewer.entities.remove(cesiumEntities.assignmentLines[ac.icao]);
        delete cesiumEntities.assignmentLines[ac.icao];
      }
    } else if (cesiumEntities.assignmentLines[ac.icao]) {
      cesiumViewer.entities.remove(cesiumEntities.assignmentLines[ac.icao]);
      delete cesiumEntities.assignmentLines[ac.icao];
    }
  });

  // PULIZIA AEREI NON PIÙ PRESENTI
  Object.keys(cesiumEntities.aircraft).forEach(icao => {
    if (!aircraftList.find(a => a.icao === icao)) {
      if (cesiumEntities.aircraft[icao]) { cesiumViewer.entities.remove(cesiumEntities.aircraft[icao]); delete cesiumEntities.aircraft[icao]; }
      if (cesiumEntities.dropLines[icao]) { cesiumViewer.entities.remove(cesiumEntities.dropLines[icao]); delete cesiumEntities.dropLines[icao]; }
      if (cesiumEntities.assignmentLines[icao]) { cesiumViewer.entities.remove(cesiumEntities.assignmentLines[icao]); delete cesiumEntities.assignmentLines[icao]; }
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