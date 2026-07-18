// SeaBreeze Inspector - Main Entry
// =============================================================================
import { SimScene } from './scene.js';
import { HUD } from './hud.js';
import { backend } from './api.js';
import { CFG } from './config.js';

const scene = new SimScene('app');
const hud = new HUD();

// =============================================================================
// Keyboard input layer
//   - 只 preventDefault 游戏键, 不杀 F5/F12/滑块箭头
//   - 一次性键 (Space/R/E/M) 忽略 auto-repeat, 防按住连发
//   - 持续键 (WASD/PgUp/PgDn/Arrows) 按住期间 ~80ms 心跳刷新 (后端 TTL 0.6s)
//   - 窗口失焦/隐藏 → 全部释放, 防按键卡死
//   - 检测中文输入法 (229/Process/composition) → 屏幕横幅警告
// =============================================================================
const ONESHOT_KEYS = new Set(['Space', 'KeyR', 'KeyE', 'KeyM']);
const heldKeys = new Set();
const keyLastSent = {};
let cWasPressed = false;

// ---- IME 警告横幅 ----
const imeBanner = document.createElement('div');
imeBanner.style.cssText = 'position:fixed;top:34px;left:50%;transform:translateX(-50%);' +
  'padding:6px 18px;background:#c88737;color:#fff;font:13px monospace;z-index:101;' +
  'border-radius:6px;display:none;box-shadow:0 2px 12px rgba(0,0,0,0.4);';
imeBanner.textContent = '⚠ 检测到中文输入法 — 字母键可能被吞! 请切英文键盘 (Win+Space)';
document.body.appendChild(imeBanner);
let imeTimer = null;

function showImeWarning() {
  imeBanner.style.display = 'block';
  if (imeTimer) clearTimeout(imeTimer);
  imeTimer = setTimeout(() => { imeBanner.style.display = 'none'; }, 3000);
}

window.addEventListener('compositionstart', showImeWarning);

function isImeEvent(e) {
  // IME 组合期间, 浏览器收到 keyCode 229 / key==='Process' 的占位事件
  return e.keyCode === 229 || e.isComposing || e.key === 'Process';
}

function releaseAllKeys() {
  for (const code of heldKeys) backend.sendKey(code + '_UP');
  heldKeys.clear();
  for (const k in keyLastSent) delete keyLastSent[k];
}

window.addEventListener('keydown', function (e) {
  if (isImeEvent(e)) { showImeWarning(); return; }

  // 相机切换 (纯前端, 不转发)
  if (e.code === 'KeyC') {
    e.preventDefault();
    if (!cWasPressed) { cWasPressed = true; scene.toggleChase(); }
    return;
  }

  if (!CFG.FORWARD_KEYS.has(e.code)) return;  // 非游戏键: 放行 (F5/F12/Tab...)
  e.preventDefault();

  // 一次性键: 只在首次按下触发, 忽略按住连发
  if (ONESHOT_KEYS.has(e.code)) {
    if (!e.repeat) backend.sendKey(e.code);
    return;
  }

  // 持续键: 首次按下 + auto-repeat 心跳 (节流 KEY_REPEAT_MS)
  const now = Date.now();
  if (!heldKeys.has(e.code)) {
    heldKeys.add(e.code);
    keyLastSent[e.code] = now;
    backend.sendKey(e.code);
  } else if (now - (keyLastSent[e.code] || 0) > CFG.KEY_REPEAT_MS) {
    keyLastSent[e.code] = now;
    backend.sendKey(e.code);  // 心跳刷新后端 TTL
  }
});

window.addEventListener('keyup', function (e) {
  if (e.code === 'KeyC') { cWasPressed = false; return; }
  if (heldKeys.delete(e.code)) {
    delete keyLastSent[e.code];
    backend.sendKey(e.code + '_UP');
  }
});

// 失焦/切页 → 释放全部按键 (防 drone 幽灵飞行)
window.addEventListener('blur', releaseAllKeys);
document.addEventListener('visibilitychange', function () {
  if (document.hidden) releaseAllKeys();
});

// =============================================================================
// Main loop
// =============================================================================
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
    backend.fetchState().then(function (data) {
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
