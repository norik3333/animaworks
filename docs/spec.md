# Digital Anima 要件定義書 v1.0

## 1. 概要

Digital Animaは、AIエージェントを「1人の人間」としてカプセル化する最小単位。

**核心の設計原則:**

- 内部状態は外部から不可視。外部との接点はテキスト会話のみ
- 記憶は「書庫型」。必要な時に必要な記憶だけを自分で検索して取り出す
- 全コンテキストは共有しない。自分の言葉で圧縮・解釈して伝える
- ハートビートにより指示待ちではなくプロアクティブに行動する
- 役割・理念は後から注入する。Digital Anima自体は「空の器」

**技術方針:**

- エージェント実行は **3モード** で動作する: **A1** (Claude Agent SDK), **A2** (LiteLLM + tool_use), **B** (1ショット補助)
- 設定は統合 **config.json**（Pydanticバリデーション）、記憶は **Markdown** で記述する
- 複数Animaが **階層構造** で協調動作する（commander → worker 同期委任）

-----

## 2. アーキテクチャ

```
┌──────────────────────────────────────────────────────┐
│                   Digital Anima                      │
│                                                       │
│  Identity ──── 自分が誰か（常駐）                      │
│  Agent Core ── 3実行モード                             │
│    ├ A1: Claude Agent SDK（Claude専用・自律行動）       │
│    ├ A2: LiteLLM + tool_use（GPT-4o, Gemini等・自律） │
│    └ B:  1ショット補助（Ollama等・FW代行）             │
│  Memory ───── 書庫型長期記憶（自律検索で想起）          │
│    ├ 会話記憶（ローリング圧縮）                        │
│    └ 短期記憶（セッション継続）                        │
│  Permissions ─ ツール/ファイル/コマンド制限             │
│  Communication ─ テキスト＋ファイル参照                 │
│  Lifecycle ── メッセージ受信/ハートビート/cron          │
│  Injection ── 役割/理念/行動規範（後から注入）          │
│                                                       │
└──────────────────────────────────────────────────────┘
        ▲                       │
   テキスト(受信)          テキスト(送信)
```

-----

## 3. ファイル構成

```
animaworks/
├── core/
│   ├── anima.py              # DigitalAnimaクラス
│   ├── agent.py               # AgentCore（実行モード選択・サイクル管理）
│   ├── memory.py              # 書庫型記憶の検索・書き込み
│   ├── conversation_memory.py # 会話記憶（ローリング圧縮）
│   ├── shortterm_memory.py    # 短期記憶（セッション継続）
│   ├── messenger.py           # Anima間メッセージ送受信
│   ├── lifecycle.py           # ハートビート・cron管理（APScheduler）
│   ├── config.py              # 統合設定（Pydantic）
│   ├── prompt_builder.py      # システムプロンプト構築（14セクション）
│   ├── tool_handler.py        # ツール実行ディスパッチ・権限チェック
│   ├── tool_schemas.py        # プロバイダ中立ツールスキーマ
│   ├── external_tools.py      # 外部ツール連携
│   ├── context_tracker.py     # コンテキスト使用量監視
│   ├── anima_factory.py      # Anima生成（テンプレート/空白/MD）
│   ├── init.py                # ランタイム初期化
│   ├── schemas.py             # データモデル（Message, CycleResult等）
│   ├── paths.py               # パス解決
│   ├── execution/             # 実行エンジン
│   │   ├── base.py            #   BaseExecutor ABC
│   │   ├── agent_sdk.py       #   Mode A1: Claude Agent SDK
│   │   ├── litellm_loop.py    #   Mode A2: LiteLLM + tool_use
│   │   ├── assisted.py        #   Mode B: フレームワーク補助
│   │   └── anthropic_fallback.py # Anthropic SDK直接
│   └── tools/                 # 外部ツール実装
│       ├── web_search.py, x_search.py, slack.py
│       ├── chatwork.py, gmail.py, github.py
│       ├── transcribe.py, aws_collector.py
│       └── local_llm.py
├── server/
│   ├── app.py                 # FastAPIアプリケーション
│   ├── routes.py              # RESTエンドポイント + WebSocket
│   ├── websocket.py           # WebSocket管理
│   └── static/                # Web UI
│       ├── index.html         # シンプルビューアー
│       └── workspace/         # インタラクティブWorkspace
├── templates/
│   ├── prompts/               # プロンプトテンプレート
│   ├── anima_templates/      # Anima雛形（_blank）
│   └── company/               # 組織ビジョンテンプレート
├── main.py                    # CLIエントリポイント
└── tests/                     # テストスイート
```

