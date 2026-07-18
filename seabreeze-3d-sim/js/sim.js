// SeaBreeze Inspector - Simulation Physics and Mission State Machine
// Structure aligned with Python backend MissionController:
//   State machine: IDLE->TAKEOFF->HOVERING<->NAVIGATE->INSPECT->RETURN->LAND / EMERGENCY
//   Control: position-loop PD (Kp*e - Kd*v), damping sign must be negative
//   Wind: sine matrix + random walk (aligned with gym-pybullet-drones noise model)
// =============================================================================
import * as THREE from 'three';

export const MissionState = {
  IDLE: 'IDLE', TAKEOFF: 'TAKEOFF', HOVERING: 'HOVERING',
  NAVIGATE: 'NAVIGATE', INSPECT: 'INSPECT', RETURN: 'RETURN',
  LAND: 'LAND', EMERGENCY: 'EMERGENCY',
};

const HOVER_H = 1.2;
const G = 9.8;

export class DroneSim {
  constructor() {
    this.pos = new THREE.Vector3(0, 0, 0);
    this.vel = new THREE.Vector3();
    this.target = new THREE.Vector3(0, 0, 0);
    this.state = MissionState.IDLE;
    this.battery = 100;
    this.wind = new THREE.Vector3();
    this._windT = 0;
    this.waypoints = [];
    this._wpIdx = 0;
    this._inspectT = 0;
    this._emergency = false;
    // PD gains aligned with drone_config.yaml controller.Kp/Kd
    this.Kp = 4.0;
    this.Kd = 3.2;
    this.maxSpeed = 3.0;
    this.flightLog = [];          // flight event log
    this._logTimer = 0;           // periodic log timer
  }

  // Flight log system
  _log(event, detail) {
    var entry = {
      t: this._simTime || 0,
      event: event,
      detail: detail || '',
      state: this.state,
      pos: this.pos.clone(),
      battery: Math.round(this.battery),
      wind: this.wind.length().toFixed(2)
    };
    this.flightLog.push(entry);
    if (this.flightLog.length > 500) this.flightLog.shift();
    return entry;
  }

  getLog(since) {
    if (!since) return this.flightLog;
    return this.flightLog.filter(function(e) { return e.t >= since; });
  }

  // Wind model: sine matrix + random walk
  _sampleWind(dt) {
    this._windT += dt;
    const gust = new THREE.Vector3(
      0.35 * Math.sin(0.9 * this._windT) + 0.2 * Math.sin(2.3 * this._windT + 1.7),
      0,
      0.3 * Math.sin(0.7 * this._windT + 0.8));
    gust.x += (Math.random() - 0.5) * 0.06;
    gust.z += (Math.random() - 0.5) * 0.06;
    this.wind.lerp(gust, Math.min(dt * 2, 1));
    return this.wind;
  }

  // State machine operations
  takeoff() {
    if (this.state !== MissionState.IDLE) return;
    this.state = MissionState.TAKEOFF;
    this._log('TAKEOFF', 'Hover height: ' + HOVER_H.toFixed(1) + 'm');
    this.target.set(this.pos.x, HOVER_H, this.pos.z);
  }

  land() {
    if (this._emergency) return;
    this.state = MissionState.LAND;
    this._log('LAND', 'Landing at ' + this.pos.x.toFixed(1) + ',' + this.pos.z.toFixed(1));
    this.target.set(this.pos.x, 0, this.pos.z);
  }

  emergency() {
    this._emergency = true;
    this.state = MissionState.EMERGENCY;
    this._log('EMERGENCY', 'Battery: ' + Math.round(this.battery) + '%');
  }

  reset() {
    this.pos.set(0, 0, 0); this.vel.set(0, 0, 0);
    this.target.set(0, 0, 0);
    this.state = MissionState.IDLE;
    this.battery = 100;
    this.waypoints = []; this._wpIdx = 0;
    this._emergency = false; this._inspectT = 0;
    this.flightLog = [];
    this._log('RESET', 'Simulation reset');
  }

  startMission(turbinePos, turbineHeight) {
    if (this.state !== MissionState.HOVERING) return false;
    const inspect = new THREE.Vector3(
      turbinePos.x - 2.6, turbineHeight + 0.3, turbinePos.z);
    this.waypoints = [
      new THREE.Vector3(this.pos.x, turbineHeight + 0.3, this.pos.z),
      new THREE.Vector3(turbinePos.x - 5, turbineHeight + 0.3, turbinePos.z - 4),
      inspect,
    ];
    this._wpIdx = 0;
    this.state = MissionState.NAVIGATE;
    this._log('MISSION', 'Waypoints: ' + this.waypoints.length + ' | Turbine at ' + turbinePos.x.toFixed(1) + ',' + turbinePos.z.toFixed(1));
    return true;
  }

  nudge(dx, dy, dz) {
    if (this.state !== MissionState.HOVERING) return;
    this.target.add(new THREE.Vector3(dx, dy, dz));
    this.target.y = Math.max(0.3, Math.min(14, this.target.y));
    const r = Math.hypot(this.target.x, this.target.z);
    if (r > 20) { this.target.x *= 20 / r; this.target.z *= 20 / r; }
  }

