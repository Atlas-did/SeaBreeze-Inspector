# v5.2 OOD 一次性正式评估 — 最终报告

**日期**:2026-09-01 | **槽位**:final(D7 一次性锁已写:`ood_test_EVAL_LOCK_final.json`)
**权重**:`runs/detect/v5_2_yolo11s_1024_seed42/weights/best.pt`(sha256 `7c3e1e39…`,ID val 选优)
**数据**:训练方交付的 `v5.2-adjudicated-idval-oodtest`(test=frozen OOD,710 图/4 场景块/138 正/189 框)
**管线**:`research/v5_2/ood_eval.py`(headline=Ultralytics val 全扫;诊断=自研贪心 IoU 匹配,conf=0.25/IoU=0.5)
**原始 JSON**:`research/v5_2/report_ood_test_20260901_143516.json`

---

## 1. 论文口径数字(OOD,只此一次)

| 指标 | 数值 |
|---|---:|
| mAP50 | **0.0365** |
| mAP50-95 | **0.0099** |
| Precision | 0.2167 |
| Recall | 0.0688 |

**对照 ID validation(seed42 best,380 图/5 场景)**:mAP50=0.2814 / R=0.2931 / mAP50-95=0.1175 / P=0.5331
→ **ID→OOD 衰减 ≈ 7.7×(mAP50:0.2814/0.0365;mAP50-95 口径 ≈12×:0.1175/0.0099)**。双评估协议的价值就在这组对照:ID val 证明训练管线健康(比 v5.1 的 0.0531 提升 5.3×),OOD 证明跨场景泛化仍是真实短板。

## 2. 三项判决(§4.第三步)

| 场景块 | 结果 | 判读 |
|---|---|---|
| DJI_0234–0251(细长前缘) | 22 GT,0 TP | 全灭——细长形状域 |
| DJI_0615–0628 | 42 GT,0 TP | 全灭——外观域 |
| DJI_0685–0713(近距灰天,52%框) | 99 GT,0 TP,4 FP | 全灭——外观域(训练方文档预警的主场景) |
| **DJI_0745–0758** | 23 GT,**4 TP / 0 FP**(P=1.0,R=0.154) | **唯一有检出**——外观最接近训练域 |

**短边分桶**:≤32:0/6,≤64:0/50,≤128:0/92(全灭);**>128:4/41(R=0.098,唯一有 TP)**
**长宽比**:≤5:4/179(0.022);≤10/≤20/>20:全 0

**判定:外观域偏移为主 + 尺度敏感性叠加。** 唯一的有效检出集中在"外观最近训练域 + 大目标(>128px)"的交集;所有小目标(原生 ~24px 级)在 OOD 全灭。

## 3. 联合门槛结论(§4.第四步)

| 门槛 | 结果 |
|---|---|
| ID val Recall 持续上升 | ✅ 0.05→0.29(ep10→50) |
| ID val mAP50 无单轮尖峰 | ✅ ep50/59 都在 0.26–0.28 |
| OOD Recall 不接近 0 | ⚠️ 0.0688——接近但不为 0;4 场景块中 1 个有真实检出(P=1.0) |
| val cls loss 不发散 | ✅ 4.82→3.39 单调下降 |
| 小目标 Recall 不塌陷 | ❌ OOD 上 ≤128px 全灭(训练侧待查) |

**按方案预言的路标:"若 ID validation 明显提高、OOD 仍很低 → 训练管线已正常,剩域泛化问题,不要继续盲调 YOLO 参数。"** 结论成立。

## 4. 下一步杠杆(按优先级)

1. **加 defect 数据(最高杠杆,方案 §4.1/交接 v2 方向 A.1)**:~2550 张"假 clean"里真实缺陷重新标注,defect 587→1500+,**重点补齐 OOD 四个场景块的外观域**(灰天近距/细长前缘/不同拍摄距离)——没有训练域样本,任何模型都学不会这些域。
2. **尺度问题单独核查**:train 正样本短边分布(split_report:≤32 有 99 个框)vs OOD 的 ≤128 全灭——检查 1024 tile 下小目标在训练域的可见性,必要时提 imgsz 或切片重叠。
3. **绿色贴片语义复核**(训练方文档 §6 已预警):若确认绿贴片只是定位工具,需全数据统一重标——会改变正类语义,慎重。
4. **seed0 vs seed42 方差**:seed0 mAP50=0.156 vs seed42=0.2814(1.8×),说明单 seed 结论不稳,论文若报 ID val 需双 seed 宏平均。

## 5. 证据链与复现

- 训练配置核对:args.yaml(两 seed)与 §7 协议逐项一致(60ep/1024/batch8/mosaic0.2/scale0.25/translate0.05/fliplr0.5)
- 数据完整性:SHA256SUMS 对应、泄漏审计全零(训练方 audit_v5_2)、junction 免复制接入
- D7 纪律:final �位已锁,重跑必须人工删锁(设计如此)
- 复现命令:`venv\Scripts\python.exe research/v5_2/ood_eval.py --split ood_test --slot final --model runs\detect\v5_2_yolo11s_1024_seed42\weights\best.pt --split-dir-root datasets\derived\v5_2_adjudicated\clean_binary_v5_2_adjudicated --imgsz 1024`
