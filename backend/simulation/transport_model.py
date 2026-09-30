"""传输层保真度模型: 传感器延迟/丢包 + 执行器一阶滞后。

审计 Phase 3 缺口: 无头仿真里的传感器是"瞬时且永不丢包"的理想源, 执行器也是
"指令即到位"。本模块补上这两类真实存在的动态, 且**默认全部关闭**:
latency=0 / drop_rate=0 / tau=0 时是严格直通, 不改变任何已发表数字。

设计约束:
  * 纯离散 (按 dt 步进), 不使用线程, 不 sleep, 不读墙钟;
  * 丢包由固定 seed 的 random.Random 驱动, 同一 seed 必然复现同一序列;
  * 采样时刻 now 用**仿真时钟**(秒), 由调用方累加 dt 得到。

扩展 (审计 §14.4 遗留差距, 默认关闭):
  * SensorTransportModel: 样本带**采样时刻** -> last_sample_time() / last_age(now),
    衡量"我手上这条测量有多旧" (注意区别于 last_delivery_time() 的**交付**时刻);
  * CommandTransportModel: 上行指令链路 (遥控/速度指令) 的离散延迟线 + 丢包;
  * 两者都支持 loss_model="gilbert-elliott" 的**突发丢包** (两状态马尔可夫);
    loss_model="iid" (默认) 时逐位保持扩展前的伯努利行为。

依赖方向: 本模块不 import 仿真/控制器任何东西, 可单独测试。
"""

from collections import deque
import math
import random

import numpy as np

# 到期判定容差: 5*0.02 与 0.1 在二进制浮点下不严格相等, 用 EPS 兜住这类误差。
_EPS = 1e-9


class _PacketLoss:
    """丢包判定: iid 伯努利 (默认) 或 Gilbert-Elliott 两状态马尔可夫。

    只在"真的有一次交付机会"时调用 _decide_drop(), 于是随机序列只取决于交付
    机会的次数, 与调用密度无关 —— 这是扩展前就有的性质, 逐位保留。

    Gilbert-Elliott (good/bad 两状态, 坏状态内**每次都丢** —— 经典形式):
      * 用直观量给参数: mean_burst_len = 坏状态平均持续多少个"丢包机会";
        drop_rate = **整体**丢包率 (不是坏状态占比之外的任何东西)。
      * 反推转移概率 (推导):
            p_bad_to_good = 1 / mean_burst_len
                坏状态停留时间服从几何分布, 均值 = 1/p_bad_to_good;
            p_good_to_bad = drop_rate * p_bad_to_good / (1 - drop_rate)
                稳态坏状态占比 pi_bad = p_good_to_bad / (p_good_to_bad +
                p_bad_to_good), 令 pi_bad = drop_rate 反解即得上式:
                p_gb / (p_gb + p_bg) = d  =>  p_gb = d * p_bg / (1 - d)。
      * 因此整体丢包率严格等于 drop_rate, 连续丢弃的游程长度服从均值
        mean_burst_len 的几何分布。mean_burst_len = 1 时 p_bad_to_good = 1,
        坏状态每次机会最多停留一次 -> "丢弃互不相邻"的最不突发边界: 边际丢包率
        仍严格是 drop_rate, 但游程恒为 1, 与 i.i.d. (游程均值 1/(1-drop_rate),
        存在长度 >= 2 的游程) **不是同一分布**。

    机会开始时**所在状态**决定本次是否丢; 状态转移在本次判定之后推进。这样
    每次机会恰好消耗一个随机数 (两种模型都一样), 同一 seed 必然复现同一序列。
    """

    def _init_loss(self, drop_rate, seed, loss_model, mean_burst_len):
        self.drop_rate = min(1.0, max(0.0, float(drop_rate)))
        self.loss_model = str(loss_model)
        if self.loss_model not in ("iid", "gilbert-elliott"):
            raise ValueError("loss_model must be 'iid' or 'gilbert-elliott'")
        self.mean_burst_len = max(1.0, float(mean_burst_len))
        self.seed = int(seed)
        self.p_bad_to_good = 0.0
        self.p_good_to_bad = 0.0
        if self.loss_model == "gilbert-elliott":
            self.p_bad_to_good = 1.0 / self.mean_burst_len
            if self.drop_rate >= 1.0:
                # drop_rate=1 时 p_gb = d*p_bg/(1-d) 发散: 稳态恒为坏且不再离开。
                self.p_bad_to_good, self.p_good_to_bad = 0.0, 1.0
            else:
                self.p_good_to_bad = (self.drop_rate * self.p_bad_to_good
                                      / (1.0 - self.drop_rate))
        self._bad = self.loss_model == "gilbert-elliott" and self.drop_rate >= 1.0
        self._bad_init = self._bad
        self._rng = random.Random(self.seed)

    def _decide_drop(self):
        """这一次交付机会是否丢包 (调用方保证"确有包到期"时才调用)。"""
        if self.drop_rate <= 0.0:
            return False                       # 关闭: 一个随机数都不取 (扩展前行为)
        if self.loss_model == "gilbert-elliott":
            if self._bad:
                dropped = True                 # 坏状态内每次都丢
                if self._rng.random() < self.p_bad_to_good:
                    self._bad = False
            else:
                dropped = False
                if self._rng.random() < self.p_good_to_bad:
                    self._bad = True
            return dropped
        return self._rng.random() < self.drop_rate   # iid: 与扩展前逐位一致

    def _reset_loss(self):
        self._rng = random.Random(self.seed)
        self._bad = self._bad_init


