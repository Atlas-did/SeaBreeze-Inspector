// SeaBreeze Inspector - HUD (telemetry + camera + arm panel)
// Single update(data) entry point, camera redraws at 10Hz
// =============================================================================
import { CFG } from './config.js';
import { backend } from './api.js';

const $ = (id) => document.getElementById(id);

export class HUD {
  constructor() {
    this._fpsAcc = 0; this._fpsN = 0;
    this._camTimer = 0;
    this._camCtx = null;
    this._mockDets = [];
    this._prevArm = [90, 90, 45];
    this._initSliders();
    this._initBadge();
    this._initCamera();
  }

  // ---- Offline badge ----
  _initBadge() {
    this._badge = document.createElement('div');
    this._badge.id = 'offline-badge';
    this._badge.style.cssText = 'position:fixed;top:0;left:50%;transform:translateX(-50%);padding:4px 16px;' +
      'background:#c83737;color:#fff;font:12px monospace;z-index:100;border-radius:0 0 6px 6px;display:none;';
    this._badge.textContent = 'BACKEND OFFLINE';
    document.body.appendChild(this._badge);
    this._prevOnline = true;
    this._badgeTimer = null;
  }

  // ---- Camera canvas init ----
  _initCamera() {
    const canvas = $('cam-canvas');
    if (!canvas) return;
    this._camCtx = canvas.getContext('2d');
    this._camCtx.fillStyle = '#0a0a0a';
    this._camCtx.fillRect(0, 0, 300, 220);
  }

  // ---- Slider bindings with bidirectional sync ----
  _initSliders() {
    for (let i = 0; i < 3; i++) {
      const el = $('j' + i);
      if (!el) continue;
      el.addEventListener('input', () => {
        const a0 = parseFloat($('j0').value);
        const a1 = parseFloat($('j1').value);
        const a2 = parseFloat($('j2').value);
        backend.sendArm([a0, a1, a2], false);
        this._label(i);
      });
      el.addEventListener('change', () => {
        const a0 = parseFloat($('j0').value);
        const a1 = parseFloat($('j1').value);
        const a2 = parseFloat($('j2').value);
        backend.sendArm([a0, a1, a2], true); // force flush on release
      });
    }
    // Presets
    document.querySelectorAll('#arm-panel .btn-row button').forEach(btn => {
      btn.addEventListener('click', () => {
        const p = btn.dataset.preset.split(',').map(Number);
        $('j0').value = p[0]; $('j1').value = p[1]; $('j2').value = p[2];
        for (let i = 0; i < 3; i++) this._label(i);
        backend.sendArm(p, true);
      });
    });
  }

  _label(i) {
    const el = $('j' + i + '-v');
    if (el) el.textContent = Math.round(parseFloat($('j' + i).value)) + ' deg';
  }

  /** Sync slider UI from backend data (only when user is not dragging) */
  _syncSliders(angles) {
    for (let i = 0; i < 3; i++) {
      const slider = $('j' + i);
      if (!slider) continue;
      if (document.activeElement !== slider) {
        slider.value = angles[i];
        this._label(i);
      }
    }
    this._prevArm = [...angles];
  }

  // ---- Main update ----
  update(data, dt) {
    if (!data) return;

    // Offline badge: 断连红色闪烁, 重连后短暂显示绿色 CONNECTED
    const online = backend.isOnline();
    if (online !== this._prevOnline) {
      this._prevOnline = online;
      if (online) {
        this._badge.textContent = 'CONNECTED';
        this._badge.style.background = '#2e9e5b';
        this._badge.style.display = 'block';
        clearTimeout(this._badgeTimer);
        this._badgeTimer = setTimeout(() => { this._badge.style.display = 'none'; }, 1500);
      } else {
        this._badge.textContent = 'BACKEND OFFLINE';
        this._badge.style.background = '#c83737';
        this._badge.style.display = 'block';
      }
    } else if (!online) {
      this._badge.style.display = 'block';
    }

    // FPS (from backend)
    this._fpsAcc += dt; this._fpsN++;
    if (this._fpsAcc >= 0.5) {
      const el = $('t-fps');
      if (el) el.textContent = data.fps || 0;
      this._fpsAcc = 0; this._fpsN = 0;
    }

    // Core telemetry
    const set = (id, val) => { const e = $(id); if (e) e.textContent = val; };
    set('t-state', data.state || 'IDLE');
    set('t-batt', Math.round(data.battery || 100) + '%');
    const bar = $('t-batt-bar');
    if (bar) { bar.style.width = (data.battery || 100) + '%'; bar.classList.toggle('low', (data.battery || 100) < 20); }

    const f3 = (v) => v ? '[' + v[0].toFixed(1) + ', ' + v[1].toFixed(1) + ', ' + v[2].toFixed(1) + ']' : '[0,0,0]';
    set('t-pos', f3(data.pos));
    set('t-vel', f3(data.vel));
    set('t-wind', '[' + ((data.wind ? data.wind[0] : 0).toFixed(2)) + ', ' + ((data.wind ? data.wind[2] : 0).toFixed(2)) + ']');

    if (data.pos) {
      const t = CFG.TURBINE_POS;
      // z-up: 水平距离用 x-y 平面, 不混入高度 z
      set('t-dist', Math.hypot(data.pos[0] - t[0], data.pos[1] - t[1]).toFixed(1) + ' m');
    }
    set('t-target', (data.state === 'HOVERING' || data.state === 'NAVIGATE') ? f3(data.pos) : '--');

    // EKF
    const mahal = data.ekf_mahal || 0;
    const ekfEl = $('t-ekf');
    if (ekfEl) {
      ekfEl.textContent = 'D=' + mahal.toFixed(1);
      ekfEl.className = 'v ' + (mahal < CFG.EKF_OK ? 'ok' : mahal < CFG.EKF_WARN ? 'warn' : 'err');
    }

    // Safety tier
    const st = data.safety_tier || 'NOMINAL';
    const stEl = $('t-safety-tier');
    if (stEl) {
      stEl.textContent = st;
      stEl.className = 'v ' + (st === 'EMERGENCY' ? 'err' : st.includes('WARN') ? 'warn' : 'ok');
    }

    // End effector
    if (data.arm_endpoint) {
      set('t-ee', '[' + data.arm_endpoint.map(Math.round).join(', ') + '] mm');
    }

    // Slider sync
    if (data.arm_angles) this._syncSliders(data.arm_angles);

    // Camera redraw (at CAMERA_FPS rate)
    this._camTimer += dt;
    if (this._camTimer >= 1 / CFG.CAMERA_FPS) {
      this._camTimer = 0;
      this._renderCamera(data);
    }
  }

