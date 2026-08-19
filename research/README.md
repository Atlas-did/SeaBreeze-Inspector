# Research Evidence Layer — Index

> Reproducible thesis evidence scripts (A1–D3) plus dataset manifests.
> Every number that appears in the thesis can be regenerated from one script in this directory.

## What this is

This directory is the **evidence layer** of the SeaBreeze-Inspector thesis: a set of
self-contained scripts, grouped by thesis section (A: Vision, B: Wind-resistance
control, C: Robotic arm, D: Reliability), that produce JSON/CSV reports backing the
claims made in the paper. Two files at `data/` make the dataset fully auditable.

## Layout

```
research/
├── README.md                    ← this file
├── EVIDENCE_MAP.md              ← claim ↔ script ↔ output mapping table
├── fog_synth.py                 ← synthetic fog (Koschmieder atmospheric scattering)
├── gen_report_figures.py        ← report figure generator
├── gen_latex_figures.py         ← LaTeX figure generator
├── md_to_docx.py                ← Markdown → Word converter
├── kimi_vision.py / kimi_k3_review.py / vision-config-kimi.json  ← vision review tooling
├── dsh_setup.ps1 / install_*.ps1 ← environment setup scripts
└── 专项/                        ← per-thesis-section evidence scripts (see below)
```

## Thesis-section scripts (`research/专项/`)

### A — Vision (needs real data + GPU)

| Script | Purpose | Runnable locally? |
|---|---|---|
| `A1/class_stats.py` | Class distribution statistics | ✅ (needs dataset) |
| `A1/group_split.py` | Grouped train/val/test split | ✅ (needs dataset) |
| `A1/remap_to_binary.py` | Re-annotate nc=1 → binary `defect` | ✅ (needs dataset) |
| `A1/wind_turbine_defect_binary.yaml` | Binary detection dataset config | — |
| `A2/train_cli.py` | YOLO training CLI | ❌ (needs GPU) |
| `A3/clean_and_visibility.py` | Atmospheric-scattering fog pairing | ✅ (needs dataset) |
| `A3/consistency_train.py` | Feature-consistency training (skeleton) | ❌ (needs GPU) |
| `A3/dehaze_joint.py` | Task-driven dehaze joint training (skeleton) | ❌ (needs GPU) |
| `A4/copy_paste_aug.py` | Copy-paste augmentation sampler | ⚠️ (function only) |
| `A4/sahi_slice.py` | SAHI tiled inference (needs `best.onnx`) | ⚠️ (needs ONNX) |
| `A4/superres_preprocess.py` | Super-resolution preprocessing | ⚠️ (needs SR model) |

### B — Wind-resistance control (runs locally, pure math)

| Script | Purpose | Runnable locally? |
|---|---|---|
| `B1/ekf_ablation.py` | EKF disturbance-observer Q/R ablation | ✅ |
| `B2/wind_resistance_model.py` + `B2/platform_x500.yaml` | Force-balance wind-resistance Monte-Carlo | ✅ |
| `B3/analyze_hover.py` | Hover drift analysis (needs real telemetry) | ⚠️ (needs data) |

### C — Robotic arm (runs locally)

| Script | Purpose | Runnable locally? |
|---|---|---|
| `C1/arm_error_decompose.py` | Arm error decomposition | ✅ |
| `C2/fk_ik_check.py` | Forward/inverse kinematics verification | ✅ |

### D — Reliability (runs locally)

| Script | Purpose | Runnable locally? |
|---|---|---|
| `D1/motion_blur.py` / `D1/dof6_blur.py` | Motion blur synthesis | ✅ |
| `D2/latency_profiler.py` | End-to-end latency profile | ⚠️ (simulated) |
| `D2/fault_inject_comm.py` | Communication fault injection | ✅ |
| `D3/gnss_fault_inject.py` | GNSS fault injection | ✅ |

## Dependencies

```bash
pip install numpy pyyaml   # required for all B/C/D scripts
pip install ultralytics    # A2/A3 only
```

## Quick run (B/C/D — no GPU, no data)

```bash
# B1 — EKF Q/R ablation
python research/专项/B1/ekf_ablation.py --out ekf_ablation_report.json

# B2 — wind-resistance model
python research/专项/B2/wind_resistance_model.py \
    --config research/专项/B2/platform_x500.yaml --out wind_resistance_report.json

# C2 — FK/IK check
python research/专项/C2/fk_ik_check.py
```

## Dataset manifests (auditability)

| File | Rows | Purpose |
|---|---|---|
| `data/data_sources.csv` | 1 | Provenance: source, license, transformations |
| `data/split_manifest.csv` | 15,528 | Per-image split + sha256 (reproducible split) |

## Known limitations (honest)

- `B1/ekf_ablation.py` — three Q settings produce near-identical RMSE (0.798 / 0.799 / 0.800);
  the ablation is **not discriminative** as written (see `EVIDENCE_MAP.md`).
- `B2/platform_x500.yaml` — parameters are **design assumptions, not measured**;
  under them the model predicts `vmax ≈ 8.2 m/s` (0% margin at 12 m/s).
- `A3/consistency_train.py` and `A3/dehaze_joint.py` are **interface skeletons**, not
  complete training loops.
- `D2/latency_profiler.py` uses `numpy.random` — simulated, not measured.

See `EVIDENCE_MAP.md` for the full claim ↔ script ↔ output table.
