# verify_scripts 输出读数指南（2026-10-06）

本目录的脚本产出仓库根目录下的 `*_summary.json` / `*_trace.csv`。**读之前先看这里**，
否则极易把"同义反复"当成"性能指标"。

## 1. 悬停：必须区分两个口径，别只看 calm

| 文件 | 口径 | 实测 | 能不能当"精度能力"宣称 |
|---|---|---|---|
| `hover_result_v3_summary.json` | **无扰动**静风 | 三轴误差全部 0（trace 实测 x≈2.6e-18、y≈2.7e-17） | ❌ **不能**。这是机器零 |
| `hover_wind_result_summary.json` | **带侧风** 0.30/0.20 m/s | 3D RMS **1.067 m**，max 1.634 m | ✅ 这才是抗扰表现 |

**为什么 calm 的 0 是"同义反复"**：无扰动仿真里控制器会把机体钉在目标点上，
误差落到浮点零量级是**必然结果**，不含任何关于控制品质的信息。两组数字差 4 个数量级
（1e-18 vs 1e0），拿 calm 的 0 去宣称"悬停精度 ≤0.0001 m"是**过度声称**。

**机制**：`measure_hover_3d.py` 现在会自动识别这种情况并写入
`numerical_zero_flag: true` + `numerical_zero_note`。已入库的旧 JSON 早于该修复，
**它们里面的 `note` 是旧版静态模板字符串**（曾出现 `axes_measured` 全 true 而 note 仍写
"未测到的维…未测量"的自相矛盾），以本指南为准。

## 2. 各文件对应关系

| 输出 | 脚本 | 说明 |
|---|---|---|
| `hover_result*_summary.json` / `_trace.csv` | `measure_hover_3d.py` | 悬停定位精度（见上，注意口径） |
| `latency_result_summary.json` | `measure_latency.py` | 闭环时延：T1 指令往返 p95 22.0 ms；T2 闭环 p95 70.2 ms（目标 100 ms） |
| `arm_tcp_result_summary.json` | `measure_arm_tcp.py` | 机械臂 TCP 精度：8 目标，均值 4.3 mm，max 4.9 mm（指标 10 mm） |
| `det_fps_*_summary.json` | `bench_detection_fps.py` | CPU 推理吞吐：640→10.68 / 1024→4.28 / 1280→2.57 fps，**均未达 20 fps 目标** |
| `gust_ekf_demo_*` | `gust_ekf_demo.py` + `wind_gust_injector.py` | 阵风 + EKF 前馈演示（OmniSim 风桥） |
| `command_mode_comparison.json` | `compare_command_modes.py` | 两种物理驱动模式对照（P1-12） |

## 3. 共同边界（引用时必须带上）

- **全部为 simulation-only**（自家仿真或 OmniSim 仿真），**无任何真机实测**。
  `docs/HIL_PROTOCOL.md` 明确标注真机路径 NOT EXECUTED。
- 检测 FPS 是 **CPU** 推理结果；上 GPU / TensorRT 另说，不能据此下"实时性达标"结论。
- 悬停的 calm 组不是性能数据（见 §1）。
