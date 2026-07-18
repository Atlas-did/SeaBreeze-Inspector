// =============================================================================
// HUD — DOM 面板绑定 (遥测 + 机械臂滑块)
// =============================================================================
import * as THREE from 'three';

const $ = (id) => document.getElementById(id);

export class HUD {
  constructor(arm, input) {
    this.arm = arm;
    this.input = input;
    this._fpsAcc = 0; this._fpsN = 0; this._fps = 60;
    this._eeTmp = new THREE.Vector3();
    this._bindSliders();
    this._bindPresets();
    this._camCanvas = document.getElementById('cam-canvas');
    this._camCtx = this._camCanvas ? this._camCanvas.getContext('2d') : null;
    this._camOverlay = document.getElementById('cam-overlay');
    this._detList = document.getElementById('det-list');
    this._detTimer = 0;
    this._mockDets = [];
    this._initCamera();
  }

  _initCamera() {
    if (!this._camCtx) return;
    this._camCtx.fillStyle = '#0a2a15';
    this._camCtx.fillRect(0, 0, 300, 220);
    this._camCtx.fillStyle = '#4dd0a0';
    this._camCtx.font = '12px monospace';
    this._camCtx.fillText('CAMERA FEED', 100, 110);
  }

  _bindSliders() {
    const lims = [[0, 180], [15, 165], [0, 180]];
    for (let i = 0; i < 3; i++) {
      const el = $(`j${i}`);
      el.addEventListener('input', () => {
        this.input.angles[i] = parseFloat(el.value);
        this.arm.setAngles(...this.input.angles);
        this._label(i);
      });
    }
  }

  _bindPresets() {
    document.querySelectorAll('#arm-panel .btn-row button').forEach((btn) => {
      btn.addEventListener('click', () => {
        const p = btn.dataset.preset.split(',').map(Number);
        this.input.angles = p;
        this.arm.setAngles(...p);
        this.syncSliders(p);
      });
    });
  }

  _label(i) { $(`j${i}-v`).textContent = `${Math.round(this.input.angles[i])}°`; }

  syncSliders(angles) {
    for (let i = 0; i < 3; i++) {
      $(`j${i}`).value = angles[i];
      this._label(i);
    }
  }

  update(sim, droneGroup, turbinePos, dt) {
    // FPS (每 30 帧更新一次显示)
    this._fpsAcc += dt; this._fpsN++;
    if (this._fpsAcc >= 0.5) {
      this._fps = Math.round(this._fpsN / this._fpsAcc);
      this._fpsAcc = 0; this._fpsN = 0;
      $('t-fps').textContent = this._fps;
    }

    $('t-state').textContent = sim.state;
    $('t-batt').textContent = `${Math.round(sim.battery)}%`;
    const bar = $('t-batt-bar');
    bar.style.width = `${sim.battery}%`;
    bar.classList.toggle('low', sim.battery < 20);

    const f = (v) => `[${v.x.toFixed(1)}, ${v.y.toFixed(1)}, ${v.z.toFixed(1)}]`;
    $('t-pos').textContent = f(sim.pos);
    $('t-vel').textContent = f(sim.vel);
    $('t-wind').textContent = `[${sim.wind.x.toFixed(2)}, ${sim.wind.z.toFixed(2)}]`;
    $('t-dist').textContent = `${Math.hypot(data.pos[0] - turbinePos.x, data.pos[2] - turbinePos.z).toFixed(1)} m`;
    $('t-target').textContent = sim.state === 'HOVERING' || sim.state === 'NAVIGATE' ? f(sim.target) : '—';

    var stEl = $('t-safety-tier');
    if (stEl) {
      if (sim._emergency) { stEl.textContent = 'EMERGENCY'; stEl.className = 'v err'; }
      else if (sim.battery < 15) { stEl.textContent = 'WARN-LOW'; stEl.className = 'v warn'; }
      else if (sim.battery < 30) { stEl.textContent = 'WARN'; stEl.className = 'v warn'; }
      else { stEl.textContent = 'NOMINAL'; stEl.className = 'v ok'; }
    }

    // 末端执行器世界坐标 (FK 验证: 与 04 文档 §4 一致)
    this.arm.ee.getWorldPosition(this._eeTmp);
    const mm = this._eeTmp.multiplyScalar(100);   // 场景单位→mm (×0.01→mm 的倒数)
    $('t-ee').textContent = `[${mm.x.toFixed(0)}, ${mm.y.toFixed(0)}, ${mm.z.toFixed(0)}] mm`;
  }

