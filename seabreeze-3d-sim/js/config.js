// SeaBreeze Inspector - Configuration
// All magic numbers centralized here
// =============================================================================
export const CFG = {
  // API
  API_STATE: '/api/state',
  API_COMMAND: '/api/command',
  POLL_INTERVAL_MS: 50,         // state polling rate
  KEY_REPEAT_MS: 80,            // keyboard forwarding throttle
  ARM_THROTTLE_MS: 100,         // arm slider forwarding throttle
  OFFLINE_THRESHOLD: 3,         // consecutive failures before "offline"

  // Scene
  TURBINE_POS: [9, 0, -2],      // turbine world position
  CAMERA_INITIAL: [6, 4, 8],    // initial camera position
  LOOKAT_INITIAL: [0, 1.5, 0],  // initial look-at target
  TRAIL_MAX: 400,               // max trail points

  // Arm joint limits
  JOINT_LIMITS: [[0, 180], [15, 165], [0, 180]],
  ARM_PRESETS: {
    home:    [90, 90, 90],
    vertical:[90, 90, 0],
    reach:   [90, 150, 60],
    limit:   [0, 15, 180],
  },

  // Safety thresholds
  BATTERY_WARN: 30,
  BATTERY_LOW: 15,
  EKF_OK: 5,
  EKF_WARN: 10,

  // Camera
  CAMERA_FPS: 10,               // camera canvas redraw rate (Hz)
  DETECTION_RANGE: 15,          // show detections within this distance (m)

  // Keys forwarded to backend
  FORWARD_KEYS: new Set([
    'Space', 'KeyW', 'KeyA', 'KeyS', 'KeyD',
    'KeyR', 'KeyE', 'KeyM',
    'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown',
  ]),

  // Logging
  CONSOLE_LOG_INTERVAL: 10,     // seconds between flight log dumps
};
