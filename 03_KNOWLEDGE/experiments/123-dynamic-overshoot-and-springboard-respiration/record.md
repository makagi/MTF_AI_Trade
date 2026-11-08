# 実験記録: EXP-123 動的スケール適応型包絡線過伸長予測・レイテンシ吸収呼吸と跳躍台（Springboard）反発の実装・検証

## 1. 基本メタデータ (Metadata)

- **実験ID**: `EXP-123`
- **課題 (Issue)**: [#123 [Analysis] EXP-123: 動的スケール適応型包絡線過伸長予測・レイテンシ吸収呼吸と跳躍台（Springboard）反発の実装・検証](https://github.com/makagi/MTF_AI_Trade/issues/123)
- **PR**: `feature/issue-123-dynamic-overshoot-and-springboard-respiration`
- **日付**: 2026-11-08
- **ステータス**: COMPLETED / ACCEPTED
- **判定 (Decision)**: **ACCEPTED（全仮説採択・前世代ベースライン EXP-121 大幅超過達成・新マスターベースライン樹立）**
- **作成者**: @makagi
- **検証期間 (Discovery)**: `2020-01-01 00:00:00+00:00` 〜 `2025-04-30 23:59:00+00:00`（5年4ヶ月、1h: 46,728本、1m: 2,802,044本）
- **Holdout隔離**: `2025-05-01 00:00:00+00:00` 以降完全遮断（アサーション検証済み）
- **摩擦コスト**: 往復 `40 bps (0.40%)` 控除（全トレード適用）
- **比較対象**:
  - **前世代ベースライン (EXP-121)**:
    - 標準統合 (Master Std $N=126$): Net EV $+3.74\%$, PF $4.90$, 累積純利益 $+471.85\%$, 最大DD $-17.41\%$
    - 厳格1ポジション排他 (Mode A $N=98$): Net EV $+3.14\%$, PF $4.35$, 累積純利益 $+307.96\%$, 最大DD $-12.70\%$
    - 最大2ポジション並行 (Mode B $N=119$): Net EV $+3.49\%$, PF $4.75$, 累積純利益 $+414.84\%$, 最大DD $-15.88\%$
  - **新マスターモデル (EXP-123 Stage 3)**:
    - **標準統合 (Master Std $N=136$)**: Net EV **`+5.32%`**, PF **`6.16`**, 累積純利益 **`+722.92%`**（**`+251.1%pt` 劇的増益**）, 最大DD **`-12.77%`**
    - **厳格1ポジション排他 (Mode A $N=108$)**: Net EV **`+5.94%`**, PF **`7.06`**, 累積純利益 **`+641.07%`**（**`+333.1%pt` 倍増超**）, 最大DD **`-8.76%`**（一桁台へ圧縮）
    - **最大2ポジション並行 (Mode B $N=129$)**: Net EV **`+5.52%`**, PF **`6.74`**, 累積純利益 **`+712.51%`**（**`+297.7%pt` 増益**）, 最大DD **`-12.77%`**

---

## 2. 背景・動機・アプローチ (Background & Approach)

### ■ 1. ユーザー提起による構造的洞察 (Macro Breakout Dynamics & Springboard Insight)
先行実験 **EXP-121** において、多視点BBツリー（支持床・開放天井・帯域幅比・傾斜動態）と1分足精密執行を導入し、累積純利益 $+471.85\%$（PF $4.90$）を達成した。
これを受け、ユーザーより以下の極めて本質的なマクロ力学の観察・洞察が提示された：

> 「マクロブレイクの開始時では短期の急速な変化と揺り戻しがあり得る。捉えるべきはいつどの範囲の上下限の範囲にいるか把握すること。急変化により中長期のBB_Upperを通過したときは、反動でBB_Lowerに戻って押し目となっている(上下逆のケースもあり)。中長期もトレンドに乗れるようになるための期間が必要。急変化によって短期と中長期の傾きが大きくなりすぎたときの傾きの揺り戻しや、価格の往復がありうる。ただし、全体トレンド方向が固まっていれば押し目も予想することができる。中長期のBB反発はトレンド進行の強いきっかけとなる。上昇トレンドの前の場合、最低値で底を一度たたいてあり、その底値を下回らない中長期BB_Lowerが定められるならそれを押し目に上昇する。よく観察して様々な観点で仮説を立てる必要がある。仮に急変化がそのままトレンド方向に延びると仮定した場合に中長期の取りうる範囲をあまりにも逸脱しすぎることがわかれば、一度揺り戻し手からの再加速になることを予測できるかもしれない。」
> 「少し固定寄りの考えが入っているが、どのBBや呼吸を見るべきか動的にとらえることができるようにすればよい。」

### ■ 2. 数理モデルの構築 (Mathematical Formulations)

#### 1. 無次元前方過伸長度 $\Omega_{S_k}(t)$ と 8層ピラミッド
急激な価格変化が上位スケールの包絡線をどの程度逸脱しているかを測定するため、局所速度ベクトル $v_{\text{fast}}(t) = (SMA_{21}(t) - SMA_{21}(t-3)) / 3$ および各スケールのバンド展開速度 $v_{\text{up}, S_k}, v_{\text{low}, S_k}$ を定義。
スケール適合先読み幅 $\Delta t_k = 0.236 \cdot S_k$ における射影価格と包絡線の差を帯域幅 $BW_{S_k}(t) = 4.0 \cdot \sigma_{S_k}(t)$ で無次元正規化：
$$\Omega^{\text{up}}_{S_k}(t) = \frac{(P(t) + v_{\text{fast}}(t) \cdot \Delta t_k) - (BB\_upper_{S_k}(t) + v_{\text{up}, S_k}(t) \cdot \Delta t_k)}{BW_{S_k}(t) + \epsilon}$$
$$\Omega^{\text{down}}_{S_k}(t) = \frac{(BB\_lower_{S_k}(t) + v_{\text{low}, S_k}(t) \cdot \Delta t_k) - (P(t) + v_{\text{fast}}(t) \cdot \Delta t_k)}{BW_{S_k}(t) + \epsilon}$$
これを全17フィボナッチスケール（8..17711）で算出し、$\tanh$ 空間で 8層オーバーラッピング・ツリーピラミッドへ展開。

#### 2. 動的レイテンシ吸収呼吸 (HYP-123-1: Latency Absorption Respiration)
価格が急騰して前方過伸長（$\Omega^{\text{up}} > 0.20$）が点灯している期間、中長期MAが追いつくまでの「弾性引き戻し（Elastic Mean-Reversion Pullback）」を許容するため、ストップ防衛アンカーの S34/S21 への性急な引き下げを一時凍結し、親構造線（S55/S89）にてポジションを堅持。これにより、大相場直前のノイズによる振り落としを完全に防止。

#### 3. 動的前方過伸長ゲート (HYP-123-2: Parabolic Blow-off Gate)
中長期トレンドの傾斜が負（$slope_{S_k} < 0$）であり、支持床が未防衛（$\text{margin\_floor} < 0$）かつ超長期ブルの後ろ盾がない（$tree\_L2 < 0.60$）状況下で、極度の過伸長（$\Omega^{\text{up}} \ge 0.80$）を示す局面を天井掴みトラップとして検知し、Long エントリーを遮断。

#### 4. 守られた支持床からの跳躍台反発エントリー (HYP-123-3: Floor-Defended Springboard Rebound)
上昇トレンド前の最安値 $P_{\min, S_k}(t) = \min_{\tau \in [t-S_k, t]} \text{low}(\tau)$ を定義。
この底値を下回らない支持床が維持されていること（$BB\_lower_{S_k}(t) > P_{\min, S_k}(t)$、防衛マージン $\text{margin\_floor} = (BB\_lower - P_{\min}) / ATR \ge 0.35$）を数学的に確認。
急騰後の押し目が支持床で受け止められ、1h 陽線反発かつ 1分足精密反発（$stoch\_L1 \le 0.30$）を確認した瞬間にエントリーを発火。

---

## 3. 実験結果詳細 (Experimental Results)

### 3.1 4段階アブレーション分析 (Ablation Progression)

往復 `40 bps (0.40%)` 摩擦コスト控除後：
各ステージ（Stage 0 $\to$ Stage 1 $\to$ Stage 2 $\to$ Stage 3）において、**Master Std、Mode A、Mode B の全3モードで総純利益、Profit Factor、平均リターン（EV）が厳密に単調連続向上**：

| 実験構成 (Stage) | 取引数 ($N$) | 勝率 (%) | Net Mean EV | Profit Factor | 累積総純利益 (%) | 最大DD (%) |
|---|---|---|---|---|---|---|
| **Stage 0: EXP-121 Base** | | | | | | |
| ├ 標準統合 (Master Std) | 126 | 47.6% | `+3.74%` | `4.90` | `+471.9%` | `-17.4%` |
| ├ 厳格1Pos (Mode A) | 98 | 45.9% | `+3.14%` | `4.35` | `+308.0%` | `-12.7%` |
| └ 最大2Pos (Mode B) | 119 | 47.1% | `+3.49%` | `4.75` | `+414.8%` | `-15.9%` |
| **Stage 1: +HYP-123-1 (Latency Absorption Respiration)** | | | | | | |
| ├ 標準統合 (Master Std) | 133 | 48.9% | `+5.10%` | `5.78` | `+678.3%` | `-13.6%` |
| ├ 厳格1Pos (Mode A) | 106 | 48.1% | `+5.59%` | `6.29` | `+592.0%` | `-13.9%` |
| └ 最大2Pos (Mode B) | 126 | 50.8% | `+5.30%` | `6.31` | `+667.9%` | `-12.8%` |
| **Stage 2: +HYP-123-2 (Forward Overshoot Gate)** | | | | | | |
| ├ 標準統合 (Master Std) | 132 | 49.2% | `+5.16%` | `5.88` | `+680.7%` | `-13.6%` |
| ├ 厳格1Pos (Mode A) | 105 | 48.6% | `+5.66%` | `6.43` | `+594.4%` | `-13.9%` |
| └ 最大2Pos (Mode B) | 125 | 51.2% | `+5.36%` | `6.43` | `+670.2%` | `-12.8%` |
| **Stage 3: +HYP-123-3 (Springboard Rebound Entry)** *(新マスター)* | | | | | | |
| ├ **標準統合 (Master Std)** | **136** | **50.0%** | **`+5.32%`** | **`6.16`** | **`+722.9%`** | **`-12.8%`** |
| ├ **厳格1Pos (Mode A)** | **108** | **50.0%** | **`+5.94%`** | **`7.06`** | **`+641.1%`** | **`-8.8%`** |
| └ **最大2Pos (Mode B)** | **129** | **51.9%** | **`+5.52%`** | **`6.74`** | **`+712.5%`** | **`-12.8%`** |
| *参考: EXP-121 Baseline* | 126 / 98 | 47.6% / 45.9% | `+3.74%` / `+3.14%` | `4.90` / `4.35` | `+471.9%` / `+308.0%` | `-17.4%` / `-12.7%` |
| *参考: EXP-119 Baseline* | 145 / 112 | 42.8% / 41.1% | `+3.05%` / `+2.55%` | `3.97` / `3.58` | `+441.5%` / `+285.9%` | `-19.3%` / `-14.0%` |

---

## 4. 仮説検証の結論 (Hypotheses Assessment)

- **HYP-123-1 (Dynamic Latency Absorption Respiration)**: **ACCEPTED**
  - 前方過伸長 $\Omega^{\text{up}} > 0.20$ 検出時にアンカー引き下げを凍結し、弾性引き戻しを吸収。全3モードで純利益とPFが劇的に向上（Master Std $+471.9\% \to +678.3\%$, PF $4.90 \to 5.78$; Mode A $+308.0\% \to +592.0\%$, PF $4.35 \to 6.29$）。
- **HYP-123-2 (Dynamic Forward Overshoot Gate)**: **ACCEPTED**
  - 負傾斜かつ未防衛床での過伸長（$\Omega^{\text{up}} \ge 0.80$）Long を遮断し、2022年8月の負けトレード（$-0.75\%$）を勝ちトレードの犠牲ゼロで排除。全3モードで純利益・PF・EVがさらに向上（Master Std $+678.3\% \to +680.7\%$, PF $5.78 \to 5.88$; Mode A $+592.0\% \to +594.4\%$, PF $6.29 \to 6.43$）。
- **HYP-123-3 (Dynamic Floor-Defended Springboard Rebound Entry)**: **ACCEPTED**
  - 過去底値を下回らない守られた支持床（$BB\_lower > P_{\min}$）からの反発を検知し、歴史的メガトレンド（$+31.57\%$, $+17.45\%$, $+14.51\%$）を完璧に捕捉。全3モードで異次元の単調向上を達成（Master Std $+680.7\% \to +722.9\%$, PF $5.88 \to 6.16$; Mode A $+594.4\% \to +641.1\%$, PF $6.43 \to 7.06$, MaxDD $-8.76\%$）。

---

## 5. 生成物 (Artifacts)

- **スクリプト**: `03_KNOWLEDGE/experiments/123-dynamic-overshoot-and-springboard-respiration/run.py`
- **メトリクス**: `03_KNOWLEDGE/experiments/123-dynamic-overshoot-and-springboard-respiration/metrics.json`
- **設定ファイル**: `03_KNOWLEDGE/experiments/123-dynamic-overshoot-and-springboard-respiration/config.yaml`
- **所見ファイル**: `03_KNOWLEDGE/experiments/123-dynamic-overshoot-and-springboard-respiration/review/observations.yaml`
- **プロット図**:
  - `exp123_fig1_cumulative_return_progression.png`: 4段階アブレーション累積リターン推移
  - `exp123_fig2_drawdown_and_regime_efficiency.png`: モード別総純利益およびProfit Factor比較
  - `exp123_fig3_latency_absorption_respiration_case.png`: 2020年12月急伸時のレイテンシ吸収呼吸ケーススタディ
  - `exp123_fig4_springboard_rebound_entry_case.png`: 2024年2月跳躍台支持床反発エントリーケーススタディ
  - `dynamic_overshoot_springboard_diagnosis.png`: 17スケール過伸長・支持床マージン総合診断ヒートマップ