  // Main loop
  step(dt) {
    dt = Math.min(dt, 0.05);
    const wind = this._sampleWind(dt);

    const flying = ![MissionState.IDLE, MissionState.LAND].includes(this.state);
    if (flying) this.battery = Math.max(0, this.battery - dt * 0.55);
    if (this.battery <= 10 && !this._emergency) this.emergency();

    // Periodic flight log (every 2 seconds)
    this._simTime = (this._simTime || 0) + dt;
    this._logTimer += dt;
    if (this._logTimer > 2 && flying) {
      this._logTimer = 0;
      this._log('FLIGHT', 'H=' + this.pos.y.toFixed(1) + ' V=' + this.vel.length().toFixed(2) + ' Bat=' + Math.round(this.battery));
    }

    switch (this.state) {
      case MissionState.TAKEOFF:
        if (Math.abs(this.pos.y - HOVER_H) < 0.05) {
          this.state = MissionState.HOVERING;
          this.target.copy(this.pos);
        }
        break;
      case MissionState.NAVIGATE: {
        const wp = this.waypoints[this._wpIdx];
        this.target.copy(wp);
        if (this.pos.distanceTo(wp) < 0.35) {
          this._wpIdx++;
          if (this._wpIdx >= this.waypoints.length) {
            this.state = MissionState.INSPECT;
            this._inspectT = 0;
          }
        }
        break;
      }
      case MissionState.INSPECT:
        this._inspectT += dt;
        this.target.x += Math.sin(this._inspectT * 0.8) * 0.0015;
        if (this._inspectT > 6) {
          this.state = MissionState.RETURN;
          this.waypoints = [new THREE.Vector3(0, HOVER_H, 0)];
          this._wpIdx = 0;
        }
        break;
      case MissionState.RETURN: {
        const home = this.waypoints[0];
        this.target.copy(home);
        if (this.pos.distanceTo(home) < 0.35) this.state = MissionState.LAND;
    this._log('LAND', 'Landing at ' + this.pos.x.toFixed(1) + ',' + this.pos.z.toFixed(1));
        break;
      }
      case MissionState.LAND:
        if (this.pos.y <= 0.02) {
          this.state = MissionState.IDLE;
          this.vel.set(0, 0, 0);
        }
        break;
    }

    // Position-loop PD (damping negative sign!)
    if (this.state === MissionState.EMERGENCY) {
      this.vel.y -= G * dt;
      this.vel.multiplyScalar(1 - 0.6 * dt);
    } else if (this.state !== MissionState.IDLE) {
      const err = new THREE.Vector3().subVectors(this.target, this.pos);
      const acc = err.multiplyScalar(this.Kp)
        .addScaledVector(this.vel, -this.Kd)
        .add(wind);
      this.vel.addScaledVector(acc, dt);
      if (this.vel.length() > this.maxSpeed) this.vel.setLength(this.maxSpeed);
    }

    this.pos.addScaledVector(this.vel, dt);
    if (this.pos.y < 0) { this.pos.y = 0; this.vel.y = 0;
      if (this.state === MissionState.EMERGENCY) this.state = MissionState.IDLE; }

    return { wind };
  }

  // Export flight log to console
  dumpLog() {
    console.table(this.flightLog.map(function(e) {
      return {
        t: e.t.toFixed(1),
        event: e.event,
        state: e.state,
        x: e.pos.x.toFixed(2),
        y: e.pos.y.toFixed(2),
        z: e.pos.z.toFixed(2),
        bat: e.battery,
        wind: e.wind,
        detail: e.detail
      };
    }));
    return this.flightLog;
  }
}

// Keyboard input
export class InputHandler {
  constructor(sim, arm, hud) {
    this.sim = sim; this.arm = arm; this.hud = hud;
    this.keys = new Set();
    this.angles = [90, 90, 45];

    window.addEventListener('keydown', (e) => this._down(e));
    window.addEventListener('keyup', (e) => this.keys.delete(e.code));
  }

  _down(e) {
    this.keys.add(e.code);
    const s = this.sim;
    switch (e.code) {
      case 'Space':
        e.preventDefault();
        if (s.state === MissionState.IDLE && !s._emergency) s.takeoff();
        else s.land();
        break;
      case 'KeyE': s.emergency(); document.body.classList.add('emergency'); break;
      case 'KeyR': s.reset(); document.body.classList.remove('emergency'); break;
      case 'KeyM': this.onMission && this.onMission(); break;
      case 'ArrowLeft':  this._setJoint(0, this.angles[0] - 2); e.preventDefault(); break;
      case 'ArrowRight': this._setJoint(0, this.angles[0] + 2); e.preventDefault(); break;
      case 'ArrowUp':    this._setJoint(1, this.angles[1] + 2); e.preventDefault(); break;
      case 'ArrowDown':  this._setJoint(1, this.angles[1] - 2); e.preventDefault(); break;
      case 'PageUp': case 'PageDown': e.preventDefault(); break;
    }
  }

  _setJoint(i, v) {
    const lims = [[0, 180], [15, 165], [0, 180]];
    this.angles[i] = Math.max(lims[i][0], Math.min(lims[i][1], v));
    this.arm.setAngles(...this.angles);
    this.hud.syncSliders(this.angles);
  }

  tick(dt) {
    const v = 2.0 * dt, h = 1.5 * dt;
    if (this.keys.has('KeyW')) this.sim.nudge(0, 0, -v);
    if (this.keys.has('KeyS')) this.sim.nudge(0, 0, v);
    if (this.keys.has('KeyA')) this.sim.nudge(-v, 0, 0);
    if (this.keys.has('KeyD')) this.sim.nudge(v, 0, 0);
    if (this.keys.has('PageUp')) this.sim.nudge(0, h, 0);
    if (this.keys.has('PageDown')) this.sim.nudge(0, -h, 0);
  }
}
