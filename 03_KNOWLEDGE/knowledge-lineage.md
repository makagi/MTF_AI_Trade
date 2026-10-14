# 知識の系譜 (Knowledge Lineage)

**Doc ID:** KNOW-LIN-001  
**Version:** 0.2.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-14  
**Related Issues:** [#4](https://github.com/makagi/MTF_AI_Trade/issues/4), [#6](https://github.com/makagi/MTF_AI_Trade/issues/6), [#9](https://github.com/makagi/MTF_AI_Trade/issues/9), [#41](https://github.com/makagi/MTF_AI_Trade/issues/41)  
**Related Docs:** [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md), [README.md](README.md), [01_CONCEPTS/glossary.md](../01_CONCEPTS/glossary.md)  

---

## 1. 証拠レベルの定義 (Evidence Levels)

本系譜図における知見のステータスは、[00_GOVERNANCE/principles.md](../00_GOVERNANCE/principles.md) §2（科学的厳密性と証拠連鎖）に基づき、以下の基準で厳格に分類する。

| ステータス | 英語表記 | 定義・判定基準 |
|---|---|---|
| **支持** | Supported | [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md)（SPEC-EVAL-001）の必須評価基準（摩擦コスト0.40%控除後のプラス期待値、年別分解の一貫性、サンプル数100件以上）を満たし、統計的に優位性が支持された知見。仕様・戦略へ昇格可能。 |
| **反証・棄却** | Refuted | 定量実験において摩擦コストに耐えられない、または年ごとの非定常性により優位性が否定・棄却された知見。将来の重複実験を防ぐ資産。 |
| **保留・途上** | Inconclusive | 特徴量としての先行性や傾向は観測されたが、売買シグナルとしての定量検証が未完了、またはサンプル不足等により結論が留保された知見。 |
| **観測** | Observed | 特定の期間・データセットにおいて定性的に観測された現象（仮説立案の材料）。 |

---

## 2. 知識系譜グラフ (Knowledge Graph)

```mermaid
graph TD
    classDef supported fill:#d4edda,stroke:#28a745,stroke-width:2px;
    classDef refuted fill:#f8d7da,stroke:#dc3545,stroke-width:2px;
    classDef inconclusive fill:#fff3cd,stroke:#ffc107,stroke-width:2px;

    K001["K-001: 長期SMA下方乖離の平均回帰性<br/>(Supported)"]:::supported
    K002["K-002: 単一足ハードサポレジの非定常性<br/>(Refuted)"]:::refuted
    K003["K-003: 1m足単独トリガーの優位性欠如<br/>(Refuted)"]:::refuted
    K004["K-004: 単一1h足価格テクニカルの限界<br/>(Refuted)"]:::refuted
    K005["K-005: Soft Logic単独逆張りの優位性欠如<br/>(Refuted: 摩擦負け・逆張りトラップ)"]:::refuted
    K006["K-006: マクロ強気 × Soft Logic 押し目買いの優位性<br/>(Supported: コスト突破 Gross +0.42% / 直近PF > 1.8)"]:::supported

    LEG_ANL1["90_LEGACY: ANL-20260922-001"] --> K001
    LEG_STATE["90_LEGACY: STATE.md (Phase 3-4.7)"] --> K002
    LEG_STATE --> K003
    LEG_STATE --> K004
    EXP041["EXP-41-001: 41-k005-soft-logic"] --> K005
    EXP041 --> K006
    K001 -.->|シナジー結合| K006
```

---

## 3. 系譜エントリー詳細

### K-001: 長期SMA下方乖離の平均回帰性
* **ステータス**: 支持 (Supported)
* **概要**: 価格が長期SMAから -2 ATR 以上下方へ乖離した局面において、Discovery 期間（2020-2023年）の各年で一貫した平均回帰（上値反発）傾向が観測された。
* **実験条件**: 日足・4時間足ベース、4年間年別オーバーレイ検証
* **過去資産の出典**: [`90_LEGACY/knowledge/records/2026-09/ANL-20260922-001_sma_mean_reversion/`](../90_LEGACY/knowledge/records/2026-09/ANL-20260922-001_sma_mean_reversion/) (FIND-001 / HYP-001)
* **仕様への影響**: 今後の戦略仕様（`02_SPECIFICATIONS/strategies/`）における平均回帰ロジックのコア仮説として採用。

---

### K-002: ハードなサポレジ線の非定常性
* **ステータス**: 反証・棄却 (Refuted)
* **概要**: 単一時間足のSMAパーフェクトオーダーや静的な特定の支持・抵抗線への接近は、年ごとに期待値の符号が激しく反転し、静的な線単体では過学習を招き有効に機能しないことが示された。
* **実験条件**: 4年間の条件別期待値計測（EDA 05）
* **過去資産の出典**: [`90_LEGACY/STATE.md`](../90_LEGACY/STATE.md) (フェーズ3 重要発見 5)
* **仕様への影響**: 静的サポレジ線の単独売買ルール化を禁止。動的・フラクタルなサポレジ認識（`01_CONCEPTS/market-structure.md`）へ移行。

---

### K-003: 超短期（1m）単独トリガーの優位性欠如
* **ステータス**: 反証・棄却 (Refuted)
* **概要**: 1時間足の環境認識に1分足のテクニカルトリガー（Stoch_d GC / BB 反発）を掛け合わせても、摩擦コスト控除前の60分後リターン分布が0%付近でランダムに分散し、単独トリガーとしての情報優位性が確認されなかった。
* **実験条件**: 1mトリガー発生後60分フォワードリターン計測
* **過去資産の出典**: [`90_LEGACY/STATE.md`](../90_LEGACY/STATE.md) (フェーズ3 重要発見 6)
* **仕様への影響**: 超短期足の単独インジケータをエントリートリガーとして採用する方針を棄却。

---

### K-004: 単一1時間足価格テクニカルの限界
* **ステータス**: 反証・棄却 (Refuted)
* **概要**: 1時間足のSMA・Stoch等の価格指標単体から機械学習（LightGBM / 2段階MoE）を用いてエッジを抽出しようと試みたが、過学習によるコスト負け（Total Return -24.9%）または取引回避に陥り、標準摩擦コスト（0.40%）を上回る期待値を維持できないことが確認された。
* **実験条件**: 4年間のWalk-Forward/CV バックテスト
* **過去資産の出典**: [`90_LEGACY/STATE.md`](../90_LEGACY/STATE.md) (フェーズ4 実験総括)
* **仕様への影響**: 前提条件 A003（単一足価格テクニカルの制約）を確立。多時間軸構造（MTF）または代替データの導入へ完全移行。

---

### K-005: Soft Logic・平滑化同調スコアとファンアウト速度単独逆張りの優位性欠如
* **ステータス**: 反証・棄却 (Refuted)
* **概要**: Discovery 全期間（2020-01-01 〜 2025-04-30、計216トレード）における定量検証（EXP-41-001）の結果、ファンアウト速度の減速と平滑化同調スコア（AFS）の逆張りシグナルは、Gross で平均 +0.13%〜+0.15% の微小反発を示すものの標準摩擦コスト（0.40%）を大きく下回り、全期間で Net EV = -0.588%、PF = 0.557 とコスト負けした。さらに下落レジーム（2022年）では逆張りトラップとなって壊滅的損失（MAE -3.18%）を記録したため、単独シグナルとしては棄却（Refuted）と判定。
* **実験条件**: BTCUSD 1h、5年4ヶ月 Discovery 期間、216トレード、往復摩擦コスト0.40%控除
* **証拠・出典リンク**: [`03_KNOWLEDGE/experiments/41-k005-soft-logic/record.md`](experiments/41-k005-soft-logic/record.md) (EXP-41-001 / [#41](https://github.com/makagi/MTF_AI_Trade/issues/41))
* **仕様への影響**: Soft Logic 単独での逆張り売買化を禁止。

---

### K-006: マクロ強気トレンド × Soft Logic 押し目買いのシナジー優位性
* **ステータス**: 支持 (Supported)
* **概要**: Discovery 全期間（計214トレード）において、上位足マクロ強気環境（Close > SMA 377）を前提とし、一時的な調整（押し目）によるスプレッド縮小からの反転再拡大（ファンアウト速度の底打ち）と AFS 押し目反転を掛け合わせた結果、Gross 平均 **+0.42%**（標準摩擦コスト0.40%を突破）、Net 平均 **+0.02%**、勝率 **50.0%**、PF **1.02** を達成した。特に直近の強気相場（2024年: Net +0.45%, 勝率 60.4%, PF 1.85 / 2025年: Net +0.77%, 勝率 75.0%, PF 3.24）において顕著な優位性を発揮した。
* **実験条件**: BTCUSD 1h、5年4ヶ月 Discovery 期間、214トレード、往復摩擦コスト0.40%控除
* **証拠・出典リンク**: [`03_KNOWLEDGE/experiments/41-k005-soft-logic/record.md`](experiments/41-k005-soft-logic/record.md) (EXP-41-001 / [#41](https://github.com/makagi/MTF_AI_Trade/issues/41))
* **仕様への影響**: 戦略仕様 `02_SPECIFICATIONS/strategies/`（MTF Trend Pullback Strategy）の主軸ロジックとして採用。

---

## 4. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-10 | 0.1.0 | 初版作成（旧知識体系の3層化・K-001〜K-005 登録） | @makagi / [#20](https://github.com/makagi/MTF_AI_Trade/pull/20) |
| 2026-10-13 | 0.2.0 | 科学的証拠表現の是正、エビデンスレベル確立、K-005 を Inconclusive へ見直し | @makagi / [#29](https://github.com/makagi/MTF_AI_Trade/pull/29) |
| 2026-10-13 | 0.2.0 | 書式・メタデータ統一 | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |
| 2026-10-14 | 0.3.0 | EXP-41-001 定量検証結果を反映、K-005 を Refuted へ更新、押し目シナジー知見 K-006 を新設・Supported 登録 | @makagi / [#41](https://github.com/makagi/MTF_AI_Trade/pull/41) |
