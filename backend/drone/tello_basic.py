"""
Tello控制器 — 状态机驱动连接 + 异常恢复

选型: 状态机驱动连接 (方案C)
  理由: 根据飞行状态管理连接生命周期,
        IDLE/CONNECTED/FLYING/LANDING等状态清晰,
        异常时可快速转入EMERGENCY状态, 鲁棒性最好。
"""

from __future__ import annotations

import math
import time
from enum import Enum, auto
from typing import Callable, Dict, Optional, Tuple

import numpy as np

# "该字段从未读过"的哨兵 (区别于读到 None / 0)
_MISSING = object()


# P0-C 加强: 状态包到达时间戳在状态字典里的字段名
RX_STAMP_FIELD = "_seabreeze_rx_monotonic"


def _install_state_stamp(tello_cls) -> bool:
    """包装 djitellopy 的 Tello.parse_state, 让每个状态包带上到达时刻。

    为什么必须在这里打点: djitellopy 的 get_battery()/get_height() 读的是
    缓存字段(tello.py:374/404 -> get_state_field -> get_own_udp_object()['state']),
    链路断了它们照样返回旧值、也不抛异常。而该状态字典**只有一处被写入**:
        udp_state_receiver(): drones[address]['state'] = Tello.parse_state(data)
    所以在 parse_state 上打点是"真的收到新包"的最强证据。
    只包装一次, 不改动库文件本身。
    """
    if getattr(tello_cls, "_seabreeze_stamped", False):
        return True
    orig = getattr(tello_cls, "parse_state", None)
    if not callable(orig):
        return False

    def _stamped(state_str):
        try:
            parsed = orig(state_str)
        except Exception as e:
            # 解析异常**绝不能外抛**: djitellopy 的 udp_state_receiver 对该异常是
            # `except Exception: break` —— 一个畸形包就会让状态接收线程**永久退出**,
            # 此后 get_current_state() 永远返回旧包(遥测冻死, 而 getter 照旧返回值 ——
            # 这是最难发现的一类失效)。这里吞掉并返回空字典: 不带时间戳 => 不会被判成
            # "新包", 方向偏保守。
            print("[WARN] 状态包解析失败(已忽略, 保持接收线程存活): {}".format(e))
            return {}
        try:
            if isinstance(parsed, dict):
                parsed[RX_STAMP_FIELD] = time.monotonic()
        except Exception:
            pass
        return parsed

    tello_cls.parse_state = staticmethod(_stamped)
    tello_cls._seabreeze_stamped = True
    return True


class FlightState(Enum):
    IDLE = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    TAKING_OFF = auto()
    HOVERING = auto()
    MOVING = auto()
    LANDING = auto()
    EMERGENCY = auto()
    DISCONNECTED = auto()


class MockTello:
    """Mock Tello 用于离线测试, 模拟飞行状态和传感器数据"""

    def __init__(self):
        self.is_flying = False
        self._battery = 100
        self._height = 0
        self._position = np.zeros(3)
        self._attitude = np.zeros(3)

    def connect(self):
        return True

    def takeoff(self):
        self.is_flying = True
        self._height = 50
        return True

    def land(self):
        self.is_flying = False
        self._height = 0
        return True

    def emergency(self):
        self.is_flying = False
        self._height = 0
        return True

    def move_forward(self, dist: int):
        self._position[0] += dist
        return True

    def move_back(self, dist: int):
        self._position[0] -= dist
        return True

    def move_left(self, dist: int):
        self._position[1] += dist
        return True

    def move_right(self, dist: int):
        self._position[1] -= dist
        return True

    def move_up(self, dist: int):
        self._height += dist
        return True

    def move_down(self, dist: int):
        self._height = max(0, self._height - dist)
        return True

    def get_battery(self) -> int:
        return self._battery

    def get_height(self) -> int:
        return int(self._height)

    def get_attitude(self):
        return {"pitch": 0, "roll": 0, "yaw": 0}

    def get_position(self):
        return self._position.copy()

    def get_state_dict(self):
        return {
            "battery": self._battery,
            "height": int(self._height),
            "position": self._position.tolist(),
            "attitude": self.get_attitude(),
            "is_flying": self.is_flying,
        }


