# 特徴量仕様 (Feature Specification)

**Doc ID:** SPEC-FEAT-001  
**Version:** 0.2.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-19  
**Related Issues:** [#39](https://github.com/makagi/MTF_AI_Trade/issues/39), [#61](https://github.com/makagi/MTF_AI_Trade/issues/61)  
**Related Docs:** [02_SPECIFICATIONS/evaluation.md](evaluation.md), [01_CONCEPTS/mtf-framework.md](../01_CONCEPTS/mtf-framework.md), [01_CONCEPTS/volatility.md](../01_CONCEPTS/volatility.md), [01_CONCEPTS/market-structure.md](../01_CONCEPTS/market-structure.md), [00_GOVERNANCE/principles.md](../00_GOVERNANCE/principles.md), [90_LEGACY/knowledge/DICTIONARY.md](../90_LEGACY/knowledge/DICTIONARY.md)  

---

## 1. Purpose & Scope

本ドキュメントは、本プロジェクトにおいて市場構造の把握、仮説検証、および機械学習モデルの入力として用いられる**マルチタイムフレーム（MTF）特徴量の共通計算仕様・契約**を定義する。

旧資産（`90_LEGACY/knowledge/DICTIONARY.md`）に蓄積された「相場力学（ゴムバンド効果、ボラティリティ圧縮、フラクタルモメンタム、空間トポロジー、Soft Logic等）」を数理的・統計的に厳密な仕様へと昇格させ、研究者（人間）および AI Agent が一貫した基準で特徴量を算出し、データリーク（先読み）のない堅牢な実験を行うことを目的とする。

---

## 2. 設計原則 (Design Principles)

特徴量の算出および実装は、以下の4大原則に厳格に従わなければならない。

### 2.1 因果律と未来参照の完全排除 (Causality & No Lookahead)
* 時刻 $t$ において利用可能な情報のみを用いて特徴量を算出しなければならない。
* ローリング計算（移動平均、ローリング最小・最大等）においては、終値確定足（`Close[t]`）以前のデータのみを参照し、未来のバー（$t+1$ 以降）の情報を含めてはならない。
* センタリング移動平均（`center=True`）や、未来の最高値・最安値を参照する平滑化フィルターの使用は厳禁とする。
* マルチタイムフレーム集約時（例: 1分足に1時間足の指標をマージする場合）は、1時間足が**完全に確定（確定足のクローズ）した後にのみ**結合し、進行中の未確定バーを参照してはならない（前方シフトの徹底）。

### 2.2 スケール不変性と定常性 (Scale Invariance & Stationarity)
* 単純な価格差（例: $\text{Close}_t - \text{SMA}_t$ のドル建て絶対値）を直接特徴量としてはならない。価格水準が大きく変動する暗号資産市場において非定常性を生むためである。
* すべての特徴量は、以下のいずれかの方法で正規化しなければならない：
  1. **現在価格比**: 価格で除算したパーセンテージ乖離（例: $(\text{Close} - \text{SMA}) / \text{Close}$）
  2. **ボラティリティ正規化**: ATR またはローリング標準偏差で除算した標準化スコア（例: 乖離幅 / ATR）
  3. **動的パーセンタイル / ミンマックス正規化**: 過去の固定ルックバック窓における相対位置（例: 過去30日間の $[0.0, 1.0]$ スケーリング）

### 2.3 ファジィ・連続スコア化 (Soft Logic & Noise Absorption)
* 「サポレジ線にタッチした」「過熱圏に突入した」といった裁量判断をハードな閾値（Boolean の True/False）でバイナリ判定し、それを AND 条件で多重結合してはならない（過剰制約によるシグナル消滅と過学習の温床）。
* 市場状態は連続値（Soft Logic: $[-1.0, 1.0]$ または $[0.0, 1.0]$）のスコアとして表現し、高頻度ノイズを平滑化（Smoothing）して吸収しなければならない。

### 2.4 記憶（Memory）の保持
* 市場の反転やブレイクアウトは単一のバーの瞬間的な事象ではなく、過去数時間〜数十時間にわたるエネルギー充填・サポレジ到達の「履歴（ラグ）」に支配される。
* 「過去 $N$ 期間におけるサポレジへの到達深度（極値記憶）」等の時間差特徴量を明示的に設計に組み込む。

---

## 3. 入出力データ型契約 (Data Contract)

### 3.1 入力データ要件
* **インデックス**: UTC timezone-aware な `pd.DatetimeIndex`。
* **必須カラム**: `open`, `high`, `low`, `close`, `volume`（すべて小文字、float64型）。
* **欠損値**: 入力データ内のギャップや不正値は `src/data_loader.py` で検証・処理済みであることを前提とする。

### 3.2 欠損値（NaN）処理方針
* 指標計算のウォームアップ期間（例: 長期SMA 377バー分の初期期間）に生じる `NaN` は、ゼロ埋め（`fillna(0)`）や前方補完（`ffill()`）を行ってはならない。
* ウォームアップ期間が終了した有効なインデックス以降のみを抽出して後続の分析・学習に引き渡す。

### 3.3 ゼロ除算防止
* ゼロ除算が発生しうる除算演算（バンド幅での除算、ボラティリティでの除算等）では、微小定数 $\epsilon = 10^{-8}$（または ATR 基準の最小イプシロン）を分母に加算しなければならない。

---

## 4. コアMTF特徴量仕様 (Core Feature Specifications)

### 4.1 ゴムパッチン指数 (Elasticity Index)
* **概念**: 超長期SMA（アンカー磁石）に対する短中期SMA束（クラスター）の密集度と乖離度の比率。短中期線が極限まで密集しながら超長期線から大きく乖離している時、強い平均回帰引力（スナップバック）が発生する。
* **入力**: $\text{Close}_t$, $\text{SMA}_{21,t}$, $\text{SMA}_{55,t}$, $\text{SMA}_{89,t}$, $\text{SMA}_{377,t}$
* **数式定義**:
  $$\text{Cluster\_Width}_t = \frac{\max(\text{SMA}_{21,t}, \text{SMA}_{55,t}, \text{SMA}_{89,t}) - \min(\text{SMA}_{21,t}, \text{SMA}_{55,t}, \text{SMA}_{89,t})}{\text{Close}_t}$$
  $$\text{Magnet\_Distance}_t = \frac{\left| \text{SMA}_{377,t} - \text{mean}(\text{SMA}_{21,t}, \text{SMA}_{55,t}, \text{SMA}_{89,t}) \right|}{\text{Close}_t}$$
  $$\text{Elasticity\_Index}_t = \frac{\text{Magnet\_Distance}_t}{\text{Cluster\_Width}_t + 10^{-8}}$$
* **解釈**: 指数が高いほど「密集した短中期線が超長期線から限界まで引き伸ばされた」状態を示し、平均回帰の期待値が高まる。

---

### 4.2 Squeeze Index (マルチタイムフレーム・ボラティリティ圧縮)
* **概念**: 複数周期のボリンジャーバンド（BB）の相対幅の総和を過去ルックバック期間（30日）で正規化し、全階層でのエネルギー充填度合いを測定する。
* **入力**: $\text{Close}_t$, 各周期 $k \in \{21, 55, 144, 377\}$ のボリンジャーバンド上下限（$\text{Upper}_{k,t}$, $\text{Lower}_{k,t}$）
* **数式定義**:
  $$\text{Total\_BB\_Width}_t = \sum_{k \in \{21, 55, 144, 377\}} \frac{\text{Upper}_{k,t} - \text{Lower}_{k,t}}{\text{Close}_t}$$
  $$\text{Squeeze\_Index}_t = \frac{\text{Total\_BB\_Width}_t - \min_{30d}(\text{Total\_BB\_Width})}{\max_{30d}(\text{Total\_BB\_Width}) - \min_{30d}(\text{Total\_BB\_Width}) + 10^{-8}}$$
* **解釈**: $0.0$ に近いほど全階層で完全収縮（Coiled Spring）した状態を示し、その後のメガトレンド爆発（Vol-Expansion）の予兆となる。

---

### 4.3 AFS (Average Fibonacci Stochastics) モメンタム
* **概念**: オシレーターの測定期間（%K）と平滑化期間（%D）に同一のフィボナッチ階層 $p \in \{7, 9, 11, 13\}$ を用いることで、フラクタル構造を破壊せずに真のモメンタムのうねりを抽出する。
* **入力**: $\text{Close}_t, \text{High}_t, \text{Low}_t$
* **数式定義**:
  $$K_t(p) = \frac{\text{Close}_t - \min_{p}(\text{Low})}{\max_{p}(\text{High}) - \min_{p}(\text{Low}) + 10^{-8}} \times 100$$
  $$\text{AFS}_t(p) = \text{SMA}(K(p), p)_t \quad (\text{平滑化窓長にも同一の } p \text{ を使用})$$
  $$\text{AFS\_Order\_Score}_t = \mathbf{1}(\text{AFS}_7 > \text{AFS}_9) + \mathbf{1}(\text{AFS}_9 > \text{AFS}_{11}) + \mathbf{1}(\text{AFS}_{11} > \text{AFS}_{13})$$
  $$\text{AFS\_Compression}_t = \text{Variance}(\text{AFS}_{7,t}, \text{AFS}_{9,t}, \text{AFS}_{11,t}, \text{AFS}_{13,t})$$
* **解釈**: `AFS_Order_Score` が 3 のとき完全上昇順列、0 のとき完全下降順列。`AFS_Compression` の極小化はモメンタムの収束を示す。

---

### 4.4 空間トポロジーと岩盤密度 (Topology & Wall Density)
* **概念**: 現在価格が上位サポレジ構造のどの位置にあるか（天井と床の挟撃比率）および近接支持線の密集度を数値化する。
* **サポレジ水準群**:
  $$\text{Levels} = \{\text{SMA}_{144}, \text{BB\_L}_{144}, \text{BB\_U}_{144}, \text{SMA}_{377}, \text{BB\_L}_{377}, \text{BB\_U}_{377}\}$$
* **数式定義**:
  $$\text{Ceiling}_t = \min(\{L \in \text{Levels}_t \mid L > \text{Close}_t\} \cup \{\text{Close}_t \times 1.10\})$$
  $$\text{Floor}_t = \max(\{L \in \text{Levels}_t \mid L < \text{Close}_t\} \cup \{\text{Close}_t \times 0.90\})$$
  $$\text{Sandwich\_Ratio}_t = \frac{\text{Close}_t - \text{Floor}_t}{\text{Ceiling}_t - \text{Floor}_t + 10^{-8}}$$
  $$\text{Wall\_Density}_t = \sum_{L \in \text{Levels}_t} \mathbf{1}(\text{Close}_t - 0.5 \times \text{ATR}_t \le L \le \text{Close}_t)$$
* **解釈**: `Sandwich_Ratio` が 0.0 付近は床（サポート）接触、1.0 付近は天井（レジスタンス）接触。`Wall_Density >= 3` は直下に複数の支持線が密集した「鉄壁の岩盤」を示す。

---

### 4.5 v4.0 Soft Logic & Memory 特徴量 (K-005 仕様)
* **背景**: ハードなAND条件によるシグナル消滅（過剰制約）を防ぐため、階層構造の連動を連続値としてスコアリングする。
* **主要指標**:
  1. **階層別・平滑化同調スコア (Smoothed Alignment Score)**:
     短期AFSと長期AFSの方向性および乖離度を $[-1.0, 1.0]$ の範囲で連続平滑化。
  2. **マクロ重力逆行スコア (Macro Gravity Divergence)**:
     短期のオシレーターが買われすぎ/売られすぎを示す一方で、マクロトレンドが逆方向に張り付いている度合いを $[-2.0, 2.0]$ でスコア化し、「ダマシの逆張りトラップ」を定常的に識別。
  3. **ATR正規化ファンアウト速度 (ATR-normalized Fan-out Velocity)**:
     複数SMA間の間隔拡大速度（1次微分）を ATR で正規化し、価格反転に先行するモメンタムの減速（Leading Indicator）を捉える。
     $$\text{Fanout\_Velocity}_t = \frac{\Delta(\text{SMA}_{21} - \text{SMA}_{89})_t}{\text{ATR}_t + 10^{-8}}$$
  4. **到達記憶特徴量 (Support Reaching Memory)**:
     過去 $N=24$ バーにおけるボリンジャーバンド位置（`BB_pos`）の最小値を保持し、「数時間前に深いサポートに到達した後に反発しているか」の時間差履歴を表現。

---

### 4.6 真空地帯 (The Void Filter)
* **概念**: モメンタムが発生しても、進行方向にマクロの壁（抵抗線・支持線）が存在すれば価格は伸びずに失速する。進行方向に障害物のない十分な真空地帯（弾道空間）が存在するかを判定する。
* **数式定義**:
  - **ロング方向 (`direction="long"`)**:
    $$\text{Overhead\_SMA}_t = \min(\{ \text{SMA}_{k,t} \mid \text{SMA}_{k,t} > \text{Close}_t \text{ for } k \in [55, 89, 144, 377] \} \cup \{\text{Close}_t \times 1.20\})$$
    $$\text{Void\_Distance\_Long}_t = \frac{\text{Overhead\_SMA}_t - \text{Close}_t}{\text{ATR}_t + 10^{-8}}$$
  - **ショート方向 (`direction="short"`)**:
    $$\text{Underlying\_SMA}_t = \max(\{ \text{SMA}_{k,t} \mid \text{SMA}_{k,t} < \text{Close}_t \text{ for } k \in [55, 89, 144, 377] \} \cup \{\text{Close}_t \times 0.80\})$$
    $$\text{Void\_Distance\_Short}_t = \frac{\text{Close}_t - \text{Underlying\_SMA}_t}{\text{ATR}_t + 10^{-8}}$$
* **解釈**: `Void_Distance` が大きいほど（例: 1.5〜2.0 ATR以上）、進行方向に障害物がなく走る空間が確保されている。ショート戦略では必ず `direction="short"` を適用し、直下のサポートまでの距離を評価する。

---

### 4.7 時間成熟度軸 (Regime Age & Wave Maturity)
* **概念**: 同一のブレイクや乖離特徴量であっても、トレンド発生直後（初動）か、持続時間の中央値を超えた老朽期（反転リスク領域）かによって期待値が正反対になる。各階層の持続時間中央値に対する経過時間比率を状況軸として定義する。
* **数式定義**:
  - 直近のレジーム転換（Bull / Bear / Range）からの経過バー数を $T_{\text{age}}$ とする。
  - 各時間階層の実証中央値持続時間（K-027 準拠: Macro = 78.5h, Meso = 21.0h, Micro = 6.0h）を用いて比率化：
    $$\text{Macro\_Age\_Ratio}_t = \frac{T_{\text{macro\_age}, t}}{78.5}$$
    $$\text{Meso\_Age\_Ratio}_t = \frac{T_{\text{meso\_age}, t}}{21.0}$$
* **解釈**: $\text{Age\_Ratio} < 1.0$ は初動〜巡航期（順張り高優位性領域）、$\text{Age\_Ratio} > 2.0$ は老朽期（過熱・天井圏警戒領域）。

---

### 4.8 サポレジ・アタック回数 (Level Test Count)
* **概念**: 動的サポレジ水準への接触回数と流動性消費モデル（CONC-STR-001 §2）。同一水準へのテストが繰り返されるほど防戦指値が消費され、反発力は低下しブレイク（貫通）確率が高まる。
* **数式定義**:
  - 水準 $L_t$ に対して、許容バンド幅 $\delta = 0.5 \times \text{ATR}_t$ とする。
  - 価格（High/Low）がバンド $[\max(L_t - \delta, 0), L_t + \delta]$ に接触している状態を接触フラグ $C_t \in \{0, 1\}$ とする。
  - **エピソード分離規則（微小ノイズ排除）**: 単一の接触波内で価格がバンド境界を1バー単位で微小振動するノイズを排除するため、先行する離脱期間が少なくとも $\text{min\_departure\_bars} = 3$ バー以上継続していた場合のみ、新規のテストエピソード開始点 $\mathbf{1}_{\text{touch\_start}, t}$ としてカウントする：
    $$\mathbf{1}_{\text{touch\_start}, t} = 1 \iff C_t = 1 \land \left(\sum_{k=1}^{\text{min\_departure\_bars}} C_{t-k} = 0\right)$$
  - 過去 $W=72$ バーにおける累積接触回数：
    $$\text{Level\_Test\_Count}_t(L, W) = \sum_{i=0}^{W-1} \mathbf{1}_{\text{touch\_start}, t-i}$$
* **解釈**: $\text{Test\_Count} \in \{1, 2\}$ は初動〜2回目の防戦反発領域（Fresh Wall）、$\text{Test\_Count} \ge 3$ は流動性枯渇によるブレイク・貫通警戒領域（Exhausted Wall）。

---

## 5. 検証・品質保証契約 (Verification & QA Contract)

1. **再現性とモジュール化**:
   - 新規に実装する特徴量は `src/` 配下または各実験ディレクトリ内で明確に関数化・クラス化し、再利用可能な形で提供しなければならない。
2. **Canary Benchmark への接続**:
   - 特徴量計算ロジックの変更・追加時は、`tests/canary/test_indicator_math.py` において合成データを用いた正解値テストを実施し、計算精度の退行を防止しなければならない。
3. **データリーク検証の義務**:
   - 特徴量計算後の DataFrame は `tests/canary/test_leakage_detection.py` および `tools/agent_eval.py` の決定論的ゲートによる検証を受け、未来データの漏洩がないことを保証しなければならない。

---

## 6. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-14 | 0.1.0 | 初版作成（旧資産 DICTIONARY.md からの昇格・仕様標準化） | @makagi / [#39](https://github.com/makagi/MTF_AI_Trade/issues/39) |
| 2026-10-19 | 0.2.0 | 時間成熟度軸 (Regime Age Ratio)、アタック回数 (Level Test Count)、The Void Filter の仕様追加・数式標準化 | @makagi / [#61](https://github.com/makagi/MTF_AI_Trade/issues/61) |

