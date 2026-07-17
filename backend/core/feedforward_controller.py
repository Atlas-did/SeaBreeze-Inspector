"""
Feedforward PID Controller — PID feedback + disturbance feedforward compensation

Control law:
    v_cmd = Kp*e + Ki*∫e + Kd*ė + Kff*d_est

Features:
    - D-term PT1 low-pass filter (anti-noise)
    - Integral separation (anti-windup)
    - Output clamping + dead zone

Config source: config/drone_config.yaml
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np

from backend.core.filters import PT1Filter, IntegralSeparator


class FeedforwardController:
    """PID feedback + disturbance feedforward compensation controller.

    v_cmd = Kp * e + Ki * ∫e + Kd * ė + Kff * d_est

    where:
        e = target_pos - current_pos    (position error)
        ∫e = integral of error
        ė = -current_vel                (error derivative, assuming target stationary)
        d_est = disturbance estimate from EKF

    Output clamped to [-max_speed, max_speed] (default ±100 cm/s for Tello SDK).
    Dead zone: |e| < dead_zone → output = 0.
    """

    def __init__(
        self,
        Kp: float = 2.0,
        Ki: float = 0.1,
        Kd: float = 1.0,
        Kff: float = -1.0,
        dt: float = 0.1,
        max_speed: float = 100.0,
        dead_zone: float = 2.0,
        d_cutoff_hz: float = 0.0,          # D-term LPF cutoff (0=disabled)
        integral_separation: float = 0.0,  # I-term freeze threshold (0=disabled)
        integral_limit: float = 50.0,
        enable_ff: bool = True,
    ) -> None:
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.Kff = Kff
        self.dt = dt
        self.max_speed = max_speed
        self.dead_zone = dead_zone
        self.integral_limit = integral_limit
        self.enable_ff = enable_ff

        self.integral = np.zeros(3)
        self.prev_error = np.zeros(3)
        self._was_saturated = False

        # D-term low-pass filter (suppresses high-frequency noise)
        self._d_filter = (
            PT1Filter(cutoff_hz=d_cutoff_hz, dt=dt)
            if d_cutoff_hz > 0 else None
        )
        # Integral separator (freezes I when error is large)
        self._i_separator = (
            IntegralSeparator(threshold=integral_separation)
            if integral_separation > 0 else None
        )

    def compute(
        self,
        target_pos: np.ndarray,
        current_pos: np.ndarray,
        disturbance_est: Optional[np.ndarray] = None,
        current_vel: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, Dict]:
        """Compute control output.

        Args:
            target_pos: target position (3D, cm)
            current_pos: current position (3D, cm)
            disturbance_est: disturbance estimate from EKF (3D, cm/s²)
            current_vel: current velocity (3D, cm/s)

        Returns:
            (control_output, info_dict)
        """
        target_pos = np.asarray(target_pos, dtype=float)
        current_pos = np.asarray(current_pos, dtype=float)
        error = target_pos - current_pos

        # Dead zone
        if np.linalg.norm(error) < self.dead_zone:
            return np.zeros(3), {
                "error": error,
                "dead_zone_active": True,
                "pid_output": np.zeros(3),
                "ff_output": np.zeros(3),
                "total_output": np.zeros(3),
            }

        # Proportional term
        P_term = self.Kp * error

        # Integral term (trapezoidal, with anti-windup)
        if not self._was_saturated:
            self.integral += error * self.dt
            self.integral = np.clip(
                self.integral, -self.integral_limit, self.integral_limit
            )
        I_term = self.Ki * self.integral
        # Integral separation: freeze when error exceeds threshold
        if (self._i_separator is not None
                and not self._i_separator.should_integrate(float(np.linalg.norm(error)))):
            I_term = np.zeros(3)

        # Derivative term: Kd * (-vel), with optional PT1 low-pass
        if current_vel is not None:
            vel = np.asarray(current_vel, dtype=float)
            D_term = -self.Kd * vel
            if self._d_filter is not None:
                D_term = np.array(
                    [self._d_filter.update(float(v)) for v in D_term]
                )
        else:
            D_term = self.Kd * (error - self.prev_error) / self.dt

        pid_output = P_term + I_term + D_term

        # Feedforward: Kff * d_est
        ff_output = np.zeros(3)
        if self.enable_ff and disturbance_est is not None:
            d_est = np.asarray(disturbance_est, dtype=float)
            ff_output = self.Kff * d_est

        total_output = pid_output + ff_output

        # Output clamping (preserves direction)
        output_norm = np.linalg.norm(total_output)
        if output_norm > self.max_speed:
            total_output = total_output * (self.max_speed / output_norm)
            self._was_saturated = True
        else:
            self._was_saturated = False

        self.prev_error = error.copy()

        info = {
            "error": error.copy(),
            "P_term": P_term,
            "I_term": I_term,
            "D_term": D_term,
            "pid_output": pid_output,
            "ff_output": ff_output,
            "total_output": total_output.copy(),
            "dead_zone_active": False,
            "saturated": self._was_saturated,
        }
        return total_output, info

    def reset(self) -> None:
        """Reset controller state (integral, error history, filters)."""
        self.integral = np.zeros(3)
        self.prev_error = np.zeros(3)
        self._was_saturated = False
        if self._d_filter is not None:
            self._d_filter.reset(0.0)
        if self._i_separator is not None:
            self._i_separator = type(self._i_separator)(self._i_separator.threshold)

    @classmethod
    def from_config(cls, config=None) -> "FeedforwardController":
        """Load controller params from drone_config.yaml.

        Usage:
            ctrl = FeedforwardController.from_config()
            ctrl = FeedforwardController.from_config(cfg_object)
        """
        if config is None:
            try:
                from backend.utils.config import ConfigLoader
                config = ConfigLoader.load("drone_config")
            except Exception:
                config = None

        def _get(cfg, path, default):
            if cfg is None:
                return default
            try:
                keys = path.split(".")
                val = cfg
                for k in keys:
                    val = getattr(val, k)
                return val
            except (AttributeError, KeyError):
                return default

        return cls(
            Kp=_get(config, "controller.Kp", 2.0),
            Ki=_get(config, "controller.Ki", 0.1),
            Kd=_get(config, "controller.Kd", 1.0),
            Kff=-1.0,
            dt=1.0 / _get(config, "flight.control_rate_hz", 10),
            max_speed=_get(config, "flight.max_speed", 50),
            d_cutoff_hz=_get(config, "controller.d_cutoff_hz", 0.0),
            integral_separation=_get(config, "controller.integral_separation", 0.0),
        )
