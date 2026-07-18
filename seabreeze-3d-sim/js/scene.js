// SeaBreeze Inspector - 3D Scene (render-only, no physics)
// =============================================================================
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { buildDrone, buildTurbine, buildEnvironment, buildWindParticles } from './models.js';
import { CFG } from './config.js';

// 后端 z-up (x东, y北, z高度) → three.js y-up (x右, y上, z屏幕外)
// 映射: three.x = b.x, three.y = b.z, three.z = -b.y
function b2t(p) { return [p[0], p[2], -p[1]]; }

export class SimScene {
  constructor(containerId) {
    // Renderer
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    document.getElementById(containerId).appendChild(this.renderer.domElement);

    // Scene
    this.scene = new THREE.Scene();
    buildEnvironment(this.scene);

    // Camera
    this.camera = new THREE.PerspectiveCamera(55, 2, 0.1, 500);
    this.camera.position.set(...CFG.CAMERA_INITIAL);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = Math.PI * 0.52;
    this.controls.target.set(...CFG.LOOKAT_INITIAL);

    // Entities
    this.turbine = buildTurbine();
    const tp = b2t(CFG.TURBINE_POS);  // CFG 存后端 z-up 坐标, 渲染前转换
    this.turbine.group.position.set(tp[0], tp[1], tp[2]);
    this.scene.add(this.turbine.group);

    this.drone = buildDrone();
    this.scene.add(this.drone.group);

    this.windPts = buildWindParticles(this.scene);

    // Trail
    this.trailGeo = new THREE.BufferGeometry();
    this.trailPos = new Float32Array(CFG.TRAIL_MAX * 3);
    this.trailGeo.setAttribute('position', new THREE.BufferAttribute(this.trailPos, 3));
    this.trail = new THREE.Line(this.trailGeo, new THREE.LineBasicMaterial({
      color: 0x37c8ff, transparent: true, opacity: 0.85 }));
    this.trail.frustumCulled = false;
    this.scene.add(this.trail);
    this.trailN = 0;
    this.trailT = 0;

    // Mission path line
    this.pathLine = new THREE.Line(new THREE.BufferGeometry(),
      new THREE.LineDashedMaterial({ color: 0xffd24a, dashSize: 0.3, gapSize: 0.2 }));
    this.pathLine.frustumCulled = false;
    this.scene.add(this.pathLine);

    // Inspection marker
    this.inspectMarker = new THREE.Mesh(
      new THREE.SphereGeometry(0.15, 16, 12),
      new THREE.MeshBasicMaterial({ color: 0x4aff7a, transparent: true, opacity: 0.9 }));
    this.inspectMarker.visible = false;
    this.scene.add(this.inspectMarker);

    // State
    this.propSpin = 0;
    this._prevState = 'IDLE';
    this.chaseCam = false;

    // Resize
    this._resize();
    window.addEventListener('resize', () => this._resize());
  }

  _resize() {
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
  }

