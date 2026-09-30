"""
机械臂控制器 — 通过pyserial与Arduino通信

【能力边界: 诚实声明, 见 capabilities()】
本控制器驱动的执行器是 3×SG90 + PCA9685, 属于**开环舵机**:
  * 无位置反馈 —— 固件回的 ACK 是它自己"命令/步进到哪"(currentAngles),
    不是测量出来的角度; 上层不得把它当成真实位置回读。
  * 无电流/温度传感 —— SG90 内部没有可读的电流或温度通道。
  * 因此"堵转检测"和"真实角度回读"在本硬件上**物理不可实现**,
    绝不允许用"写串口没抛异常"冒充"已到位/没堵转"。
本文件真正实现的是: 主机侧 ACK 协议(等待固件确认, 超时或内容不符 -> False)、
固件动作完成后回一行 ACK、以及限位开关(固件读 GPIO, 触发时回 LIMIT 并拒绝该方向)。
"""

import re
import time

import numpy as np

from backend.arm.arm_kinematics import IK

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


# 安全角度范围 (量纲: 度), 顺序 = (base, shoulder, elbow)
# 来源: config/arm_config.yaml -> servo.angle_limits (SG90 物理极限 0-180,
#       大臂留碰撞裕量 15-165)。若 YAML 缺失/不可读则回退到下面这组默认值。
_DEFAULT_ANGLE_LIMITS = ((0.0, 180.0), (15.0, 165.0), (0.0, 180.0))
JOINT_NAMES = ("base", "shoulder", "elbow")


def _load_angle_limits():
    """读取 (min, max) 三元组; 任何异常都回退到 _DEFAULT_ANGLE_LIMITS"""
    limits = list(_DEFAULT_ANGLE_LIMITS)
    cfg = _load_arm_config()
    if cfg:
        try:
            y = cfg["servo"]["angle_limits"]
            for i, name in enumerate(JOINT_NAMES):
                limits[i] = (float(y[name]["min"]), float(y[name]["max"]))
        except Exception:
            pass
    return tuple(limits)


