// SeaBreeze Inspector - 3D Inspection Sim (API-driven)
// Python backend provides state via /api/state, JS does rendering only
// =============================================================================
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { buildDrone, buildTurbine, buildEnvironment, buildWindParticles } from './models.js';
import { HUD } from './hud.js';

const API = '/api/state';

// Renderer / Scene / Camera
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.getElementById('app').appendChild(renderer.domElement);

const scene = new THREE.Scene();
buildEnvironment(scene);

const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 500);
camera.position.set(6, 4, 8);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.maxPolarAngle = Math.PI * 0.52;
controls.target.set(0, 1.5, 0);

// Entities
const turbine = buildTurbine();
turbine.group.position.set(9, 0, -2);
scene.add(turbine.group);

const drone = buildDrone();
scene.add(drone.group);

const windPts = buildWindParticles(scene);

// Trail
const TRAIL_MAX = 400;
const trailGeo = new THREE.BufferGeometry();
const trailPos = new Float32Array(TRAIL_MAX * 3);
trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPos, 3));
const trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({
  color: 0x37c8ff, transparent: true, opacity: 0.85 }));
trail.frustumCulled = false;
scene.add(trail);
let trailN = 0, trailT = 0;

// HUD
const hud = new HUD(drone.arm);
const turbinePos = turbine.group.position.clone();

// ---- Keyboard forwarding to backend ----
const keysDown = new Set();
const keyForward = new Set(['Space', 'KeyW', 'KeyA', 'KeyS', 'KeyD',
  'KeyR', 'KeyE', 'KeyM', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown']);
const keyRepeat = {};

window.addEventListener('keydown', function(e) {
  keysDown.add(e.code);
  if (keyForward.has(e.code)) {
    e.preventDefault();
    var now = Date.now();
    if (!keyRepeat[e.code] || now - keyRepeat[e.code] > 80) {
      keyRepeat[e.code] = now;
      fetch('/api/command?key=' + e.code).catch(function(){});
    }
  }
});
window.addEventListener('keyup', function(e) {
  keysDown.delete(e.code);
  delete keyRepeat[e.code];
});

// ---- API polling ----
let simData = {
  pos: [0,0,0], vel: [0,0,0], state: 'IDLE', battery: 100,
  wind: [0,0,0], arm_angles: [90,90,45], arm_endpoint: [0,0,135],
  ekf_mahal: 0, safety_tier: 'NOMINAL', detections: [], fps: 60
};
let chaseCam = false;

function pollState() {
  fetch(API).then(function(r) { return r.json(); }).then(function(data) {
    if (data && data.pos) simData = data;
  }).catch(function(e) {
    console.warn('Backend not reachable:', e.message);
  });
}

// --- Slider forwarding ---
function initSliders() {
  for (var i = 0; i < 3; i++) {
    var el = document.getElementById('j' + i);
    if (!el) continue;
    el.addEventListener('input', function() {
      var angles = [
        parseFloat(document.getElementById('j0').value),
        parseFloat(document.getElementById('j1').value),
        parseFloat(document.getElementById('j2').value)
      ];
      fetch('/api/command?key=arm&a0=' + angles[0] + '&a1=' + angles[1] + '&a2=' + angles[2]).catch(function(){});
    });
  }
  // Preset buttons
  document.querySelectorAll('#arm-panel .btn-row button').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var p = btn.dataset.preset.split(',').map(Number);
      document.getElementById('j0').value = p[0];
      document.getElementById('j1').value = p[1];
      document.getElementById('j2').value = p[2];
      fetch('/api/command?key=arm&a0=' + p[0] + '&a1=' + p[1] + '&a2=' + p[2]).catch(function(){});
    });
  });
}
initSliders();

// Main loop
const clock = new THREE.Clock();
let propSpin = 0, pollTimer = 0, logTimer = 0;