### 3.1 config.json（統合設定）

全設定を `~/.animaworks/config.json` に統合。Pydantic `AnimaWorksConfig` モデルでバリデーションし、person単位のオーバーライドをサポートする。

**トップレベル構造:**

|セクション         |説明                              |
|----------------|--------------------------------|
|`system`        |動作モード、ログレベル                   |
|`credentials`   |プロバイダ別APIキー・エンドポイント（名前付きマップ）   |
|`anima_defaults`|全Animaに適用されるデフォルト値             |
|`animas`       |Anima単位のオーバーライド（未指定フィールドはdefaults適用）|

**AnimaModelConfig フィールド:**

|フィールド                           |型              |デフォルト                   |説明                        |
|---------------------------------|---------------|------------------------|--------------------------|
|`model`                          |`str`          |`claude-sonnet-4-20250514`|使用するモデル名（bare name、プロバイダprefixなし）|
|`fallback_model`                 |`str \| null`  |`null`                  |フォールバックモデル                  |
|`max_tokens`                     |`int`          |`4096`                  |1回のレスポンスの最大トークン数             |
|`max_turns`                      |`int`          |`20`                    |1サイクルの最大ターン数                |
|`credential`                     |`str`          |`"anthropic"`           |使用するcredentials名             |
|`context_threshold`              |`float`        |`0.50`                  |短期記憶外部化の閾値（コンテキスト使用率）       |
|`max_chains`                     |`int`          |`2`                     |自動セッション継続の最大回数              |
|`conversation_history_threshold` |`float`        |`0.30`                  |会話記憶の圧縮トリガー（コンテキスト使用率）      |
|`execution_mode`                 |`str \| null`  |`null`（自動検出）             |`"autonomous"` or `"assisted"`|
|`role`                           |`str \| null`  |`null`                  |`"commander"` or `"worker"`   |
|`supervisor`                     |`str \| null`  |`null`                  |上位Animaの名前                  |
|`speciality`                     |`str \| null`  |`null`                  |自由記述の専門分野                   |

**config.json 例:**

```json
{
  "version": 1,
  "system": { "mode": "server", "log_level": "INFO" },
  "credentials": {
    "anthropic": { "api_key": "", "base_url": null },
    "ollama": { "api_key": "dummy", "base_url": "http://localhost:11434/v1" }
  },
  "anima_defaults": {
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 4096,
    "max_turns": 20,
    "credential": "anthropic",
    "context_threshold": 0.50,
    "conversation_history_threshold": 0.30
  },
  "animas": {
    "alice": { "role": "commander" },
    "bob": { "model": "gpt-4o", "credential": "openai", "role": "worker", "supervisor": "alice" }
  }
}
```

**セキュリティ:** config.jsonのパーミッションは `0o600`（owner read/write only）で保存される。APIキーは環境変数での管理も引き続きサポート。

-----

## 4. 記憶システム（書庫型）

### 4.1 設計理念

従来のAIエージェントは記憶を機械的に切り詰めてプロンプトに詰め込む（切り詰め型）。これは「直近の記憶しかない前向性健忘」に等しい。

書庫型は異なる。人間が書庫から必要な資料を引き出すように、Digital Animaは **必要な時に必要な記憶だけを自分で検索して取り出す。** 記憶の量に上限はない。コンテキストに入るのは「今必要なもの」だけ。

### 4.2 脳科学モデルとの対応

```
┌─────────────────────────────────────────────────┐
│  ワーキングメモリ（前頭前皮質）                    │
│  = コンテキストウィンドウ                          │
│  容量制限あり。「今考えていること」の一時保持       │
│  → SDKに委譲。追加実装は不要                       │
└──────────────────┬──────────────────────────────┘
                    │ 想起（検索）/ 記銘（書き込み）
┌──────────────────┴──────────────────────────────┐
│  長期記憶（大脳皮質・海馬系）                      │
│                                                    │
│  episodes/   エピソード記憶 — いつ何があったか     │
│  knowledge/  意味記憶 — 学んだ教訓・知識           │
│  procedures/ 手続き記憶 — 作業の手順書             │
└────────────────────────────────────────────────┘
```

### 4.3 記憶ディレクトリの役割

