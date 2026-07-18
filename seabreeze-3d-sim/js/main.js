// SeaBreeze Inspector - Main Entry
// =============================================================================
import { SimScene } from './scene.js';
import { HUD } from './hud.js';
import { backend } from './api.js';
import { CFG } from './config.js';

const scene = new SimScene('app');
const hud = new HUD();

// Keyboard forwarding
const keyLastSent = {};
let cWasPressed = false;

window.addEventListener('keydown', function(e) {
  e.preventDefault();
  if (e.code === 'KeyC') {
    if (!cWasPressed) { cWasPressed = true; scene.toggleChase(); }
    return;
  }
  if (CFG.FORWARD_KEYS.has(e.code)) {
    var now = Date.now();
    if (!keyLastSent[e.code] || now - keyLastSent[e.code] > CFG.KEY_REPEAT_MS) {
      keyLastSent[e.code] = now;
      backend.sendKey(e.code);
    }
  }
});

window.addEventListener('keyup', function(e) {
  if (e.code === 'KeyC') cWasPressed = false;
  delete keyLastSent[e.code];
});

// Main loop
var lastTime = performance.now();
var pollTimer = 0;
var logTimer = 0;
var latestData = null;

function animate() {
  requestAnimationFrame(animate);

  var now = performance.now();
  var dt = Math.min(0.05, (now - lastTime) / 1000);
  lastTime = now;

  // Poll backend
  pollTimer += dt;
  if (pollTimer >= CFG.POLL_INTERVAL_MS / 1000) {
    pollTimer = 0;
    backend.fetchState().then(function(data) {
      if (data && data.pos) {
        latestData = data;
        scene.update(data, dt);
        hud.update(data, dt);

        logTimer += CFG.POLL_INTERVAL_MS / 1000;
        if (logTimer >= CFG.CONSOLE_LOG_INTERVAL) {
          logTimer = 0;
          console.log('State:', data.state, 'Batt:', Math.round(data.battery || 0) + '%',
            'EKF D=', (data.ekf_mahal || 0).toFixed(1),
            'Online:', backend.isOnline());
          window.__simData = data;
        }
      }
    });
  }

  // Fallback render with last known data
  if (latestData) {
    scene.update(latestData, dt);
    hud.update(latestData, dt);
  }
}

// Kick off first render immediately
scene.update({ pos: [0, 0, 0], vel: [0, 0, 0], state: 'IDLE', battery: 100,
  wind: [0, 0, 0], arm_angles: [90, 90, 45], arm_endpoint: [0, -57, 112],
  ekf_mahal: 0, safety_tier: 'NOMINAL', detections: [], fps: 0 }, 0);

animate();
