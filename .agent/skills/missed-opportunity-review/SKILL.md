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

### ステップ 2: Stage A ブラインド提示・2段階エスカレーション判定（サブエージェント先行試行 ＆ 人間差分レビュー対応）
1. **標準提示情報（主軸階層）**:
   - エージェントは `gallery_stageA.md` および `case_01_stageA.png` 〜 `case_10_stageA.png` を用いて、判断時点 $t$ の多角的な客観情報を確認する：
     - 日時（`UTC` および `JST`、始値時刻および `t0 + 1h` の 1h足確定時刻）
     - OHLCV 数値（始値・高値・安値・終値・出来高）
     - 価格レンジ（過去 24h レンジ、過去 120h レンジ）
     - テクニカル指標（ATR 24、BB 幅/バンド位置、AFS Stoch_D 7/9/11/13 および Order Score、Macro Age Ratio）
     - 主軸 SMA（21, 34, 55, 89, 144, 233）の確定値と傾き
2. **判断に迷いがある場合の条件付き上位階層参照（2段階エスカレーション）**:
   - [00_GOVERNANCE/principles.md](../../../00_GOVERNANCE/principles.md) §3.4 および [01_CONCEPTS/mtf-framework.md](../../../01_CONCEPTS/mtf-framework.md) §4.3 に基づき、Stage A の判断は以下の2段階で実施する：
     - **Stage A1（主軸階層での1次判定）**: 標準チャートと主軸階層（例: `21〜233`）の情報のみで明確に判断できる場合は `long` または `skip` を確定し、迷い・矛盾がある場合はいったん `unsure`（保留）と記録する。
     - **Stage A2（迷いケースに対する上位階層参照）**: `unsure` となったケース（①頭上ラインを跨げるか反落するか微妙、②主軸ラインを全て上抜けて目標が見えない／過伸長が疑われる、③主軸ライン割れが押し目かトレンド崩壊か迷う）に対してのみ、**1〜2段階上の階層（上位SMA・上位時間足環境）の傾き・位置・乖離度**を確認し、最終判断（`long` / `skip`）と「どの上位情報で迷いが解消したか」を記録する。
3. **進行モード（サブエージェント先行試行 ＋ 人間による差分レビュー）**:
   - **サブエージェント先行試行**: 人間の回答を待たずに進める場合、メインエージェントは正解（`answer_key.json` / `stageB`）を一切知らない独立コンテキストのサブエージェント（`invoke_subagent`）を起動し、上記 Stage A1 $\rightarrow$ Stage A2 の2段階ブラインド判定を全10ケースに対して実行させる。
   - **人間による個別回答・差分レビュー**: レビュアー（人間）は1ケースずつ任意の順序で回答することも、サブエージェントの先行試行結果（特にエージェントが迷ったケースや Stage B 正解と食い違った難問ケース）を対象に差分所見を回答することもできる。
   - 回答受領時は `tools/missed_opportunity_review.py --update-case <ID>` で `observations.yaml` に即時保存する：
     ```bash
     uv run python tools/missed_opportunity_review.py --experiment <N> --update-case <ID> --call <long|skip|unsure> --rationale "..."
     ```
4. **厳格な制約**: Stage A の判定完了前に、対象ケースの正解ラベル（M1/C1/C2）や未来のチャート・価格推移（Stage B）を決して参照・開示してはならない。

### ステップ 3: Stage B 結末開示と所見収集
1. Stage A の回答完了後、Stage B（結末チャート、MFE 到達点、真のラベル）を開示し、予想と結末のギャップを検証する：
   ```bash
   uv run python tools/missed_opportunity_review.py --experiment <N> --update-case <ID> --reveal --comment "..."
   ```
2. 各ケースについて以下を確認・記録する：
   - 予想と結末のギャップ（なぜ伸びたのか / なぜ失速したのか）
   - 主軸階層で迷ったケースにおいて、上位階層（1〜2段上）のどの情報が有効な決定打となったか（または上位を見ても騙された場合は何が決定的に違ったか）

### ステップ 4: 記録と正答率の算出
1. `review/observations.yaml` に回答・根拠・所見・正解ラベルを逐次記録する。
2. 回答済みケースに基づき Stage A 識別能力（正答率）を算出・記録する：
   $$\text{Accuracy} = \frac{\text{True M1 identified as } long + \text{True Controls (C1/C2) identified as } skip}{\text{Total Answered Cases}}$$
3. 全件（または回答対象）のレビュー完了後、`summary.candidate_hypotheses` に次期事前登録仮説候補を整理する。

### ステップ 5: 課題化
得られた仮説候補のうち有望なものを、次期 Analysis Issue のドラフトとして提案する。

---

## 3. ブラインド・サブエージェントへの標準指示文テンプレート

サブエージェントに Stage A のブラインド先行試行を委譲する際は、後知恵バイアス（未来リーク）を物理的に防ぐため、以下の指示文テンプレートを使用する。