|ディレクトリ                   |脳の対応              |内容              |更新方法                 |
|--------------------------|-------------------|----------------|---------------------|
|`state/`                  |ワーキングメモリの永続部分    |今の状態・未完了タスク      |毎サイクル上書き             |
|`state/conversation.json` |会話記憶              |ローリング会話履歴        |閾値超過時にLLM要約で圧縮      |
|`shortterm/`              |短期記憶（セッション継続）    |コンテキスト引き継ぎ       |セッション切替時に自動外部化     |
|`episodes/`               |エピソード記憶（海馬）      |日別の行動ログ          |日付ファイルに追記           |
|`knowledge/`              |意味記憶（側頭葉皮質）      |教訓・ルール・相手の特性     |トピック別に作成・更新        |
|`procedures/`             |手続き記憶（基底核）       |作業手順書            |必要に応じて改訂           |

### 4.4 記憶操作

**想起（思い出す）** — 判断の前に必ず書庫を検索する。

1. `knowledge/` をキーワード検索（相手名、トピック等）
1. 必要に応じて `episodes/` も検索（過去に何があったか）
1. 手順が不明なら `procedures/` を確認
1. 関連する記憶を読み込んでから判断する

**記銘（書き込む）** — 行動の後に記憶を更新する。

1. `episodes/YYYY-MM-DD.md` に行動ログを追記
1. 新しく学んだことがあれば `knowledge/` に書き込み
1. 重要な教訓は `[IMPORTANT]` タグを付けて保護
1. `state/current_task.md` を更新

**統合（振り返り）** — エピソード記憶から意味記憶への転送。脳科学でいう睡眠中の記憶固定化に相当する。

- `episodes/` のログからパターンを抽出し `knowledge/` に一般化して書き出す
- ハートビートまたはcronで定期実行する

### 4.5 エピソード記憶のフォーマット

```markdown
# 2026-02-12 行動ログ

## 09:15 Chatwork未返信チェック
- トリガー: ハートビート
- 判断: 2件の未返信を発見。社内は自分で対応、社外はエスカレーション
- 結果: 返信案を作成し承認を取得
- 教訓: なし

## 14:30 田中さんへの返信
- トリガー: メッセージ受信
- 判断: 過去にカジュアル文面でリジェクトされた記憶あり → フォーマルで作成
- 結果: 承認済み
- 教訓: 建設業界への対応方針が正しいことを再確認
```

### 4.6 知識のフォーマット

```markdown
# 対応方針

## コミュニケーションルール
- [IMPORTANT] 必ずフォーマルなビジネス文面で対応すること
- カジュアルな文面はNG（2026-02-11にリジェクトされた）
- 建設業界はフォーマルなコミュニケーションを重視する

## 連絡先
- 主な担当者: 田中さん
```

### 4.7 実験による検証結果

書庫型記憶は手動テスト（2026-02-12実施）で全5項目S判定を取得済み。

- **想起**: プロンプトに含まれていない過去の記憶を自発的に検索して活用できた
- **記銘**: 行動ログ・教訓・新規知識を適切にファイルに書き込めた
- **Reflexion**: リジェクト（失敗）から教訓を抽出し、次回の判断を変えられた
- **統合**: 個別エピソードからメタパターンを抽出し知識として一般化できた
- **復元**: コンテキストクリア後も `state/` と `episodes/` から状態を復元できた

成功の鍵は「記憶を検索せずに判断するのは禁止」というシステムプロンプトの強い指示。

### 4.8 会話記憶（ConversationMemory）

ローリングチャット履歴。蓄積量が `conversation_history_threshold`（デフォルト30%）を超えると、古いターンをLLM要約で圧縮し、直近ターンは原文保持。`state/conversation.json` に保存。

### 4.9 短期記憶（ShortTermMemory）

セッション継続のための外部化記憶。A2モードでコンテキスト閾値を超えた際、`session_state.json`（機械用）と `session_state.md`（次回プロンプト注入用）を生成。`shortterm/archive/` に自動退避（最大100件）。

-----

## 5. Identity（自己定義）

Digital Animaが「自分は何者か」を認識する情報。ワーキングメモリに常駐する。

```markdown
# Identity: Tanaka

## 性格特性
- 慎重で、リスクを先に考える
- 詳細志向で、曖昧さを嫌う

## 視点
技術的実現可能性を重視する。「それは本当に動くのか」が常に判断の起点。

## 得意なこと
- バックエンド設計、パフォーマンス最適化

## 苦手なこと
- UI/UXデザインの判断、ユーザーの感情的ニーズの把握
```

-----

## 6. Permissions（権限）

Digital Animaが「何ができるか」の制限。権限の制限は「視野の狭さ」を生み、他者への依存 = 組織の価値を生む。

