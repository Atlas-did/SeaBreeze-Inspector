"""
机械臂控制器 — 通过pyserial与Arduino通信
"""

import time

import numpy as np

from backend.arm.arm_kinematics import FK, IK, L1, L2, L3

# 从 arm_config.yaml 加载参数 (惰性加载, mock模式不触发)
_arm_config_cache = None


def _load_arm_config():
    global _arm_config_cache
    if _arm_config_cache is not None:
        return _arm_config_cache
    try:
        from backend.utils.config import ConfigLoader
        _arm_config_cache = ConfigLoader.load("arm_config")
        return _arm_config_cache
    except Exception:
        _arm_config_cache = False
        return None


class ArmController:
    """机械臂控制器, 通过串口与Arduino Nano通信"""

    def __init__(self, port: str = "", baudrate: int = None, timeout: float = 2.0):
        # 从 arm_config.yaml 读取默认参数
        cfg = _load_arm_config()
        if baudrate is None and cfg:
            try:
                baudrate = cfg["hardware"]["serial"]["baudrate"]
            except Exception:
                baudrate = 115200
        elif baudrate is None:
            baudrate = 115200
        if not port and cfg:
            try:
                port = str(cfg["hardware"]["serial"]["port"])
            except Exception:
                pass

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None  # type: ignore
        self._current_angles = np.array([90.0, 90.0, 90.0])

    def connect(self) -> bool:
        """连接Arduino串口"""
        try:
            import serial  # 延迟导入, mock模式不需要pyserial
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(2)  # 等待Arduino复位
            return True
        except ImportError:
            print("[ERR] pyserial未安装, 无法连接Arduino。安装: pip install pyserial")
            return False
        except Exception as e:
            print(f"[ERR] 串口连接失败: {e}")
            return False

    def disconnect(self):
        if self.ser:
            self.ser.close()
            self.ser = None

    def set_joint_angles(self, angles, duration: int = 500) -> bool:
        """发送角度指令 A<base>,<shoulder>,<elbow>

        duration: 预期运动时间(ms), 用于Python端等待。
                  Arduino固件以固定50°/s平滑运动, 此参数不影响实际速度。
        """
        # 等待舵机运动完成 (50°/s, 每度20ms) — Mock和真机都执行
        max_delta = max(abs(np.array(angles) - self._current_angles))
        wait_ms = min(max_delta * 20, duration)

        if self.ser is None:
            print("[WARN] 未连接Arduino, 使用模拟模式")
        else:
            cmd = f"A{int(angles[0])},{int(angles[1])},{int(angles[2])}\n"
            self.ser.write(cmd.encode())

        time.sleep(wait_ms / 1000.0)
        self._current_angles = np.array(angles)
        return True

    def move_to_position(self, x, y, z, duration: int = 500) -> bool:
        """先IK求解, 再发送角度"""
        angles = IK(x, y, z)
        return self.set_joint_angles(angles, duration)

    def get_current_angles(self):
        """查询当前角度"""
        if self.ser:
            self.ser.write(b"Q\n")
            time.sleep(0.1)
            if self.ser.in_waiting:
                resp = self.ser.readline().decode().strip()
                # 解析 "A:90,S:45,E:30"
                try:
                    parts = resp.replace("A:", "").replace("S:", "").replace("E:", "").split(",")
                    self._current_angles = np.array([float(p) for p in parts])
                except Exception:
                    pass
        return self._current_angles.copy()

    def reset(self):
        """归位"""
        self.set_joint_angles([90, 90, 90])
