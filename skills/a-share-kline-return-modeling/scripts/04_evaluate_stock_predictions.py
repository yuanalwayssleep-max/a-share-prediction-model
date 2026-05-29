#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PREDICTION_DIR = SKILL_DIR / "outputs" / "stock_direction_predictions"
DEFAULT_STOCK_FEATURE_FILE = SKILL_DIR / "data" / "个股k线特征数据.csv"
PREDICT_SCRIPT = SKILL_DIR / "scripts" / "01_predict_stock_direction.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估个股Top预测结果，并检查是否存在future_特征泄漏")
    parser.add_argument("--prediction-file", action="append", default=[], help="预测结果CSV；可重复传入")
    parser.add_argument("--prediction-dir", default=str(DEFAULT_PREDICTION_DIR), help="预测结果目录")
    parser.add_argument("--glob", default="个股5日*预测_LightGBM_Top3输出_*_系统日期*.csv", help="未指定文件时使用的glob")
    parser.add_argument("--stock-file", default=str(DEFAULT_STOCK_FEATURE_FILE), help="个股特征表，用于泄漏检查")
    parser.add_argument("--output", default="", help="可选：把月度汇总写入CSV")
    parser.add_argument("--show-daily", action="store_true", help="输出每日命中明细")
    parser.add_argument("--show-low-days", action="store_true", default=True, help="输出0命中和1命中日期")
    return parser.parse_args()


def load_prediction_files(args: argparse.Namespace) -> list[Path]:
    if args.prediction_file:
        return [Path(item).resolve() for item in args.prediction_file]
    prediction_dir = Path(args.prediction_dir).resolve()
    return sorted(prediction_dir.glob(args.glob))


def read_prediction(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"symbol": str})
    if "trade_date" not in df.columns or "actual_top_quantile_label" not in df.columns:
        raise RuntimeError(f"预测文件缺少必要列: {path}")
    df["source_file"] = path.name
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    if "future_5_return" in df.columns:
        df["future_5_return"] = pd.to_numeric(df["future_5_return"], errors="coerce")
    df["actual_top_quantile_label"] = pd.to_numeric(df["actual_top_quantile_label"], errors="coerce")
    if "actual_top_n_label" in df.columns:
        df["actual_top_n_label"] = pd.to_numeric(df["actual_top_n_label"], errors="coerce")
    return df


def audit_feature_leakage(stock_file: Path) -> tuple[int, list[str]]:
    if not stock_file.exists() or not PREDICT_SCRIPT.exists():
        return 0, []
    spec = importlib.util.spec_from_file_location("predict_stock_direction", PREDICT_SCRIPT)
    if spec is None or spec.loader is None:
        return 0, []
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    df = module.load_stock_features(stock_file)
    df = module.add_cross_section_features(df)
    feature_cols = module.select_feature_columns(df)
    leaked = sorted(col for col in feature_cols if "future_" in col)
    return len(feature_cols), leaked


def evaluate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    label_col = "actual_top_n_label" if "actual_top_n_label" in df.columns else "actual_top_quantile_label"
    metric_name = "top_n_hit_rate" if label_col == "actual_top_n_label" else "top_quantile_hit_rate"
    verified = df.loc[df[label_col].notna()].copy()
    if verified.empty:
        return pd.DataFrame(), pd.DataFrame()
    verified["month"] = verified["trade_date"].dt.strftime("%Y-%m")
    daily = (
        verified.groupby(["month", "trade_date"], dropna=False)
        .agg(
            picks=("symbol", "count"),
            hits=(label_col, "sum"),
            avg_future_5_return=("future_5_return", "mean"),
        )
        .reset_index()
    )
    daily["hit_rate"] = daily["hits"] / daily["picks"]
    daily["hit_metric"] = metric_name
    daily["trade_date"] = daily["trade_date"].dt.strftime("%Y-%m-%d")

    top1 = verified.loc[verified.get("rank_by_top_quantile_prob", pd.Series(np.nan, index=verified.index)).eq(1)].copy()
    top1_month = top1.groupby("month")[label_col].mean().rename("top1_hit_rate")
    monthly = (
        daily.groupby("month", dropna=False)
        .agg(
            days=("trade_date", "count"),
            hits=("hits", "sum"),
            total=("picks", "sum"),
            zero_hit_days=("hits", lambda s: int((s == 0).sum())),
            one_hit_days=("hits", lambda s: int((s == 1).sum())),
            two_hit_days=("hits", lambda s: int((s == 2).sum())),
            three_hit_days=("hits", lambda s: int((s == 3).sum())),
            avg_future_5_return=("avg_future_5_return", "mean"),
            hit_metric=("hit_metric", "first"),
        )
        .reset_index()
    )
    monthly["hit_rate"] = monthly["hits"] / monthly["total"]
    monthly = monthly.merge(top1_month.reset_index(), on="month", how="left")
    return monthly, daily


def print_table(df: pd.DataFrame, columns: list[str], percent_cols: set[str]) -> None:
    if df.empty:
        print("无可评估数据")
        return
    out = df[columns].copy()
    for col in percent_cols:
        if col in out.columns:
            out[col] = out[col].map(lambda x: "" if pd.isna(x) else f"{x:.2%}")
    print(out.to_string(index=False))


def main() -> None:
    args = parse_args()
    paths = load_prediction_files(args)
    if not paths:
        raise RuntimeError("没有找到预测结果文件")

    frames = [read_prediction(path) for path in paths]
    df = pd.concat(frames, ignore_index=True)
    monthly, daily = evaluate(df)
    feature_count, leaked = audit_feature_leakage(Path(args.stock_file).resolve())

    print(f"预测文件数: {len(paths)}")
    print(f"模型特征数: {feature_count}")
    print(f"future_泄漏特征: {leaked if leaked else '无'}")
    print("\n月度汇总:")
    print_table(
        monthly,
        [
            "month",
            "days",
            "hits",
            "total",
            "hit_rate",
            "top1_hit_rate",
            "hit_metric",
            "zero_hit_days",
            "one_hit_days",
            "avg_future_5_return",
        ],
        {"hit_rate", "top1_hit_rate", "avg_future_5_return"},
    )

    if args.show_low_days and not daily.empty:
        low = daily.loc[daily["hits"] <= 1].copy()
        print("\n低命中日期(<=1/3):")
        print_table(low, ["trade_date", "hits", "picks", "hit_rate", "avg_future_5_return"], {"hit_rate", "avg_future_5_return"})

    if args.show_daily and not daily.empty:
        print("\n每日明细:")
        print_table(daily, ["trade_date", "hits", "picks", "hit_rate", "avg_future_5_return"], {"hit_rate", "avg_future_5_return"})

    if args.output and not monthly.empty:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        monthly.to_csv(output, index=False, encoding="utf-8-sig")
        print(f"\n月度汇总已写入: {output}")


if __name__ == "__main__":
    main()