  /** Update from Python backend API data */
  updateFromAPI(data, turbinePos, dt) {
    this._fpsAcc += dt; this._fpsN++;
    if (this._fpsAcc >= 0.5) {
      t-fps.textContent = data.fps || 60;
      this._fpsAcc = 0; this._fpsN = 0;
    }

    t-state.textContent = data.state || 'IDLE';
    t-batt.textContent = Math.round(data.battery || 100) + '%';
    var bar = t-batt-bar;
    bar.style.width = (data.battery || 100) + '%';
    bar.classList.toggle('low', (data.battery || 100) < 20);

    var f3 = function(v) {
      if (!v || v.length < 3) return '[0,0,0]';
      return '[' + v[0].toFixed(1) + ', ' + v[1].toFixed(1) + ', ' + v[2].toFixed(1) + ']';
    };
    t-pos.textContent = f3(data.pos);
    t-vel.textContent = f3(data.vel);
    t-wind.textContent = '[' + (data.wind ? data.wind[0].toFixed(2) : '0.00') + ', ' + (data.wind ? data.wind[2].toFixed(2) : '0.00') + ']';

    if (turbinePos && data.pos) {
      var dx = data.pos[0] - turbinePos.x;
      var dz = data.pos[2] - turbinePos.z;
      t-dist.textContent = Math.hypot(dx, dz).toFixed(1) + ' m';
    }

    t-target.textContent = (data.state === 'HOVERING' || data.state === 'NAVIGATE') ? f3(data.pos) : '--';

    // EKF
    var mahal = data.ekf_mahal || 0;
    t-ekf.textContent = 'D=' + mahal.toFixed(1);
    t-ekf.className = 'v ' + (mahal < 5 ? 'ok' : mahal < 10 ? 'warn' : 'err');

    // Safety
    var st = data.safety_tier || 'NOMINAL';
    t-safety-tier.textContent = st;
    t-safety-tier.className = 'v ' + (st === 'EMERGENCY' ? 'err' : st === 'WARN' ? 'warn' : 'ok');

    // EE
    if (data.arm_endpoint) {
      t-ee.textContent = '[' + data.arm_endpoint.map(function(v) { return Math.round(v); }).join(', ') + '] mm';
    }

    // Camera + detections
    this._detTimer += dt;
    if (this._detTimer > 1.0) {
      this._detTimer = 0;
      this._updateCamera(data, null, turbinePos);
    }
  }

    _updateCamera(data, droneGroup, turbinePos) {
    if (!this._camCtx) return;
    var ctx = this._camCtx;
    var W = 300, H = 220;

    // Dark background
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, W, H);

    // Grid overlay
    ctx.strokeStyle = '#1a3a2a';
    ctx.lineWidth = 0.5;
    for (var x = 0; x < W; x += 30) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
    for (var y = 0; y < H; y += 30) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }

    // Check distance to turbine
    var dist = Math.hypot(data.pos[0] - turbinePos.x, data.pos[2] - turbinePos.z);
    var state = data.state || 'IDLE';
    var isClose = (state === 'HOVERING' || state === 'INSPECT' || state === 'NAVIGATE') && dist < 15;

    if (isClose) {
      // Draw turbine silhouette
      ctx.fillStyle = '#2a4a3a';
      ctx.fillRect(120, 30, 60, 160);
      ctx.fillStyle = '#1a2a1a';
      ctx.fillRect(100, 20, 100, 20);

      // Mock detections
      this._mockDets = [
        { cls: 'crack', conf: 0.82 + Math.random() * 0.08, x: 130, y: 60, w: 40, h: 20 },
        { cls: 'corrosion', conf: 0.71 + Math.random() * 0.12, x: 160, y: 110, w: 50, h: 25 },
      ];
      if (dist < 8) {
        this._mockDets.push({ cls: 'rust', conf: 0.65 + Math.random() * 0.15, x: 140, y: 150, w: 35, h: 18 });
      }

      // Draw detection boxes
      for (var i = 0; i < this._mockDets.length; i++) {
        var d = this._mockDets[i];
        ctx.strokeStyle = d.conf > 0.75 ? '#ff4444' : '#ffaa22';
        ctx.lineWidth = 2;
        ctx.strokeRect(d.x, d.y, d.w, d.h);
        ctx.fillStyle = d.conf > 0.75 ? '#ff4444' : '#ffaa22';
        ctx.font = '10px monospace';
        ctx.fillText(d.cls + ' ' + Math.round(d.conf * 100) + '%', d.x + 2, d.y - 2);
      }

      // Update detection list
      if (this._detList) {
        this._detList.innerHTML = this._mockDets.map(function(d) {
          return '<div class="det-item">' + d.cls + ' <span class="conf">' + Math.round(d.conf * 100) + '%</span></div>';
        }).join('');
      }
    } else {
      this._mockDets = [];
      if (this._detList) this._detList.innerHTML = '<div class="det-item" style="color:#7fa8c8">No targets</div>';
      ctx.fillStyle = '#3a6a4a';
      ctx.font = '14px monospace';
      ctx.fillText('SCANNING...', 95, 110);
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
    ctx.fillText('DIST: ' + dist.toFixed(1) + 'm | ' + state, 8, H - 6);
  }

}