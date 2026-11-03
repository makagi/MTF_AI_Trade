# MTFシステムトレード 用語集 (Glossary)

**Doc ID:** CONC-GLS-001  
**Version:** 0.4.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-11-03  
**Related Issues:** [#12](https://github.com/makagi/MTF_AI_Trade/issues/12), [#97](https://github.com/makagi/MTF_AI_Trade/issues/97), [#101](https://github.com/makagi/MTF_AI_Trade/issues/101)  
**Related Docs:** [00_GOVERNANCE/principles.md](../00_GOVERNANCE/principles.md), [mtf-framework.md](mtf-framework.md), [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md), [04_IMPLEMENTATION/agent-rules.md](../04_IMPLEMENTATION/agent-rules.md)  

---

## 1. 目的 (Purpose)

本用語集は、プロジェクト内で用いられる独自用語、相場概念、統計・評価用語、およびAIエージェント開発基盤の用語の定義を一元管理する。

人間オペレーターおよび各種AIエージェント（Requirements Agent, Orchestrator, Coding Workers 等）が共通の定義に基づいて作業し、認識の齟齬や解釈のブレを防止することを目的とする。

---

## 2. 科学的認識・証拠連鎖 (Knowledge & Evidence)

[00_GOVERNANCE/principles.md](../00_GOVERNANCE/principles.md) §2 で規定する8段階の証拠連鎖に関する用語。

| 用語 | 英語表記 | 定義・説明 |
|---|---|---|
| **客観的事実** | Fact | 価格、出来高、約定履歴、タイムスタンプなど、解釈や推論を含まない直接的な市場データ。 |
| **観測** | Observation | 計算されたテクニカル指標、特定時間軸のライン、サポレジからの距離など、客観的ルールに基づきデータから抽出された状態。 |
| **解釈** | Interpretation | 観測結果に対して相場構造や参加者の心理・流動性を踏まえて意味づけを行った推論（例:「上値が重い」「ブレイクが近い」）。 |
| **仮説** | Hypothesis | 「条件Xが成立したとき、期待値Yが生じる」という、検証可能かつ反証可能な形式に定式化された作業仮説。事前登録（Analysis Issue）が必須。 |
| **実験** | Experiment | 自己完結したシミュレーションスクリプト（`run.py`）により、過去データ（Discovery期間）を用いて仮説を検証する手続き。 |
| **証拠** | Evidence | 評価仕様（SPEC-EVAL-001）に準拠して算出された定量的データ（サンプル数、摩擦コスト控除後期待値、年別分解、MFE/MAE等）。 |
| **結論** | Conclusion | 証拠と事前登録された合否判定基準を照合した結果判定（`Supported`: 支持 / `Refuted`: 反証 / `Inconclusive`: 保留）。 |
| **意思決定** | Decision | 結論に基づき、仕様への昇格（Specification）、戦略採択（Strategy）、または棄却を決定すること。合意は人間のPRマージを以て確定する。 |
| **知識** | Knowledge | 検証サイクルを経て体系化された知見。系譜図（`knowledge-lineage.md`）に `K-xxx` として登録され、再利用される。 |

---

## 3. 多時間軸相場認識 (MTF & Market Dynamics)

[mtf-framework.md](mtf-framework.md) および [market-structure.md](market-structure.md) に基づく独自相場認識用語。

| 用語 | 英語表記 | 定義・説明 |
|---|---|---|
| **マクロ重力** | Macro Gravity | 上位時間軸（日足・週足等）の構造やサポレジが、下位時間軸（15分・1分等）の局所的なシグナルに対して及ぼす支配的な影響力。上位の抵抗帯直前での下位ロングはマクロ重力に逆行するため抑制対象となる。 |
| **ソフトロジック** | Soft Logic | 単純なハード閾値（AND条件）ではなく、各時間軸のモメンタムや傾きの同調度を連続値スコアとして評価するモデル。 |
| **平滑化同調スコア** | Smoothed Concurrence Score | 複数の時間軸間で波の方向や勢いがどれだけ同調しているかを、ノイズを除去して平滑化した連続値スコア。 |
| **ファンアウト速度** | Fan-out Velocity | 複数期間の移動平均線やバンドの乖離速度（ATR正規化）から、トレンドの初動・加速・減速（先行性）を捉える指標。 |
| **波の伝播** | Wave Propagation | 下位時間軸で発生した小さなトレンドや反転が、中期・長期時間軸へとフラクタルに波及していく動的現象。 |
| **Armed 状態** | Armed State | 上位足のサポレジ接近やボラティリティ圧縮を経て、セットアップ条件が成立し、短期足のエントリートリガーを待機している「発火準備完了」状態。 |
| **ロールリバーサル** | Role Reversal | サポート帯が下抜かれた後にレジスタンス帯へと役割が転換する（またはその逆）現象。 |
| **流動性プール** | Liquidity Pool | スイング高値の上やスイング安値の下など、市場参加者の損切り注文（ストップロス）が集中的に溜まっている価格帯。 |
| **先行上限到達** | Early Ceiling | 短期・中位階層が先行して高値・上限に達し、上値抵抗に阻まれて頭打ちとなる現象。中長期構造線が下から追いつくまでレンジ振動へ移行する。 |
| **階層追いつき収斂** | Catch-Up Convergence | 先行した価格や短期構造線に対し、遅行する中長期・超長期構造線群が時間をかけて下から追いつき密集（ボリンジャーバンド極限スクイズ）する動態。 |
| **超長期落差ギャップ** | Scale Vacuum Gap | 中長期構造線が上限付近まで追いついて密集した結果、その直下に位置する最深超長期親ライン（SMA 6765等）との間に生じる広大な支持線ゼロの空白地帯（15〜50 ATR）。 |
| **真空吸い込みクラッシュ** | Vacuum Plunge Crash | 密集支持帯の底割れをトリガーとし、直下の超長期落差ギャップ（支持線ゼロの真空地帯）へ価格が一気に吸い込まれ、最深親ラインまで垂直落下する現象。 |
| **多重ボリンジャーバンド・エンベロープ** | MTF BB Envelope | 期間 $k$ の移動平均線（$\text{SMA}_k$）を同期間のボリンジャーバンド中心線（$\text{BB\_Mid}_k$）と捉え、短期から超長期までの各階層のバンド上下端（$\text{BB\_Upper}_k, \text{BB\_Lower}_k$）とバンド幅（$\text{Bandwidth}_k$）を入れ子状の二次元空間として統合認識するモデル。 |
| **未収縮バンド幅レンジ拘束則** | Uncontracted Bandwidth Constraint | 上位・超長期スケール $k$ のボリンジャーバンド幅（$\text{Bandwidth}_k$）が十分に収縮しきっていない状態では、価格が持続的なブレイクアウトを果たせずバンド内部へ押し戻されてレンジ（往復振動）を継続する力学。 |
| **超長期親ライン支持転換** | Role Reversal Support | 下落局面で上値抵抗として機能していた超長期親ライン（例: `SMA 6765`）が、価格の下げ止まり・横ばい推移の過程で価格の下側へと潜り込み、以降の急落を受け止める最終下値支持線へと役割を転換する構造変化。 |
| **周期ピーク・ボトム反転同期** | Cycle Peak/Trough Synchronization | 多重ボリンジャーバンドの上下端（$\text{BB\_Upper}_k, \text{BB\_Lower}_k$）や親ラインへの空間的到達と、オシレーター群（AFS 多数決スコアや $\text{stoch\_d}$ 等）の周期的ピーク（上端過熱）またはボトム（下端売られすぎ）の折り返しが同期して反落・反発を引き起こす現象。 |

---

## 4. ボラティリティ・統計・レジーム (Volatility, Statistics & Regimes)

[volatility.md](volatility.md), [market-regime.md](market-regime.md), [expected-value.md](expected-value.md) に基づく用語。

| 用語 | 英語表記 | 定義・説明 |
|---|---|---|
| **スクイーズ / エクスパンション** | Squeeze / Expansion | 変動幅が圧縮されてエネルギーが蓄積する局面（Squeeze）と、境界を突破して急激にエネルギーが解放される局面（Expansion）の周期的サイクル。 |
| **スケール不変性** | Scale-Invariance | 価格の絶対値に依存せず、ATR等のボラティリティ単位で価格幅や距離を正規化することで、過去と現在の統計的比較を可能にする性質。 |
| **市場レジーム** | Market Regime | 方向性（Trend / Range）と変動性（High Vol / Low Vol）の2軸から構成される市場局面。 |
| **非定常性** | Non-stationarity | 時間の経過とともに市場の期待値、分散、自己相関、シグナルの有効性が変化する性質。 |
| **期待値** | Expected Value | 1回の取引あたりに期待できる数学的純利益：$E = (P_{\text{win}} \times W_{\text{avg}}) - (P_{\text{loss}} \times L_{\text{avg}})$。 |
| **摩擦コスト** | Friction Costs | 手数料、スプレッド、スリッページ、遅延からなる取引執行コスト。当システムの標準往復コストは 0.40%（SPEC-EVAL-001 §3）。 |
| **MFE / MAE** | MFE / MAE | **MFE**: エントリー後の最大順行幅（潜在利益）。**MAE**: エントリー後の最大逆行幅（潜在損失リスク）。エントリー条件自体の優位性をイグジットから独立して測る指標。 |
| **下方リスク切断** | Downside Truncation | 致命的なテールリスクをストップロスや資金管理により確実に遮断し、破産確率をゼロに抑えるリスク管理（Risk First）。 |
| **上方利益の凸性** | Upside Convexity | トレンドや拡散局面において利益を固定幅で早期に切らず、波の終焉まで追随することで、損失に対して利益を非対称に拡大させる構造。 |

---

## 5. 開発・AI協調・ガバナンス (Development & Agent Architecture)

[04_IMPLEMENTATION/agent-rules.md](../04_IMPLEMENTATION/agent-rules.md) および [00_GOVERNANCE/](../00_GOVERNANCE/) に基づく用語。

| 用語 | 英語表記 | 定義・説明 |
|---|---|---|
| **Requirements Agent** | Requirements Agent | 人間の曖昧な入力を受け取り、コードベース・仕様・知見を調査して要求を構造化し、客観判定基準付きの GitHub Issue を起票するエージェント（Antigravity等）。 |
| **Orchestrator** | Orchestrator | GitHub Issue を起点として作業ブランチ作成、タスク分解、ワーカーエージェントの呼び出しと実行ループを管制するエージェント（Orca等）。 |
| **ヒューマンゲート** | Human Gate | AIエージェントによる PR の自己承認・自己マージを厳禁とし、合意および main 反映の権限を人間オペレーターのみが保持する統制原則。 |
| **単一情報源** | SSOT (Single Source of Truth) | 同一の意味を持つ定義や数値を重複定義せず、最上位の正本文書を1箇所に確定して参照する原則。 |
| **カナリアベンチマーク** | Canary Benchmark | 既知の標準課題セット（Gold Standard）を用いて、エージェントのコード生成や計算能力を pytest 等の機械的テストで客観評価する仕組み。 |
| **決定論的ゲート** | Deterministic Gates | 自然言語の主観レビューではなく、構文（ruff/ast）、整合性（`kb.py validate`）、定量契約（`SPEC-EVAL-001`）を機械的に判定する実行時フィルター。 |
| **継続的改善フライホイール** | Continuous Flywheel | M1（ガバナンス/環境） $\rightarrow$ M2（Agent QA） $\rightarrow$ M3（特徴量検証） $\rightarrow$ M4（戦略実運用）を進めつつ、実践から得られた知見や失敗を恒久的に上位基盤へ還元する自己進化ループ。 |

---

## 6. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-12 | 0.1.0 | 初版作成（相場認識・文書階層・開発Agent体系の用語定義） | @makagi / [#25](https://github.com/makagi/MTF_AI_Trade/pull/25) |
| 2026-10-13 | 0.2.0 | 書式・メタデータ統一 | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |
| 2026-11-03 | 0.3.0 | 先行上限到達、階層追いつき収斂、超長期落差ギャップ、真空吸い込みクラッシュの用語定義を追加 | @makagi / [#97](https://github.com/makagi/MTF_AI_Trade/issues/97) |
| 2026-11-03 | 0.4.0 | 多重ボリンジャーバンド・エンベロープ、未収縮バンド幅レンジ拘束則、超長期親ライン支持転換、周期ピーク・ボトム反転同期の用語定義を追加 | @makagi / [#101](https://github.com/makagi/MTF_AI_Trade/issues/101) |
