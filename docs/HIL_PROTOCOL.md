# HIL / 上机测试协议（拆桨 · 系留 · SITL）

> **状态：尚未执行（NOT EXECUTED）**
> 本文是**流程与记录模板**。截至最后更新，本仓库的自动化证据只到**契约层**
> （指令路由、闸门、看门狗、fail-closed 行为，见 `tests/`），
> **没有任何一项真机飞行证据**。未执行的项不得在报告/论文中写成"已验证"。

---

## 0. 三层测试与它们各自能证明什么

| 层级 | 目的 | 能证明 | **不能**证明 |
|---|---|---|---|
| **L1 拆桨桌面测试** | 全链路软件行为 + 硬件接口 | 指令真的到达底层、故障注入下的状态机与看门狗行为、机械臂串口协议 | 空气动力学、定位精度、载荷能力 |
| **L2 系留低空测试** | 姿态/高度控制与安全分支 | 起飞/悬停/降落、高度保持、急停与受控下降在**真实动力学**下的表现 | 导航精度（无外部定位时）、抗风、续航 |
| **L3 SITL / 真飞控 HIL** | 控制律与定位环路 | 导航/巡检/返航在带真实飞控动力学下的行为 | 传感器实物质量、结构强度、防水防腐 |

**硬规则**：任何一层的结论都不能外推到上一层；L2 通过 ≠ 能导航，L3 通过 ≠ 能上机作业。

---

## 1. 通用安全前置（每次上机前逐条打勾）

- [ ] **桨叶已拆除**（L1）或**系留绳已固定且限长 ≤ 1.5 m**（L2）
- [ ] 现场有**独立于地面站的物理急停手段**（手抓/断电/独立遥控），且操作人已就位
- [ ] 人员与旋翼保持 ≥ 1.5 m，护目镜已佩戴
- [ ] 电池电压正常，无鼓包；Tello 固件与 APP 版本已记录
- [ ] **软件闸门自检通过**（见 §4 的对应表）
- [ ] 本次测试的**代码 commit SHA** 已记录
- [ ] 断网演练：地面站进程被 kill 后，飞行器行为已知（Tello 失联后悬停→自动降落）

---

## 2. L1 拆桨桌面测试（props off）

**目标**：在没有飞行风险的前提下，验证软件链路与故障分支。

> **⚠ 必须先分清两类项目**（第三轮审计指出）：本文原先笼统写"全程电机不转"，但其中
> 若干项目会调用**飞行原语**（`takeoff()` / `emergency_descent()` / `land()`），
> 那些动作**会转动电机**。两类必须分开执行、分别记录，且**桨叶必须已拆除**。

### L1-A 纯指令路由 / 闸门类（不触发任何飞行原语，电机不应转动）

- **连接失败路径**：先不接 Tello，确认 `HARDWARE_FAULT` 且**任务不启动**（不降级为模拟）。
- **视觉不可用路径**：把 `config/yolo_config.yaml` 的权重路径改成不存在的文件，确认 `vision_status=VISION_UNAVAILABLE`，且 `request_state("INSPECT")` 被拒。
- **定位闸门**：不接外部定位，确认 `localization_available()=False` 且 NAVIGATE/INSPECT/RETURN 全被拒。
- **速度指令到达**：`set_velocity` 后确认底层确实收到 `send_rc_control`（先用 `scripts/hil_smoke.py` 的离线模式验证，再上机看日志）。
- **停桨闸门（拒绝分支）**：高度未知时调用 `kill()`，确认**拒绝执行**并打印明确错误。
- **遥测看门狗**：断开 Tello Wi‑Fi，确认在 `timeout_land/kill` 量级内触发保护，且 `telemetry_fresh=False`。
- **机械臂**：`capabilities()` 打印；ACK 开启时（`wait_ack=True`）确认收到固件 ACK 才返回 True；拔掉串口确认返回 False（**不得假成功**）。
- **终态闩锁**：`mark_fault()` 后 `request_state("TAKEOFF")` 必须被拒；再模拟一次 KILL 级安全事件，
  确认**仍不得**自行回到 IDLE —— 只能 `clear_fault()`，且**飞行中禁止复位**。
- **任务期失效**：在 NAVIGATE/INSPECT/RETURN 中断开定位 / 让视频无帧，确认当场停速度并进
  `MISSION_FAILED`（`get_state_dict()["mission_failed_reason"]` 可读）。

### L1-B 会触发飞行原语类（**电机会转** —— 桨叶必须已拆除、机体固定、人离开旋翼平面）

- **起飞原语可达性**：`takeoff()` 确实下发（电机起转、日志可见），随后立即 `land()`。
- **受控下降闭环**：空中触发 `mark_fault()` → `emergency_descent()` 被调用**且检查返回值**；
  降到 ≤30cm 后自动 `land()` 收尾；落地后**不再**下发动作。
- **下降能力缺失的升级**：使底层返回 False，确认打印"受控下降未推进…需要飞控级 failsafe 或外部急停"。
- **停桨闸门（允许分支）**：只有高度已知且 ≤30cm 时才真正停桨。

