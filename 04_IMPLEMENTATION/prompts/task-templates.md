# エージェント向け タスク指示テンプレート集 (Task Prompt Templates)

**Doc ID:** PROMPT-TSK-001  
**Version:** 0.2.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-14  
**Related Issues:** [#35](https://github.com/makagi/MTF_AI_Trade/issues/35)  
**Related Docs:** [system-prompt.md](system-prompt.md), [../agent-rules.md](../agent-rules.md), [../../02_SPECIFICATIONS/evaluation.md](../../02_SPECIFICATIONS/evaluation.md), [../../03_KNOWLEDGE/README.md](../../03_KNOWLEDGE/README.md)  

---

## 1. 概要

本ドキュメントは、人間（スマホ/端末）からの要求を受け取った Antigravity（Requirements Agent）や Orca（Orchestrator）が、ワーカーエージェントへ具体的な作業を指示・委譲する際に使用する標準タスクプロンプトのテンプレート集である。

旧資産（`90_LEGACY/knowledge/PROMPTS.md`）の知見を継承し、現行の 3層協調アーキテクチャ、`SPEC-EVAL-001`、および決定論的ゲート（`tools/agent_eval.py`）に準拠して現代化した。

---

## 2. テンプレート一覧

### テンプレート A: 新規仮説の検証と実験レコード作成

新しい市場歪み・セットアップ仮説を検証し、自己完結した実験ディレクトリを作成させる指示テンプレート。

```markdown
以下の Analysis Issue に基づき、新規仮説の検証実験を実施し、実験レコードを作成してください。

【対象 Issue】: #{issue_no}
【分析テーマ】: {title}
【対象銘柄】: BTCUSD
【時間足】: 1h
【データ期間】: Discovery 期間 (2020-01-01 〜 2025-04-30: src.data_loader.load_discovery_data())
【仮説内容】: {hypothesis_text}
【事前登録合格基準】:
- 摩擦コスト（0.40%）控除後の純期待値が明確にプラスであること。
- 年別オーバーレイ（2020〜2025年）において極端な外れ値依存がないこと。
- サンプル数 N >= 100。

【実行手順】
1. `uv run python tools/kb.py new {issue_no} {slug} --title "{title}"` で実験スケルトンを作成。
2. `config.yaml` に検証パラメータを定義。
3. `run.py` を実装し、無条件ベースラインと条件付きシグナルのパフォーマンスを比較（`evaluate_returns`, `evaluate_yearly_breakdown` を使用）。
4. MFE/MAE 分布および年別損益グラフを `artifacts/` に出力。
5. `metrics.json` に評価結果を保存。
6. `record.md` に結果の考察と判定（Supported / Refuted / Inconclusive）を記述。
7. 完了後、必ず `uv run python tools/agent_eval.py check 03_KNOWLEDGE/experiments/{issue_no}-{slug}` を実行し、全ゲートの合格を確認して結果を報告してください。
```

---

### テンプレート B: 先行実験の継承・派生検証 (Lineage 発展)

既存の実験（`experiments/<N>-<slug>/`）や知見（`K-xxx`）から、条件追加（フィルター追加）や別パラメータでの改善を検証させる指示テンプレート。

```markdown
先行実験 `03_KNOWLEDGE/experiments/{prior_issue}-{prior_slug}` から派生した以下の改善仮説を検証してください。

【対象 Issue】: #{issue_no}
【派生元実験】: #{prior_issue} ({prior_slug})
【検証する改善仮説】: {derivative_hypothesis}
【データ期間】: Discovery 期間 (2020-01-01 〜 2025-04-30)

【実行手順】
1. `uv run python tools/kb.py new {issue_no} {slug} --title "{title}"` で派生実験ディレクトリを作成。
2. 先行実験のロジックを継承し、追加条件・変更点を反映した `run.py` を実装。
3. 先行実験と同一の指標（サンプル数、純期待値、PF、Max DD）で直接比較。
4. `record.md` に先行実験からの改善点、残存課題、および客観的エビデンスを明記。
5. `uv run python tools/agent_eval.py check 03_KNOWLEDGE/experiments/{issue_no}-{slug}` でゲート通過を確認し、PR を作成してください。
```

---

### テンプレート C: Validation 期間での一発勝負テスト (Out-of-Sample)

Discovery 期間で支持された有望な仮説に対し、未知の Validation 期間（2025-05-01 〜 2026-03-31）を用いて過学習を暴く一発勝負テスト指示テンプレート。

```markdown
Discovery 期間で合格した実験 `03_KNOWLEDGE/experiments/{prior_issue}-{prior_slug}` について、Validation 期間（レジーム両面検証案: 2025-05-01 〜 2026-03-31）を用いて一発勝負の頑健性検証を行ってください。

【対象 Issue】: #{issue_no}
【対象実験】: #{prior_issue} ({prior_slug})
【データ期間】: Validation 期間 (2025-05-01 〜 2026-03-31: src.data_loader.load_validation_data())
※ 局面1（2025年5〜10月の上昇）および 局面2（10月〜2026年3月の下落）の両面検証。

【厳格規律】
- パラメータの最適化・再探索は一切禁止。Discovery 期間と同一固定パラメータで実行すること。
- 結果がマイナスとなった場合、チューニングして再実行してはならず、仮説を「棄却（Refuted）」として確定すること。

【実行手順】
1. `uv run python tools/kb.py new {issue_no} {slug}-val --title "{title} - Validation Test"` でレコード作成。
2. `load_validation_data()` を用いて固定パラメータで実行。
3. Discovery 期間からの劣化度（Performance Degradation）を計測。
4. `record.md` にレジーム両面での頑健性評価と最終判定を記述。
5. `uv run python tools/agent_eval.py check 03_KNOWLEDGE/experiments/{issue_no}-{slug}-val` でゲート通過を確認して報告してください。
```

---

### テンプレート D: 既存知識ベースの調査・要約指示

特定テーマに関する過去の検証状況や棄却理由をワーカーに調査・整理させる指示テンプレート。

```markdown
ナレッジベース（03_KNOWLEDGE/knowledge-lineage.md, 03_KNOWLEDGE/knowledge/, 99_HISTORY/decision-log.md）を調査し、以下のテーマについて現在判明している事実を整理してください。

【調査対象テーマ】: {theme_or_keywords}

【回答に含めるべき内容】
1. 関連する知見（K-xxx）および意思決定（Dxxx）の一覧
2. 支持されている事実（Supported）と棄却されたアプローチ（Refuted）
3. 過去に直面した課題（例: 摩擦コスト負け、非定常性、取引回避など）
4. 次に検証すべき優先度の高いアプローチ・改善仮説の提案
```

---

## 3. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-14 | 0.2.0 | 初版作成（90_LEGACY/PROMPTS.md を現代化し新仕様・ゲート・3層体制へ整合） | @makagi / [#38](https://github.com/makagi/MTF_AI_Trade/pull/38) |
