"""CLI 入口：python -m backend.omnisim altitude --target-m 1.5 --backend sim

用统一口径执行"目标高度保持"实验，输出与 OmniSim 公共测试可比的稳态高度误差。

示例：
  # 自家仿真基准（静风理想）
  python -m backend.omnisim altitude --target-m 1.5 --backend sim --json
  # 自家仿真基准（带风，保真度参考）
  python -m backend.omnisim altitude --target-m 1.5 --backend sim --wind --json
  # OmniSim（需先启动 mavic_omnilink_bridge 并设 OMNISIM_BASE_URL）
  python -m backend.omnisim altitude --target-m 1.5 --backend omnisim
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.drone.commands import run_altitude_hold

DEFAULT_OUT_DIR = Path("data/processed/omnisim/commands")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m backend.omnisim",
                                description="SeaBreeze 目标高度保持实验（统一口径）")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("altitude", help="目标高度保持实验")
    a.add_argument("--target-m", type=float, default=1.5, help="目标高度（米），默认 1.5")
    a.add_argument("--backend", choices=["sim", "omnisim", "mock"],
                   default="sim", help="执行后端；mock 不支持动态悬停")
    a.add_argument("--calm", dest="wind", action="store_false", default=False,
                   help="静风理想工况（默认）")
    a.add_argument("--wind", dest="wind", action="store_true",
                   help="带风工况（0.5m/s 顺风+阵风）")
    a.add_argument("--settle-s", type=float, default=40.0, help="稳态观测时长（秒）")
    a.add_argument("--seed", type=int, default=42, help="随机种子（可复现）")
    a.add_argument("--note", default="", help="备注（如实验编号/天气假设）")
    a.add_argument("--json", action="store_true", help="只输出 JSON")
    a.add_argument("--out", default=None, help="结果 JSON 输出路径（默认写入 data/processed/omnisim/commands/）")
    return p


def _build_driver(backend: str, windy: bool):
    if backend == "sim":
        from backend.simulation.altitude_driver import build_sim_driver
        return build_sim_driver(calm=not windy)
    if backend == "omnisim":
        from backend.omnisim.adapter import OmniSimDriver
        return OmniSimDriver()
    if backend == "mock":
        raise ValueError("mock 后端无法执行动态高度保持（MockTello 无动力学）；"
                         "请用 --backend sim 得到自家仿真基准，或用 --backend omnisim。")
    raise ValueError(f"未知后端 {backend!r}")


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command != "altitude":
        print(f"未支持的子命令 {args.command!r}", file=sys.stderr)
        return 2

    try:
        driver = _build_driver(args.backend, getattr(args, "wind", False))
        result = run_altitude_hold(
            driver,
            target_m=args.target_m,
            settle_s=args.settle_s,
            seed=args.seed,
            note=args.note,
        )
    except Exception as e:  # 未就绪/未实现：给清晰提示，退出码 2
        print(f"[omnisim] 无法执行：{e}", file=sys.stderr)
        return 2

    payload = result.to_dict()

    out = args.out
    if not out and args.backend != "omnisim":
        out_dir = DEFAULT_OUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        wind_tag = "wind" if getattr(args, "wind", False) else "calm"
        out = str(out_dir / f"altitude_hold_{args.target_m}m_{args.backend}_{wind_tag}_{args.seed}.json")

    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"op={result.op} backend={result.backend} accepted={result.accepted}")
        print(f"  target={result.target_m}m  measured={result.measured_m}m  "
              f"error={result.error_m}m  std={result.steady_std_m}m  "
              f"state={result.state}")
        print(f"  evidence_level=simulation-only  seed={result.seed}  note={result.note!r}")
        if out:
            print(f"  已写入: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