### 步骤
1. 桨叶拆除，机体固定（L1-B 尤其重要）；接通 Arduino/PCA9685 与 Tello。
2. 启动：`python backend/main.py --mode hardware`（真机模式）。
   **注意**：CLI 只接受 `simulation` / `hardware` 两个取值，本文档早先写的 `--mode real` 是错的。
3. 先做完 **L1-A** 全部项目并记录；再做 **L1-B**，每项前后确认桨叶状态与人员位置。
4. 记录到 `docs/hil_records/props_off_TEMPLATE.md`（模板已按 A/B 分类）。

### 通过判据
- **L1-A**：每一项都按**设计的行为**发生（拒绝/失败/进故障态），**没有任何一项"看起来成功"**，
  且**电机全程不转**。
- **L1-B**：电机按预期起转/停止；下降闭环与收尾降落可复现；**无一项静默失败**。

---

## 3. L2 系留低空测试（tethered, ≤1.5 m）

**目标**：真实动力学下的起飞/悬停/降落与安全分支。

### 步骤
1. 系留绳固定，长度 ≤1.5 m；空域清空；操作人手握急停手段。
2. `python backend/main.py --mode hardware`；确认 `localization_available()=False`（**无外部定位时不应允许自动导航** —— 这正是预期）。
3. 手动起飞到 0.5–1.0 m：记录高度保持的**实测**均值/最大偏差（用飞行日志 CSV，不要凭肉眼）。
4. **受控下降**：触发 `EMERGENCY`，确认按分帧脉冲下降且**不砍桨**；触地后进 `IDLE`。
5. **急停**：高度 >30cm 时调用 `kill()` → 必须**被拒绝**；降到 ≤30cm 后调用 → 允许。
6. **失联**：地面站断电/关 Wi-Fi，记录飞行器自身行为与恢复流程。
7. 记录到 `docs/hil_records/tethered_TEMPLATE.md`。

### 通过判据
- 高度保持实测偏差与仿真同量级（**给出实测数字**，不是"看起来稳"）。
- 受控下降与急停拒绝行为与闸门设计一致。
- 失联后有明确的、可复现的处置结果。

---

## 4. L3 SITL / 真飞控 HIL

**现状**：本仓库**没有** PX4/ArduPilot SITL 环境，也没有真实飞控在环。
下面的接口是预留，**尚未实现**：

- `DroneInterface.set_velocity()` 已是正式契约（真机 Tello 与仿真适配器都已实现）→ 接 PX4 offboard 时实现同名方法即可。
- 定位源契约见 `backend/localization/base.py`（带时间戳/质量/有效期）→ 接 VIO/RTK 时实现 `read()` 即可。
- 仿真侧的传输模型（延迟/丢包/执行器滞后）见 `backend/simulation/transport_model.py`（Phase 3 引入）。

**要做的事**（未完成，按顺序）：
1. 搭 PX4 SITL（Gazebo）或 ArduPilot SITL，实现 `Px4Adapter(DroneInterface)`；
2. 在 SITL 下跑 `scripts/bench_sim_modes.py` 的同一协议，比较 SITL 与本地运动学仿真的差距；
3. 接真实飞控 HIL（飞控 + 真传感器，机体固定）；
4. 上机前完成 L1 + L2 全部通过。

---

## 5. 软件闸门 ↔ 测试项对应表

| 代码闸门 | 位置 | L1 验证项 | L2 验证项 |
|---|---|---|---|
| 视觉不可用拒绝 INSPECT | `main.py::_state_gate_reason` | ✔ | — |
| 无外部定位拒绝 NAVIGATE/INSPECT/RETURN | `main.py::localization_available` | ✔ | ✔ |
| 定位观测过期/低质量即不可用 | `backend/localization/base.py` | ✔ | ✔ |
| 遥测以**状态包到达**为准 | `tello_basic.py::has_fresh_telemetry` | ✔（拔网） | ✔（关地面站） |
| `motor_cutoff` 高度未知/偏高一律拒绝 | `tello_basic.py::motor_cutoff` | ✔ | ✔ |
| 降落/下降/停桨三概念分离 | `controlled_land` / `emergency_descent` / `motor_cutoff` | ✔ | ✔ |
| 控制循环异常 → FAULT（不静默死掉） | `main.py::_update` | ✔ | ✔ |
| 机械臂无串口/写失败 → False | `backend/arm/arm_controller.py` | ✔ | — |

---

## 6. 记录模板

- 拆桨桌面：`docs/hil_records/props_off_TEMPLATE.md`
- 系留低空：`docs/hil_records/tethered_TEMPLATE.md`

每份记录必须包含：日期、执行人、**代码 commit SHA**、Tello/固件版本、环境（室内/室外、温度、风力）、逐项结果（通过/失败/未测）、实测数字、异常与处置、结论（**只对本层成立**）。

---

## 7. 与仿真基准的关系

`scripts/bench_sim_modes.py`（协议 v1）给出 legacy 与 velocity 两条路径在**仿真**下的对比：

- legacy 位置级联在 2 m/s **持续风**下横向误差发散（数百米量级）；
- velocity 模式（与真机 RC 同源）在同风况下保持有界（个位数厘米量级）。

这是**仿真证据**，说明"速度链路更接近真机、且在风下更稳"，**不能**据此声称真机性能 —— 真机需要 L2/L3 的实测数字填进上面的模板。
