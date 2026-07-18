// SeaBreeze Inspector - Backend API Client
// State polling with retry + offline detection
// =============================================================================
import { CFG } from './config.js';

class BackendClient {
  constructor() {
    this._failCount = 0;
    this._online = true;
    this._lastState = null;
    this._armPending = null;
    this._armTimer = 0;
  }

  /** Fetch current simulation state */
  async fetchState() {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 2000);
      const res = await fetch(CFG.API_STATE, { signal: ctrl.signal });
      clearTimeout(timer);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      this._failCount = 0;
      this._online = true;
      this._lastState = data;
      return data;
    } catch (e) {
      this._failCount++;
      if (this._failCount >= CFG.OFFLINE_THRESHOLD) {
        this._online = false;
      }
      return this._lastState; // return last known good state
    }
  }

  /** Send key command to backend */
  sendKey(code) {
    fetch(CFG.API_COMMAND + '?key=' + code).catch(() => {});
  }

  /** Set arm angles (throttled to ARM_THROTTLE_MS) */
  sendArm(angles, immediate) {
    this._armPending = angles;
    if (immediate) {
      this._flushArm();
      return;
    }
  }

  _flushArm() {
    if (!this._armPending) return;
    const a = this._armPending;
    const url = CFG.API_COMMAND + '?key=arm&a0=' + a[0] + '&a1=' + a[1] + '&a2=' + a[2];
    fetch(url).catch(() => {});
    this._armPending = null;
  }

  isOnline() { return this._online; }
  getLastState() { return this._lastState; }
}

export const backend = new BackendClient();

// Periodic arm flush
setInterval(() => backend._flushArm(), CFG.ARM_THROTTLE_MS);