```markdown
# Permissions: Tanaka

## 使えるツール
Read, Write, Edit, Bash, Grep, Glob

## 使えないツール
WebSearch, WebFetch

## 読める場所
- /project/src/backend/ 配下
- /project/docs/ 配下
- /shared/reports/ 配下

## 書ける場所
- /project/src/backend/ 配下
- /workspace/Tanaka/ 配下

## 見えない場所
- /project/.env
- /project/src/frontend/ 配下（Suzukiの管轄）

## 実行できるコマンド
npm test, npm run build, git diff, git log

## 実行できないコマンド
git push（承認必要）, rm -rf, docker
```

フロントのコードが読めないから「フロント側の制約を教えて」と同僚に聞く必要がある。この「知らないから聞く」が組織の水平コミュニケーション。

-----

## 7. Communication（通信）

### 原則

- テキスト＋ファイル参照のみ。内部状態の直接共有は禁止
- 自分の言葉で圧縮・解釈して伝える。全コンテキストは送らない
- 長い内容はファイルとして置き「ここに置いたから見て」と伝える

### メッセージ構造

```json
{
  "id": "20260213_100000_abc",
  "thread_id": "",
  "reply_to": "",
  "from_person": "Tanaka",
  "to_person": "Suzuki",
  "type": "message",
  "content": "認証APIの設計を見直した。auth-api-design.md に置いたので確認してほしい。",
  "attachments": [],
  "timestamp": "2026-02-13T10:00:00Z"
}
```

### メッセージタイプ

現在の実装では `type` フィールドのデフォルトは `"message"` の単一型。以下のタイプ分類は将来拡張として設計に残す。

|type（将来拡張） |説明        |
|------------|----------|
|request     |上位からの依頼・指示|
|report      |上位への報告    |
|consultation|同僚への相談    |
|broadcast   |全体通知      |

Suzukiは設計書だけを見る。Tanakaの思考過程や破棄した案は見えない。この情報の非対称性が、異なるバックグラウンドからの新しい視点を可能にする。

-----

## 8. Lifecycle（生命サイクル）

### 8.1 起動トリガー

Digital Animaは自分の内部時計を持つ。3つのトリガーはすべて「個」に属する。

|トリガー   |内容                     |
|-------|-----------------------|
|メッセージ受信|他者からメッセージが届いたら起動       |
|ハートビート |定期的に状況を確認。何もなければ何もしない  |
|cron   |自分の時計で、決まった時間に決まったことを実行|

### 8.2 ハートビート

一定間隔で「顔を上げて周囲を見渡す」行為。メインのコンテキストを保持したまま実行し、何もなければ何もしない。

```markdown
# Heartbeat: Tanaka

## 実行間隔
30分ごと

## 活動時間
9:00 - 22:00（JST）

## チェックリスト
- Inboxに未読メッセージがあるか
- 進行中タスクにブロッカーが発生していないか
- 自分の作業領域に新しいファイルが置かれていないか
- 何もなければ何もしない（HEARTBEAT_OK）

## 通知ルール
- 緊急と判断した場合のみ関係者に通知
- 同じ内容の通知は24時間以内に繰り返さない
```

### 8.3 cron

自分の時計で決まった時間に決まったことを行う。ハートビートと違い、必ず何かを実行して結果を出す。

cronは外部のスケジューラーや組織構造に依存しない。**各Digital Animaが自分のcronを持つ。** 人間が自分の習慣として毎朝日記を書くのと同じ。

```markdown
# Cron: Tanaka

## 毎朝の業務計画（毎日 9:00 JST）
長期記憶から昨日の進捗を確認し、今日のタスクを計画する。
理念と目標に照らして優先順位を判断する。
結果は /workspace/Tanaka/daily-plan.md に書き出す。

## 週次振り返り（毎週金曜 17:00 JST）
今週のepisodes/を読み返し、パターンを抽出してknowledge/に統合する。
（記憶の統合 = 脳科学でいう睡眠中の記憶固定化）
```

**ハートビートとcronの違い:**

|項目    |ハートビート        |cron          |
|------|--------------|--------------|
|人間での例 |仕事中に時々メールを確認  |毎朝の日課、週次の振り返り |
|コンテキスト|保持する          |保持しない（新規セッション）|
|判断    |「気にすべきことがあるか？」|盲目的に実行する      |
|何もない時 |何もしない         |必ず何かを出力する     |
|所属    |個人の内部         |個人の内部         |

### 8.4 1サイクルの流れ

```
起動（メッセージ or ハートビート or cron）
  ↓
想起: 関連する記憶を書庫から検索
  ↓
思考・行動: Agent Core（A1/A2/Bモード）が処理
  ↓
通信: 結果を要約してテキスト送信 or ファイル作成
  ↓
記銘: 行動ログ・教訓・知識を書き込み
  ↓
状態更新: state/ を更新
  ↓
休止
```

