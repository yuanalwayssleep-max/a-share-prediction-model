#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

import apply_signal_decision_layer as signal_layer
import predict_market_risk as market_model
import predict_stock_direction as stock_model


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STOCK_FEATURE_FILE = SKILL_DIR / "data" / "个股k线特征数据.csv"
DEFAULT_INDEX_FEATURE_FILE = SKILL_DIR / "data" / "指数k线特征数据.csv"
DEFAULT_STOCK_LIST_FILE = SKILL_DIR / "data" / "00_股票清单.csv"
DEFAULT_OUTPUT_DIR = SKILL_DIR / "outputs" / "holiday_window_predictions"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="节假日前后窗口预测：只跑长假前后N个交易日")
    parser.add_argument("--stock-list", default=str(DEFAULT_STOCK_LIST_FILE), help="股票清单路径")
    parser.add_argument("--stock-file", default=str(DEFAULT_STOCK_FEATURE_FILE), help="个股k线特征数据.csv路径")
    parser.add_argument("--index-file", default=str(DEFAULT_INDEX_FEATURE_FILE), help="指数k线特征数据.csv路径")
    parser.add_argument("--start-date", default="2025-01-01", help="假期识别起始日期，默认覆盖2025春节前")
    parser.add_argument("--end-date", default="", help="假期识别结束日期，默认使用数据最新日期")
    parser.add_argument("--window-size", type=int, default=3, help="节前/节后各取几个交易日")
    parser.add_argument("--min-gap-days", type=int, default=4, help="自然日休市间隔达到几天视为假期")
    parser.add_argument("--lookback-days", type=int, default=365, help="模型训练回看自然日数")
    parser.add_argument("--top-quantile", type=float, default=0.2, help="个股Top分位正样本比例")
    parser.add_argument("--top-n", type=int, default=3, help="个股候选TopN")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录")
    return parser.parse_args()


def safe_date_tag(value: str) -> str:
    return pd.to_datetime(value).strftime("%Y%m%d")


def normalize_symbol(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)


def holiday_name(pre_date: pd.Timestamp, post_date: pd.Timestamp, gap_days: int) -> str:
    md = pre_date.strftime("%m-%d")
    year = pre_date.year
    if md <= "02-20" and gap_days >= 7:
        return f"{year}春节"
    if "04-01" <= md <= "04-07":
        return f"{year}清明"
    if "04-25" <= md <= "05-05":
        return f"{year}五一"
    if "05-20" <= md <= "06-10":
        return f"{year}端午"
    if "09-20" <= md <= "10-10":
        return f"{year}国庆"
    if md >= "12-25" or post_date.strftime("%m-%d") <= "01-10":
        return f"{year}元旦"
    return f"{pre_date:%Y%m%d}_{post_date:%Y%m%d}_休市{gap_days}天"


def build_holiday_windows(trade_dates: pd.Series, start_date: str, end_date: str, window_size: int, min_gap_days: int) -> pd.DataFrame:
    dates = pd.Series(pd.to_datetime(trade_dates, errors="coerce").dropna().unique()).sort_values().reset_index(drop=True)
    cal = pd.DataFrame({"trade_date": dates})
    cal["next_trade_date"] = cal["trade_date"].shift(-1)
    cal["gap_days"] = (cal["next_trade_date"] - cal["trade_date"]).dt.days

    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date) if end_date else cal["trade_date"].max()
    rows: list[dict[str, object]] = []
    for idx, row in cal.loc[cal["gap_days"] >= min_gap_days].iterrows():
        pre_date = row["trade_date"]
        post_date = row["next_trade_date"]
        gap_days = int(row["gap_days"])
        name = holiday_name(pre_date, post_date, gap_days)
        for offset in range(window_size):
            pre_idx = idx - offset
            if pre_idx >= 0:
                anchor = cal.loc[pre_idx, "trade_date"]
                if start <= anchor <= end:
                    rows.append(
                        {
                            "trade_date": anchor,
                            "holiday_name": name,
                            "holiday_phase": "节前",
                            "holiday_tday": offset + 1,
                            "holiday_gap_days": gap_days,
                            "holiday_pre_last_trade_date": pre_date,
                            "holiday_post_first_trade_date": post_date,
                        }
                    )
            post_idx = idx + 1 + offset
            if post_idx < len(cal):
                anchor = cal.loc[post_idx, "trade_date"]
                if start <= anchor <= end:
                    rows.append(
                        {
                            "trade_date": anchor,
                            "holiday_name": name,
                            "holiday_phase": "节后",
                            "holiday_tday": offset + 1,
                            "holiday_gap_days": gap_days,
                            "holiday_pre_last_trade_date": pre_date,
                            "holiday_post_first_trade_date": post_date,
                        }
                    )
    out = pd.DataFrame(rows).drop_duplicates(["trade_date", "holiday_name", "holiday_phase"])
    if out.empty:
        raise RuntimeError("没有识别到符合条件的假期窗口")
    out = out.sort_values(["trade_date", "holiday_phase"]).reset_index(drop=True)
    for col in ["trade_date", "holiday_pre_last_trade_date", "holiday_post_first_trade_date"]:
        out[col] = pd.to_datetime(out[col]).dt.strftime("%Y-%m-%d")
    return out


