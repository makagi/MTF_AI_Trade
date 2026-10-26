---
name: missed-opportunity-review
description: >-
  Conduct Missed Opportunity Review (MOR) upon completing an Analysis experiment.
  Extracts missed 4+ ATR moves (M1) and matching control cases (C1/C2), presents blind
  Stage A charts to human reviewer, records calls and rationales, reveals Stage B outcomes,
  and formulates pre-registration candidate hypotheses for follow-up issues.
---

# Missed Opportunity Review (MOR) Skill

本スキルは、Analysis 実験完了時に「シグナルが出なかったのに大きく動いた場面（見逃しエントリー：M1）」と「似ているのに伸びなかった対照群（C1/C2）」をブラインドで提示し、人間の視点・所見を安全に仮説生成へと繋げる Human-in-the-Loop レビュー手順を規定します。

---

## 1. 目的と基本原則

1. **数値探索の限界突破**:
   - バックテスト数値だけの過剰適合を避け、人間がチャートから感知する直感・文脈（サポレジ、移動平均線の収束/拡散、出来高推移など）を抽出する。
2. **後知恵バイアスの完全排除（2段階ブラインド提示）**:
   - **Stage A（判断時点）**: 判断時点 $t$ 以前のデータのみを描画。未来の値動きを完全に遮断した状態でレビュアーの判断（`long` / `skip` / `unsure`）と根拠を記録する。
   - **Stage B（結末開示）**: Stage A の回答完了後に結末（72hの値動き、MFE、真の分類）を開示し、所見を収集する。
3. **対照群（Controls）の混在**:
   - 伸びた場面（M1）だけでなく、特徴量が酷似しているのに伸びなかった場面（C1）やシグナル発生後の負けトレード（C2）をシャッフルして提示し、無根拠なポジティブバイアスを抑制する。
4. **知見登録の厳格な分離（仮説生成 $\neq$ 知見確定）**:
   - レビュアーの所見は「仮説候補（Candidate Hypotheses）」であり、直接 `K-xxx`（知見）に登録してはならない。必ず新しい Analysis Issue を起票し、事前登録 $\rightarrow$ 検証を経て検証する。

---

## 2. 標準ワークフロー

```mermaid
flowchart TD
    A["Analysis 実験完了 (metrics.json / record.md)"] --> B["MOR ツール実行 (tools/missed_opportunity_review.py)"]
    B --> C["Stage A 提示 (Blind: 10ケース)"]
    C --> D["ユーザー判断回収 (long / skip / unsure + 根拠)"]
    D --> E["Stage B 開示 (Outcome + answer_key)"]
    E --> F["所見収集 & observations.yaml 記録"]
    F --> G["正答率算出 & 次期仮説の整理"]
    G --> H["PR に review/ を含めて提出"]
```

### ステップ 1: レビュースイートの自動生成
Analysis 実験の集計完了後、以下を実行して `review/` 配下にファイルを生成する。
```bash
uv run python tools/missed_opportunity_review.py --experiment <N> --signal <signal_id> --seed 42
```
生成物:
- `review/case_01_stageA.png` 〜 `case_10_stageA.png` (判断時点)
- `review/case_01_stageB.png` 〜 `case_10_stageB.png` (結末)
- `review/gallery_stageA.md` (ブラインド質問票)
- `review/gallery_stageB.md` (結末ギャラリー)
- `review/answer_key.json` (正解ラベル: 非公開)
- `review/cases.json` (特徴量スナップショット)
- `review/observations.yaml` (回答記録テンプレート)

### ステップ 2: Stage A ブラインド提示と回答収集（一括・個別の両対応）
1. エージェントはユーザーに `gallery_stageA.md` の閲覧を案内するか、チャット上に Case 01 〜 10 の判断時点チャートおよび詳細指標を提示する。
   - **外部ツール照合の支援**: レビュアーが TradingView 等の外部ツールで詳細を検証しやすいよう、各ケースには以下の多角的な客観情報を明記する：
     - 日時（`UTC` および `JST`、1h足確定時刻）
     - OHLCV 数値（始値・高値・安値・終値・出来高）
     - 価格レンジ（過去 24h レンジ、過去 120h レンジ）
     - テクニカル指標（ATR 24、BB 幅/バンド位置、AFS Compression / Order Score）
     - 主要 SMA（21, 34, 55, 89, 144, 233）の確定値
2. **個別回答（1ケースずつ）の進行**:
   - レビュアーは全10ケースを一度に回答する必要はなく、**1ケースずつ任意の順序で回答を進めることができる**。
   - ユーザーから回答（`long` / `skip` / `unsure`）と根拠を受領した時点で、エージェントは直ちに `observations.yaml` にそのケースを保存する：
     ```bash
     uv run python tools/missed_opportunity_review.py --experiment <N> --update-case <ID> --call <long|skip|unsure> --rationale "..."
     ```
3. **厳格な制約**: 対象ケースの回答完了前に、そのケースの正解ラベル（M1/C1/C2）や未来のチャート・価格推移を開示・示唆してはならない。

### ステップ 3: Stage B 結末開示と所見収集
1. ケースごとの回答受領後、レビュアーの希望に応じて即座にそのケースの Stage B（結末チャート、MFE 到達点、真のラベル）を開示するか、あるいは複数ケース回答後にまとめて開示する：
   ```bash
   uv run python tools/missed_opportunity_review.py --experiment <N> --update-case <ID> --reveal --comment "..."
   ```
2. 各ケースについて以下を確認・記録する：
   - 予想と結末のギャップ（なぜ伸びたのか / なぜ失速したのか）
   - M1 と C1 を見分ける手がかりとなりそうな視点

### ステップ 4: 記録と正答率の算出
1. `review/observations.yaml` に回答・根拠・所見・正解ラベルを逐次記録する。
2. 回答済みケースに基づき Stage A 識別能力（正答率）を算出・記録する：
   $$\text{Accuracy} = \frac{\text{True M1 identified as } long + \text{True Controls (C1/C2) identified as } skip}{\text{Total Answered Cases}}$$
3. 未回答のケース数と進捗（例: `3/10 完了`）を提示し、いつでも中断・再開できるようにする。
4. 全件（または回答対象）のレビュー完了後、`summary.candidate_hypotheses` に次期事前登録仮説候補を整理する。

### ステップ 5: 課題化
得られた仮説候補のうち有望なものを、次期 Analysis Issue のドラフトとして提案する。

---

## 3. 禁止事項 (Prohibitions)

- **未来リークの禁止**: Stage A 提示段階で、MFE、到達価格、ラベル名（M1/C1/C2）、シグナル発生有無を決して漏洩してはならない。
- **直接知見化の禁止**: MOR で得られたユーザーの直感や所見を、単独で `03_KNOWLEDGE/` に知見（K-xxx）として登録してはならない。
- **Holdout 期間の汚染禁止**: MOR で抽出するケースは必ず Discovery 期間（`< 2025-05-01`）内に限定し、Holdout 期間のチャートを提示してはならない。
