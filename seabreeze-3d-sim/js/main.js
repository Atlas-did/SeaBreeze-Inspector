// SeaBreeze Inspector - 3D Inspection Simulation Entry
// Renderer: Three.js | Physics: sim.js (same structure as Python backend)
// =============================================================================
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { buildDrone, buildTurbine, buildEnvironment, buildWindParticles } from './models.js';
import { DroneSim, InputHandler, MissionState } from './sim.js';
import { HUD } from './hud.js';

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

// Inspection path visualization
const pathLine = new THREE.Line(
  new THREE.BufferGeometry(),
  new THREE.LineDashedMaterial({ color: 0xffd24a, dashSize: 0.3, gapSize: 0.2 }));
pathLine.frustumCulled = false;
scene.add(pathLine);
const inspectMarker = new THREE.Mesh(
  new THREE.SphereGeometry(0.15, 16, 12),
  new THREE.MeshBasicMaterial({ color: 0x4aff7a, transparent: true, opacity: 0.9 }));
inspectMarker.visible = false;
scene.add(inspectMarker);

// Simulation + Input + HUD
const sim = new DroneSim();
const hud = new HUD(drone.arm, null);
const input = new InputHandler(sim, drone.arm, hud);
hud.input = input;
const turbinePos = turbine.group.position.clone();

input.onMission = () => {
  if (sim.startMission(turbinePos, turbine.height)) {
    const pts = [sim.pos.clone(), ...sim.waypoints.map((w) => w.clone())];
    pathLine.geometry.setFromPoints(pts);
    pathLine.computeLineDistances();
    inspectMarker.position.copy(sim.waypoints[sim.waypoints.length - 1]);
    inspectMarker.visible = true;
  }
};

// Main loop
const clock = new THREE.Clock();
let propSpin = 0;

function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.05);

  input.tick(dt);

  // Chase camera toggle (C key)
  if (input.keys.has('KeyC') && !input._cPressed) {
    input._cPressed = true;
    input._chaseCam = !input._chaseCam;
    if (!input._chaseCam) {
      controls.target.set(0, 1.5, 0);
      camera.position.set(6, 4, 8);
    }
  }
  if (!input.keys.has('KeyC')) input._cPressed = false;

  if (input._chaseCam) {
    controls.target.copy(sim.pos);
    controls.target.y += 1;
    var chasePos = sim.pos.clone();
    chasePos.x += 3; chasePos.y += 2; chasePos.z += 3;
    camera.position.lerp(chasePos, 0.05);
  }
  sim.step(dt);

  // Drone pose
  drone.group.position.copy(sim.pos);
  const tilt = 0.12;
  drone.group.rotation.z = THREE.MathUtils.lerp(drone.group.rotation.z, -sim.vel.x * tilt, 0.1);
  drone.group.rotation.x = THREE.MathUtils.lerp(drone.group.rotation.x, sim.vel.z * tilt, 0.1);

  // Propeller spin
  const flying = ![MissionState.IDLE, MissionState.LAND].includes(sim.state);
  propSpin = THREE.MathUtils.lerp(propSpin, flying ? 60 : 0, 0.05);
  for (const p of drone.props) p.rotation.y += propSpin * dt;

  // Turbine blades
  turbine.rotor.rotation.x += (0.4 + sim.wind.length() * 0.8) * dt;

  // Wind particles
  const wp = windPts.geometry.attributes.position;
  for (let i = 0; i < wp.count; i++) {
    wp.array[i * 3] += (0.5 + sim.wind.x * 3) * dt;
    wp.array[i * 3 + 2] += sim.wind.z * 3 * dt;
    if (wp.array[i * 3] > 20) wp.array[i * 3] = -20;
    if (wp.array[i * 3 + 2] > 20) wp.array[i * 3 + 2] = -20;
    if (wp.array[i * 3 + 2] < -20) wp.array[i * 3 + 2] = 20;
  }
  wp.needsUpdate = true;

  // Trail
  trailT += dt;
  if (trailT >= 0.1 && sim.pos.y > 0.05) {
    trailT = 0;
    if (trailN < TRAIL_MAX) {
      trailPos[trailN * 3] = sim.pos.x;
      trailPos[trailN * 3 + 1] = sim.pos.y;
      trailPos[trailN * 3 + 2] = sim.pos.z;
      trailN++;
    } else {
      trailPos.copyWithin(0, 3);
      trailPos[(TRAIL_MAX - 1) * 3] = sim.pos.x;
      trailPos[(TRAIL_MAX - 1) * 3 + 1] = sim.pos.y;
      trailPos[(TRAIL_MAX - 1) * 3 + 2] = sim.pos.z;
    }
    trailGeo.attributes.position.needsUpdate = true;
    trailGeo.setDrawRange(0, trailN);
  }
  if (sim.state === MissionState.IDLE && trailN > 0) {
    trailN = 0; trailGeo.setDrawRange(0, 0);
  }

  // Inspection marker pulse
  if (inspectMarker.visible) {
    const s = 1 + 0.3 * Math.sin(clock.elapsedTime * 5);
    inspectMarker.scale.setScalar(s);
    if (sim.state === MissionState.IDLE) inspectMarker.visible = false;
  }

  // EKF approximation and safety tiers
  sim.ekfMahal = sim.vel.length() * 0.5 + sim.wind.length() * 2;  // simplified mahalanobis proxy
  sim.safetyTier = sim._emergency ? 'EMERGENCY' :
    sim.battery < 15 ? 'WARN-LOW' :
    sim.battery < 30 ? 'WARN' : 'NOMINAL';
  sim.heightPct = Math.min(100, Math.round(sim.pos.y / 14 * 100));

  hud.update(sim, drone.group, turbinePos, dt);

  // Periodic flight log dump to console (every 10s)
  sim._logDumpTimer = (sim._logDumpTimer || 0) + dt;
  if (sim._logDumpTimer > 10 && flying) {
    sim._logDumpTimer = 0;
    console.log('--- Flight Log (' + sim.flightLog.length + ' entries) ---');
    console.log('State:', sim.state, 'Battery:', Math.round(sim.battery) + '%',
                'Pos:', sim.pos.x.toFixed(1) + ',' + sim.pos.y.toFixed(1) + ',' + sim.pos.z.toFixed(1));
    // Also expose globally for manual inspection
    window.__flightLog = sim.flightLog;
    window.__dumpLog = function() { sim.dumpLog(); };
  }
  controls.update();
  renderer.render(scene, camera);
}

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

animate();