def load_stock_frame(stock_file: Path, stock_list_file: Path) -> pd.DataFrame:
    stock_list = stock_model.load_stock_list(stock_list_file)
    df = stock_model.load_stock_features(stock_file)
    df = df[df["symbol"].isin(set(stock_list["symbol"]))].copy()
    if df.empty:
        raise RuntimeError("股票清单中的代码在个股特征数据中都不存在")
    return df


def predict_stock_for_anchors(df: pd.DataFrame, anchors: list[pd.Timestamp], args: argparse.Namespace) -> pd.DataFrame:
    feature_cols = stock_model.select_feature_columns(df)
    frames: list[pd.DataFrame] = []
    coverage = stock_model.date_coverage(df)
    for anchor_date in anchors:
        train_start = (anchor_date - pd.Timedelta(days=args.lookback_days)).strftime("%Y-%m-%d")
        pred = stock_model.predict_one_anchor(
            df,
            feature_cols,
            anchor_date,
            train_start,
            "",
            0.5,
            args.top_n,
            0.01,
            -0.01,
            True,
            True,
            "top_quantile",
            args.top_quantile,
            False,
        )
        row = coverage.loc[coverage[stock_model.DATE_COL].eq(anchor_date)]
        if not row.empty:
            pred["anchor_stock_count"] = int(row["stock_count"].iloc[0])
            pred["anchor_coverage_ratio"] = float(row["coverage_ratio"].iloc[0])
        frames.append(pred)
        print(f"stock {anchor_date:%Y-%m-%d} done")
    return pd.concat(frames, ignore_index=True)


def predict_market_for_anchors(index_file: Path, anchors: list[pd.Timestamp], args: argparse.Namespace) -> pd.DataFrame:
    df = market_model.load_index_features(index_file)
    feature_cols = market_model.select_feature_columns(df)
    frames: list[pd.DataFrame] = []
    for anchor_date in anchors:
        pred = market_model.predict_one_anchor(
            df,
            feature_cols,
            anchor_date,
            args.lookback_days,
            0.5,
            0.01,
            -0.01,
            0.65,
            0.45,
        )
        frames.append(pred)
        print(f"market {anchor_date:%Y-%m-%d} done")
    return pd.concat(frames, ignore_index=True)