class SensorTransportModel(_PacketLoss):
    """传感器传输: 离散延迟线 + 可复现丢包。

    语义 (每个仿真步调用一次 push, 再调用一次 poll):
      * push(sample, now): 样本进入延迟线, 预定在 now + latency_s 交付;
      * poll(now): 取出所有"已到期"的样本; 若有到期样本且未被丢包, 返回其中
        **最新**的一条 (旧包在接收端已被后到的包取代); 没有到期样本、或到期
        样本被丢包, 返回 None。

    poll 返回 None 有两种含义 (尚未到期 / 被丢弃), 需要区分时看
    delivery_count 与 drop_count。

    默认 latency_s=0, drop_rate=0: 同一时刻 push 的样本在同一时刻 poll 立即
    返回 —— 严格直通, 这是 SimRuntime 默认路径逐位不变的基础。
    """

    def __init__(self, latency_s=0.0, drop_rate=0.0, stale_after_s=None, seed=0,
                 loss_model="iid", mean_burst_len=1.0):
        """Args:
            latency_s: 单程延迟 (秒), 负数按 0 处理。
            drop_rate: 丢包率 [0,1]; 0=永不丢, 1=恒丢。仅在"有到期样本"时掷骰,
                因此随机序列只取决于交付机会的次数, 与调用密度无关。
            stale_after_s: 超过多久没有**成功交付**即视为过期; None=不判断。
            seed: 丢包随机序列的种子 (可复现)。
            loss_model: "iid" (默认, 逐位等于扩展前的伯努利) 或
                "gilbert-elliott" (突发丢包, 推导见 _PacketLoss)。
            mean_burst_len: 仅 gilbert-elliott 使用: 坏状态平均持续多少个
                丢包机会 (交付机会, 即帧); >=1, 1 时退化为接近 i.i.d.。
        """
        self.latency_s = max(0.0, float(latency_s))
        self.stale_after_s = None if stale_after_s is None else float(stale_after_s)
        self._init_loss(drop_rate, seed, loss_model, mean_burst_len)
        self._queue = deque()        # [(deliver_at, seq, sample, sample_time)]
        self._seq = 0
        self.delivery_count = 0      # 成功交付给消费者的样本数
        self.drop_count = 0          # 到期但被丢弃的样本数
        self._last_delivery_time = None
        self._last_sample_time = None
        self._first_push_time = None

    def push(self, sample, now):
        """把本帧样本送进延迟线, 并记录它的**采样时刻** = now。

        sample 由调用方保持不再修改 (仿真每帧新建)。
        """
        now = float(now)
        if self._first_push_time is None:
            self._first_push_time = now
        self._seq += 1
        self._queue.append((now + self.latency_s, self._seq, sample, now))

    def poll(self, now):
        """返回此刻应交付的样本; 未到期或被丢包时返回 None。"""
        now = float(now)
        due = None
        while self._queue and self._queue[0][0] <= now + _EPS:
            due = self._queue.popleft()   # 越晚到期者胜出 (旧包被取代)
        if due is None:
            return None
        # 掷骰只在真的有包到期时进行, 保证同一 seed 的序列可复现。
        if self._decide_drop():
            self.drop_count += 1
            return None
        self.delivery_count += 1
        self._last_delivery_time = now
        self._last_sample_time = due[3]        # 原始采样时刻, 不是交付时刻
        return due[2]

    def last_delivery_time(self):
        """最近一次成功交付的仿真时刻 (秒); 从未交付返回 None。"""
        return self._last_delivery_time

    def last_sample_time(self):
        """最近一次**成功交付**样本的采样时刻 (秒); 从未交付返回 None。

        与 last_delivery_time() 的区别: 后者是"交付发生"的仿真时刻, 本方法给
        的是"这条测量被采集"的时刻, 两者相差一个传输延迟。
        """
        return self._last_sample_time

    def last_age(self, now):
        """当前手上这条测量的年龄 = now - last_sample_time(); 从未交付返回 None。"""
        if self._last_sample_time is None:
            return None
        return float(now) - self._last_sample_time

    def is_stale(self, now):
        """自最近一次交付起是否已超时 (stale_after_s=None 时恒为 False)。

        还没交付过任何样本时, 以第一个 push 的时刻为基准 (延迟线的暖机期),
        避免刚构造就被判过期。
        """
        if self.stale_after_s is None:
            return False
        ref = self._last_delivery_time
        if ref is None:
            ref = self._first_push_time
        if ref is None:
            return False
        return (float(now) - ref) > self.stale_after_s

    def reset(self):
        """清空延迟线与计数 (仿真 KeyR 复位)。丢包 RNG 流按 seed 重新开始。

        一并清空时间戳状态: reset 后 last_sample_time()/last_age() 都回到 None。
        """
        self._queue.clear()
        self._seq = 0
        self.delivery_count = 0
        self.drop_count = 0
        self._last_delivery_time = None
        self._last_sample_time = None
        self._first_push_time = None
        self._reset_loss()