```markdown
あなたは Missed Opportunity Review (MOR) のブラインド・レビュアー（Stage A 判定エージェント）です。
対象ディレクトリ: `03_KNOWLEDGE/experiments/<EXP_DIR>/review/`

### 【絶対厳守ルール（カンニング・未来リークの禁止）】
1. **閲覧を許可するファイル**:
   - `gallery_stageA.md`
   - `case_01_stageA.png` 〜 `case_10_stageA.png`
   - 判断時点 $t$ 以前（`<= t`）の過去データおよび上位階層指標（迷いが生じた場合の1〜2段上のSMA/上位足情報）
2. **閲覧・参照を一切禁止するファイル・データ**:
   - `answer_key.json`、`gallery_stageB.md`、`case_01_stageB.png` 〜 `case_10_stageB.png`、`cases.json`、`observations.yaml`
   - 判断時点 $t$ より未来（`> t`）の価格・ローソク足データすべて

---

### 【あなたのタスク：2段階エスカレーションによる Stage A ブラインド判定】

Case 01 〜 Case 10 の全10ケースについて、以下の2段階プロセスでエントリー判断を行ってください。

#### Step 1: 主軸階層（Stage A チャート & `gallery_stageA.md` 記載の `SMA 21〜233`・AFS・Slope・1m足）による1次判断
各ケースの Stage A チャート画像（`case_XX_stageA.png`）と `gallery_stageA.md` の数値を観察し、以下の基準で1次判断（`call_step1`）を下してください：
- **`long`**: 主軸階層（`SMA 21〜233`）の並び・傾き・下位1m足の初動が明確に良好であり、頭上抵抗までの上値余地（または長期SMAへの回帰余地）が十分にあると判断できる場合。
- **`skip`**: 頭上の長期・中期SMAが下向きで直上に蓋をしている、ボリンジャーバンドやSMAから過度に乖離して高値掴みリスクが高い、または1m足・AFSの勢いが失速しており見送りが妥当と明確に判断できる場合。
- **`unsure`**: 主軸階層（`21〜233`）だけでは判断に迷い・矛盾がある場合。具体的には以下のいずれかに該当する場合：
  1. 頭上のSMAに向かっているが、その傾きが横ばい等で「跨ぎ抜けるか・跳ね返されるか」迷う場合
  2. 主軸の `SMA 233` までをすべて上抜けており、主軸階層内では「まだ上値目標（引力）があるのか・すでに過伸長（高値圏）なのか」判断できない場合
  3. 主軸の長期線（`SMA 233` 等）を割り込んでいるが、「さらに上位トレンドの深い押し目なのか・構造的な下落トレンドなのか」迷う場合

#### Step 2: 判断に迷いがあるケース（`unsure`）に対する上位階層（1〜2段上）の確認と最終決着
Step 1 で `unsure`（または判断が微妙なボーダーライン）となったケースについてのみ、判断時点 $t$ における **もう1〜2段階上の階層（上位SMA・上位時間足の傾き、現在価格との位置関係・ATR換算距離）** を確認し、以下の観点で迷いを解消して最終判断（`final_call`: `long` または `skip`）を下してください：
1. **頭上抵抗の突破可否の決着**: 1〜2段上の階層が上向き／下値支持していれば `long`（突破支持）、上位階層も頭上で下向きに垂れ下がり密集していれば `skip`（反落リスク大）。
2. **`SMA 233` 上抜け後の目標有無・過伸長の決着**: 1〜2段上に未突破の親ラインが控えていればそこへ近づく・跨ごうとする引力が働くため `long`（ただしその親ラインが下向きなら到達後の反落警戒を付記）、上位階層からも極端に上方乖離していれば過伸長として `skip`。
3. **`SMA 233` 割れ時の押し目／崩壊の決着**: 1〜2段上の親ラインがすぐ下で上向きにサポートしていれば `long`（上位押し目）、上位も下向きまたは頭上にあれば `skip`。

---

### 【出力フォーマット】
Case 01 〜 Case 10 のそれぞれについて、以下の項目を構造化して返答してください（ファイルの書き換えは行わず、レポートとして返答すること）：
- `case_id`: `01` 〜 `10`
- `call_step1`: 主軸階層のみでの1次判断（`long` / `skip` / `unsure`）
- `step1_rationale`: 1次判断の根拠（なぜ明確に決まったか、またはどの点に迷いが生じたか）
- `escalated`: 上位階層（1〜2段上）を参照したか（`true` / `false`）
- `higher_order_observation`: （参照した場合）1〜2段上の階層の位置・距離・傾きの観測事実と、それによって迷いがどう解消したか
- `final_call`: 最終判断（`long` / `skip`）
- `exit_caution`: （`long` の場合）頭上の上位ライン到達・跨ぎ後の反落警戒など、エグジット時に注意すべき条件
```

---

## 4. 禁止事項 (Prohibitions)

- **未来リークの禁止**: Stage A 提示・判定段階で、MFE、到達価格、ラベル名（M1/C1/C2）、シグナル発生有無を決して漏洩・参照してはならない。
- **直接知見化の禁止**: MOR で得られた直感や所見を、単独で `03_KNOWLEDGE/` に知見（K-xxx）として登録してはならない。
- **Holdout 期間の汚染禁止**: MOR で抽出するケースは必ず Discovery 期間（`< 2025-05-01`）内に限定し、Holdout 期間のチャートを提示してはならない。
