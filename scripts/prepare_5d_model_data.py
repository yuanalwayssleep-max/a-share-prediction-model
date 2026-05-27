#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in [ROOT / "scripts", ROOT / "scripts" / "pipeline"]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from merge_daily_k_files import DEFAULT_INDEX_FEATURE_FILE, DEFAULT_OUTPUT_FILE
from split_5d_model_tables import DEFAULT_BASE_OUTPUT, DEFAULT_FEATURE_OUTPUT
from train_5d_return_model import DEFAULT_DAILY_DIR, DEFAULT_META_CSV


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="准备5日方向模型数据：合并日K主表并拆分基础表/特征表")
    parser.add_argument("--input-dir", default=str(DEFAULT_DAILY_DIR), help="单只股票日K目录")
    parser.add_argument("--meta-csv", default=str(DEFAULT_META_CSV), help="股票元数据CSV")
    parser.add_argument("--sample-output", default=str(DEFAULT_OUTPUT_FILE), help="5日方向样本主表输出路径")
    parser.add_argument("--index-feature-file", default=str(DEFAULT_INDEX_FEATURE_FILE), help="核心指数特征CSV")
    parser.add_argument("--feature-set", choices=["core", "all"], default="core", help="主表输出字段集合")
    parser.add_argument("--base-output", default=str(DEFAULT_BASE_OUTPUT), help="A股日K基础表输出路径")
    parser.add_argument("--feature-output", default=str(DEFAULT_FEATURE_OUTPUT), help="5日方向模型特征表输出路径")
    parser.add_argument("--merge", action="store_true", help="只执行合并主表")
    parser.add_argument("--split", action="store_true", help="只执行拆分基础表/特征表")
    parser.add_argument("--all", action="store_true", help="执行合并和拆分；默认行为")
    return parser.parse_args()


def run_command(cmd: list[str]) -> None:
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    args = parse_args()
    run_merge = args.all or args.merge or not args.split
    run_split = args.all or args.split or not args.merge

    sample_output = str(Path(args.sample_output).resolve())
    if run_merge:
        run_command(
            [
                sys.executable,
                "scripts/pipeline/merge_daily_k_files.py",
                "--input-dir",
                str(Path(args.input_dir).resolve()),
                "--meta-csv",
                str(Path(args.meta_csv).resolve()),
                "--output-file",
                sample_output,
                "--index-feature-file",
                str(Path(args.index_feature_file).resolve()),
                "--feature-set",
                args.feature_set,
            ]
        )

    if run_split:
        run_command(
            [
                sys.executable,
                "scripts/pipeline/split_5d_model_tables.py",
                "--input-file",
                sample_output,
                "--base-output",
                str(Path(args.base_output).resolve()),
                "--feature-output",
                str(Path(args.feature_output).resolve()),
            ]
        )


if __name__ == "__main__":
    main()