class TelloController:
    """Tello无人机控制器 — 状态机驱动"""

    # 状态转换表: {当前状态: {事件: 下一状态}}
    TRANSITIONS = {
        FlightState.IDLE: {"connect": FlightState.CONNECTING},
        FlightState.CONNECTING: {"success": FlightState.CONNECTED, "fail": FlightState.IDLE},
        FlightState.CONNECTED: {"takeoff": FlightState.TAKING_OFF, "disconnect": FlightState.DISCONNECTED},
        FlightState.TAKING_OFF: {"complete": FlightState.HOVERING, "fail": FlightState.EMERGENCY},
        FlightState.HOVERING: {"move": FlightState.MOVING, "land": FlightState.LANDING, "emergency": FlightState.EMERGENCY},
        # P0-2 附带修复: MOVING 此前没有 "land" 边, 导致飞行中调用 land() 直接失败
        # (必须先 hover 再 land) —— 这是降落路径上的真实缺口, 补上。
        FlightState.MOVING: {"hover": FlightState.HOVERING, "land": FlightState.LANDING, "emergency": FlightState.EMERGENCY},
        FlightState.LANDING: {"complete": FlightState.CONNECTED, "fail": FlightState.EMERGENCY},
        FlightState.EMERGENCY: {"reset": FlightState.IDLE},
        FlightState.DISCONNECTED: {"connect": FlightState.CONNECTING},
    }

    # --- P0 安全修复(A): 高度阈值 -------------------------------------------
    SAFE_CUTOFF_HEIGHT_CM = 30.0        # 无白名单理由时, 允许停桨的最高高度
    # 审计 P0-D 补完: kill()/legacy_kill 此前沿用 3m 上限, 但"高度 <3m"并不是
    # 通用安全证明(该高度本身也可能来自陈旧/无效遥测)。现收紧到与 SAFE 同阈值:
    # 只有确认在 30cm 以内才允许真正停桨, 否则拒绝并继续受控下降。
    LEGACY_CUTOFF_HEIGHT_CM = 30.0
    # 显式白名单: reason -> 允许停桨的最高高度(cm); None = 该情形下不再看高度。
    # 碰撞/翻转/外部急停属于"机械已经失效, 继续转桨比停桨更危险"的场景。
    MOTOR_CUTOFF_WHITELIST = {
        "collision": None,
        "flip": None,
        "external_estop": None,
        "legacy_kill": LEGACY_CUTOFF_HEIGHT_CM,
    }
    # --- 下降速度与超时 -----------------------------------------------------
    DEFAULT_DESCEND_SPEED = 30          # controlled_land 的下降速度 (cm/s)
    EMERGENCY_DESCEND_SPEED = 60        # emergency_descent 的下降速度 (cm/s)
    EMERGENCY_ENTRY_BUDGET_S = 0.5      # emergency() 单次下降脉冲时长 (不阻塞主循环)
    DEFAULT_TELEMETRY_MAX_AGE_S = 1.0   # 遥测"新鲜"的默认时限 (s)
    # 停桨判高专用的时限: 比通用遥测更严 —— 高度过期时宁可拒绝停桨。
    SAFETY_TELEMETRY_MAX_AGE_S = 0.5

    def __init__(self, config=None, mock: bool = False):
        self.config = config
        self.mock = mock
        self.state = FlightState.IDLE
        self._state_entry_time = time.time()
        self._battery = 100
        self._height = 0
        self._position = np.zeros(3)
        self._attitude = np.zeros(3)
        self._tello = None
        self._emergency_reason = ""

        # P0 安全修复(B): 遥测新鲜度 —— 以"真的收到新包"为准, 而不是"getter 没抛异常"。
        # 时间基准必须是单调时钟(墙上时钟会被 NTP/时区调整拉扯, 让"新鲜"判定失真)。
        # None 表示"从未收到过任何遥测包" —— 此时一切以高度为依据的判断都必须判为未知。
        self.last_packet_timestamp: Optional[float] = None
        self.telemetry_packet_count: int = 0
        self._last_state_digest: Optional[Tuple] = None
        self._last_field_values: Dict[str, object] = {}

        # P0-2: 接入 RCManager 做真正的速度控制 (20Hz 持续下发 + 0.5s 超时归零)。
        # 此前 RCManager 已存在却从未被接线, 主循环走的是 move_to() 一次性位移。
        from backend.drone.rc_manager import RCManager
        self._rc = RCManager(mock=mock)

    def _transition(self, event: str) -> bool:
        """状态转换"""
        if self.state in self.TRANSITIONS and event in self.TRANSITIONS[self.state]:
            old_state = self.state
            self.state = self.TRANSITIONS[self.state][event]
            self._state_entry_time = time.time()
            # P0-2: 切入非"可控飞行"状态(降落/紧急/起飞/断开)时先归零速度,
            # 避免带着上一条速度指令进入新状态。
            if self.state not in (FlightState.HOVERING, FlightState.MOVING):
                self._rc.set_command(0, 0, 0, 0)
            print(f"[STATE] {old_state.name} --{event}--> {self.state.name}")
            return True
        print(f"[WARN] 无效转换: {self.state.name} --{event}-->")
        return False

    def connect(self, wifi_ssid: str = "Tello", max_retry: int = 3) -> bool:
        """连接Tello WiFi, 重试3次"""
        if self.mock:
            self._transition("connect")
            self._transition("success")
            return True

        try:
            from djitellopy import Tello
            # P0-C 加强: 在状态包解析处打到达时间戳(唯一可靠的新包证据)
            _install_state_stamp(Tello)
            self._tello = Tello()
            self._tello.connect()
            self._transition("connect")
            self._transition("success")
            # P0-2: 连接成功后把底层对象交给 RCManager 并启动 20Hz 发送线程
            self._rc.attach(self._tello)
            self._rc.start()
            return True
        except Exception as e:
            print(f"[ERR] 连接失败: {e}")
            self._transition("fail")
            return False

    def takeoff(self) -> bool:
        """起飞"""
        if self.state != FlightState.CONNECTED:
            print("[WARN] 未连接, 无法起飞")
            return False
        self._transition("takeoff")
        if self.mock:
            self._height = 100
            self._transition("complete")
            return True
        try:
            self._tello.takeoff()
            self._transition("complete")
            return True
        except Exception as e:
            print(f"[ERR] 起飞失败: {e}")
            self._transition("fail")
            return False

    def land(self) -> bool:
        """降落"""
        if self.state in (FlightState.HOVERING, FlightState.MOVING):
            self._transition("land")
            if self.mock:
                self._height = 0
                self._transition("complete")
                return True
            try:
                self._tello.land()
                self._transition("complete")
                return True
            except Exception as e:
                self._emergency(f"降落失败: {e}")
                return False
        return False

    def controlled_land(self, descend_speed: Optional[int] = None,
                        timeout_s: float = 8.0, poll_s: float = 0.1,
                        land_height_cm: float = 30.0) -> bool:
        """受控闭环降落 —— **全程不砍桨**。

        语义: 用 RC 速度以有界的下降速度下降, 循环轮询高度直到 <30cm 或超时,
        然后调用 land() 让飞控自己完成触地(land 是飞控的受控动作, 不是停桨)。

        返回 True  = 已成功下发 land();
        返回 False = 无底层链路, 或底层 land() 抛出异常。
        """
        speed = self.DEFAULT_DESCEND_SPEED if descend_speed is None else descend_speed
        self.stop_velocity()          # 下降前先归零, 不要带着旧速度进入降落
        if self.mock:
            if self._transition("land") and self.state is FlightState.LANDING:
                self._height = 0
                self._transition("complete")
            else:
                self._height = 0
            return True
        if self._tello is None:
            print("[ERROR] controlled_land 失败: 无底层链路")
            return False

        t0 = time.monotonic()
        confirmed_low = False
        while True:
            # ud<0 = 下降; 每轮重发, 抵消 RCManager 的 0.5s 超时归零。
            self._rc.set_command(0, 0, -abs(int(speed)), 0)
            height = self._read_height_cm()
            if height is not None and height <= land_height_cm:
                confirmed_low = True
                break
            if time.monotonic() - t0 >= timeout_s:
                break
            time.sleep(poll_s)
        self.stop_velocity()
        if not confirmed_low:
            print(f"[WARN] controlled_land 超时({timeout_s}s)仍未确认 <{land_height_cm}cm "
                  "(高度可能未知/遥测陈旧); 仍调用 land() 兜底 —— land 不是停桨")
        # land() 只在 HOVERING/MOVING 有状态边; 紧急态下强制切 LANDING。
        if self.state in (FlightState.HOVERING, FlightState.MOVING):
            self._transition("land")
        else:
            old_state = self.state
            self.state = FlightState.LANDING
            self._state_entry_time = time.time()
            print(f"[STATE] {old_state.name} --controlled_land(force)--> LANDING")
        try:
            self._tello.land()
        except Exception as e:
            print(f"[ERROR] controlled_land: 底层 land() 失败: {e}")
            self._emergency(f"降落失败: {e}")
            return False
        if self.state is FlightState.LANDING:
            self._transition("complete")
        return True

    def emergency_descent(self, descend_speed: Optional[int] = None,
                          timeout_s: float = 5.0, poll_s: float = 0.1,
                          floor_height_cm: float = 30.0,
                          release_velocity: bool = True) -> bool:
        """紧急下降 —— 高速有界下降, **绝不砍桨**。

        与 controlled_land() 的区别: 这里用的是更高的下降速度, 且结束时**不**
        自动 land(); 低空后要不要 land 由调用方决定(通常由主循环/飞控收尾)。

        返回 True  = 下降流程已执行完毕(确认低空或超时);
        返回 False = 根本没有下降能力(无底层链路)。
        """
        speed = self.EMERGENCY_DESCEND_SPEED if descend_speed is None else descend_speed
        self.stop_velocity()          # 任何下降动作前先归零, 防止带着旧速度指令下降
        if self.mock:
            self._height = 0
            return True
        if self._tello is None:
            print("[ERROR] emergency_descent 失败: 无底层链路")
            return False

        t0 = time.monotonic()
        reached_floor = False
        while True:
            # ud<0 = 下降; 每轮重发, 避免 RCManager 的 0.5s 超时归零把下降中断。
            self._rc.set_command(0, 0, -abs(int(speed)), 0)
            height = self._read_height_cm()
            if height is not None and height <= floor_height_cm:
                reached_floor = True
                break
            if time.monotonic() - t0 >= timeout_s:
                break
            time.sleep(poll_s)
        if release_velocity:
            self.stop_velocity()
        if reached_floor:
            print(f"[SAFE] emergency_descent 已到 {floor_height_cm}cm 以下 (未停桨)")
        else:
            print(f"[WARN] emergency_descent 超时({timeout_s}s)未确认低空 "
                  "(高度可能未知/链路陈旧), 仍未停桨")
        return True

    def emergency(self) -> bool:
        """进入紧急状态 (向后兼容入口) —— **本方法不是停桨**。

        P0 安全修复(A): 旧实现在 <=300cm 时直调 SDK emergency()(那等于砍桨),
        把"紧急下降"和"停桨"混成了一个动作。现在:
          * 只负责把状态机切到 EMERGENCY;
          * 实际下降交给 emergency_descent()(高速、有界、绝不砍桨);
          * 真正停桨必须由调用方显式走 motor_cutoff(reason) 的安全闸门。
        """
        if not self._transition("emergency"):
            # 如果当前状态没有定义 emergency 转换边，直接切换
            old_state = self.state
            self.state = FlightState.EMERGENCY
            self._state_entry_time = time.time()
            print(f"[STATE] {old_state.name} --emergency(force)--> {self.state.name}")
        self._emergency_reason = self._emergency_reason or "受控紧急降落"
        # 只做一个短的下降脉冲, 不长时间阻塞主控制回路(10Hz):
        # 主循环在 EMERGENCY 态自己会把目标高度压到 0 并持续下发速度。
        # release_velocity=False: 把下降指令留在 RC 通道上, 让 20Hz 线程继续发。
        return self.emergency_descent(
            release_velocity=False,
            timeout_s=self.EMERGENCY_ENTRY_BUDGET_S,
        )

    def motor_cutoff(self, reason: str = "unspecified") -> bool:
        """真正的停桨 —— 唯一会砍桨的入口, 且必须**先能证明安全**。

        放行条件(全部满足才停桨):
          1. 高度已知且有效: 有限值、非负、且遥测新鲜(见 height_is_known());
          2. 高度在安全阈值内: h <= SAFE_CUTOFF_HEIGHT_CM(30cm);
             或者 reason 在 MOTOR_CUTOFF_WHITELIST 里(碰撞/翻转/外部急停等
             机械已失效场景 —— 此时继续转桨比停桨更危险), 白名单可携带
             自己的高度上限(legacy_kill 现已收紧到 30cm, 见 LEGACY_CUTOFF_HEIGHT_CM)。

        高度未知/无效/遥测陈旧 -> **拒绝执行并返回 False**, 绝不退化成"看运气"的砍桨。
        被拒绝时控制器状态保持不变(没有停桨就不该对外声称已处于 EMERGENCY)。
        """
        self.stop_velocity()          # 停桨前必须归零, 否则 RC 线程会继续下发旧速度
        height = self._read_height_cm()
        if height is None or not self.height_is_known(sample=height):
            print("[ERROR] motor_cutoff refused: height unknown "
                  f"(reason={reason}); 高度未知/无效/遥测陈旧, 拒绝停桨")
            return False
        max_allowed = self.MOTOR_CUTOFF_WHITELIST.get(reason, self.SAFE_CUTOFF_HEIGHT_CM)
        if max_allowed is not None and height > max_allowed:
            print(f"[ERROR] motor_cutoff refused: height {height}cm > {max_allowed}cm "
                  f"(reason={reason}); 拒绝高空停桨")
            return False

        if self.mock:
            self._height = 0
        elif self._tello is not None:
            try:
                self._tello.emergency()
            except Exception as e:
                print(f"[ERROR] motor_cutoff: 底层 emergency() 失败: {e}")
                return False
        self.state = FlightState.EMERGENCY
        self._state_entry_time = time.time()
        self._emergency_reason = self._emergency_reason or f"motor_cutoff:{reason}"
        print(f"[SAFE] motor_cutoff 执行: reason={reason}, height={height}cm")
        return True

    def kill(self) -> bool:
        """[兼容保留] 硬停桨 —— 现在只是 motor_cutoff("legacy_kill") 的薄封装。

        P0 安全修复(A): 旧实现把"高度未知"当成"低空"(get_height() 返回 0 或抛异常
        都会走进砍桨分支), 而且 except 之后照样 return True。现在统一走
        motor_cutoff() 的高度安全闸门 + 白名单策略:
          * 高度未知/无效/遥测陈旧 -> 拒绝, 返回 False, 不碰底层 emergency();
          * 高度已知且 <=300cm(legacy 阈值) -> 停桨, 返回 True;
          * 高度 >300cm -> 拒绝, 返回 False(不再偷偷降级成一次性 move_down)。
        """
        return self.motor_cutoff("legacy_kill")

    # =========================================================================
    # P0-2: 真正的速度控制 (RC) —— 替代周期性 move_to() 一次性位移
    # =========================================================================

    def set_velocity(self, vx: float, vy: float, vz: float, yaw: float = 0.0) -> bool:
        """下发速度指令 (cm/s, 范围 ±100)。

        坐标约定与主循环 current_pos 一致: x=左右, y=前后, z=上下(正=上升)。
        真机由 RCManager 以 20Hz 持续发送 rc_control; 超过 0.5s 没有新指令
        会自动归零, 避免失控飞丢。
        """
        if not self.mock and self.state not in (FlightState.HOVERING, FlightState.MOVING):
            return False
        self._rc.set_command(lr=vx, fb=vy, ud=vz, yaw=yaw)
        if self.state == FlightState.HOVERING and (abs(vx) + abs(vy) + abs(vz)) > 1:
            self._transition("move")
        return True

    def stop_velocity(self) -> None:
        """立即归零速度 (悬停等待)"""
        self._rc.set_command(0, 0, 0, 0)

    # =========================================================================
    # P0 安全修复(B): 遥测新鲜度 —— 基于"真的收到新包", 而不是"getter 没抛异常"
    # =========================================================================

    def _mark_telemetry_packet(self) -> float:
        """显式记录"刚收到一个遥测包"(返回单调时钟时间戳)。

        状态接收线程/仿真桥在真正解出新包时可以直接调用它; 也可以完全不调用,
        由 _read_telemetry() 依据证据自动打点。
        """
        now = time.monotonic()
        self.last_packet_timestamp = now
        self.telemetry_packet_count += 1
        return now

    def telemetry_packet_timestamp(self) -> Optional[float]:
        """最后一个遥测包的到达时刻(time.monotonic()); 从未收到过则为 None。"""
        return self.last_packet_timestamp

    def has_fresh_telemetry(self, max_age_s: float = 1.0) -> bool:
        """链路是否在 max_age_s 内真的送来过新遥测包。

        注意: 这里**不看 getter 是否还在返回旧值** —— djitellopy 的 get_battery()
        /get_height() 读的是缓存字段, 链路断了它们照样返回上一次的值(不抛异常),
        所以"没抛异常"证明不了新鲜。
        """
        ts = self.last_packet_timestamp
        if ts is None:
            return False
        return (time.monotonic() - ts) <= max_age_s

    def _sdk_state_digest(self) -> Optional[Tuple]:
        """真机路径: 取 djitellopy 整个状态快照的指纹。

        单个字段不变不能说明"没收到包"(悬停时 h/bat 本来就不变), 但**整包指纹变化**
        是"确实收到新包"的强证据(pitch/roll/yaw/vg* 每个包都在抖)。
        底层对象不支持(如测试假对象)时返回 None, 由调用方退回到"字段值变化"判据。
        """
        tello = self._tello
        getter = getattr(tello, "get_current_state", None) if tello is not None else None
        if not callable(getter):
            return None
        try:
            state = getter()
        except Exception:
            return None
        if not isinstance(state, dict):
            return None
        try:
            return tuple(sorted((str(k), str(v)) for k, v in state.items()))
        except Exception:
            return None

    def release(self) -> None:
        """释放 RC 发送线程 (任务结束时调用)"""
        self.stop_velocity()
        self._rc.stop()

    def move_to(self, x: float, y: float, z: float, speed: int = 30) -> bool:
        """[已弃用] 移动到相对位置(cm)。

        P0-2: 主控制链已改用 set_velocity()。本方法保留仅作兼容与离线测试;
        其实现是一次性位移指令(move_left/forward/...), 且 >20cm 死区,
        不适用于 10Hz 控制回路 —— 不要再从主循环调用。
        """
        if self.state not in (FlightState.HOVERING, FlightState.MOVING):
            return False

        if self.mock:
            self._position += np.array([x, y, z])
            self._height += z
            return True

        try:
            # 使用位移指令 (更可靠)
            if abs(x) > 20:
                self._tello.move_left(int(x)) if x > 0 else self._tello.move_right(int(-x))
            if abs(y) > 20:
                self._tello.move_forward(int(y)) if y > 0 else self._tello.move_back(int(-y))
            if abs(z) > 20:
                self._tello.move_up(int(z)) if z > 0 else self._tello.move_down(int(-z))
            return True
        except Exception as e:
            print(f"[ERR] 移动失败: {e}")
            return False

    def hover(self):
        """悬停"""
        self._transition("hover")

    def _read_telemetry(self, field: str, getter: Callable):
        """发起一次**真正的底层读取**, 并只在"有新包证据"时打点。

        判新包的证据(满足任一):
          * mock=True: 模拟链路, 每次读取都视为新包(需求明确要求);
          * SDK 整包快照指纹发生变化(真机 djitellopy 路径);
          * 该字段本次取值与上一次不同(底层无快照能力时的退路)。
        读取抛异常 / 返回 None -> 不打点, 返回 None(既不新鲜, 也没有值)。
        """
        try:
            value = getter()
        except Exception as e:
            print(f"[WARN] 遥测读取失败({field}): {e}")
            return None
        if value is None:
            return None
        if self.mock:
            self._mark_telemetry_packet()
            return value
        # P0-C 加强: 若底层能给出状态包到达时间戳, 它就是**权威判据** ——
        # 时间戳未推进就表示"没有新包", 此时绝不能再退回指纹启发式
        # (指纹初值为 None, 会把"冻结"误判成新包 -> 重复计数/假新鲜)。
        stamped = self._consume_rx_stamp()
        if stamped is not None:
            return value
        digest = self._sdk_state_digest()
        if digest is not None:
            if digest != self._last_state_digest:
                self._mark_telemetry_packet()
            self._last_state_digest = digest
        elif self._last_field_values.get(field, _MISSING) != value:
            # 值变了 => 一定读到了新东西; 值没变 => 无法证明有新包, 不打点。
            self._mark_telemetry_packet()
        self._last_field_values[field] = value
        return value

    def _consume_rx_stamp(self) -> Optional[bool]:
        """消费状态包到达时间戳。

        返回:
          True  新包, 已按**真实到达时刻**打点;
          False 时间戳未推进 —— 权威判定"没有新包"(不得退回启发式);
          None  底层不提供时间戳(或没有状态快照能力), 调用方退回指纹启发式。
        """
        tello = self._tello
        getter = getattr(tello, "get_current_state", None) if tello is not None else None
        if not callable(getter):
            return None
        try:
            state = getter()
        except Exception:
            return None
        if not isinstance(state, dict) or RX_STAMP_FIELD not in state:
            return None
        stamp = state.get(RX_STAMP_FIELD)
        if stamp is None or stamp == getattr(self, "_last_rx_stamp", None):
            return False
        self._last_rx_stamp = stamp
        # 直接用真实到达时刻, 而不是"读取时刻"
        self.last_packet_timestamp = float(stamp)
        self.telemetry_packet_count += 1
        return True

    def _read_height_cm(self) -> Optional[float]:
        """读高度(cm); 未知/无效一律返回 None。"""
        if self.mock:
            value = self._read_telemetry("height", lambda: self._height)
        elif self._tello is None:
            return None
        else:
            value = self._read_telemetry("height", self._tello.get_height)
        if value is None:
            return None
        try:
            height = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(height) or height < 0:
            return None
        return height

    def height_is_known(self, sample: Optional[float] = None,
                        max_age_s: Optional[float] = None) -> bool:
        """高度是否可以采信 —— 非有限值、负值、以及**遥测不新鲜时的高度**都判为未知。

        sample: 已经读到的高度值(避免重复发起一次读取); 省略则本方法自己读一次。
        max_age_s: 新鲜度时限, 省略时用 SAFETY_TELEMETRY_MAX_AGE_S(安全闸门专用)。
        """
        if sample is None:
            sample = self._read_height_cm()
        if sample is None:
            return False
        try:
            height = float(sample)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(height):
            return False
        if height < 0:
            return False
        limit = self.SAFETY_TELEMETRY_MAX_AGE_S if max_age_s is None else max_age_s
        if not self.has_fresh_telemetry(max_age_s=limit):
            return False
        return True

    def get_battery(self) -> int:
        """电量(%) —— 走遥测打点路径(读取成功且确为新包才刷新新鲜度)。"""
        if self.mock:
            return int(self._read_telemetry("battery", lambda: self._battery))
        if self._tello is None:
            return 0
        value = self._read_telemetry("battery", self._tello.get_battery)
        return 0 if value is None else value

    def get_height(self) -> int:
        """高度(cm) —— 走遥测打点路径; 读取失败/非数值时返回 0。

        注意: 返回 0 **不代表**"贴地", 只代表这一格没有可用数据;
        以高度为依据的安全判断必须用 height_is_known()/_read_height_cm()。
        """
        if self.mock:
            return int(self._read_telemetry("height", lambda: self._height))
        if self._tello is None:
            return 0
        value = self._read_telemetry("height", self._tello.get_height)
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            print(f"[WARN] 高度非数值 {value!r}, 按 0 处理(安全判断请用 height_is_known())")
            return 0

    def get_attitude(self) -> Dict:
        return {"pitch": 0, "roll": 0, "yaw": 0} if self.mock else {}

    def get_state_dict(self) -> Dict:
        """返回标准化状态字典"""
        return {
            "state": self.state.name,
            "battery": self.get_battery(),
            "height": self.get_height(),
            "position": self._position.tolist(),
            "emergency_reason": self._emergency_reason,
        }

    def _emergency(self, reason: str):
        """触发紧急状态"""
        self._emergency_reason = reason
        self.emergency()

    @property
    def is_flying(self) -> bool:
        return self.state in (FlightState.HOVERING, FlightState.MOVING, FlightState.TAKING_OFF)