  /** Per-frame update: position entities from API data, render */
  update(data, dt) {
    const pos = data.pos || [0, 0, 0];
    const vel = data.vel || [0, 0, 0];
    const wind = data.wind || [0, 0, 0];

    // Drone position (后端 z-up → three y-up)
    const dp = b2t(pos);
    this.drone.group.position.set(dp[0], dp[1], dp[2]);

    // Tilt: 前飞低头 (rotation.z), 侧飞压坡 (rotation.x)
    const tilt = 0.15;
    this.drone.group.rotation.z = THREE.MathUtils.lerp(this.drone.group.rotation.z, -vel[0] * tilt, 0.1);
    this.drone.group.rotation.x = THREE.MathUtils.lerp(this.drone.group.rotation.x, -vel[1] * tilt, 0.1);

    // Propellers
    const flying = data.state !== 'IDLE' && data.state !== 'LAND';
    this.propSpin = THREE.MathUtils.lerp(this.propSpin, flying ? 60 : 0, 0.05);
    for (const p of this.drone.props) p.rotation.y += this.propSpin * dt;

    // Arm angles
    if (data.arm_angles && this.drone.arm) {
      this.drone.arm.setAngles(data.arm_angles[0], data.arm_angles[1], data.arm_angles[2]);
    }

    // Turbine blades
    this.turbine.rotor.rotation.x += (0.4 + Math.hypot(wind[0] || 0, wind[2] || 0) * 0.8) * dt;

    // Wind particles (wind 为后端 z-up: three.z = -wind.y)
    const wp = this.windPts.geometry.attributes.position;
    for (let i = 0; i < wp.count; i++) {
      wp.array[i * 3] += (0.5 + (wind[0] || 0) * 3) * dt;
      wp.array[i * 3 + 2] += -(wind[1] || 0) * 3 * dt;
      if (wp.array[i * 3] > 20) wp.array[i * 3] = -20;
      if (wp.array[i * 3 + 2] > 20) wp.array[i * 3 + 2] = -20;
      if (wp.array[i * 3 + 2] < -20) wp.array[i * 3 + 2] = 20;
    }
    wp.needsUpdate = true;

    // Trail (pos[2] 是后端 z-up 高度; 轨迹点转 three 坐标)
    this.trailT += dt;
    if (this.trailT >= 0.1 && pos[2] > 0.05) {
      this.trailT = 0;
      const tp2 = b2t(pos);
      if (this.trailN < CFG.TRAIL_MAX) {
        this.trailPos[this.trailN * 3] = tp2[0];
        this.trailPos[this.trailN * 3 + 1] = tp2[1];
        this.trailPos[this.trailN * 3 + 2] = tp2[2];
        this.trailN++;
      } else {
        this.trailPos.copyWithin(0, 3);
        this.trailPos[(CFG.TRAIL_MAX - 1) * 3] = tp2[0];
        this.trailPos[(CFG.TRAIL_MAX - 1) * 3 + 1] = tp2[1];
        this.trailPos[(CFG.TRAIL_MAX - 1) * 3 + 2] = tp2[2];
      }
      this.trailGeo.attributes.position.needsUpdate = true;
      this.trailGeo.setDrawRange(0, this.trailN);
    }
    if (data.state === 'IDLE' && this.trailN > 0) {
      this.trailN = 0;
      this.trailGeo.setDrawRange(0, 0);
    }

    // State transitions: draw mission path
    if (data.state !== this._prevState) {
      if (data.state === 'NAVIGATE') {
        this._drawMissionPath(pos);
      } else if (data.state === 'RETURN') {
        this._drawReturnPath(pos);
      }
      this._prevState = data.state;
    }

    // Inspection marker pulse
    if (this.inspectMarker.visible) {
      const s = 1 + 0.3 * Math.sin(performance.now() * 0.005);
      this.inspectMarker.scale.setScalar(s);
      if (data.state === 'IDLE') this.inspectMarker.visible = false;
    }

    // Chase camera (pos 转 three 坐标)
    if (this.chaseCam) {
      const cp = b2t(pos);
      const p = new THREE.Vector3(cp[0], cp[1], cp[2]);
      this.controls.target.copy(p);
      this.controls.target.y += 1;
      const chase = p.clone();
      chase.x += 3; chase.y += 2; chase.z += 3;
      this.camera.position.lerp(chase, 0.05);
    }

    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  toggleChase() {
    this.chaseCam = !this.chaseCam;
    if (!this.chaseCam) {
      this.controls.target.set(...CFG.LOOKAT_INITIAL);
      this.camera.position.set(...CFG.CAMERA_INITIAL);
    }
  }

  _drawMissionPath(fromPos) {
    const t = CFG.TURBINE_POS;  // 后端 z-up
    // 巡检路径: 当前点 → 风机西侧接近点 → 塔面巡检点 (z-up 下先算好再转 three)
    const raw = [
      fromPos,
      [t[0] - 5, t[1] - 8, 4.0],
      [t[0] - 2.6, t[1], 4.2],
    ];
    const pts = raw.map(p => { const q = b2t(p); return new THREE.Vector3(q[0], q[1], q[2]); });
    this.pathLine.geometry.setFromPoints(pts);
    this.pathLine.computeLineDistances();
    this.inspectMarker.position.copy(pts[pts.length - 1]);
    this.inspectMarker.visible = true;
  }

  _drawReturnPath(fromPos) {
    const home = b2t([0, 0, 1.2]);
    const f = b2t(fromPos);
    const pts = [
      new THREE.Vector3(f[0], f[1], f[2]),
      new THREE.Vector3(home[0], home[1], home[2]),
    ];
    this.pathLine.geometry.setFromPoints(pts);
    this.pathLine.computeLineDistances();
    this.inspectMarker.visible = false;
  }
}
