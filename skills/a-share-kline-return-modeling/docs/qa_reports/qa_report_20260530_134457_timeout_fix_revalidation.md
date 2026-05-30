# QA Report: GNU timeout Fix Revalidation

Timestamp: 2026-05-30 13:44:57 CST
Status: IN_PROGRESS
Workdir: /Users/cocoon/Documents/code/a-share-prediction-model
Scope: Revalidate prior QA smoke blocker caused by missing GNU timeout; then run bounded contract tests.
Out of scope: no model training, no full main pipeline, no git operations, no sensitive file reads.

## Command 1: Re-run prior blocked timeout smoke

```bash
timeout 60s python3 skills/a-share-kline-return-modeling/scripts/21_generate_final_signals.py --position-policy full_size
```

Timeout: 90s harness / 60s GNU timeout

Exit code: 0

Key output:
```text
# Final Signal Generation Report

Scope: executable signal file only; no truth or future columns are written.

## Summary

- signal rows: 714
- signal days: 238
- policy: full_size
- average size multiplier: 1.0000

## Monthly

| month   | position_policy   |   trade_days |   avg_size_multiplier |   low_days |   mid_days |   high_days |   avg_total_position_weight |
|:--------|:------------------|-------------:|----------------------:|-----------:|-----------:|------------:|----------------------------:|
| 2025-05 | full_size         |           15 |                1.0000 |          1 |          2 |          12 |                      0.2000 |
| 2025-06 | full_size         |           20 |                1.0000 |          2 |          8 |          10 |                      0.2000 |
| 2025-07 | full_size         |           23 |                1.0000 |          3 |          7 |          13 |                      0.2000 |
| 2025-08 | full_size         |           21 |                1.0000 |          3 |          5 |          13 |                      0.2000 |
| 2025-09 | full_size         |           22 |                1.0000 |          0 |          5 |          17 |                      0.2000 |
| 2025-10 | full_size         |           17 |                1.0000 |          2 |          2 |          13 |                      0.2000 |
| 2025-11 | full_size         |           20 |                1.0000 |          1 |          3 |          16 |                      0.2000 |
| 2025-12 | full_size         |           23 |                1.0000 |          4 |          8 |          11 |                      0.2000 |
| 2026-01 | full_size         |           20 |                1.0000 |          0 |          1 |          19 |                      0.2000 |
| 2026-02 | full_size         |           14 |                1.0000 |          1 |          9 |           4 |                      0.2000 |
| 2026-03 | full_size         |           22 |                1.0000 |          3 |          4 |          15 |                      0.2000 |
| 2026-04 | full_size         |           21 |                1.0000 |          0 |          3 |          18 |                      0.2000 |

## Daily Sample

| trade_date          | position_policy   | opportunity_tier   |   position_size_multiplier |   picks |   suggested_new_sleeve_weight |   suggested_total_position_weight | industries         | month   |
|:--------------------|:------------------|:-------------------|---------------------------:|--------:|------------------------------:|----------------------------------:|:-------------------|:--------|
| 2025-05-12 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,通用设备         | 2025-05 |
| 2025-05-13 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,自动化设备        | 2025-05 |
| 2025-05-14 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,自动化设备        | 2025-05 |
| 2025-05-15 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,专用设备,软件开发    | 2025-05 |
| 2025-05-16 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,软件开发         | 2025-05 |
| 2025-05-19 00:00:00 | full_size         | mid                |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,软件开发         | 2025-05 |
| 2025-05-20 00:00:00 | full_size         | low                |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,软件开发         | 2025-05 |
| 2025-05-21 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,专用设备,软件开发    | 2025-05 |
| 2025-05-22 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,软件开发         | 2025-05 |
| 2025-05-23 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,其他电源设备Ⅱ,软件开发 | 2025-05 |
| 2025-05-26 00:00:00 | full_size         | mid                |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,专用设备,软件开发    | 2025-05 |
| 2025-05-27 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,专用设备,软件开发    | 2025-05 |
| 2025-05-28 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,专用设备,软件开发    | 2025-05 |
| 2025-05-29 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,工程机械         | 2025-05 |
| 2025-05-30 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,元件,自动化设备     | 2025-05 |
| 2025-06-03 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,自动化设备        | 2025-06 |
| 2025-06-04 00:00:00 | full_size         | low                |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,自动化设备        | 2025-06 |
| 2025-06-05 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,自动化设备        | 2025-06 |
| 2025-06-06 00:00:00 | full_size         | mid                |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,生物制品         | 2025-06 |
| 2025-06-09 00:00:00 | full_size         | high               |                     1.0000 |       3 |                        0.2000 |                            0.2000 | IT服务Ⅱ,工程机械,生物制品    | 2025-06 |

wrote skills/a-share-kline-return-modeling/outputs/final_signals/final_signals_full_size_2025-05_2026-04.csv
```

Result: PASS

## Command 2: Contract validation

```bash
timeout 60s python3 -m pytest skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py -q
```

Timeout: 90s harness / 60s GNU timeout

Exit code: 0

Key output:
```text
......                                                                   [100%]
6 passed in 0.74s
```

Result: PASS

## Command 3: Contract validation

```bash
timeout 60s python3 skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py
```

Timeout: 90s harness / 60s GNU timeout

Exit code: 0

Key output:
```text
signal_file    policy  trades  signal_days  avg_size_multiplier  final_equity_curve  total_return  max_drawdown  avg_trade_return  trade_win_rate  positive_month_ratio  worst_month_return  avg_exposure  max_exposure
final_signals_full_size_2025-05_2026-04.csv full_size     714          238                  1.0            2.756132      1.756132     -0.099143          0.024745        0.521008              0.846154           -0.065302      0.963122           1.0
wrote /Users/cocoon/Documents/code/a-share-prediction-model/skills/a-share-kline-return-modeling/outputs/evaluation/test_final_signal_backtest/final_signal_backtest_report.md
all final signal contract checks passed
```

Result: PASS

## Command 4: Contract validation

```bash
timeout 60s python3 -m pytest skills/a-share-kline-return-modeling/tests -q
```

Timeout: 90s harness / 60s GNU timeout

Exit code: 0

Key output:
```text
..........                                                               [100%]
10 passed in 1.51s
```

Result: PASS

## Final Conclusion

Final status: COMPLETED

GNU timeout blocker is resolved. Prior blocked smoke and bounded contract tests pass with GNU timeout.