  // ---- Camera canvas rendering ----
  _renderCamera(data) {
    const ctx = this._camCtx;
    if (!ctx) return;
    const W = 300, H = 220;

    // Background
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, W, H);

    // Grid
    ctx.strokeStyle = '#1a3a2a';
    ctx.lineWidth = 0.5;
    for (let x = 0; x < W; x += 30) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
    for (let y = 0; y < H; y += 30) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }

    // Distance check (z-up: x-y 水平面)
    const t = CFG.TURBINE_POS;
    const dist = data.pos ? Math.hypot(data.pos[0] - t[0], data.pos[1] - t[1]) : 999;
    const isClose = (data.state === 'HOVERING' || data.state === 'INSPECT' || data.state === 'NAVIGATE') && dist < CFG.DETECTION_RANGE;

    // Detections: prefer backend, fallback to mock
    let dets = (data.detections && data.detections.length > 0) ? data.detections : null;
    if (!dets && isClose) {
      dets = [
        { cls: 'crack', conf: 0.82, bbox: [120, 50, 40, 20] },
        { cls: 'corrosion', conf: 0.71, bbox: [160, 100, 50, 25] },
      ];
      if (dist < 8) dets.push({ cls: 'rust', conf: 0.65, bbox: [140, 150, 35, 18] });
    }

    // Turbine silhouette when close
    if (isClose) {
      ctx.fillStyle = '#1a3a2a';
      ctx.fillRect(120, 30, 60, 160);
      ctx.fillStyle = '#0f1f0f';
      ctx.fillRect(100, 20, 100, 20);
    }

    // Draw detections
    if (dets) {
      for (const d of dets) {
        const b = d.bbox || [100, 80, 40, 30];
        ctx.strokeStyle = d.conf > 0.75 ? '#ff4444' : '#ffaa22';
        ctx.lineWidth = 2;
        ctx.strokeRect(b[0], b[1], b[2], b[3]);
        ctx.fillStyle = d.conf > 0.75 ? '#ff4444' : '#ffaa22';
        ctx.font = '10px monospace';
        ctx.fillText((d.cls || '?') + ' ' + Math.round((d.conf || 0) * 100) + '%', b[0] + 2, b[1] - 2);
      }
      // Detection list
      const list = $('det-list');
      if (list) {
        list.innerHTML = dets.map(d =>
          '<div class="det-item">' + (d.cls || '?') + ' <span class="conf">' + Math.round((d.conf || 0) * 100) + '%</span></div>'
        ).join('');
      }
    } else {
      const list = $('det-list');
      if (list) list.innerHTML = '<div class="det-item" style="color:#7fa8c8">No targets</div>';
      if (!isClose) {
        ctx.fillStyle = '#3a6a4a';
        ctx.font = '14px monospace';
        ctx.fillText('SCANNING...', 95, 110);
      }
    }

    // Crosshair
    ctx.strokeStyle = '#4dd0a044';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(W / 2, 0); ctx.lineTo(W / 2, H); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(W / 2, H / 2, 15, 0, Math.PI * 2); ctx.stroke();

    // Status bar
    ctx.fillStyle = '#00000088';
    ctx.fillRect(0, H - 20, W, 20);
    ctx.fillStyle = '#4dd0a0';
    ctx.font = '10px monospace';
    ctx.fillText('DIST: ' + dist.toFixed(1) + 'm | ' + (data.state || 'IDLE'), 8, H - 6);
  }
}
