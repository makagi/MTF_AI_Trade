# Canary Benchmark (Agent QA Test Suite)

**Doc ID:** TEST-CAN-001  
**Version:** 0.1.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-13  
**Related Issues:** [#33](https://github.com/makagi/MTF_AI_Trade/issues/33)  
**Related Docs:** [../../04_IMPLEMENTATION/agent-rules.md](../../04_IMPLEMENTATION/agent-rules.md), [../../02_SPECIFICATIONS/evaluation.md](../../02_SPECIFICATIONS/evaluation.md), [../../00_GOVERNANCE/principles.md](../../00_GOVERNANCE/principles.md)  

---

## 1. Purpose

本ディレクトリは、AI エージェント（Codex, Open Claw, ローカルLLM等）のコード生成能力・クオンツ計算精度を客観評価するための**カナリアテスト（Canary Benchmark）**スイートを提供する。

LLM による主観評価（LLM-as-a-Judge）を排除し、決定論的な標準課題セット（Gold Standard）と pytest による機械的アサーションによってエージェントの合否を判定する。

---

## 2. Benchmark Suites

| テストファイル | 検証対象 | 採点基準 |
|---|---|---|
| `test_indicator_math.py` | 基本指標（SMA, ATR, Bollinger Bands）の計算精度 | 既知の合成データに対する許容誤差 `1e-4` 以内の完全一致 |
| `test_mfe_mae_logic.py` | MFE / MAE の前方評価ロジック | フォワードウィンドウ（Lookahead）の正しい抽出と数式の一致 |
| `test_spec_compliance.py` | SPEC-EVAL-001 準拠性 | 往復 0.40% 摩擦コスト控除と必須メトリクス形式の出力 |
| `test_leakage_detection.py` | データリーク・境界違反の防止 | Final Holdout 期間（2026-04-01以降）の完全遮断と未来情報非依存 |

---

## 3. Fixtures (Gold Standard Data)

`fixtures/` 配下に固定された客観データを配置する。

* `synthetic_ohlcv.csv`: 決定論的な周期・トレンド波形を持つ合成 OHLCV（シード固定: 200行）。
* `gold_standards.json`: 数値検証の正解値（Gold Standard）。

---

## 4. 実行方法

```powershell
# カナリアテストのみを実行
uv run pytest tests/canary

# ユニットテストのみを実行
uv run pytest tests/unit

# 全テストを実行
uv run pytest
```

---

## 5. M3 からの継続的進化 (Flywheel)

M3（特徴量検証）の実践中にエージェントが起こした失敗パターン（例: 特異なNaN処理ミス、分足と時足の整合性バグ、未経験指標の計算誤差等）は、随時本スイートへ新しいテスト関数として追加し、エージェント評価網を自己進化させる。
