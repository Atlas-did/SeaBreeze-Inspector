# WIND PATCH: generated from seabreeze_tello_bridge.py + gust injection (see repo verify_scripts/gust_ekf_demo.py)
# Copyright 2026 SeaBreeze
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""SeaBreeze Tello flight controller — stable quadcopter control for OmniSim.

Why this exists: OmniSim's stock Mavic bridge uses a P-only stabiliser
that oscillates wildly under Newton physics with small-inertia URDFs
(measured: roll/pitch swings of ±2 rad and 7 m horizontal drift on a
1.5 m takeoff). This controller is a proper cascaded control:

    position -> velocity -> attitude -> motor mix
              (P)        (P)         (P+D)

  - Attitude: PD on roll/pitch (stabilises, damps oscillation)
  - Altitude: P on height + D on vertical speed
  - Horizontal: P on position error + D on xy velocity (stops drift)

Constants are tuned for the SeaBreeze Tello URDF (0.087 kg, 0.060 m
motor arms). Lift/torque come from tello_dynamics.py via supervisor
add_force_with_offset, mirroring the Mavic design.

HTTP surface (port 6090, loopback):
    GET  /state   -> {x,y,z,roll,pitch,yaw,mode,target_altitude_m,...}
    POST /action  -> takeoff {altitude}, land, hover, stop, reset,
                     goto_waypoint {x,y,altitude,yaw},
                     goto_path {waypoints:[{x,y,altitude?,yaw?},...]}
                     # goto_path flies the waypoint list in order; the drone
                     # points along each leg (or the waypoint's explicit yaw),
                     # slewing the heading at YAW_TURN_RATE for smooth turns.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from omnisim import Supervisor


# ---------------------------------------------------------------------------
# Crash log: the engine shows only "controller exited with status: 1" and
# does NOT pipe controller stderr into the world log, so an early traceback
# used to be silently lost (measured: the v8.1.15 migration crash was
# invisible). Tee stdout/stderr into a per-PID temp file — any future crash
# leaves a readable traceback there.
# ---------------------------------------------------------------------------
class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, s):
        for st in self._streams:
            try:
                st.write(s)
                st.flush()
            except Exception:
                pass

    def flush(self):
        for st in self._streams:
            try:
                st.flush()
            except Exception:
                pass


_log_path = os.path.join(tempfile.gettempdir(),
                         f"seabreeze_tello_bridge_{os.getpid()}.log")
try:
    _log_fp = open(_log_path, "w", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.__stdout__, _log_fp)
    sys.stderr = _Tee(sys.__stderr__, _log_fp)
    print(f"[seabreeze_tello] log file: {_log_path}")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Tello flight constants (tuned for the SeaBreeze Tello URDF)
# ---------------------------------------------------------------------------
MASS = 0.087            # kg (real Tello)
G = 9.81
WEIGHT = MASS * G       # 0.853 N

# Thrust geometry. Each rotor force = k_thrust * omega^2.
# Hover: total thrust = WEIGHT = 4 * k_thrust * omega_hover^2.
# Hover omega chosen LOW (~80 rad/s) to avoid Newton numerical blow-up on
# high-speed spinning joints. Measured: 500 rad/s props destabilise after a
# few seconds of stable hover (z 1.6 -> flip at t+6s); slower props should
# hold.
K_THRUST = WEIGHT / (4.0 * 80.0 * 80.0)   # ~3.33e-5, hover omega ~80

# Attitude PD. Counter-rotating props fixed the mid-hover flip; now the
# remaining flips happen only when tilting for horizontal motion (tilt ->
# lift horizontal component -> positive feedback that weak gains can't
# arrest). Bump authority: strong P on error + rate damping.
K_ATT_P = 1.0           # restoring per rad (fraction of hover omega)
K_ATT_D = 0.3           # damping per (rad/s) on estimated rate
K_ATT_CLAMP = 0.5       # max omega-fraction differential per axis

# Altitude P + vertical-speed D + bounded I. P-only settles at a systematic
# offset: the true hover point needs ~+6.8% thrust above the nominal base
# omega (measured 2026-09-01: ω 82.7 vs base 80.0 → z rests −0.056 m under a
# 1.5 m target, just outside the ≤±5 cm contest bar). The integral nulls it.
K_ALT_P = 1.2
K_ALT_D = 0.5
K_ALT_I = 0.35           # per (m·s) — equilibrium integral state ≈0.19 (< clamp)
K_ALT_I_CLAMP = 0.25     # bounded so a spike/reset can never wind it up

# Horizontal: position P + velocity D, plus goto velocity profiling.
K_POS_P = 0.9
K_POS_D = 1.2          # strong brake so goto stops at target, no overshoot

# Goto velocity profile: decelerate as distance closes so the drone stops
# AT the waypoint instead of blowing past it and flipping.
GOTO_VMAX = 0.6        # m/s horizontal cruise
GOTO_DECEL = 1.5       # m/s^2 braking

