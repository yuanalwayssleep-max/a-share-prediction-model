#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PREDICTION_DIR = SKILL_DIR / "outputs" / "stock_direction_predictions"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估个股候选池TopK覆盖率和亏损率")
    parser.add_argument("--prediction-file", action="append", default=[], help="预测结果CSV；可重复传入")
    parser.add_argument("--prediction-dir", default=str(DEFAULT_PREDICTION_DIR), help="预测结果目录")
    parser.add_argument("--glob", default="个股5日收益10pct预测_LightGBM*_*.csv", help="未指定文件时使用的glob")
    parser.add_argument("--score-col", default="", help="排序分数字段；默认自动选择 final_return_signal_score 或 predicted_return_threshold_prob")
    parser.add_argument("--top-k", default="3,10,20,30,50", help="逗号分隔的TopK列表")
    parser.add_argument("--output-daily", default="", help="可选：写出每日TopK明细CSV")
    parser.add_argument("--output-summary", default="", help="可选：写出TopK汇总CSV")
    return parser.parse_args()


def load_paths(args: argparse.Namespace) -> list[Path]:
    if args.prediction_file:
        return [Path(item).resolve() for item in args.prediction_file]
    return sorted(Path(args.prediction_dir).resolve().glob(args.glob))


def choose_score_col(df: pd.DataFrame, requested: str) -> str:
    if requested:
        if requested not in df.columns:
            raise RuntimeError(f"预测文件缺少指定排序列: {requested}")
        return requested
    for col in ("final_return_signal_score", "predicted_return_threshold_prob", "top_quantile_signal_score"):
        if col in df.columns:
            return col
    raise RuntimeError("无法自动识别排序列")


def read_predictions(paths: list[Path], score_col: str) -> tuple[pd.DataFrame, str]:
    frames: list[pd.DataFrame] = []
    selected_score_col = score_col
    for path in paths:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype={"symbol": str})
        if "trade_date" not in df.columns or "future_5_return" not in df.columns:
            raise RuntimeError(f"预测文件缺少 trade_date/future_5_return: {path}")
        if not selected_score_col:
            selected_score_col = choose_score_col(df, "")
        if selected_score_col not in df.columns:
            raise RuntimeError(f"预测文件缺少排序列 {selected_score_col}: {path}")
        df["source_file"] = path.name
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
        df["future_5_return"] = pd.to_numeric(df["future_5_return"], errors="coerce")
        df[selected_score_col] = pd.to_numeric(df[selected_score_col], errors="coerce")
        frames.append(df)
    if not frames:
        raise RuntimeError("没有找到预测文件")
    return pd.concat(frames, ignore_index=True), selected_score_col


def evaluate(df: pd.DataFrame, score_col: str, top_ks: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily_rows: list[dict[str, object]] = []
    for trade_date, day in df.groupby("trade_date", dropna=False):
        ranked = day.sort_values([score_col, "symbol"], ascending=[False, True]).reset_index(drop=True)
        actual_ge10 = int((ranked["future_5_return"] >= 0.10).sum())
        actual_ge05 = int((ranked["future_5_return"] >= 0.05).sum())
        actual_loss05 = int((ranked["future_5_return"] <= -0.05).sum())
        for top_k in top_ks:
            top = ranked.head(top_k)
            ge10_hits = int((top["future_5_return"] >= 0.10).sum())
            ge05_hits = int((top["future_5_return"] >= 0.05).sum())
            loss05_hits = int((top["future_5_return"] <= -0.05).sum())
            daily_rows.append(
                {
                    "trade_date": trade_date.strftime("%Y-%m-%d") if pd.notna(trade_date) else "",
                    "top_k": top_k,
                    "picks": len(top),
                    "actual_ge10": actual_ge10,
                    "actual_ge05": actual_ge05,
                    "actual_loss05": actual_loss05,
                    "ge10_hits": ge10_hits,
                    "ge05_hits": ge05_hits,
                    "loss05_hits": loss05_hits,
                    "ge10_precision": ge10_hits / len(top) if len(top) else 0.0,
                    "ge05_precision": ge05_hits / len(top) if len(top) else 0.0,
                    "loss05_rate": loss05_hits / len(top) if len(top) else 0.0,
                    "ge10_coverage": ge10_hits / actual_ge10 if actual_ge10 else 0.0,
                    "avg_future_5_return": float(top["future_5_return"].mean()) if len(top) else 0.0,
                    "best_future_5_return": float(top["future_5_return"].max()) if len(top) else 0.0,
                    "worst_future_5_return": float(top["future_5_return"].min()) if len(top) else 0.0,
                }
            )
    daily = pd.DataFrame(daily_rows)
    summary = (
        daily.groupby("top_k", dropna=False)
        .agg(
            days=("trade_date", "nunique"),
            picks=("picks", "sum"),
            actual_ge10=("actual_ge10", "sum"),
            ge10_hits=("ge10_hits", "sum"),
            ge05_hits=("ge05_hits", "sum"),
            loss05_hits=("loss05_hits", "sum"),
            avg_ge10_precision=("ge10_precision", "mean"),
            avg_ge05_precision=("ge05_precision", "mean"),
            avg_loss05_rate=("loss05_rate", "mean"),
            avg_ge10_coverage=("ge10_coverage", "mean"),
            avg_future_5_return=("avg_future_5_return", "mean"),
        )
        .reset_index()
    )
    return summary, daily


def print_table(df: pd.DataFrame) -> None:
    out = df.copy()
    percent_cols = [
        "avg_ge10_precision",
        "avg_ge05_precision",
        "avg_loss05_rate",
        "avg_ge10_coverage",
        "avg_future_5_return",
        "ge10_precision",
        "ge05_precision",
        "loss05_rate",
        "ge10_coverage",
    ]
    for col in percent_cols:
        if col in out.columns:
            out[col] = out[col].map(lambda x: "" if pd.isna(x) else f"{x:.2%}")
    print(out.to_string(index=False))


def main() -> None:
    args = parse_args()
    top_ks = sorted({int(item.strip()) for item in args.top_k.split(",") if item.strip()})
    paths = load_paths(args)
    df, score_col = read_predictions(paths, args.score_col)
    summary, daily = evaluate(df, score_col, top_ks)

    print(f"预测文件数: {len(paths)}")
    print(f"排序列: {score_col}")
    print("\nTopK汇总:")
    print_table(summary)

    print("\nTop30低覆盖日期:")
    top30 = daily.loc[daily["top_k"].eq(30)].copy()
    if not top30.empty:
        low = top30.sort_values(["ge10_coverage", "ge10_hits", "avg_future_5_return"]).head(10)
        print_table(low[["trade_date", "actual_ge10", "ge10_hits", "ge10_coverage", "loss05_hits", "avg_future_5_return"]])

    if args.output_daily:
        output = Path(args.output_daily).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        daily.to_csv(output, index=False, encoding="utf-8-sig")
        print(f"\n每日明细已写入: {output}")
    if args.output_summary:
        output = Path(args.output_summary).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        summary.to_csv(output, index=False, encoding="utf-8-sig")
        print(f"汇总已写入: {output}")


if __name__ == "__main__":
    main()
