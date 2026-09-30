# L1 拆桨桌面测试记录（模板）

> 复制本文件为 `props_off_YYYYMMDD_<执行人>.md` 并填写。未填写的项视为**未测**。

- **日期**：
- **执行人**：
- **代码 commit SHA**：`git rev-parse HEAD` → 
- **Tello 固件 / APP 版本**：
- **Arduino 固件版本/编译时间**：
- **环境**：室内 / 温度 / 是否接桨（**必须为"已拆除"**）

## 安全前置

- [ ] 桨叶已拆除
- [ ] 机体固定
- [ ] 独立急停手段就位（说明具体方式）：
- [ ] 护目镜 / 人员距离 ≥1.5m

## 逐项结果

| # | 项 | 期望 | 实测 | 结果 |
|---|---|---|---|---|
| 1 | 不接 Tello 启动 | `HARDWARE_FAULT`，任务不启动，**不降级为模拟** | | ☐通过 ☐失败 ☐未测 |
| 2 | 权重路径改为不存在 | `vision_status=VISION_UNAVAILABLE`；`request_state("INSPECT")` 被拒 | | ☐ ☐ ☐ |
| 3 | 不接外部定位 | `localization_available()=False`；NAVIGATE/INSPECT/RETURN 全被拒 | | ☐ ☐ ☐ |
| 4 | `set_velocity` | 底层确收到 `send_rc_control`（贴日志片段） | | ☐ ☐ ☐ |
| 5 | 高度未知时 `kill()` | **拒绝**执行 + 明确错误；状态不变 | | ☐ ☐ ☐ |
| 6 | 高度 ≤30cm 时 `kill()` | 允许执行 | | ☐ ☐ ☐ |
| 7 | 断开 Tello Wi-Fi | `telemetry_fresh=False`；在 timeout_land/kill 内触发保护 | | ☐ ☐ ☐ |
| 8 | 机械臂 `capabilities()` | 如实（无位置反馈/无电流/无堵转） | | ☐ ☐ ☐ |
| 9 | 拔掉机械臂串口后下发角度 | 返回 **False**（不得假成功） | | ☐ ☐ ☐ |
| 10 | ACK 开启（`wait_ack=True`） | 收到固件 ACK 才 True；不回则超时 False | | ☐ ☐ ☐ |

## 实测数字

- RC 下发频率（实测 Hz）：
- 断网后触发保护的时间（s）：
- 其它：

## 异常与处置

（逐条写：现象 / 原始日志 / 判断 / 处置 / 是否复现）

## 结论

- 本层结论（**只对拆桨桌面测试成立**）：
- 未通过/未测项 与 阻塞原因：