function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.05);

  // Poll backend
  pollTimer += dt;
  if (pollTimer > 0.05) {
    pollTimer = 0;
    pollState();
  }

  // Chase camera toggle
  if (keysDown.has('KeyC') && !window._cPressed) {
    window._cPressed = true;
    chaseCam = !chaseCam;
    if (!chaseCam) {
      controls.target.set(0, 1.5, 0);
      camera.position.set(6, 4, 8);
    }
  }
  if (!keysDown.has('KeyC')) window._cPressed = false;

  // Update drone position from backend
  var pos = new THREE.Vector3(simData.pos[0], simData.pos[1], simData.pos[2]);
  drone.group.position.copy(pos);

  // Tilt based on velocity
  var vel = new THREE.Vector3(simData.vel[0], simData.vel[1], simData.vel[2]);
  var tilt = 0.15;
  drone.group.rotation.z = THREE.MathUtils.lerp(drone.group.rotation.z, -vel.x * tilt, 0.1);
  drone.group.rotation.x = THREE.MathUtils.lerp(drone.group.rotation.x, vel.z * tilt, 0.1);

  // Propeller spin
  var flying = simData.state !== 'IDLE' && simData.state !== 'LAND';
  propSpin = THREE.MathUtils.lerp(propSpin, flying ? 60 : 0, 0.05);
  for (var k = 0; k < drone.props.length; k++) drone.props[k].rotation.y += propSpin * dt;

  // Arm angles from backend
  if (simData.arm_angles && drone.arm) {
    drone.arm.setAngles(simData.arm_angles[0], simData.arm_angles[1], simData.arm_angles[2]);
  }

  // Sync sliders
  if (simData.arm_angles) {
    for (var j = 0; j < 3; j++) {
      var sl = document.getElementById('j' + j);
      var lb = document.getElementById('j' + j + '-v');
      if (sl) sl.value = simData.arm_angles[j];
      if (lb) lb.textContent = Math.round(simData.arm_angles[j]) + ' deg';
    }
  }

  // Turbine blades
  turbine.rotor.rotation.x += (0.4 + (simData.wind ? Math.hypot(simData.wind[0], simData.wind[2]) : 0) * 0.8) * dt;

  // Wind particles
  var wp = windPts.geometry.attributes.position;
  var wx = simData.wind ? simData.wind[0] : 0;
  var wz = simData.wind ? simData.wind[2] : 0;
  for (let i = 0; i < wp.count; i++) {
    wp.array[i * 3] += (0.5 + wx * 3) * dt;
    wp.array[i * 3 + 2] += wz * 3 * dt;
    if (wp.array[i * 3] > 20) wp.array[i * 3] = -20;
    if (wp.array[i * 3 + 2] > 20) wp.array[i * 3 + 2] = -20;
    if (wp.array[i * 3 + 2] < -20) wp.array[i * 3 + 2] = 20;
  }
  wp.needsUpdate = true;

  // Trail
  trailT += dt;
  if (trailT >= 0.1 && pos.y > 0.05) {
    trailT = 0;
    if (trailN < TRAIL_MAX) {
      trailPos[trailN * 3] = pos.x;
      trailPos[trailN * 3 + 1] = pos.y;
      trailPos[trailN * 3 + 2] = pos.z;
      trailN++;
    } else {
      trailPos.copyWithin(0, 3);
      trailPos[(TRAIL_MAX - 1) * 3] = pos.x;
      trailPos[(TRAIL_MAX - 1) * 3 + 1] = pos.y;
      trailPos[(TRAIL_MAX - 1) * 3 + 2] = pos.z;
    }
    trailGeo.attributes.position.needsUpdate = true;
    trailGeo.setDrawRange(0, trailN);
  }
  if (simData.state === 'IDLE' && trailN > 0) {
    trailN = 0; trailGeo.setDrawRange(0, 0);
  }

  // Chase camera
  if (chaseCam) {
    controls.target.copy(pos);
    controls.target.y += 1;
    var chasePos = pos.clone();
    chasePos.x += 3; chasePos.y += 2; chasePos.z += 3;
    camera.position.lerp(chasePos, 0.05);
  }

  // Flight log to console
  logTimer += dt;
  if (logTimer > 10) {
    logTimer = 0;
    console.log('State:', simData.state, 'Batt:', Math.round(simData.battery) + '%',
                'Pos:', pos.x.toFixed(1) + ',' + pos.y.toFixed(1) + ',' + pos.z.toFixed(1),
                'EKF D=', simData.ekf_mahal.toFixed(1), 'Safety:', simData.safety_tier);
    window.__simData = simData;
    window.__dumpState = function() { console.table(simData); };
  }

  hud.updateFromAPI(simData, turbinePos, dt);
  controls.update();
  renderer.render(scene, camera);
}

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

animate();
