#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统一运行5日预测后处理：市场风险修正、自适应阈值、信号决策层")
    parser.add_argument("--market-risk", action="store_true", help="运行市场风险修正")
    parser.add_argument("--adaptive-threshold", action="store_true", help="运行自适应阈值修正")
    parser.add_argument("--signal-layer", action="store_true", help="运行信号决策层")
    parser.add_argument("--all", action="store_true", help="顺序运行全部后处理")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="透传给底层脚本的参数；可在前面加 -- 分隔")
    return parser.parse_args()


def passthrough_args(args: list[str]) -> list[str]:
    return args[1:] if args and args[0] == "--" else args


def run(script: str, args: list[str]) -> None:
    cmd = [sys.executable, script, *args]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    parsed = parse_args()
    selected = {
        "market-risk": parsed.all or parsed.market_risk,
        "adaptive-threshold": parsed.all or parsed.adaptive_threshold,
        "signal-layer": parsed.all or parsed.signal_layer,
    }
    if not any(selected.values()):
        raise SystemExit("请指定 --market-risk、--adaptive-threshold、--signal-layer 或 --all")

    rest = passthrough_args(parsed.args)
    if selected["market-risk"]:
        run("scripts/postprocess/apply_market_risk_correction.py", rest)
    if selected["adaptive-threshold"]:
        run("scripts/postprocess/apply_adaptive_threshold_correction.py", rest)
    if selected["signal-layer"]:
        run("scripts/postprocess/apply_signal_decision_layer.py", rest)


if __name__ == "__main__":
    main()