# Yaw hold: keep the initial heading so the body-frame tilt decomposition
# stays valid. Applied as a DIRECT body torque (N*m) via TelloDynamics.step.
# Strong: differential thrust for roll/pitch breaks the reaction-torque
# balance (measured: goto tilt -> yaw drifts to -2.3 rad in 2 s -> flip),
# so yaw authority must counter that, not just hold a heading.
K_YAW_TORQUE = 0.05     # N*m per rad
K_YAW_TORQUE_D = 0.02   # N*m per (rad/s)
K_YAW_MAX_TORQUE = 0.10

# Multi-segment path: max heading slew rate. Keeps turns smooth instead of
# commanding an instant heading jump (a pi-rad step would saturate the yaw
# torque -> overshoot -> flip risk). ~86 deg/s is brisk for inspection.
YAW_TURN_RATE = 1.5     # rad/s

# Motor mix scaling (radians of rotor speed offset per unit command).
MOTOR_SCALE = 40.0

MAX_TILT = 0.20         # rad (~11 deg)
WAYPOINT_REACH_XY = 0.20
WAYPOINT_REACH_Z = 0.25

BRIDGE_HOST = "127.0.0.1"


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def wrap_pi(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Wind bridge patch: gust wind disturbance via drag-form addForce.
# Model mirrors verify_scripts/wind_gust_injector.py (same formula & envs):
#   v(t) = v_mean + v_gust*sin(2*pi*t/T_gust) + U(-v_turb,+v_turb)
#   F    = 0.5*rho*Cd*A*v^2  along `direction` (world frame)
# Embedded here so the demo needs no second Supervisor/world surgery; the
# bridge already holds Supervisor powers (teleport), addForce is the same API.
# ---------------------------------------------------------------------------
import random as _random

WIND_DEFAULTS = {
    "v_mean": float(os.environ.get("WIND_V_MEAN", 0.0)),
    "v_gust": float(os.environ.get("WIND_V_GUST", 0.0)),
    "t_gust": float(os.environ.get("WIND_T_GUST", 20.0)),
    "v_turb": float(os.environ.get("WIND_V_TURB", 0.0)),
    "dir": [float(x) for x in os.environ.get("WIND_DIR", "1,0,0").split(",")],
    "area_m2": float(os.environ.get("WIND_AREA_M2", 0.02)),
    "seed": int(os.environ.get("WIND_SEED", "1")),
}


class WindModel:
    """Configurable gust wind; drag force applied to the drone each tick."""

    RHO = 1.225
    CD = 1.0

    def __init__(self):
        self.enabled = False
        self.position_hold = os.environ.get("WIND_HOLD", "1") not in ("0", "false", "False")
        self.ff_tilt = [0.0, 0.0]    # rad, world-frame FF tilt (pitch_x, -roll_y)
        self._t0 = None               # wind clock phase anchor (per enable)
        self.v_mean = 0.0
        self.v_gust = 0.0
        self.t_gust = 20.0
        self.v_turb = 0.0
        self.direction = [1.0, 0.0, 0.0]
        self.area_m2 = 0.02
        self._rng = _random.Random(1)
        self.v_now = 0.0
        self.f_now = 0.0
        self.force = [0.0, 0.0, 0.0]

    def configure(self, body):
        """POST /action {"action":"wind", ...} payload -> True if changed."""
        changed = False
        if "seed" in body:
            self._rng = _random.Random(int(body["seed"]))
            changed = True
        for k in ("v_mean", "v_gust", "t_gust", "v_turb", "area_m2"):
            if k in body and body[k] is not None:
                setattr(self, k, float(body[k]))
                changed = True
        if "dir" in body and isinstance(body["dir"], list) and len(body["dir"]) == 3:
            n = math.sqrt(sum(c * c for c in body["dir"])) or 1.0
            self.direction = [float(c) / n for c in body["dir"]]
            changed = True
        if "enable" in body and body["enable"] is not None:
            self.enabled = bool(body["enable"])
            changed = True
        if "position_hold" in body and body["position_hold"] is not None:
            self.position_hold = bool(body["position_hold"])
            changed = True
        if "ff_tilt" in body and isinstance(body["ff_tilt"], list) and len(body["ff_tilt"]) == 2:
            self.ff_tilt = [float(body["ff_tilt"][0]), float(body["ff_tilt"][1])]
            changed = True
        if not self.enabled:
            self.v_now = self.f_now = 0.0
            self.force = [0.0, 0.0, 0.0]
        elif self.enabled and changed:
            # Re-arming the wind restarts the gust phase clock and the
            # turbulence stream, so two legs configured identically see the
            # identical v(t) profile — that is what makes A/B legs fair.
            self._t0 = None
            self._rng = _random.Random(self.seed if hasattr(self, "seed") else 1)
        return changed

    def step(self, t_s):
        """Advance the gust profile; return world-frame force or None."""
        if not self.enabled or self.v_mean <= 0.0:
            self.v_now = self.f_now = 0.0
            self.force = [0.0, 0.0, 0.0]
            return None
        if self._t0 is None:
            self._t0 = t_s
        t_w = t_s - self._t0
        gust = self.v_gust * math.sin(2.0 * math.pi * t_w / max(1e-3, self.t_gust))
        turb = self._rng.uniform(-self.v_turb, self.v_turb)
        v = max(0.0, self.v_mean + gust + turb)
        f = 0.5 * self.RHO * self.CD * self.area_m2 * v * v
        self.v_now, self.f_now = v, f
        self.force = [f * d for d in self.direction]
        return self.force

    def snapshot(self):
        return {
            "enabled": self.enabled, "v_now": round(self.v_now, 3),
            "position_hold": self.position_hold,
            "ff_tilt": [round(c, 4) for c in self.ff_tilt],
            "f_n": round(self.f_now, 4), "force": [round(c, 4) for c in self.force],
            "v_mean": self.v_mean, "v_gust": self.v_gust,
            "t_gust": self.t_gust, "v_turb": self.v_turb,
            "area_m2": self.area_m2,
        }


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.x = self.y = self.z = 0.0
        self.roll = self.pitch = self.yaw = 0.0
        self.vx = self.vy = self.vz = 0.0
        self.target_alt = 0.0
        self.target_x: Optional[float] = None
        self.target_y: Optional[float] = None
        # Multi-segment path: remaining waypoints after the current target.
        # Each = {"x":float,"y":float,"altitude":float|None,"yaw":float|None}.
        self.waypoints: list = []
        self.mode = "idle"          # idle|takeoff|hover|goto|land|landed
        self.fault: Optional[str] = None
        self.sim_time = 0.0
        self.tick_period_s = 0.008
        self.last_pose_for_v: Optional[tuple] = None
        self.reset_request: Optional[dict] = None
        self.wind = {"enabled": False, "v_now": 0.0, "f_n": 0.0}

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            dbg = dict(getattr(self, "debug", {}) or {})
            return {
                "x": self.x, "y": self.y, "z": self.z,
                "roll": self.roll, "pitch": self.pitch, "yaw": self.yaw,
                "vx": self.vx, "vy": self.vy, "v_xy": math.hypot(self.vx, self.vy), "v_z": self.vz,
                "wind": dict(self.wind),
                "target_altitude_m": self.target_alt,
                "mode": self.mode, "fault": self.fault,
                "sim_time": self.sim_time,
                "waypoints_remaining": len(self.waypoints),
                "debug": dbg,
            }


# ---------------------------------------------------------------------------
# Rotor dynamics (lift + yaw torque) — see tello_dynamics.py
# ---------------------------------------------------------------------------
class TelloDynamics:
    """Applies per-rotor lift + yaw torque from motor velocities.

    F = k_thrust * omega^2 per rotor, along body +Z, at the motor anchors.
    Yaw torque from diagonal-pair asymmetry.
    """
    PROP = [
        (0.060, 0.060, 0.020),
        (0.060, -0.060, 0.020),
        (-0.060, 0.060, 0.020),
        (-0.060, -0.060, 0.020),
    ]
    k_thrust = K_THRUST
    # Yaw reaction torque. With real counter-rotating prop joints in Newton,
    # the physical spin already produces reaction torque; this addTorque is a
    # small correction only (was double-counting before).
    k_torque = K_THRUST * 0.0005

    def __init__(self, robot):
        self.robot = robot

    def step(self, fl: float, fr: float, rl: float, rr: float,
             yaw_tau: float = 0.0) -> None:
        for (px, py, pz), w in zip(self.PROP, (fl, fr, rl, rr)):
            f = self.k_thrust * w * w
            self.robot.addForceWithOffset([0.0, 0.0, f], [px, py, pz], True)
        # Yaw torque commanded directly by the controller (N*m about +Z).
        # Decoupled from the motor mixer so the sign is exact and Newton's
        # tiny-prop reaction torque is irrelevant.
        self.robot.addTorque([0.0, 0.0, yaw_tau], True)


# ---------------------------------------------------------------------------
# Flight control loop
# ---------------------------------------------------------------------------
class TelloController:
    def __init__(self, supervisor: Supervisor):
        self.supervisor = supervisor
        self.state = State()
        self.dynamics = TelloDynamics(supervisor.getSelf())
        self.timestep = int(supervisor.getBasicTimeStep())

        # Idle on spawn; takeoff is commanded via POST /action takeoff.
        # Devices. IMU/GPS only materialise with OMNISIM_URDF_USE_SENSORS=1
        # (URDF <gazebo> sensor blocks) — launching without it used to hit the
        # hard raise below and the engine only printed "exited with status: 1"
        # with no traceback. Now: fall back to supervisor pose reads, which
        # give the same world pose the simulated IMU/GPS would report, so the
        # env var becomes an optimisation rather than a requirement.
        self._self_node = supervisor.getSelf()
        self.wind = WindModel()
        self.wind.configure(WIND_DEFAULTS)
        self.imu = supervisor.getDevice("inertial unit")
        self.gps = supervisor.getDevice("gps")
        if self.imu is not None and self.gps is not None:
            self.imu.enable(self.timestep)
            self.gps.enable(self.timestep)
            self._use_devices = True
        else:
            self._use_devices = False
            print("[seabreeze_tello] IMU/GPS devices not materialised "
                  "(OMNISIM_URDF_USE_SENSORS=1 not set?) — using supervisor "
                  "pose reads instead; flight behaviour identical.")

        # Gyro (diagnostic only — flight rates come from IMU diff). The URDF
        # importer materialises the IMU triplet ("inertial unit" + "_gyro" +
        # "_accel") under OMNISIM_URDF_USE_SENSORS=1. Exposed in /state debug
        # to A/B against the IMU-diff rates: a Gyro stuck at [0,0,0] during
        # real rotation is the Newton-backend defect the maintainer listed in
        # the issue #10 6-defect chain (claimed fixed in v8.1.15 — verify).
        self.gyro = (supervisor.getDevice("inertial unit_gyro")
                     or supervisor.getDevice("gyro"))
        if self.gyro is not None:
            self.gyro.enable(self.timestep)
        print(f"[seabreeze_tello] gyro device: "
              f"{'present' if self.gyro is not None else 'ABSENT'}")

        self.motors = []
        for name in ("front left propeller", "front right propeller",
                     "rear left propeller", "rear right propeller"):
            m = supervisor.getDevice(name + "_motor") or supervisor.getDevice(name)
            if m is None:
                raise RuntimeError(f"Tello: missing motor {name}")
            m.setPosition(float("inf"))
            m.setVelocity(1.0)
            self.motors.append(m)

        # Reset teleport fields (for /action reset).
        self_node = supervisor.getSelf()
        self.translation_field = self_node.getField("translation")
        self.rotation_field = self_node.getField("rotation")

        self._t0 = time.time()
        self._sim_t = 0.0                  # sim-clock seconds (advances by basicTimeStep/tick)
        self._reset_settle = 0             # steps of estimator re-anchoring after reset teleport
        self._last_omega = [0.0] * 4
        self._last_omega_actual = [0.0] * 4
        self._last_roll = 0.0
        self._last_pitch = 0.0
        self._last_att_time = 0.0
        self._roll_rate = 0.0
        self._pitch_rate = 0.0
        self._yaw_lock = 0.0          # held heading in takeoff/hover/land
        self._alt_i = 0.0             # altitude integral state (bounded)
        self._yaw_target = 0.0        # current commanded heading (slewed)
        self._yaw_desired = 0.0       # where the drone wants to point
        self._last_yaw = 0.0
        self._last_yaw_t = 0.0

    def _set_yaw_desired(self, leg_start: dict, wp: dict) -> None:
        """Command heading for the leg from `leg_start` into waypoint `wp`.

        Explicit per-waypoint `yaw` wins; otherwise point along the segment
        from `leg_start` to `wp` (the drone faces the direction it travels).
        """
        if wp.get("yaw") is not None:
            self._yaw_desired = float(wp["yaw"])
        else:
            self._yaw_desired = math.atan2(
                wp["y"] - leg_start["y"], wp["x"] - leg_start["x"])

    # -- per-tick control ------------------------------------------------
    def flight_step(self) -> None:
        if self._use_devices:
            roll, pitch, yaw = self.imu.getRollPitchYaw()
            gx, gy, gz = self.gps.getValues()
            # Gyro diagnostic (body-frame rad/s): compared against the IMU-diff
            # rates in /state debug to verify the device actually reports.
            self._gyro_read = (list(self.gyro.getValues())
                               if self.gyro is not None else [0.0, 0.0, 0.0])
        else:
            # Supervisor fallback: world pose straight off the robot node.
            # getOrientation is row-major world-from-body (mavic bridge ships
            # the same matrix as world_orientation_3x3_row_major); ZYX Euler
            # extraction. Webots' IMU yaw uses a north=-Y reference so its
            # absolute heading differs by a constant — irrelevant here, the
            # yaw lock is relative (_yaw_lock captured at takeoff).
            gx, gy, gz = self._self_node.getPosition()
            R = self._self_node.getOrientation()
            roll = math.atan2(R[7], R[8])
            pitch = -math.asin(max(-1.0, min(1.0, R[6])))
            yaw = math.atan2(R[3], R[0])
        self._sim_t += self.timestep / 1000.0   # exact per-tick sim clock
        t_sim = self._sim_t

        if getattr(self, "_reset_settle", 0) > 0:
            # Settle phase right after a reset teleport: re-anchor every
            # estimator on the fresh pose EACH step. The pose teleport shows
            # up in the Newton backend as a velocity, so any differential that
            # crosses the teleport boundary becomes a huge false rate/velocity
            # (measured: +21 m/s) and the controller thrashes. Re-anchoring for
            # ~10 steps (~80 ms) lets the pose stabilise.
            self._last_roll, self._last_pitch, self._last_yaw = roll, pitch, yaw
            self._last_att_time = t_sim
            self._last_yaw_t = t_sim
            self._roll_rate = self._pitch_rate = 0.0
            self._reset_settle -= 1

        with self.state.lock:
            self.state.x, self.state.y, self.state.z = gx, gy, gz
            self.state.roll, self.state.pitch, self.state.yaw = roll, pitch, yaw
            self.state.sim_time = t_sim
            target_alt = self.state.target_alt
            tx, ty = self.state.target_x, self.state.target_y
            mode = self.state.mode
            # velocity from successive poses, differenced on the sim clock
            # (wall-clock dt makes the estimate jittery in realtime mode and
            # Nx too high in fast mode -> position loop oscillation).
            prev = self.state.last_pose_for_v
            if getattr(self, "_reset_settle", 0) > 0:
                # never differ across the teleport boundary; treat as at rest
                self.state.vx = self.state.vy = self.state.vz = 0.0
                self.state.last_pose_for_v = None
            elif prev is not None:
                dt = t_sim - prev[4]
                if dt > 1e-3:
                    self.state.vx = (gx - prev[0]) / dt
                    self.state.vy = (gy - prev[1]) / dt
                    self.state.vz = (gz - prev[2]) / dt
                self.state.last_pose_for_v = (gx, gy, gz, roll, t_sim)
            else:
                self.state.last_pose_for_v = (gx, gy, gz, roll, t_sim)

        # ---- mode transitions / target logic ----
        if mode in ("takeoff", "hover", "goto"):
            if mode == "goto" and tx is not None and ty is not None:
                dx = tx - gx; dy = ty - gy
                dz = target_alt - gz
                if (math.hypot(dx, dy) < WAYPOINT_REACH_XY
                        and abs(dz) < WAYPOINT_REACH_Z):
                    with self.state.lock:
                        if self.state.waypoints:
                            # Multi-segment path: advance to the next leg.
                            wp = self.state.waypoints.pop(0)
                            self.state.target_x = wp["x"]
                            self.state.target_y = wp["y"]
                            if wp.get("altitude") is not None:
                                self.state.target_alt = float(wp["altitude"])
                        else:
                            self.state.mode = "hover"
                            # hold the arrival heading once the path is done
                            self._yaw_lock = self._yaw_target
                    if self.state.mode == "goto":
                        # leg start = the just-reached waypoint (tx, ty)
                        self._set_yaw_desired(
                            {"x": tx, "y": ty},
                            {"x": self.state.target_x, "y": self.state.target_y,
                             "yaw": wp.get("yaw")})
        elif mode == "land":
            if gz < 0.20 and abs(self.state.vz) < 0.3:
                with self.state.lock:
                    self.state.mode = "landed"
                    self.state.target_alt = 0.0
                for m in self.motors:
                    m.setVelocity(0.0)
                self._last_omega = [0.0] * 4
                return

        # ---- cascaded control ----
        # Level hold with velocity damping: hover brakes horizontal drift
        # without chasing a position target (which caused overshoot -> flip
        # on waypoint arrival).
        target_roll = 0.0
        target_pitch = 0.0
        if mode in ("takeoff", "hover"):
            if (mode == "hover" and self.wind.position_hold
                    and self.state.target_x is not None):
                # Wind-bridge position hold: world-frame P on position error
                # + D on velocity (anchor = takeoff/hover point, shifted by
                # the EKF feedforward offset ff_offset when the backend
                # provides one). Pure feedback stiffness — the gust demo's
                # A-leg baseline.
                vx_des = clamp(K_POS_P * (self.state.target_x - gx), -0.35, 0.35)
                vy_des = clamp(K_POS_P * (self.state.target_y - gy), -0.35, 0.35)
                # Feedback (position P + velocity D) plus the EKF feedforward
                # tilt: theta_ff = d_hat/g compensates the measured gust
                # before the position loop has to build up an error. World
                # frame; yaw is locked at 0 in this world so no rotation.
                ff_p = clamp(self.wind.ff_tilt[0], -MAX_TILT, MAX_TILT)
                ff_r = clamp(-self.wind.ff_tilt[1], -MAX_TILT, MAX_TILT)
                target_pitch = clamp(K_POS_P * (vx_des - self.state.vx),
                                     -MAX_TILT, MAX_TILT) + ff_p
                target_roll = clamp(-K_POS_P * (vy_des - self.state.vy),
                                    -MAX_TILT, MAX_TILT) + ff_r
                target_pitch = clamp(target_pitch, -MAX_TILT, MAX_TILT)
                target_roll = clamp(target_roll, -MAX_TILT, MAX_TILT)
            else:
                target_pitch = clamp(-K_POS_D * self.state.vx, -MAX_TILT, MAX_TILT)
                # Positive roll banks right -> thrust tilts toward -y (measured:
                # roll=+0.2 made vy grow more negative). So a +y velocity drift
                # needs NEGATIVE roll; hence the + sign (mirrors pitch below).
                target_roll = clamp(+K_POS_D * self.state.vy, -MAX_TILT, MAX_TILT)
        elif mode == "goto" and tx is not None and ty is not None:
            ex = tx - gx
            ey = ty - gy
            dist = math.hypot(ex, ey)
            # Desired velocity toward target, capped by deceleration profile
            # so we arrive with ~0 speed (trapezoidal stop).
            if dist > 1e-3:
                vx_des = (ex / dist) * min(GOTO_VMAX, math.sqrt(2 * GOTO_DECEL * dist))
                vy_des = (ey / dist) * min(GOTO_VMAX, math.sqrt(2 * GOTO_DECEL * dist))
            else:
                vx_des = vy_des = 0.0
            target_pitch = clamp(K_POS_P * (vx_des - self.state.vx), -MAX_TILT, MAX_TILT)
            # Same sign rule as the level-hold above: positive roll -> -y, so
            # to accelerate toward +y we must command NEGATIVE roll.
            target_roll = clamp(-K_POS_P * (vy_des - self.state.vy), -MAX_TILT, MAX_TILT)

        # World-frame tilt commands (brake / steer the WORLD velocity or track
        # the world target) -> rotate into the body frame: the drone may be
        # yawed (multi-segment paths leave it facing any heading). At yaw=0
        # this is the identity, so single-leg behaviour is unchanged.
        c, s = math.cos(yaw), math.sin(yaw)
        body_r = target_roll * c + target_pitch * s
        body_p = -target_roll * s + target_pitch * c
        target_roll, target_pitch = body_r, body_p

        # Attitude PD with a TRUE derivative: roll/pitch rate estimated from
        # pose differencing, low-passed. (K_ATT_D*gain on the pose itself was
        # a bug — it is just more proportional and cannot damp oscillation.)
        dt = max(1e-3, t_sim - self._last_att_time)
        roll_rate = (roll - self._last_roll) / dt
        pitch_rate = (pitch - self._last_pitch) / dt
        # 1-pole low pass (tick ~8ms, tau ~30ms -> alpha ~0.8)
        alpha = 0.8
        self._roll_rate = alpha * self._roll_rate + (1 - alpha) * roll_rate
        self._pitch_rate = alpha * self._pitch_rate + (1 - alpha) * pitch_rate
        self._last_roll, self._last_pitch = roll, pitch
        self._last_att_time = t_sim

        roll_err = target_roll - roll
        pitch_err = target_pitch - pitch

        # Attitude PD with true angular-rate damping. Counter-rotating props
        # fixed the hover flip; strong P+D must also arrest tilt-induced
        # flips during horizontal motion.
        roll_d = clamp(K_ATT_P * roll_err - K_ATT_D * self._roll_rate,
                       -K_ATT_CLAMP, K_ATT_CLAMP)
        pitch_d = clamp(K_ATT_P * pitch_err - K_ATT_D * self._pitch_rate,
                        -K_ATT_CLAMP, K_ATT_CLAMP)

        # Vertical: flight-1 mix — hover omega plus a bounded motor-speed
        # offset. Keeps the vertical authority gentle (proven stable).
        alt_err = target_alt - gz
        dt = self.timestep / 1000.0
        if mode == "idle":
            # Idle = powered-on float: neutral hover thrust at the current
            # altitude. If idle left the motors OFF the drone free-falls from
            # its spawn pose, lands and tips over (contact instability), and
            # then reset's pose teleport becomes a +20 m/s velocity spike that
            # the attitude/altitude loop cannot recover from (measured).
            # Hover-holding keeps the spawn/reset pose clean and stable.
            vert_input = 0.0
            self._alt_i = 0.0
        else:
            # Bounded integral nulls the hover steady-state offset (true
            # hover needs ~+6.8% thrust above nominal base omega, measured
            # 2026-09-01: P-only settles z at -0.056 m under a 1.5 m target).
            # Freeze during reset-settle: the teleport velocity spike must
            # not wind it up (measured +20 m/s vz spike after a crash reset).
            if getattr(self, "_reset_settle", 0) <= 0:
                self._alt_i = clamp(self._alt_i + alt_err * dt,
                                    -K_ALT_I_CLAMP, K_ALT_I_CLAMP)
            vert_input = clamp(K_ALT_P * alt_err - K_ALT_D * self.state.vz
                               + K_ALT_I * self._alt_i,
                               -0.8, 1.0)
        base_omega = math.sqrt(WEIGHT / (4.0 * K_THRUST))
        base_omega += MOTOR_SCALE * vert_input

        fl = max(0.0, base_omega * (1.0 - pitch_d + roll_d))
        fr = max(0.0, base_omega * (1.0 - pitch_d - roll_d))
        rl = max(0.0, base_omega * (1.0 + pitch_d + roll_d))
        rr = max(0.0, base_omega * (1.0 + pitch_d - roll_d))

        # Landed: motors off (idle floats at hover omega, handled above).
        if mode == "landed":
            fl = fr = rl = rr = 0.0

        # Yaw: in goto, slew the commanded heading toward the desired heading
        # at YAW_TURN_RATE (shortest arc) for smooth turns; otherwise hold the
        # locked heading. Applied as direct body torque (N*m), decoupled from
        # the motor mixer, via TelloDynamics.step.
        if mode == "goto":
            step = YAW_TURN_RATE * self.timestep / 1000.0
            self._yaw_target = self._yaw_target + clamp(
                wrap_pi(self._yaw_desired - self._yaw_target), -step, step)
        else:
            self._yaw_target = self._yaw_lock
        yaw_err = wrap_pi(self._yaw_target - yaw)
        yaw_rate = (yaw - self._last_yaw) / max(1e-3, t_sim - self._last_yaw_t)
        self._last_yaw = yaw
        self._last_yaw_t = t_sim
        yaw_tau = K_YAW_TORQUE * yaw_err - K_YAW_TORQUE_D * yaw_rate
        yaw_tau = clamp(yaw_tau, -K_YAW_MAX_TORQUE, K_YAW_MAX_TORQUE)

        # COUNTER-ROTATING mixer: FR/RL spin negative. No yaw term here —
        # yaw is commanded directly as body torque above (exact sign).
        #
        # Roll sign is CRITICAL. With PROP = FL(+x,+y), FR(+x,-y),
        # RL(-x,+y), RR(-x,-y) the roll torque is
        #   Tx = 0.06*(f_fl - f_fr + f_rl - f_rr) = +0.48*k*base^2*roll_d
        #   Ty = 0.06*(-f_fl - f_fr + f_rl + f_rr) = +0.48*k*base^2*pitch_d
        # So a POSITIVE roll_d must INCREASE the +y (left) props and DECREASE
        # the -y (right) props. The previous "1-pd-rd / 1-pd+rd" pattern made
        # Tx = -0.48*k*base^2*roll_d: bank command was INVERTED, turning the
        # roll loop into positive feedback (hover looked stable only because a
        # perfect sim keeps roll exactly at 0; any perturbation -> exponential
        # flip during forward flight).
        fl = max(-2000.0, min(2000.0, base_omega * (1.0 - pitch_d + roll_d)))
        fr = max(-2000.0, min(2000.0, -base_omega * (1.0 - pitch_d - roll_d)))
        rl = max(-2000.0, min(2000.0, -base_omega * (1.0 + pitch_d + roll_d)))
        rr = max(-2000.0, min(2000.0, base_omega * (1.0 + pitch_d - roll_d)))

        for m, w in zip(self.motors, (fl, fr, rl, rr)):
            m.setVelocity(w)
        self._last_omega = [fl, fr, rl, rr]
        self._last_omega_actual = [m.getVelocity() for m in self.motors]
        self.dynamics.step(fl, fr, rl, rr, yaw_tau)
        # --- wind bridge patch: apply gust force in world frame ---
        _wf = self.wind.step(t_sim)
        if _wf is not None:
            self._self_node.addForce(_wf, False)
        with self.state.lock:
            self.state.wind = {
                "enabled": self.wind.enabled,
                "v_now": round(self.wind.v_now, 3),
                "f_n": round(self.wind.f_now, 4),
            }

        # Debug telemetry for the P0 goto-flip diagnosis.
        with self.state.lock:
            self.state.debug = {
                "base_omega": round(base_omega, 2),
                "roll_d": round(roll_d, 3), "pitch_d": round(pitch_d, 3),
                "target_roll": round(target_roll, 3),
                "target_pitch": round(target_pitch, 3),
                "fl": round(fl, 1), "fr": round(fr, 1),
                "rl": round(rl, 1), "rr": round(rr, 1),
                "afl": round(self._last_omega_actual[0], 1),
                "afr": round(self._last_omega_actual[1], 1),
                "arl": round(self._last_omega_actual[2], 1),
                "arr": round(self._last_omega_actual[3], 1),
                "roll_rate": round(self._roll_rate, 3),
                "pitch_rate": round(self._pitch_rate, 3),
                "yaw_rate": round(yaw_rate, 3),
                "gyro": [round(v, 3) for v in getattr(self, "_gyro_read",
                                                      [0.0, 0.0, 0.0])],
                "vx": round(self.state.vx, 3), "vy": round(self.state.vy, 3),
                "alt_err": round(alt_err, 3), "vert_input": round(vert_input, 3),
                "alt_i": round(getattr(self, "_alt_i", 0.0), 3),
                "yaw_tau": round(yaw_tau, 4),
            }

    def main_loop(self) -> None:
        while self.supervisor.step(self.timestep) != -1:
            with self.state.lock:
                req = self.state.reset_request
                self.state.reset_request = None
            if req and self.translation_field and self.rotation_field:
                self.translation_field.setSFVec3f([req["x"], req["y"], req.get("z", 0.1)])
                self.rotation_field.setSFRotation([0.0, 0.0, 1.0, req.get("yaw", 0.0)])
                # Teleporting the pose fields does NOT clear the body's
                # momentum: reset after a crash/tumble leaves the drone
                # spinning/flailing in place, and the teleport displacement
                # itself becomes velocity (measured: +20 m/s vz spike on
                # z:0.03->0.1, which slams the altitude D term to full-down).
                # resetPhysics() zeroes velocity and clears contact state, so
                # the drone re-materialises at rest at the new pose.
                self_node = self.supervisor.getSelf()
                self_node.resetPhysics()
                with self.state.lock:
                    self.state.last_pose_for_v = None
                    self._reset_settle = 10
            try:
                self.flight_step()
            except Exception as e:
                with self.state.lock:
                    self.state.fault = str(e)


# ---------------------------------------------------------------------------
# HTTP bridge
# ---------------------------------------------------------------------------
def make_handler(ctrl: TelloController):
    state = ctrl.state
    action_lock = threading.RLock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _json(self, code, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.split("?")[0] == "/state":
                self._json(200, state.snapshot())
            elif self.path.split("?")[0] == "/capabilities":
                self._json(200, {
                    "robot_id": "seabreeze_tello",
                    "model": "DJI Tello",
                    "mass_kg": MASS,
                    "actions": ["takeoff", "land", "hover", "goto_waypoint", "wind",
                                "goto_path", "stop", "reset"],
                })
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path.split("?")[0] != "/action":
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except Exception:
                self._json(400, {"error": "malformed_json"})
                return
            action = body.get("action", "")
            with action_lock:
                if action == "takeoff":
                    alt = float(body.get("altitude", 1.0))
                    with state.lock:
                        state.target_alt = max(0.4, alt)
                        state.target_x = state.x
                        state.target_y = state.y
                        state.mode = "takeoff"
                        state.fault = None
                        # A back-to-back reset->takeoff can run BEFORE the reset
                        # teleport is applied (main loop does it on its next
                        # step), so state.yaw is still the previous flight's
                        # heading. Anchor to the reset teleport's yaw (0.0)
                        # while a reset is pending; otherwise lock the live one.
                        pending_reset = state.reset_request is not None
                    ctrl._yaw_lock = 0.0 if pending_reset else ctrl.state.yaw
                    self._json(200, {"accepted": True, "target_altitude": alt})
                elif action == "land":
                    with state.lock:
                        state.target_alt = 0.0
                        state.target_x = state.x
                        state.target_y = state.y
                        state.waypoints = []
                        state.mode = "land"
                        state.fault = None
                    self._json(200, {"accepted": True})
                elif action == "hover":
                    with state.lock:
                        state.target_x = state.x
                        state.target_y = state.y
                        if state.target_alt < 0.4:
                            state.target_alt = max(state.z, 0.5)
                        state.waypoints = []
                        state.mode = "hover"
                        state.fault = None
                    self._json(200, {"accepted": True})
                elif action == "goto_waypoint":
                    tx = float(body.get("x", 0.0))
                    ty = float(body.get("y", 0.0))
                    yaw_wp = body.get("yaw")
                    with state.lock:
                        state.target_x = tx
                        state.target_y = ty
                        state.target_alt = float(body.get("altitude", state.target_alt or 1.0))
                        state.waypoints = []
                        state.mode = "goto"
                        state.fault = None
                    # Point along the initial leg (or the explicit yaw).
                    ctrl._set_yaw_desired(
                        {"x": state.x, "y": state.y},
                        {"x": tx, "y": ty, "yaw": yaw_wp})
                    self._json(200, {"accepted": True, "x": tx, "y": ty})
                elif action == "goto_path":
                    wps_raw = body.get("waypoints")
                    if not isinstance(wps_raw, list) or not wps_raw:
                        self._json(400, {"error": "waypoints must be a non-empty list"})
                        return
                    try:
                        wps = [{
                            "x": float(w["x"]), "y": float(w["y"]),
                            "altitude": float(w["altitude"]) if w.get("altitude") is not None else None,
                            "yaw": float(w["yaw"]) if w.get("yaw") is not None else None,
                        } for w in wps_raw]
                    except (TypeError, KeyError, ValueError):
                        self._json(400, {"error": "bad waypoint (need x,y; optional altitude,yaw)"})
                        return
                    first = wps[0]
                    with state.lock:
                        state.waypoints = wps[1:]
                        state.target_x = first["x"]
                        state.target_y = first["y"]
                        if first["altitude"] is not None:
                            state.target_alt = first["altitude"]
                        state.mode = "goto"
                        state.fault = None
                    ctrl._set_yaw_desired({"x": state.x, "y": state.y}, first)
                    self._json(200, {"accepted": True, "waypoints": len(wps)})
                elif action == "stop":
                    with state.lock:
                        state.target_x = state.target_y = None
                        state.target_alt = 0.0
                        state.waypoints = []
                        state.mode = "idle"
                        state.fault = None
                    self._json(200, {"halted_at": time.time()})
                elif action == "reset":
                    with state.lock:
                        state.mode = "idle"
                        state.fault = None
                        state.reset_request = {"x": 0.0, "y": 0.0, "z": 0.1, "yaw": 0.0}
                    # Teleport targets yaw=0; anchor the heading reference too
                    # so a back-to-back reset->takeoff holds 0 (not the stale
                    # heading of the previous flight, see takeoff handler).
                    ctrl._yaw_lock = 0.0
                    ctrl._yaw_target = 0.0
                    self._json(200, {"reset": True})
                elif action == "wind":
                    ctrl.wind.configure(body)
                    self._json(200, {"accepted": True, "wind": ctrl.wind.snapshot()})
                else:
                    self._json(400, {"error": f"unknown action {action!r}"})

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(prog="seabreeze_tello_bridge")
    parser.add_argument("--port", type=int, default=6090)
    args = parser.parse_args()

    supervisor = Supervisor()
    ctrl = TelloController(supervisor)

    server = ThreadingHTTPServer((BRIDGE_HOST, args.port), make_handler(ctrl))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[seabreeze_tello] HTTP listening on http://{BRIDGE_HOST}:{args.port}")

    ctrl.main_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
