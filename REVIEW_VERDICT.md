# Review Verdict — "Four branches & thesis evidence layer"

> Independent verification of an external review of this repository.
> Every claim below was checked against the actual repo state and (where a script is
> involved) re-run locally. Verdict per item: ✅ correct · ⚠️ correct with nuance · ❌ wrong.

## Summary

The reviewer is **substantially correct on all material points**. All three scientific
findings (B1/B2) reproduce *exactly* when the scripts are run. All documentation and
engineering-hygiene findings are confirmed against the repo. Two minor imprecisions,
noted below, do not change any conclusion.

## Branch & commit claims

| Reviewer claim | Verdict |
|---|---|
| Repo has 4 branches: `main`, `w1`, 2 × `copilot/*` | ✅ Confirmed (`git ls-remote`) |
| `main` HEAD = `0b441da` | ✅ Confirmed (`origin/main`) |
| `w1` = `main` + exactly 2 commits | ✅ Confirmed (`1334ee8`, `e054081`) |
| `w1` = 2 commits, 34 files, ~1.8万 lines | ✅ Confirmed (commit 1 = 32 files/2447 lines, commit 2 = 2 files/15531 lines) |
| Commit 1 = research/ 20 evidence scripts (A–D groups) | ✅ Confirmed (20 `.py` + 2 `.yaml` in `research/专项/`) |
| Commit 2 = `data_sources.csv` + `split_manifest.csv` (15529 rows) | ✅ Confirmed (15,528 data rows + header) |
| `copilot/...-job` = one small workflow change, didn't fix CI | ✅ Confirmed (own commit = 1 file, 6+/1- in `test.yml`) |
| `copilot/...-again` = only an "Initial plan" commit | ✅ Confirmed (top commit has no file changes) |
| `w1` can fast-forward merge into `main` | ✅ Confirmed (`w1..main` is empty) |

> ⚠️ One nuance: the *local* `main` branch is stale at `d9d49c8` (the reviewer correctly
> described `origin/main` = `0b441da`). Before merging, run `git fetch && git pull origin main`.

## Scientific findings (re-run locally)

| Reviewer claim | Reproduced output | Verdict |
|---|---|---|
| B1 Q ablation has no discrimination: 0.798 / 0.799 / 0.800 | `0.798 / 0.799 / 0.800` | ✅ exact |
| B1 still-air baseline ≈ 0.109 (not ≈ 0) | `static_baseline.d_hat_std = 0.1090` | ✅ exact |
| B2 12 m/s margin = 0.0%, vmax ≈ 8.2 m/s | `vmax_mean = 8.2`, `p_ok_12ms = 0.0%` | ✅ exact |
| B2 params are "design assumptions, not measured" | `platform_x500.yaml` header states this verbatim | ✅ |

## Documentation findings

| Reviewer claim | Verdict |
|---|---|
| README badge points to `offshore-wind-uav-arm/offshore-wind-uav-arm` (non-existent) | ✅ Confirmed (`README.md:6`) — **fixed** |
| README says port 8800, `http_bridge.py` is 8811 | ✅ Confirmed (`README.md:51` vs `_PORT = 8811`) — **fixed** |
| `docs/SOFTWARE.md` references deleted `safety_guard.py` / `communication.py` | ✅ Confirmed (neither file exists; replaced by `mission/safety.py`, `utils/bus.py`) — **fixed** |
| `seabreeze-3d-sim/README.md` references `3D_SIMULATION_OPTIONS.md` | ⚠️ Correct with nuance: the file exists at `docs/3D_SIMULATION_OPTIONS.md` but is **gitignored** (not tracked) — a concrete victim of the `.gitignore` whitelist anti-pattern — **fixed** |
| `seabreeze-3d-sim/README.md` references `../seabreeze_models_bpy.py.txt` (wrong name+path) | ✅ Confirmed (actual file: `seabreeze-3d-sim/seabreeze_models_bpy.py`) — **fixed** |
| `.gitignore` `docs/*.md` whitelist is an anti-pattern | ✅ Confirmed (18 docs tracked but only 10 whitelisted; new docs silently ignored) |

## Engineering hygiene

| Reviewer claim | Verdict |
|---|---|
| `best.onnx` (12.3 MB) + `best.torchscript` (12.5 MB) committed to git | ✅ Confirmed (`git ls-files` shows both; `.gitignore` only excludes `*.pt`) |
| CI `continue-on-error: true` on dependency install | ✅ Confirmed (3 occurrences in `.github/workflows/test.yml`) |
| `w1` name is semantically opaque | ✅ Confirmed (agreed) |

## Recommended actions (awaiting go-ahead — these touch the remote)

These are **not** auto-applied because they mutate remote state. Confirm to proceed:

```bash
# 1. Sync local main to origin, then fast-forward merge w1
git checkout main && git fetch origin && git pull origin main
git merge w1                                   # fast-forwards cleanly

# 2. Delete the two abandoned Copilot branches
git push origin --delete copilot/fix-failing-github-actions-job
git push origin --delete copilot/fix-failing-github-actions-job-again

# 3. Rename w1 → thesis-evidence (after merge, or in place)
git branch -m w1 thesis-evidence
git push origin :w1 thesis-evidence

# 4. Stop tracking the two large weights (keeps them on disk, drops from git)
git rm --cached data/weights/best.onnx data/weights/best.torchscript
# then add to .gitignore: data/weights/*.onnx, data/weights/*.torchscript
```

## Bottom line

The reviewer's critique is accurate and actionable. The single most valuable asset it
identifies — the reproducible evidence layer (`research/` + `split_manifest.csv`) — is
real, but **three scripts currently contradict the thesis** (B1 non-discriminative
ablation, B1 non-zero static baseline, B2 0% margin at 12 m/s). Fix those scripts or
soften those claims before submission; do not publish the numbers as-is.
