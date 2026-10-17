# 知識の系譜 (Knowledge Lineage)

**Doc ID:** KNOW-LIN-001  
**Version:** 0.7.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-17  
**Related Issues:** [#4](https://github.com/makagi/MTF_AI_Trade/issues/4), [#6](https://github.com/makagi/MTF_AI_Trade/issues/6), [#9](https://github.com/makagi/MTF_AI_Trade/issues/9), [#41](https://github.com/makagi/MTF_AI_Trade/issues/41), [#43](https://github.com/makagi/MTF_AI_Trade/issues/43), [#45](https://github.com/makagi/MTF_AI_Trade/issues/45), [#47](https://github.com/makagi/MTF_AI_Trade/issues/47), [#49](https://github.com/makagi/MTF_AI_Trade/issues/49)  
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
    classDef observed fill:#e2e3e5,stroke:#6c757d,stroke-width:2px;

    K001["K-001: 長期SMA下方乖離の平均回帰性<br/>(Supported)"]:::supported
    K002["K-002: 単一足ハードサポレジの非定常性<br/>(Refuted)"]:::refuted
    K003["K-003: 1m足単独トリガーの優位性欠如<br/>(Refuted)"]:::refuted
    K004["K-004: 単一1h足価格テクニカルの限界<br/>(Refuted)"]:::refuted
    K005["K-005: Soft Logicの押し目再点火フィルター特性<br/>(Supported as Filter)"]:::supported
    K006["K-006: フィボナッチ時間足間等価性とMTF間引き構造<br/>(Supported)"]:::supported
    K007["K-007: MTF 3階層レジーム分類と状態遷移モデル<br/>(Supported)"]:::supported
    K008["K-008: MTF状況依存エッジと極限パニック平均回帰<br/>(Supported)"]:::supported
    K009["K-009: 極限Squeezeアクティビティブレイク<br/>(Supported: Net+0.42%)"]:::supported
    K010["K-010: クラッシュ1番底禁止と2番底ダイバージェンス<br/>(Supported: MAE 33%抑制)"]:::supported
    K011["K-011: クライマックスピンバー単独の優位性欠如<br/>(Refuted: MAE -3.74%)"]:::refuted
    K012["K-012: 上位足抵抗帯モメンタム過熱の時代依存性<br/>(Inconclusive)"]:::inconclusive
    K013["K-013: 清算カスケード後のボラティリティ枯渇<br/>(Observed)"]:::observed
    K014["K-014: 乖離逆張りにおける厳格MTF防壁の必須性<br/>(Supported)"]:::supported

    LEG_ANL1["90_LEGACY: ANL-20260922-001"] --> K001
    LEG_STATE["90_LEGACY: STATE.md (Phase 3-4.7)"] --> K002
    LEG_STATE --> K003
    LEG_STATE --> K004
    EXP041["EXP-41-001: 41-k005-soft-logic"] --> K005
    EXP043["EXP-43-001: 43-fib-mtf-context"] --> K006
    EXP045["EXP-45-001: 45-mtf-state-classification"] --> K007
    K006 -.->|計算量間引きと等価性基盤| K007
    K007 -->|状況把握コンテキスト| K008
    K001 -->|下方乖離の前提条件| K008
    EXP047["EXP-47-001: 47-mtf-context-integrated-eval"] --> K008
    EXP047 -->|フィルター有効性の実証| K005
    EXP049["EXP-49-001: 49-shock-dynamics-cross-period"] --> K009
    EXP049 --> K010
    EXP049 --> K011
    EXP049 --> K012
    EXP049 --> K013
    EXP049 --> K014
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

### K-005: Soft Logicの文脈依存性と押し目再点火フィルター特性
* **ステータス**: 役割限定支持 (Supported as Filter / Refuted as Standalone Trigger)
* **概要**: 統合実験（EXP-41-001, EXP-47-001）において、ファンアウト速度減速・AFS反転同調（Soft Logic）は、単独トリガーとして無条件に発火させた場合、1,252件中54%がレンジ往復ノイズ（`Range_PingPong`）に巻き込まれ、Net EV -0.17%（累積損失 -217%）と摩擦コストに耐えられない（単独トリガーとしては反証・棄却）。一方、K-007 で定義した `Bull_Healthy_Pullback`（強気押し目）局面においてのみ、強気相場（2020年: PF 2.27, Net +0.66% / 2024年: PF 1.22, Net +0.24% / 2025年: PF 5.49, Net +0.31%）で安定した再点火フィルターとして機能することが実証された。
* **実験条件**: BTCUSD 1h、5年4ヶ月 Discovery 期間、往復摩擦コスト0.40%控除、MTF 3階層状況結合
* **証拠・出典リンク**: [`03_KNOWLEDGE/experiments/47-mtf-context-integrated-eval/record.md`](experiments/47-mtf-context-integrated-eval/record.md) (EXP-47-001 / [#47](https://github.com/makagi/MTF_AI_Trade/issues/47))
* **仕様への影響**: Soft Logic を単独エントリーシグナルとして採用することを禁止。戦略仕様（SPEC-STRAT）において「Macro Bull ＋ Meso 押し目」が成立した後の「再点火確認フィルター（Secondary Confirmation Filter）」としてのみ採用を認可。

---

### K-006: フィボナッチ時間足間等価性と特徴量別MTF利用規律
* **ステータス**: 観測・支持 (Observed / Supported)
* **概要**: 4年間（2021-2024年、約210万分・3.5万時間）の実データ分析（EXP-43-001）において、1分足の超長期フィボナッチ項（$F_{1m} \in [610 \sim 6765]$）と1時間足の近接フィボナッチ項（$F_{1h} \in [8 \sim 144]$）の関係性を網羅的に検証した結果、特徴量の性質により以下の決定的な挙動差が実証された：
  1. **価格追随系（SMA、ローリング最高値HH / 最安値LL）**: 相関 $r > 0.999$、誤差 $< 0.8\%$、比率 $\approx 1.000$ であり**完全代替可能**。下位足での巨大計算を上位足へ代用できる。
  2. **正規化幅系（BB Width / Squeeze Index）**: 相関 $r \approx 0.94$ と波形は同期するが、サンプリング頻度差により約11〜15%の系統的スケール差が存在。パーセンタイル正規化による利用が必須。
  3. **オシレーター系（Stochastics %K / AFS）**: 長期オシレーターは相関するが、短期（610 vs 8）ではノイズにより MAE 16.9pt と激しく乖離。短期オシレーターの時間足間代用は禁止（平滑化AFS必須）。
  4. **値幅・ボラティリティ系（ATR）**: 波形相関は $r > 0.98$ と極大だが、絶対値は $\frac{1}{\sqrt{60}}$ 則（約1/10）に従い次元が異なるため、時間スケール補正が不可欠。
  5. **間引き（Downsampling）**: 1h足でマクロ・メソのセットアップ（Armed）を監視することで、下位1m足の計算・監視データ量を **約 96.1% 間引くアーキテクチャ** の成立を確認。
* **実験条件**: BTCUSD 1h & 1m、4年間、フィボナッチ項 $F_1 \sim F_{21}$ の全特徴量比較分析
* **証拠・出典リンク**: [`03_KNOWLEDGE/experiments/43-fib-mtf-context/record.md`](experiments/43-fib-mtf-context/record.md) (EXP-43-001 / [#43](https://github.com/makagi/MTF_AI_Trade/issues/43))
* **仕様への影響**: MTF特徴量仕様（SPEC-FEAT-001）および状況把握モデルの利用前規律として採用。特徴量の性質（価格追随型・正規化型・オシレーター型・値幅型）に応じた時間足代用・スケーリング補正ルールを義務化。

---

### K-007: MTF 3階層レジーム分類と状態遷移モデル
* **ステータス**: 観測・支持 (Observed / Supported)
* **概要**: 4年間（2021-2024年、35,064時間）の1時間足・日足データを用いたMTF 3階層（Macro / Meso / Micro）レジーム分類とマルコフ状態遷移分析（EXP-45-001）において、客観的な市場構造特性が実証された：
  1. **市場滞在比率**: 全時間の 75.5% は保ち合い（Range 47.5% ＋ Squeeze 28.0%）に費やされ、明確な強気/弱気トレンド推進はそれぞれ 13.9% / 8.5% のみ。
  2. **Squeeze の持続性とブレイク方向非対称性**: Squeeze は平均 56.7時間（最長 623時間＝約26日）持続。解放時の第1遷移先として、強気推進（26.2%）へ飛ぶ確率は弱気ブレイク（13.1%）の2倍。
  3. **強気押し目の再点火率**: `Bull_Healthy_Pullback`（強気押し目）終了後、42.2% の高確率で直接 `Bull_Trend_Continuation`（強気推進）へ再点火。弱気転落は 0.0%。
  4. **各レジームのフォワードリスク特性**: `Bull_Healthy_Pullback` は MFE +2.18% に対し MAE -0.66%（リスクリワード比 3.3）と極めて安定。一方 `Bear_Panic_Exhaustion` は MFE +3.15% に対し MAE -4.25% と最大逆行リスクを持つ。
* **実験条件**: BTCUSD 1h & 1d、4年間、フィボナッチMTF特徴量（SMA, AFS, BBW）による客観的3階層分類
* **証拠・出典リンク**: [`03_KNOWLEDGE/experiments/45-mtf-state-classification/record.md`](experiments/45-mtf-state-classification/record.md) (EXP-45-001 / [#45](https://github.com/makagi/MTF_AI_Trade/issues/45))
* **仕様への影響**: 戦略設計および特徴量評価における共通コンテキストエンジンとして採用。シグナル評価を全体勝率ではなく「どのレジームで発生したか」で条件付き評価する基盤を確立。

---

### K-008: MTF状況依存エッジと極限パニック平均回帰
* **ステータス**: 支持 (Supported)
* **概要**: MTF状況把握モデルと各特徴量の統合検証（EXP-47-001）において、以下の決定的な事実が実証された：
  1. **市場75%の保ち合い完全遮断**: 全時間の 75.5% を占める `Range_PingPong` および `Squeeze_Pre_Breakout` において指標シグナルを発火させると、すべて Net EV マイナス（-0.13% 〜 -0.64%）となり摩擦損失の主因となる。これらを状況モデルで遮断することで、1,252件中682件の無駄な売買を排除できる。
  2. **パニック極値における平均回帰（K-001真の境界）**: K-001（下方乖離）は、中途半端な押し目（Macro Bull）では Net -0.93% と大敗するが、`Bear_Panic_Exhaustion`（Macro Bear ＋ SMA 89から -2.5 ATR超の暴落 ＋ AFS 7 < 30）の極限局面においてのみ、**Net EV +0.38%、勝率 55.6%、PF 1.45、MFE +3.15%** という強烈なプラス期待値を記録する。
* **実験条件**: BTCUSD 1h、5年4ヶ月 Discovery 期間、往復摩擦コスト0.40%控除
* **証拠・出典リンク**: [`03_KNOWLEDGE/experiments/47-mtf-context-integrated-eval/record.md`](experiments/47-mtf-context-integrated-eval/record.md) (EXP-47-001 / [#47](https://github.com/makagi/MTF_AI_Trade/issues/47))
* **仕様への影響**: Milestone 4 の戦略設計において、「レンジ・保ち合い時の完全取引停止ゲート」および「極限パニック暴落時の平均回帰逆張り戦略（Panic Reversion）」の仕様根拠として採用。

---

### K-009: 極限Squeezeからのアクティビティ急増ブレイクアウト
* **ステータス**: 支持 (Supported)
* **概要**: バンド幅が過去下位8%まで収縮した極限エネルギー蓄積（Extreme Squeeze）から、アクティビティ急増（>1.6倍）を伴ってSMA 21をブレイクした初動は、Discovery 期間全体で **Net EV +0.42%、PF 1.38、MFE +2.94% vs MAE -1.77%（リスクリワード比 1.66）** と高い摩擦耐性と順行エッジを示した。特に強気バブル期（2020-2021年）では Net EV +2.57% と極大化した。
* **実験条件**: BTCUSD 1h、5年4ヶ月 Discovery 期間、往復摩擦コスト0.40%控除
* **証拠・出典リンク**: [`03_KNOWLEDGE/experiments/49-shock-dynamics-cross-period/record.md`](experiments/49-shock-dynamics-cross-period/record.md) (EXP-49-001 / [#49](https://github.com/makagi/MTF_AI_Trade/issues/49))
* **仕様への影響**: ブレイクアウト戦略（Breakout Strategy）のコアトリガー条件として採用。通常のSqueezeではなく「下位8%極限圧縮＋アクティビティ急増」に限定する。

---

### K-010: フラッシュクラッシュ「1番底禁止」と「2番底ダイバージェンス」の規律
* **ステータス**: 支持 (Supported)
* **概要**: 6時間で 3 ATR超の暴落直後において、最初の反発（1番底）に即時逆張りした場合は **Net EV -0.41%、MAE -3.23%** と深いドローダウンに巻き込まれて大敗する（Refuted: 落ちるナイフの罠）。一方、12〜48時間後に再度安値を試し、オシレーター（AFS 7）の強気ダイバージェンスを確認した「2番底」でエントリーした場合、**MAEは -2.15% へと約 33% 抑制** され、強気相場（P1）では Net EV +0.22% とプラス化した。
* **実験条件**: BTCUSD 1h、急落後12〜48時間追跡、往復摩擦コスト0.40%控除
* **証拠・出典リンク**: [`03_KNOWLEDGE/experiments/49-shock-dynamics-cross-period/record.md`](experiments/49-shock-dynamics-cross-period/record.md) (EXP-49-001 / [#49](https://github.com/makagi/MTF_AI_Trade/issues/49))
* **仕様への影響**: パニック逆張り戦略において「急落直後の1番足での即時買いを禁止」し、「2番底ダイバージェンス形成待ち」を必須エントリー規律として義務化。

---

### K-011: クライマックスピンバー単独の優位性欠如
* **ステータス**: 反証・棄却 (Refuted)
* **概要**: 2.8倍超のアクティビティ急変を伴う長い下ヒゲピンバー（下ヒゲ45%超）の発生は、一見反発のサインに見えるが、無条件フォワードでは **Net EV -0.51%、PF 0.67、MAE -3.74%** と惨敗した。単足のヒゲ単体では相場の勢いを止められず、単独シグナルとしての優位性は否定された。
* **実験条件**: BTCUSD 1h、全76件、往復摩擦コスト0.40%控除
* **証拠・出典リンク**: [`03_KNOWLEDGE/experiments/49-shock-dynamics-cross-period/record.md`](experiments/49-shock-dynamics-cross-period/record.md) (EXP-49-001 / [#49](https://github.com/makagi/MTF_AI_Trade/issues/49))
* **仕様への影響**: 単一足のローソク足ヒゲ・ピンバー単体に基づくエントリーシグナルの採用を禁止。

---

### K-012: 上位足抵抗帯モメンタム過熱の時代依存性
* **ステータス**: 保留・時代依存 (Inconclusive / Regime-Dependent)
* **概要**: 日足SMA 377付近到達 ＋ 1h AFS過熱（>80）からの反転売りは、強気相場初期（P1: Net +0.18%）や弱気相場（P2: Net -0.03%）では機能する一方、近年の本格回復・最高値更新相場（P3）では強力な踏み上げにより **Net EV -1.06%** と大敗した。相場のトレンド強度によって結果が激しく非定常である。
* **実験条件**: BTCUSD 1h、全242件、3時代別Cross-Period比較
* **証拠・出典リンク**: [`03_KNOWLEDGE/experiments/49-shock-dynamics-cross-period/record.md`](experiments/49-shock-dynamics-cross-period/record.md) (EXP-49-001 / [#49](https://github.com/makagi/MTF_AI_Trade/issues/49))
* **仕様への影響**: 上位足抵抗線での過熱逆張りを単独ルール化することを保留。マクロトレンド推進度合いの定量判定を必須とする。

---

### K-013: 清算カスケード後のボラティリティ枯渇特性
* **ステータス**: 観測 (Observed)
* **概要**: 単足で 2.8 ATR超の巨大レンジ足（清算カスケード）が発生した直後の 24〜48時間は、市場参加者のエネルギー消費とポジション解消により、極端なボラティリティから一転して保ち合い・レンジ相場へ移行する傾向が観測された。
* **実験条件**: BTCUSD 1h、大急変足発生後のフォワードボラティリティ計測
* **証拠・出典リンク**: [`03_KNOWLEDGE/experiments/49-shock-dynamics-cross-period/record.md`](experiments/49-shock-dynamics-cross-period/record.md) (EXP-49-001 / [#49](https://github.com/makagi/MTF_AI_Trade/issues/49))
* **仕様への影響**: 急変発生直後の追随順張りを禁止し、ボラティリティ沈静化を待つクールダウン期間（Cool-off Period）設計の基礎として活用。

---

### K-014: 乖離逆張りにおける厳格MTF防壁の必須性
* **ステータス**: 支持 (Supported)
* **概要**: SMA 89乖離 < -2.5 ATR 単体で緩い条件の逆張りを行うと、4,036件と取引が過多になり **Net EV -0.47%、PF 0.67、MAE -2.99%** と大敗する。K-008 で実証されたように、「Macro Bear ＋ 極限パニック（Bear_Panic_Exhaustion）」という厳格な二重防壁を通過した少数精鋭のセットアップ（Net +0.38%）に限定しない限り、平均回帰エッジは発現しないことが再確認された。
* **実験条件**: BTCUSD 1h、全4,036件、往復摩擦コスト0.40%控除
* **証拠・出典リンク**: [`03_KNOWLEDGE/experiments/49-shock-dynamics-cross-period/record.md`](experiments/49-shock-dynamics-cross-period/record.md) (EXP-49-001 / [#49](https://github.com/makagi/MTF_AI_Trade/issues/49))
* **仕様への影響**: 逆張り戦略において緩い閾値による過剰売買を禁止。厳格なMTFレジーム条件を必須防壁とする。

---

## 4. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-10 | 0.1.0 | 初版作成（旧知識体系の3層化・K-001〜K-005 登録） | @makagi / [#20](https://github.com/makagi/MTF_AI_Trade/pull/20) |
| 2026-10-13 | 0.2.0 | 科学的証拠表現の是正、エビデンスレベル確立、K-005 を Inconclusive へ見直し | @makagi / [#29](https://github.com/makagi/MTF_AI_Trade/pull/29) |
| 2026-10-13 | 0.2.0 | 書式・メタデータ統一 | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |
| 2026-10-15 | 0.3.0 | EXP-41-001 観察記録反映、MTF状況把握分析の先行方針に伴い K-005 を保留・観察中 (Inconclusive) として整理 | @makagi / [#41](https://github.com/makagi/MTF_AI_Trade/pull/41) |
| 2026-10-16 | 0.4.0 | EXP-43-001 反映、K-006（フィボナッチ時間足間等価性とMTF間引き構造）を新設・登録 | @makagi / [#43](https://github.com/makagi/MTF_AI_Trade/pull/43) |
| 2026-10-16 | 0.5.0 | EXP-45-001 反映、K-007（MTF 3階層レジーム分類と状態遷移モデル）を新設・登録 | @makagi / [#45](https://github.com/makagi/MTF_AI_Trade/issues/45) |
| 2026-10-17 | 0.6.0 | EXP-47-001 反映、K-005 を再評価（押し目フィルターとして支持）、K-008（MTF状況依存エッジと極限パニック平均回帰）を新設・登録 | @makagi / [#47](https://github.com/makagi/MTF_AI_Trade/issues/47) |
| 2026-10-17 | 0.7.0 | EXP-49-001 反映、急変前後の動態・ショック現象と期間別頑健性検証（K-009〜K-014）を新設・登録（計14知見へ拡充） | @makagi / [#49](https://github.com/makagi/MTF_AI_Trade/issues/49) |