def apply_final_signal(stock_pred: pd.DataFrame, market_pred: pd.DataFrame, stock_features: pd.DataFrame) -> pd.DataFrame:
    stock_for_signal = stock_pred.copy()
    stock_for_signal["symbol"] = normalize_symbol(stock_for_signal["symbol"])
    stock_features_for_signal = stock_features.copy()
    stock_features_for_signal["symbol"] = normalize_symbol(stock_features_for_signal["symbol"])
    stock_features_for_signal["trade_date"] = pd.to_datetime(stock_features_for_signal["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    stock_for_signal = signal_layer.enrich_with_feature_percentiles(stock_for_signal, stock_features_for_signal)
    market_daily = signal_layer.build_market_daily(market_pred)
    signal_args = SimpleNamespace(max_top_n=3, min_top1_score=0.62, min_top2_score=0.68, min_top3_score=0.65)
    return signal_layer.build_signals(stock_for_signal, market_daily, signal_args)


def build_summary(final_signal: pd.DataFrame) -> pd.DataFrame:
    final = final_signal[final_signal["is_final_signal"].eq(1)].copy()
    groups = []
    for keys, group in final_signal.groupby(["holiday_name", "holiday_phase"], dropna=False):
        holiday, phase = keys
        chosen = group[group["is_final_signal"].eq(1)]
        groups.append(
            {
                "holiday_name": holiday,
                "holiday_phase": phase,
                "window_dates": group["trade_date"].nunique(),
                "signal_dates": chosen["trade_date"].nunique(),
                "signal_count": len(chosen),
                "up_rate": (chosen["future_5_return"] > 0).mean() if not chosen.empty else np.nan,
                "avg_future_5_return": chosen["future_5_return"].mean() if not chosen.empty else np.nan,
                "median_future_5_return": chosen["future_5_return"].median() if not chosen.empty else np.nan,
                "no_trade_dates": group.loc[group["signal_action"].eq("不出手"), "trade_date"].nunique(),
                "top3_dates": group.loc[group["signal_action"].eq("Top3"), "trade_date"].nunique(),
                "top2_dates": group.loc[group["signal_action"].eq("Top2"), "trade_date"].nunique(),
                "top1_dates": group.loc[group["signal_action"].eq("Top1"), "trade_date"].nunique(),
            }
        )
    summary = pd.DataFrame(groups).sort_values(["holiday_name", "holiday_phase"]).reset_index(drop=True)
    total = {
        "holiday_name": "全部",
        "holiday_phase": "全部",
        "window_dates": final_signal["trade_date"].nunique(),
        "signal_dates": final["trade_date"].nunique(),
        "signal_count": len(final),
        "up_rate": (final["future_5_return"] > 0).mean() if not final.empty else np.nan,
        "avg_future_5_return": final["future_5_return"].mean() if not final.empty else np.nan,
        "median_future_5_return": final["future_5_return"].median() if not final.empty else np.nan,
        "no_trade_dates": final_signal.loc[final_signal["signal_action"].eq("不出手"), "trade_date"].nunique(),
        "top3_dates": final_signal.loc[final_signal["signal_action"].eq("Top3"), "trade_date"].nunique(),
        "top2_dates": final_signal.loc[final_signal["signal_action"].eq("Top2"), "trade_date"].nunique(),
        "top1_dates": final_signal.loc[final_signal["signal_action"].eq("Top1"), "trade_date"].nunique(),
    }
    return pd.concat([summary, pd.DataFrame([total])], ignore_index=True)


def main() -> None:
    args = parse_args()
    stock_file = Path(args.stock_file).resolve()
    stock_list_file = Path(args.stock_list).resolve()
    index_file = Path(args.index_file).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    stock_df = load_stock_frame(stock_file, stock_list_file)
    start_date = pd.to_datetime(args.start_date).strftime("%Y-%m-%d")
    end_date = pd.to_datetime(args.end_date).strftime("%Y-%m-%d") if args.end_date else stock_df[stock_model.DATE_COL].max().strftime("%Y-%m-%d")
    windows = build_holiday_windows(stock_df[stock_model.DATE_COL], start_date, end_date, args.window_size, args.min_gap_days)
    anchor_dates = pd.to_datetime(windows["trade_date"].drop_duplicates().sort_values()).tolist()
    print(f"holiday windows={windows['holiday_name'].nunique()}, anchor_dates={len(anchor_dates)}")

    stock_pred = predict_stock_for_anchors(stock_df, anchor_dates, args)
    market_pred = predict_market_for_anchors(index_file, anchor_dates, args)
    final_signal = apply_final_signal(stock_pred, market_pred, stock_df)
    final_signal = final_signal.merge(windows, on="trade_date", how="left")
    summary = build_summary(final_signal)

    tag = f"{safe_date_tag(start_date)}_{safe_date_tag(end_date)}"
    detail_path = output_dir / f"节假日前后最终信号_{tag}_系统日期{date.today():%Y%m%d}.csv"
    summary_path = output_dir / f"节假日前后表现汇总_{tag}_系统日期{date.today():%Y%m%d}.csv"
    final_signal.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    total = summary.loc[summary["holiday_name"].eq("全部")].iloc[0]
    print(f"明细: {detail_path}")
    print(f"汇总: {summary_path}")
    print(
        "overall "
        f"signal_count={int(total['signal_count'])}, "
        f"signal_dates={int(total['signal_dates'])}, "
        f"up_rate={total['up_rate']:.4f}, "
        f"avg_return={total['avg_future_5_return']:.4f}"
    )


if __name__ == "__main__":
    main()
