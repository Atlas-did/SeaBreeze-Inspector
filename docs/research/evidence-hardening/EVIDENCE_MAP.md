# Evidence Map — Claim ↔ Script ↔ Output

> Maps every verifiable claim in the thesis to the exact script that regenerates it,
> and the output file that holds the number. The "Status" column is honest: only
> claims whose script reproduces correctly are marked ✅.

## How to read

- **Claim** = the sentence the thesis makes (or would make).
- **Script** = the file that reproduces the number.
- **Output** = the artifact produced, and the number it currently yields.
- **Status** = ✅ reproducible / ⚠️ needs data or GPU / ❌ currently does not support the claim.

## A — Vision

| Claim | Script | Output | Status |
|---|---|---|---|
| Dataset is split leak-free by acquisition unit | `A1/group_split.py` | grouped split, 0 cross-split groups | ✅ (needs dataset) |
| Labels remapped multi-class → binary `defect` | `A1/remap_to_binary.py` | 22,394 → 22,394 boxes, 0 errors | ✅ (needs dataset) |
| Detector trained on binary defect task | `A2/train_cli.py` | `runs/train/...` weights | ❌ (needs GPU) |
| Synthetic fog via Koschmieder ASM | `A3/clean_and_visibility.py` | fog-paired images | ✅ (needs dataset) |
| Feature-consistency improves fog robustness | `A3/consistency_train.py` | training run | ❌ (skeleton) |
| Task-driven dehazing improves detection | `A3/dehaze_joint.py` | training run | ❌ (skeleton) |
| Copy-paste augments rare defects | `A4/copy_paste_aug.py` | augmented dataset | ⚠️ (function only) |
| SAHI tiled inference catches small defects | `A4/sahi_slice.py` | tiled detections | ⚠️ (needs `best.onnx`) |

## B — Wind-resistance control

| Claim | Script | Output | Status |
|---|---|---|---|
| "Q scales with disturbance-tracking aggressiveness" | `B1/ekf_ablation.py` | `ekf_ablation_report.json` | ❌ **not supported** — RMSE 0.798 / 0.799 / 0.800 |
| Observer output ≈ 0 in still air | `B1/ekf_ablation.py` | `static_baseline.d_hat_std = 0.109` | ❌ **not supported** (should be ≈ 0) |
| "Platform withstands Beaufort 6 (12 m/s) wind" | `B2/wind_resistance_model.py` | `vmax_mean = 8.2 m/s`, `p_ok_12ms = 0.0%` | ❌ **contradicted** by current params |
| Wind-resistance limit is ~8 m/s (design params) | `B2/wind_resistance_model.py` | `vmax 5–95% = [7.0, 9.5] m/s` | ✅ (given the assumed params) |
| Hover drift below X cm | `B3/analyze_hover.py` | hover report | ⚠️ (needs real telemetry) |

## C — Robotic arm

| Claim | Script | Output | Status |
|---|---|---|---|
| Arm error decomposed (kinematic / noise / repeatability) | `C1/arm_error_decompose.py` | error report | ✅ |
| FK/IK consistent (P50 ≈ 2.7e-10 mm) | `C2/fk_ik_check.py` | FK/IK residual report | ✅ |

## D — Reliability

| Claim | Script | Output | Status |
|---|---|---|---|
| Motion-blur augmentation models 6-DOF shake | `D1/motion_blur.py` / `D1/dof6_blur.py` | blurred images | ✅ |
| End-to-end latency decomposed t0–t3 | `D2/latency_profiler.py` | latency report | ⚠️ **simulated** (`np.random`) |
| Communication fault injection (N ≥ 20 per cell) | `D2/fault_inject_comm.py` | injection matrix | ⚠️ (state machine, not run) |
| GNSS fault injection | `D3/gnss_fault_inject.py` | fault report | ✅ |

## Critical fixes before thesis submission

1. **B1** — make the ablation discriminative: sweep Q over orders of magnitude, also
   sweep R, or report tracking-latency under time-varying disturbance (not just RMSE).
2. **B2** — replace assumed `platform_x500.yaml` params with measured platform values,
   or downgrade the "Beaufort 6" wording to "~8 m/s under design assumptions".
3. **D2** — replace `np.random` with instrumented hardware timings (monotonic clock).
4. **A3** — complete `consistency_train.py` / `dehaze_joint.py` into runnable loops,
   or drop the corresponding claims.