class ArmController:
    """机械臂控制器, 通过串口与Arduino Nano通信

    失败关闭(fail-closed)语义: 硬件模式下未连接串口时 set_joint_angles()
    返回 False 而不假装成功; 仅当显式声明/自动判定为模拟模式时才允许"空转成功"。
    """

    # 状态取值
    STATUS_OK = "OK"                        # 硬件已连接, 最近一次指令发送成功
    STATUS_MOCK = "MOCK"                    # 模拟模式
    STATUS_ARM_UNAVAILABLE = "ARM_UNAVAILABLE"  # 硬件模式但无串口/写入失败
    STATUS_ANGLE_REJECTED = "ANGLE_REJECTED"     # 角度越界
    STATUS_ANGLE_INVALID = "ANGLE_INVALID"       # 非有限值/非法输入
    STATUS_ACK_TIMEOUT = "ACK_TIMEOUT"           # 等待固件 ACK 超时
    STATUS_ACK_MISMATCH = "ACK_MISMATCH"         # 回包不是 ACK / ACK 角度与请求不符
    STATUS_LIMIT_TRIGGERED = "LIMIT_TRIGGERED"   # 固件回 LIMIT:<joint>, 限位开关触发

    # ---- 能力自述: False = 本硬件物理上做不到, 上层不要当成"有" ----
    CAPABILITIES = {
        "position_feedback": False,      # SG90 开环, 无角度传感
        "current_sensing": False,        # 无电流采样通道
        "temperature_sensing": False,    # 无温度传感
        "stall_detection": False,        # 无电流/位置 -> 堵转不可判
        "limit_switches": True,          # 固件支持 GPIO 限位开关(需实际接线)
        "ack_protocol": True,            # 主机侧 ACK 等待 + 固件动作完成回 ACK
        "open_loop": True,
        "hardware_verified": False,      # 固件改动未经实机验证
    }

    def capabilities(self) -> dict:
        """如实返回本硬件/本实现的能力边界 (不要粉饰)

        返回字典中恒为 False 的项(position_feedback / current_sensing /
        temperature_sensing / stall_detection)是**物理不可实现**, 不是"待实现"。
        要真正做堵转检测, 必须换硬件: 例如带电流反馈的舵机/编码器舵机,
        或串入电流采样电阻/INA219 类电流传感器 + 位置编码器, 二者缺一不可。
        limit_switches=True 指固件已实现 GPIO 读取(触发回 LIMIT 并拒绝该方向),
        但需真实接线; hardware_verified=False 表示尚未在实机验证。
        """
        caps = dict(self.CAPABILITIES)
        caps["ack_wait_enabled"] = bool(self._wait_ack)
        caps["ack_timeout_s"] = float(self.ack_timeout)
        caps["ack_tolerance_deg"] = float(self.ack_tolerance)
        caps["mock"] = bool(self._mock)
        return caps

    def __init__(self, port: str = "", baudrate: int = None, timeout: float = 2.0,
                 mock: bool = None, blocking_wait: bool = None,
                 wait_ack: bool = False, ack_timeout: float = 0.2,
                 ack_tolerance: float = 1.0):
        """构造控制器

        mock: True  = 显式模拟模式(不发串口, set_joint_angles 直接返回 True);
              False = 显式硬件模式(必须 connect() 成功, 否则指令失败关闭);
              None (默认) = 自动判定: port 为空 → 模拟模式, 否则硬件模式。
              默认值保持既有行为(空 port 即 mock), 因为既有调用方依赖它。
        blocking_wait: True = 发送后按 duration 阻塞等待; False = 发送后立即返回;
              None (默认) = 模拟模式 True(保持既有测试时序), 硬件模式 False
              (Arduino 固件自己做 50°/s 平滑, 不让控制循环被 duration 拖住)。
        wait_ack: True = 硬件模式下写完 A... 后**等固件回一行**再决定成败。
              默认 False —— 既有调用方/测试依赖"发完即返回"(不留 0.2s 等待),
              所以 ACK 确认是**显式选项**; 需要真正确认时必须打开它, 或在
              单次调用上传 wait_ack=True。ACK 是"固件确认它自己运动到哪",
              不是位置反馈(SG90 开环, 见模块 docstring)。
        ack_timeout: 单次 ACK 等待上限(秒), 默认 0.2s。注意固件是在**动作完成后**
              才回 ACK(50°/s 平滑 + 看门狗 500ms 上限), 大角度移动耗时会超过
              0.2s → 会判 ACK_TIMEOUT。要覆盖长动作请显式调大该值(或改用
              get_current_angles() 轮询 Q 查询)。
        ack_tolerance: ACK 角度与请求角度的允许偏差(度), 默认 ±1.0 度
              (对应固件整数步进 1°/步 的量化误差)。超出即 ACK_MISMATCH。
        """
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
        self.angle_limits = _load_angle_limits()

        # 模式: 显式 > 自动(空 port 视为模拟, 保持既有语义)
        if mock is None:
            self._mock = not str(self.port or "").strip()
        else:
            self._mock = bool(mock)
        if blocking_wait is None:
            self._blocking_wait = bool(self._mock)
        else:
            self._blocking_wait = bool(blocking_wait)

        self.status = self.STATUS_MOCK if self._mock else self.STATUS_ARM_UNAVAILABLE
        self.fault_reason = None if self._mock else "not connected: call connect() first"
        self._mock_warned = False

        # ---- ACK 等待配置 ----
        self._wait_ack = bool(wait_ack)
        self.ack_timeout = float(ack_timeout)
        self.ack_tolerance = float(ack_tolerance)
        self.last_ack_angles = None      # 最近一次 ACK 回读到的角度(固件自报, 非测量)
        self.last_limit_joint = None     # 最近一次 LIMIT 触发的关节名

    # ---------------- 可观测状态 ----------------
    @property
    def is_mock(self) -> bool:
        return self._mock

    @property
    def is_connected(self) -> bool:
        """硬件模式下串口是否真的打开(模拟模式恒为 False, 它不需要串口)"""
        return self.ser is not None

    def _fail(self, status: str, reason: str) -> bool:
        self.status = status
        self.fault_reason = reason
        print(f"[ERR] {status}: {reason}")
        return False

    def _unavailable(self, reason: str) -> bool:
        """串口 I/O 抛异常 → 全局不可用(硬件模式一律 ARM_UNAVAILABLE)"""
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        return self._fail(self.STATUS_ARM_UNAVAILABLE, reason)

    # ---------------- ACK / LIMIT 回包 ----------------
    # 每行只取 3 个数字做角度比对, 兼容 "ACK:A90,S45,E30" 与 "ACK:90,45,30"。
    # 注意: 这些数字是**固件自报的当前(命令)角度**, 不是传感器测量值。
    _NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")

    def _read_reply_line(self, deadline: float):
        """在 deadline 之前等到一行非空回复 → str; 超时 → None

        只读"已到达"的字节(in_waiting), 因此不会超出 ack_timeout 阻塞。
        read 抛异常时向上抛, 由调用方转成全局不可用。
        """
        while True:
            try:
                waiting = int(getattr(self.ser, "in_waiting", 0) or 0)
            except Exception:
                waiting = 0
            if waiting > 0:
                raw = self.ser.readline()
                text = raw.decode(errors="replace").strip() if raw else ""
                if text:            # 空行(固件启动横幅噪声)忽略, 继续等
                    return text
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.005)

    def _await_ack(self, requested, deadline: float):
        """等一行固件回复 → (ok, err)

        约定(见 set_joint_angles docstring):
          * "ACK:..." 且解析出 3 个角度且与请求偏差 <= ack_tolerance → ok
          * "LIMIT:<joint>" → LIMIT_TRIGGERED, 记录 self.last_limit_joint
          * 其它任何内容 / ACK 角度不符 → ACK_MISMATCH
          * deadline 前无回复 → ACK_TIMEOUT
        """
        self.last_ack_angles = None
        self.last_limit_joint = None
        line = self._read_reply_line(deadline)
        if line is None:
            return False, (self.STATUS_ACK_TIMEOUT,
                           f"{self.ack_timeout:.3f}s 内未收到固件 ACK/LIMIT 回复")
        upper = line.upper()
        if upper.startswith("LIMIT"):
            joint = line.split(":", 1)[1].strip().lower() if ":" in line else "unknown"
            self.last_limit_joint = joint
            return False, (self.STATUS_LIMIT_TRIGGERED,
                           f"限位开关触发, 固件拒绝该方向: {joint}")
        if not upper.startswith("ACK"):
            return False, (self.STATUS_ACK_MISMATCH,
                           f"回包既非 ACK 也非 LIMIT: {line!r}")
        nums = [float(x) for x in self._NUM_RE.findall(line[3:])]
        if len(nums) != len(JOINT_NAMES):
            return False, (self.STATUS_ACK_MISMATCH,
                           f"ACK 解析不出{len(JOINT_NAMES)}个角度: {line!r}")
        self.last_ack_angles = np.array(nums)
        dev = float(np.max(np.abs(self.last_ack_angles - np.asarray(requested, dtype=float))))
        if dev > self.ack_tolerance:
            return False, (self.STATUS_ACK_MISMATCH,
                           f"ACK 角度与请求不符(容差±{self.ack_tolerance:g}度, 实测偏差"
                           f"{dev:.2f}度): 回读={nums}, 请求={np.asarray(requested).tolist()}")
        self._drain_rx()   # 丢掉紧随 ACK 之后的 [OK]/[WDOG] 之类日志行, 防串帧
        return True, None

    def _drain_rx(self):
        """尽力丢弃已经到达的剩余字节(固件日志行), 避免下一帧读到上一帧尾巴"""
        try:
            while int(getattr(self.ser, "in_waiting", 0) or 0) > 0:
                if not self.ser.readline():
                    break
        except Exception:
            pass

    def connect(self) -> bool:
        """连接Arduino串口"""
        try:
            import serial  # 延迟导入, mock模式不需要pyserial
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(2)  # 等待Arduino复位
            # 丢掉开机横幅/上电归位残留: 否则第一帧可能把开机 ACK 当成自己的回复
            try:
                self.ser.reset_input_buffer()
            except Exception:
                pass
            self.status = self.STATUS_OK
            self.fault_reason = None
            return True
        except ImportError:
            return self._fail(self.STATUS_ARM_UNAVAILABLE,
                              "pyserial未安装, 无法连接Arduino。安装: pip install pyserial")
        except Exception as e:
            return self._fail(self.STATUS_ARM_UNAVAILABLE, f"串口连接失败: {e}")

    def disconnect(self):
        """关闭串口; 之后硬件模式下 set_joint_angles 会失败关闭"""
        if self.ser:
            self.ser.close()
        self.ser = None
        if not self._mock:
            self.status = self.STATUS_ARM_UNAVAILABLE
            self.fault_reason = "disconnected by caller"

    def _validate_angles(self, angles):
        """角度校验 → (arr, None) 或 (None, (status, reason))

        拒绝: 数量非3 / 不可解析 / nan / inf / 超出 angle_limits。
        """
        try:
            arr = np.asarray(angles, dtype=float).reshape(-1)
        except Exception as e:
            return None, (self.STATUS_ANGLE_INVALID, f"角度不可解析: {e!r}")
        if arr.size != len(JOINT_NAMES):
            return None, (self.STATUS_ANGLE_INVALID,
                          f"需要{len(JOINT_NAMES)}个角度, 实收{arr.size}个")
        for i in range(arr.size):
            v = float(arr[i])
            if not np.isfinite(v):
                return None, (self.STATUS_ANGLE_INVALID,
                              f"{JOINT_NAMES[i]}角度非有限值: {v}")
            lo, hi = self.angle_limits[i]
            if v < lo or v > hi:
                return None, (self.STATUS_ANGLE_REJECTED,
                              f"{JOINT_NAMES[i]}(ch{i})角度越界: {v:.2f} "
                              f"不在 [{lo:.0f}, {hi:.0f}] 度")
        return arr, None

    def set_joint_angles(self, angles, duration: int = 500, wait_ack: bool = None) -> bool:
        """发送角度指令 A<base>,<shoulder>,<elbow>

        返回 True 仅当: (a) 模拟模式(显式 mock=True 或空 port 自动判定), 或
                        (b) 硬件模式且串口写入成功(未开启 ACK 等待时), 或
                        (c) 硬件模式 + 开启 ACK 等待, 且固件回了内容一致的 ACK。
        硬件模式下 self.ser is None → 返回 False, status=ARM_UNAVAILABLE,
        fault_reason 说明原因, 绝不"打印模拟模式后返回 True"。
        角度越界 → False(status=ANGLE_REJECTED); nan/inf/数量不对 → False
        (status=ANGLE_INVALID), 两种情况都不会发出任何串口指令。

        duration: 预期运动时间(ms), 用于计算等待; Arduino 固件以固定50°/s
                  平滑运动, 此参数不影响实际速度。是否真的阻塞由
                  blocking_wait 决定: 模拟模式默认阻塞(兼容既有语义),
                  硬件模式默认不阻塞, 避免拖住主控制循环。

        wait_ack: None(默认) → 用构造参数 wait_ack(默认 False);
                  True → 写完等一行回复, 约定如下:
                    * 以 "ACK" 开头且能解析出 3 个角度、与请求偏差 <=
                      ack_tolerance(默认±1.0度) → True(status=OK), 回读值存
                      self.last_ack_angles;
                    * 以 "LIMIT" 开头 → False(status=LIMIT_TRIGGERED), 触发关节
                      存入 self.last_limit_joint, 且**不更新内部角度**;
                    * 超时(默认 0.2s) → False(status=ACK_TIMEOUT);
                    * 其它任何内容、或 ACK 角度超出容差 → False
                      (status=ACK_MISMATCH) —— 这是"内容不符"的约定: 宁可判失败,
                      也不把无法确认的回复当成成功。
                  注意 ACK 是固件自报它运动到哪(开环, 非测量), 且它在动作**完成后**
                  才回; 大角度移动会超过 0.2s, 那种情况请调大 ack_timeout。
        """
        arr, err = self._validate_angles(angles)
        if err is not None:
            return self._fail(err[0], err[1])

        if self.ser is None:
            if not self._mock:
                return self._fail(self.STATUS_ARM_UNAVAILABLE,
                                  "硬件模式下无串口连接, 角度指令未发送")
            if not self._mock_warned:
                self._mock_warned = True
                print("[WARN] 模拟模式(未连接Arduino), 仅更新内部角度状态")
        else:
            cmd = f"A{int(arr[0])},{int(arr[1])},{int(arr[2])}\n"
            try:
                self.ser.write(cmd.encode())
            except Exception as e:
                return self._unavailable(f"串口写入失败: {e}")

            ack_wait = self._wait_ack if wait_ack is None else bool(wait_ack)
            if ack_wait:
                try:
                    ack_ok, ack_err = self._await_ack(arr,
                                                      time.monotonic() + self.ack_timeout)
                except Exception as e:
                    return self._unavailable(f"串口读取失败(ACK): {e}")
                if not ack_ok:
                    # 失败关闭: 不更新 _current_angles, 也不报成功
                    return self._fail(ack_err[0], ack_err[1])

        max_delta = float(np.max(np.abs(arr - self._current_angles)))
        wait_ms = min(max_delta * 20, duration)
        if self._blocking_wait:
            time.sleep(wait_ms / 1000.0)

        self._current_angles = arr
        self.status = self.STATUS_MOCK if self._mock else self.STATUS_OK
        self.fault_reason = None
        return True

    def move_to_position(self, x, y, z, duration: int = 500, wait_ack: bool = None) -> bool:
        """先IK求解, 再发送角度(不可达/越界时由 set_joint_angles 失败关闭)

        wait_ack 语义同 set_joint_angles。
        """
        angles = IK(x, y, z)
        return self.set_joint_angles(angles, duration, wait_ack=wait_ack)

    def get_current_angles(self):
        """查询当前角度

        硬件模式下发 Q 并读回固件自报角度。**这不是位置反馈**: SG90 开环,
        固件报的是它自己步进到的角度; 读失败 → 全局不可用(ARM_UNAVAILABLE),
        但本方法仍返回最后一次已知角度, 不抛异常。
        """
        if self.ser:
            try:
                self.ser.write(b"Q\n")
                time.sleep(0.1)
                if getattr(self.ser, "in_waiting", 0):
                    resp = self.ser.readline().decode(errors="replace").strip()
                    # 解析 "A:90,S:45,E:30"
                    try:
                        parts = resp.replace("A:", "").replace("S:", "").replace("E:", "").split(",")
                        self._current_angles = np.array([float(p) for p in parts])
                    except Exception:
                        pass
            except Exception as e:
                self._unavailable(f"串口读取失败(Q查询): {e}")
        return self._current_angles.copy()

    def reset(self, wait_ack: bool = None) -> bool:
        """归位(回到 base/shoulder/elbow = 90/90/90), 返回是否真的下发成功

        wait_ack 语义同 set_joint_angles(默认沿用构造配置)。
        """
        return self.set_joint_angles([90, 90, 90], wait_ack=wait_ack)