class CommandTransportModel(_PacketLoss):
    """上行指令链路 (遥控/速度指令) 的传输保真度: 离散延迟线 + 可复现丢包。

    延迟语义与 SensorTransportModel 完全一致: push(cmd, now) 预定在
    now + latency_s 到达, poll 在首个满足 k*dt >= latency_s 的步交付, 即
    k = ceil(latency_s / dt) (浮点用 _EPS 兜住)。

    交付语义不同 (指令是**状态**, 测量是**一次读数**): poll(now) 返回"此刻已
    到达的最新一条指令", 同一条指令会被反复返回直到有更新的指令到达; 尚未有
    任何指令到达 (冷启动) 才返回 None。

    丢包语义: 被丢弃的指令不会返回, 也不覆盖 last_command —— poll 仍返回上一条
    成功到达的指令, 由**调用方**决定是保持它还是归零 (真机上 RCManager 是 0.5s
    后自动归零, 那个超时属于遥控状态机, 不属于传输层)。每个到期指令是一次独立
    的交付机会, 各掷一次骰 (默认 latency=0 时每帧恰好一次)。

    默认 latency_s=0, drop_rate=0: push 后同一时刻就能 poll 到, 严格直通。
    """

    def __init__(self, latency_s=0.0, drop_rate=0.0, seed=0, loss_model="iid",
                 mean_burst_len=1.0):
        """Args: 同 SensorTransportModel (stale_after_s 对指令无意义, 故不提供)。"""
        self.latency_s = max(0.0, float(latency_s))
        self._init_loss(drop_rate, seed, loss_model, mean_burst_len)
        self._queue = deque()        # [(deliver_at, seq, cmd)]
        self._seq = 0
        self.delivery_count = 0      # 成功到达调用方的指令数
        self.drop_count = 0          # 到达时被丢弃的指令数
        self.last_command = None     # 最近一次成功到达的指令 (从未到达为 None)
        self._last_delivery_time = None
        self._first_push_time = None

    def push(self, cmd, now):
        """把本帧要下发的指令送进延迟线; cmd 由调用方保持不再修改。"""
        now = float(now)
        if self._first_push_time is None:
            self._first_push_time = now
        self._seq += 1
        self._queue.append((now + self.latency_s, self._seq, cmd))

    def poll(self, now):
        """返回此刻已到达的最新一条指令; 尚无指令到达时返回 None。"""
        now = float(now)
        while self._queue and self._queue[0][0] <= now + _EPS:
            _, _, cmd = self._queue.popleft()   # 按到达先后处理, 越晚到达者胜出
            if self._decide_drop():
                self.drop_count += 1
                continue                        # 丢掉的指令不返回也不覆盖上一条
            self.delivery_count += 1
            self._last_delivery_time = now
            self.last_command = cmd
        return self.last_command

    def last_delivery_time(self):
        """最近一次成功交付指令的仿真时刻 (秒); 从未交付返回 None。"""
        return self._last_delivery_time

    def reset(self):
        """清空延迟线/计数/上一条指令; 丢包 RNG 流按 seed 重新开始 (可复现)。"""
        self._queue.clear()
        self._seq = 0
        self.delivery_count = 0
        self.drop_count = 0
        self.last_command = None
        self._last_delivery_time = None
        self._first_push_time = None
        self._reset_loss()


