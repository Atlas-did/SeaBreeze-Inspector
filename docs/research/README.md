# Research & Evidence Working Papers (8/17 – 8/20, 2026)

Internal-facing research documents tracking the detection-model lineage and
evidence hardening campaign. English codebase docs live in `docs/`; this
directory preserves the working layer (Chinese) exactly as produced.

**Status headline**: the numbers cited in earlier README/docs
(YOLOv8-Nano, mAP@0.5 = 0.577) are **invalid** — a SHA-256 audit found 83%
of the v3 validation set appeared verbatim in the training set. Current
provisional lineage:

| ver | setup | mAP@0.5 | note |
|-----|-------|---------|------|
| v3 | 3-class, 1280px | 0.577 | **invalid** (83% leakage) |
| v4 | YOLO11s, 1024 tiles, binary nc=1 | 0.668 | provisional; adjacent-parent frames cross splits 50% → measures same-scene generalization |
| v5 | scene-isolated split | 0.027 | OOD failure, as expected |
| v5.1 | v5 + oversampling 2:1 | 0.053 | real gain but unusable; next: v5.2 dual protocol (ID val + OOD test) |

## Layout

- `GAP_TRACKER.md` — 12-module status tracker + v4 breakthrough record
- `plans/` — campaign plan (8/19)
- `evidence-hardening/` — 10 P1-series hardening docs + evidence map
- `experiments/` — v4 experiment report, v5 failure analysis, v5.1 analysis
- `module-docs/` — A1–D3, 26 experiment-design docs (unified 8-section template)
- `anti-fog/` — fog-invariant feature-consistency training proposals v1–v3

Related artifacts: `scripts/evidence/` (A1–D3 audit/experiment scripts),
`data/manifests/` (leakage audit + dataset manifests),
`runs/train/seabreeze/v4/` (v4 training curves & confusion matrices).

All numbers marked *provisional*; do not cite in the paper until the v5.2
dual-protocol evaluation is frozen.
