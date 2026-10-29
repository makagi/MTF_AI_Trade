# MTFシステムトレード Principles (行動原則)

**Doc ID:** GOV-PRN-001  
**Version:** 0.4.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-29  
**Related Issues:** [#7](https://github.com/makagi/MTF_AI_Trade/issues/7), [#13](https://github.com/makagi/MTF_AI_Trade/issues/13), [#57](https://github.com/makagi/MTF_AI_Trade/issues/57), [#84](https://github.com/makagi/MTF_AI_Trade/issues/84)  
**Related Docs:** [00_GOVERNANCE/vision.md](vision.md), [00_GOVERNANCE/issue-driven-workflow.md](issue-driven-workflow.md), [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md), [04_IMPLEMENTATION/agent-rules.md](../04_IMPLEMENTATION/agent-rules.md)  

---

## 1. Risk First (資金保全とリスク管理の最優先)

### 1.1 存続性を収益性に優先させる (Capital Preservation First)
どのような優れた期待値を持つ手法であっても、市場から退場してしまえば以後の利益を享受することはできない。  
システムトレードの設計・評価において、**「収益性の最大化」よりも先に「資金の存続性・破産確率の排除」を最優先**する。

### 1.2 下方リスクの厳格な切断 (Downside Truncation)
想定外の市場急変、流動性ショック、ブラック・スワン等のテールリスクに対して、損失が致命傷に至る前に物理的・論理的にリスクを遮断する。  
「いずれ戻るだろう」という希望観測に基づくポジションの放置やナンピンを排除する。

### 1.3 ドローダウン制約の順守
システムは常に過去最大ドローダウンを更新するリスクに晒されている。許容最大ドローダウン（Max Drawdown）を前提としてポジションサイズおよびリスク許容度を設計する。  
※ 具体的なリスク限度額、ストップ幅、サイジング計算式は [02_SPECIFICATIONS/](../02_SPECIFICATIONS/) で規定し、本原則では理念としての優先順位を拘束する。

---

## 2. Knowledge and Evidence (科学的厳密性と証拠連鎖)

### 2.1 事実・解釈・仮説・結論の連鎖を厳格に分離する
主観や推論が事実と混同されることを防ぐため、以下の8段階の情報連鎖を区別する。

```text
Fact (客観的事実: 価格、出来高、約定履歴、タイムスタンプ)
    ↓
Observation (観測: 計算された指標、特定時間軸のライン、距離)
    ↓
Interpretation (解釈: 相場認識としての意味づけ、買い手・売り手の流動性把握)
    ↓
Hypothesis (仮説: 検証可能・反証可能な形式への定式化、事前登録)
    ↓
Experiment (実験: 自己完結したシミュレーション・分析スクリプト)
    ↓
Evidence (証拠: 評価仕様準拠の定量データ、摩擦コスト控除後期待値、年別分解)
    ↓
Conclusion (結論: Supported / Refuted / Inconclusive の客観判定)
    ↓
Decision (意思決定: 仕様への昇格、戦略採択、または棄却)
```

検証されていない仮説（Hypothesis）や個人の相場観（Interpretation）を、確定した事実（Fact）や知識（Knowledge）として扱ってはならない。

### 2.2 根拠の追跡可能性 (Traceability)
重要な意思決定には、必ずデータバージョン、コード、評価メトリクス、起因Issueを紐付け、将来にわたって「なぜその判断を下したか」を追跡可能にする。

### 2.3 失敗と反証の知識化 (Value of Negative Results)
期待した結果が得られなかった実験や、優位性が否定（Refuted）された仮説も同等の価値を持つ知識として記録する。  
否定された結果を隠蔽せず永続化することで、将来の無駄な重複実験を防ぐ。

### 2.4 境界条件の特定と双方向差分分析 (Boundary Conditions & Differential Analysis)
特定の単一期間（例: バブル相場のみ）で成立した現象を過大評価してはならない。  
成立した場合の再現性検証にとどまらず、**非成立（失敗・騙し・期待値マイナス）となった現象についても、類似の状況において一貫して同様の結果（非成立・負のエッジ）となるかを必ず検証しなければならない**。  
偶発的な1回の失敗に過剰反応して無効化条件をでっち上げる過学習を排除し、類似状況において「成立した局面」と「非成立だった局面」の客観的差分（*What made the difference?*）を定量的に特定する。  
どのような環境でエッジが消失・無効化するかの**境界条件（Boundary Conditions / Invalidation Criteria）**および構造的トラップを特定して初めて、再現可能な知識として承認される。

---

## 3. MTF Analysis (多時間軸の階層認識)

### 3.1 時間軸の明示
市場分析においては、常に観測対象の時間軸（Weekly / Daily / 4H / 1H / 15m / 1m 等）を明示する。時間軸を伴わない「上昇トレンド」「サポレジ」の記述を禁止する。

### 3.2 階層間の相互作用とマクロ重力
各時間軸は孤立して存在しない。上位時間軸（長期）の構造は下位時間軸（短期）に対して圧倒的な影響力（マクロ重力）を持つ。下位足のシグナルが上位足の抵抗帯に衝突するリスクを常に評価する。

### 3.3 動的構造としての認識
サポレジやトレンドラインは静的な幾何学線ではなく、市場参加者の流動性とテスト回数・経過時間によって強度が変化する動的構造として扱う。

### 3.4 判断に迷いがある場合の条件付き上位階層参照と利益余地の対称評価 (Hierarchical Escalation & Profit-Room Symmetry)
特定の長期パラメータ（特定の移動平均期間や特定の時間足）をすべての局面に一律のハードフィルタとして強制してはならない。また、「上位が下向きだから」「直前に大陽線が出たから」といった表層的な減点法（リスク回避偏重）だけで好機を即座に切り捨ててはならない。  
現在観測している主軸階層（スケール $k$）だけで方向性・**利益を取れる余地（Profit Room / 空白地帯）**・リスク境界が明確に判断できる場合はその階層で意思決定を完結させ、**主軸階層において判断に迷いや矛盾が生じる場合（例: 頭上抵抗を跨げるか反落するか微妙な局面、上位抵抗までの空白地帯を狙う回帰初動、主軸ラインをすべて抜けて上値目標が見えない／過伸長か迷う局面、主軸ライン割れが押し目かトレンド崩壊か判別しづらい局面）にのみ、1〜2段階上の階層（$k+1, k+2$）を参照して決着をつける**というスケール不変（Scale-Invariant）の条件付きエスカレーション原則を採用する。

---

## 4. Separation of Concerns (関心の分離)

### 4.1 Concept と Specification の分離
* **Concept (普遍概念)**: どう市場を理解・モデル化するか（`01_CONCEPTS/`）。
* **Specification (具体的仕様)**: このシステムでどう計算・判定するか（`02_SPECIFICATIONS/`）。  
Concept を変更せずに Specification をチューニング・差し替え可能な構造を維持する。

### 4.2 Strategy と Implementation の分離
* **Strategy (売買戦略)**: 個別の仕様部品（Entry / Exit / Risk）を有機的に組み合わせた売買ルール一式（`02_SPECIFICATIONS/strategies/`）。
* **Implementation (実装基盤)**: 戦略を実行・検証するコード、データ基盤、AI Agent 群。

```text
Concept (相場認識・モデル)
    ↓
Specification (判定・評価の個別仕様: 部品)
    ↓
Strategy (売買ルール一式: 部品の組み合わせ)
    ↓
Implementation (実行コード・アーキテクチャ)
```

### 4.3 Research と Production の分離
研究・探索用コードと、実運用・本番用コードを明確に分離し、研究の都合で本番システムの安定性を損なわない。

---

## 5. Reproducibility (再現性の担保)

重要な分析・実験・バックテストについて、以下の環境と条件を完全に記録・固定する。
* データセットハッシュおよび期間（Discovery / Validation）
* ソースコード・コミットハッシュ
* パラメータおよびシード値
* 実行コマンド（`uv run ...`）

「同一の条件を与えれば、いかなる第三者や別エージェントであっても同一の結果を再現できる」状態を必須要件とする。

---

## 6. Change Management (変更の系譜と不可逆性)

### 6.1 変更理由とエビデンスの記録
仕様やコードを変更する際は、「何を変更したか」だけでなく「なぜ変更したか」「どの実験結果を根拠にしたか」を記録する。

### 6.2 過去の判断を抹消しない
過去の意思決定やアーキテクチャ選択は上書き削除せず、[99_HISTORY/decision-log.md](../99_HISTORY/decision-log.md)（ADR）に履歴として永続化する。

---

## 7. AI Collaboration & Human Gate (エージェント協調と人間の最終責任)

### 7.1 役割分担と権限境界の厳守
AIエージェント群は単一の万能知能として扱わず、明確な役割と権限境界を定めて協調させる。  
具体的なエージェント構成（Requirements Agent / Orchestrator / Multi-agents）および権限マトリクスの単一情報源（SSOT）は **[04_IMPLEMENTATION/agent-rules.md](../04_IMPLEMENTATION/agent-rules.md)** とする。

### 7.2 Human Gate (自己承認・自己マージの禁止)
いかなる AI エージェントも自律的に PR をマージしてはならない。仕様合意・本番反映の最終責任および承認権限は、常に人間オペレーターのみが保持する。

### 7.3 推論と客観的事実の区別
AIエージェントが出力した「もっともらしい考察」を、定量検証を経た事実と混同してはならない。

---

## 8. Simplicity (単純性の原則)

最初から過剰に複雑な仕組みを構築しない。  
まず最小限の構造（MVP）から開始し、運用や実験で明確に必要性が確認されたものから詳細化する。  
**「将来必要になるかもしれない」という予測のみで仕様や抽象化レイヤーを増やしてはならない。**

---

## 9. Single Source of Truth (単一情報源の原則)

同じ意味の情報や数値を複数箇所に重複して定義しない。  
摩擦コスト（0.40%）や期間分割などの共通パラメータは [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md) を唯一の正本とし、他文書やコードからは必ずこれを参照する。

---

## 10. Continuous Improvement & Evolutionary Flywheel (継続的改善フライホイール)

完成を最終目的とせず、継続的な測定と進化を前提とする。

```text
【Milestone 1: ガバナンス・文書基盤】
       │ 提供 (ルール・評価仕様)
       ▼
【Milestone 2: Agent QA・管制基盤】
       │ 提供 (客観テスト・安定実行)
       ▼
【Milestone 3: 特徴量・仮説の自律検証】
       │ 蓄積 (K-xxx 知識群)
       ▼
【Milestone 4: 戦略ポートフォリオ・実運用】
```

### 10.1 特徴量知識の高まりによる戦略昇格
いきなり完成された「必勝戦略」を作ろうとせず、まずは各特徴量（SR、ATR、ボラティリティ等）の市場レジームごとの振る舞いやエッジの有無を `K-xxx` として地道に検証・蓄積する。  
特徴量に対する統計的・定量的理解が十分に深まった段階で初めて、それらを有機的に結合した戦略（M4）へと昇格させる。

### 10.2 実践からの自己フィードバック (Flywheel)
1. **M3 $\rightarrow$ M2 (エージェント基盤の進化)**:
   - 検証実験中に下位エージェントが起こした失敗や例外は、即座に「Canary Benchmark（事前テスト）」へ追加され、モデル選定・自動乗り換えの評価精度を高める。
2. **M3 $\rightarrow$ M1 (ガバナンス・評価仕様の洗練)**:
   - 実験の過程で生じたルールの曖昧さや例外ケースは、Issue 駆動で上位ルールへとフィードバックされる。
3. **M4 $\rightarrow$ 全体 (実運用からの継続進化)**:
   - 実運用段階においても、スリッページや市場構造変化のモニタリングを通じて、評価仕様や戦略、エージェント基盤へのフィードバックを恒久的に継続する。

---

## 11. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-09 | 0.1.0 | 初版作成（基本設計原則） | @makagi / [#16](https://github.com/makagi/MTF_AI_Trade/pull/16) |
| 2026-10-12 | 0.2.0 | Risk First 原則、8段階証拠連鎖、継続的改善フライホイール確立 | @makagi / [#23](https://github.com/makagi/MTF_AI_Trade/pull/23) |
| 2026-10-13 | 0.2.0 | 書式・メタデータ統一 | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |
| 2026-10-19 | 0.3.0 | 境界条件の特定と双方向差分分析（成立・非成立の類似状況再現性）の原則（2.4）を追加 | @makagi / [#57](https://github.com/makagi/MTF_AI_Trade/pull/57) |
| 2026-10-29 | 0.4.0 | 判断に迷いがある場合の条件付き上位階層参照（Hierarchical Escalation on Ambiguity）の原則（3.4）を追加 | @makagi / [#84](https://github.com/makagi/MTF_AI_Trade/issues/84) |