class ActuatorLag:
    """执行器一阶滞后 (first-order lag / PT1), 用于速度环。

    连续模型:  tau * dv/dt = cmd - v        (一阶惯性环节)
    在 [t, t+dt] 上令 cmd 恒定 (零阶保持) 积分, 得精确离散解:
        v(t+dt) = cmd + (v(t) - cmd) * exp(-dt/tau)
    代数等价于本类实现的增量形式:
        v_new = v + (cmd - v) * (1 - exp(-dt / tau))
    正确性依据: 上式就是该 ODE 的解析解在一步内的闭式表达 (不是欧拉近似),
    因此任意 dt 下都不引入离散化误差, 只有浮点舍入。

    物理含义: 与 RC 低通 / 电机转速环同形, tau 是时间常数 —— 阶跃响应在
    t = tau 时达到 1 - 1/e ≈ 63.2%, 在 3*tau 时约 95%, 5*tau 时约 99.3%。
    它刻画"速度指令不会瞬时变成机体速度", 正是审计指出的
    "仿真里速度是理想源"这一差距。

    tau_s <= 0 时**严格直通**: 直接返回 cmd 的副本, 不做任何浮点混合 ——
    保证默认参数下与"没有这个类"逐位一致。
    """

    def __init__(self, tau_s=0.0):
        """Args: tau_s: 时间常数 (秒); <=0 表示直通 (无滞后)。"""
        self.tau_s = float(tau_s)
        # 初值取静止 (v=0): 真实执行器从静止起步, 阶跃开始时确实存在瞬态。
        self._v = np.zeros(3)
        self.update_count = 0

    @property
    def value(self):
        """当前滞后输出 (副本)。"""
        return self._v.copy()

    def reset(self, v0=None):
        """复位内部状态 (仿真 KeyR): v0 为 None 时回到静止。"""
        self._v = np.zeros(3) if v0 is None else np.asarray(v0, dtype=float).ravel()[:3].copy()
        self.update_count = 0

    def update(self, cmd, dt):
        """推进一个 dt, 返回滞后后的速度指令 (副本, m/s)。"""
        cmd = np.asarray(cmd, dtype=float).ravel()
        if self.tau_s <= 0.0:
            self._v = cmd.copy()      # 直通: 等于 cmd, 逐位一致
            self.update_count += 1
            return self._v.copy()
        dt = float(dt)
        if dt <= 0.0:
            return self._v.copy()
        alpha = 1.0 - math.exp(-dt / self.tau_s)
        self._v = self._v + (cmd - self._v) * alpha
        self.update_count += 1
        return self._v.copy()