-----

## 9. Injectable Slot（後から注入）

Digital Animaは「空の器」。役割・理念はMarkdownで注入する。

```markdown
# Injection: Tanaka

## 役割
テックリード。技術的意思決定とコードレビューを担当。
担当範囲はバックエンドアーキテクチャ。

## 理念
高品質なソフトウェアを通じてユーザーの課題を解決する。

## 行動規範
- 品質は妥協しない
- シンプルさを追求する
- 迷ったときは「ユーザーにとって何が最善か」に立ち返る

## やらないこと
- 本番DBへの直接アクセス
- フロントエンドの実装（Suzukiに任せる）
- 承認なしのmainブランチへのpush
```

-----

## 10. システムプロンプトの構築

各Markdown・テンプレートを結合して1つのシステムプロンプトを構築する。`prompt_builder.py` が14セクションを順に組み立てる。

```
システムプロンプト =
  environment（ガードレール・フォルダ構造）
  + bootstrap（初回起動指示 — 該当時のみ）
  + company/vision.md（組織ビジョン）
  + identity.md（あなたは誰か）
  + injection.md（役割・理念）
  + permissions.md（何ができるか）
  + state/current_task.md（今の状態）
  + state/pending.md（未完了タスク）
  + memory_guide（記憶ディレクトリガイド + ファイル一覧）
  + skills_guide（個人スキル）
  + common_skills（共通スキル）
  + tools_guide（外部ツール — 許可時のみ）
  + behavior_rules（検索してから判断せよ）
  + messaging（メッセージ送受信 + 同僚Anima一覧）
```

各セクションは `---` で区切られ、条件付きセクション（bootstrap, tools_guide等）は該当時のみ注入される。

「記憶を検索せずに判断するのは禁止」を `behavior_rules` に含めることが書庫型記憶の成功の鍵（実験で検証済み）。

-----

## 11. 実装済み機能

- **Digital Animaクラス** — カプセル化・自律動作。1 Anima = 1ディレクトリ
- **3実行モード** — A1: Claude Agent SDK / A2: LiteLLM + tool_use / B: Assisted（1ショット補助）
- **書庫型記憶** — episodes（日別ログ）/ knowledge（教訓・知識）/ procedures（手順書）/ state（作業記憶）
- **会話記憶** — ローリング圧縮。閾値超過時にLLM要約で古いターンを圧縮
- **短期記憶** — セッション継続。コンテキスト閾値超過時にJSON+MDで外部化
- **ハートビート・cron** — APSchedulerによるスケジュール管理。日本語スケジュール記法対応
- **Anima間メッセージ** — Messenger経由のテキスト通信。階層委任（commander → worker 同期委任）
- **統合設定** — config.json + Pydanticバリデーション。person単位のオーバーライド
- **FastAPIサーバー** — REST + WebSocket + Web UI（3Dオフィス・会話画面）
- **外部ツール9種** — web_search, slack, chatwork, gmail, github, x_search, transcribe, aws_collector, local_llm
- **Anima生成** — テンプレート / 空白（_blank）/ MDファイルからの生成
- **スキルシステム** — 個人スキル + 共通スキル（Markdownベースのプロシージャ）

-----

## 12. 設計判断の記録

|判断                             |理由                                                         |
|-------------------------------|-----------------------------------------------------------|
|記憶はJSON → Markdownファイル         |実験でMarkdownの方がAIが自然に読み書きでき、Grep検索との相性が良いと判明                |
|記憶の忘却はスコアベース → [IMPORTANT]タグ＋統合|シンプルなタグ方式の方が実用的。統合（consolidation）で自然に重要度が整理される             |
|config.md → config.json          |per-anima MDから統合JSONへ。Pydanticバリデーション + per-anima overrides|
|エージェントループは自作しない                |Claude Agent SDKに委譲。車輪の再発明はしない                             |
|実行モード3分岐                       |Claude SDK最優先、LiteLLM汎用、Assisted弱モデル対応。全てAnimaカプセル内      |
|agent.pyリファクタリング                |1848行→465行。execution/, tool_handler, tool_schemas に分離         |
|権限は「視野の制限」                     |知らないことがあるから他者に聞く。全知は組織を無意味にする                              |
|書庫型記憶を採用                       |切り詰め型（直近N件をプロンプトに詰める）では記憶がスケールしない。書庫型なら記憶量に上限がない           |
|cronは「個」の内部時計                  |cronは組織のスケジューラーではなく、各Digital Animaが自分で持つ習慣。人間が自分の日課を持つのと同じ|
