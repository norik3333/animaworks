# AnimaWorks

**Organization-as-Code for LLM Agents**

AnimaWorksは、AIエージェントをツールではなく、組織の自律的なメンバーとして扱うフレームワーク。各エージェント（Digital Anima）は固有のアイデンティティ・記憶・通信チャネルを持ち、自分のスケジュールで自律的に動作する。人間の組織と同じ原理でメッセージパッシングによって協働する。

> *不完全な個の協働が、単一の全能者より堅牢な組織を作る。*

**[English README](README.md)**

## 3つの核心

- **カプセル化** — 内部の思考・記憶は外から見えない。他者とはテキスト会話だけでつながる
- **書庫型記憶** — 記憶をプロンプトに詰め込むのではなく、必要な時に自分で書庫を検索して思い出す
- **自律性** — 指示を待つのではなく、自分の時計（ハートビート・cron）で動き、自分の理念で判断する

## アーキテクチャ

```
┌──────────────────────────────────────────────────────┐
│            Digital Anima: (Alice)                     │
├──────────────────────────────────────────────────────┤
│  Identity ────── 自分が誰か（常駐）                     │
│  Agent Core ──── 4つの実行モード                        │
│    ├ A1: Claude Agent SDK（Claude モデル専用）           │
│    ├ A1 Fallback: Anthropic SDK直接（SDK未インストール時）│
│    ├ A2: LiteLLM + tool_use（GPT-4o, Gemini 等）       │
│    └ B:  LiteLLM テキストベースツールループ（Ollama 等）   │
│  Memory ──────── 書庫型。自律検索で想起                  │
│  Boards ──────── Slack型共有チャネル                     │
│  Permissions ─── ツール/ファイル/コマンド制限             │
│  Communication ─ テキスト＋ファイル参照                  │
│  Lifecycle ───── メッセージ/ハートビート/cron             │
│  Injection ───── 役割/理念/行動規範（注入式）             │
└──────────────────────────────────────────────────────┘
```

## 脳科学にインスパイアされた記憶システム

従来のAIエージェントは記憶を切り詰めてプロンプトに詰め込む（＝直近の記憶しかない健忘）。AnimaWorksの書庫型記憶は、人間が書庫から資料を引き出すように **必要な時に必要な記憶だけを自分で検索して取り出す。**

| ディレクトリ | 脳科学モデル | 内容 |
|---|---|---|
| `episodes/` | エピソード記憶 | 日別の行動ログ |
| `knowledge/` | 意味記憶 | 教訓・ルール・学んだ知識 |
| `procedures/` | 手続き記憶 | 作業手順書 |
| `state/` | ワーキングメモリ | 今の状態・未完了タスク |
| `shortterm/` | 短期記憶 | セッション継続（コンテキスト引き継ぎ） |
| `activity_log/` | 統一活動記録 | 全インタラクションのJSONL時系列ログ |

### 記憶ライフサイクル

- **Priming（自動想起）** — 4チャネル並列の記憶検索をシステムプロンプトに自動注入（送信者プロファイル、直近の活動、関連知識、スキルマッチング）
- **Consolidation（記憶統合）** — 日次（エピソード → 意味記憶、NREM睡眠アナログ）および週次（知識マージ + エピソード圧縮）
- **Forgetting（能動的忘却）** — シナプスホメオスタシス仮説に基づく3段階の忘却:
  1. シナプスダウンスケーリング（日次）: 低アクセスチャンクをマーク
  2. ニューロジェネシス再編（週次）: 類似する低活性チャンクをマージ
  3. 完全忘却（月次）: 非活性チャンクをアーカイブ・削除

## クイックスタート

### 一番カンタンな方法: Claude Code（Mode A1）

[Claude Code](https://docs.anthropic.com/en/docs/claude-code) がインストールされていれば、**APIキーの設定は不要**。Claude Code が認証を自動処理し、各AnimaはClaude Codeサブプロセスとしてフルツールアクセス（Read / Write / Edit / Bash / Grep / Glob）で動作する。

```bash
git clone https://github.com/xuiltul/animaworks.git
cd animaworks
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

animaworks init    # 対話式セットアップ（初回のみ）
animaworks start   # サーバー起動
```

http://localhost:18500/ を開く — これだけ。

### 代替手段: API直接アクセス

Claude Codeを使わない場合や、他のLLMプロバイダ（GPT-4o, Gemini, Ollama 等）を使いたい場合:

```bash
cp .env.example .env
# .envを編集 — 最低限 ANTHROPIC_API_KEY を設定（Claudeモデル用）
```

詳細は [APIキーリファレンス](#apiキーリファレンス) を参照。

## APIキーリファレンス

**Mode A1（Claude Code）ではAPIキーは不要。** 以下のキーは代替モードやオプション機能にのみ必要。

### LLMプロバイダ

| キー | サービス | モード | 取得先 |
|-----|---------|------|--------|
| *（不要）* | Claude Code | A1 | [docs.anthropic.com/en/docs/claude-code](https://docs.anthropic.com/en/docs/claude-code) |
| `ANTHROPIC_API_KEY` | Anthropic API | A1 Fallback / A2 | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | OpenAI | A2 | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `GOOGLE_API_KEY` | Google AI | A2 | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

### 画像生成（オプション）

| キー | サービス | 生成物 | 取得先 |
|-----|---------|-------|--------|
| `NOVELAI_API_TOKEN` | NovelAI | アニメ調キャラクター画像 | [novelai.net](https://novelai.net/) → Settings > Account > API |
| `FAL_KEY` | fal.ai (Flux) | スタイライズド / フォトリアル画像 | [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys) |
| `MESHY_API_KEY` | Meshy | 3Dキャラクターモデル (GLB) | [meshy.ai](https://www.meshy.ai/) → Dashboard > API Keys |

### 外部連携（オプション）

| キー | サービス | 取得先 |
|-----|---------|--------|
| `SLACK_BOT_TOKEN` | Slack | [Slackセットアップガイド](docs/slack-socket-mode-setup.md) 参照 |
| `SLACK_APP_TOKEN` | Slack Socket Mode | [Slackセットアップガイド](docs/slack-socket-mode-setup.md) 参照 |
| `CHATWORK_API_TOKEN` | Chatwork | [chatwork.com](https://www.chatwork.com/) → 設定 > APIトークン |
| `OLLAMA_SERVERS` | Ollama（ローカルLLM） | デフォルト: `http://localhost:11434` |

## 画像生成

AnimaWorksはキャラクター画像と3Dモデルを自動生成できる。各AnimaにダッシュボードやWorkspaceで使えるビジュアルを付与する。

### 仕組み

1. 新しいAnimaが作成されると、**Asset Reconciler** がアイデンティティを読み取り、LLMを使って画像生成プロンプトを合成
2. 設定済みのサービスで画像を生成し、`~/.animaworks/animas/{name}/assets/` に保存
3. 上司Animaの画像がある場合、**Vibe Transfer** で画風を自動継承 — チーム全体のビジュアルが統一される
4. 2D画像から3Dモデルを生成し、3D Workspaceで使用可能

### セットアップ

`.env` に使いたいサービスのAPIキーを設定:

```bash
# アニメ調キャラクター画像に推奨:
NOVELAI_API_TOKEN=pst-...

# Flux系の画像生成:
FAL_KEY=...

# Workspaceで使う3Dモデル:
MESHY_API_KEY=...
```

### アセットの再生成

```bash
# 特定Animaの画像を再生成
animaworks optimize-assets alice

# Web UIのRemake機能でインタラクティブにスタイルを調整も可能
```

画像生成キーが未設定でも、Animaは問題なく動作する — ビジュアルアバターが付かないだけ。

## 最初のAnimaを作る

### ステップ1: キャラクターシートを書く

Animaを説明するMarkdownファイルを作成する。最低限、名前・役割・性格があればOK:

```markdown
# Character: Alice

## 基本情報

| 項目 | 設定 |
|------|------|
| 英名 | alice |
| 役割 | エンジニア |

## 人格

冷静で几帳面なエンジニア。問題に対して正確に、穏やかに取り組む。
巧みさよりも明快さを重視し、常に自分の推論を説明する。
わからないことはわからないと正直に言う。

## 役割・行動方針

- プロジェクトの技術インフラを管理する
- コード変更をレビューし、改善を提案する
- わかりやすい技術文書を書く
- 定期巡回中に気づいた問題を主体的に調査する
```

### ステップ2: Animaを作成する

```bash
animaworks create-anima --from-md alice.md --role engineer --name alice
```

`--role` フラグでプリセットテンプレート（モデル選択、ターン制限、専門プロンプト）を適用。利用可能なロール: `engineer`, `manager`, `writer`, `researcher`, `ops`, `general`

### ステップ3: Animaと話す

```bash
# CLIから
animaworks chat alice "こんにちは！何ができますか？"

# またはWeb UIでAliceをクリック
# http://localhost:18500/
```

### ステップ4: 自律動作を見守る

起動後、Aliceは自動的に:

- **ハートビート**を実行 — 定期的にタスクを確認し、共有チャネルを読み、次の行動を自分で決める
- **cronタスク**を実行 — `~/.animaworks/animas/alice/cron.md` で定義したスケジュールジョブ
- **記憶を統合** — 毎晩、エピソードが知識に蒸留される（睡眠時学習のアナロジー）
- 他のAnimaと**コミュニケーション** — 共有Boardチャネルやダイレクトメッセージで

### Animaを増やす

2人目のキャラクターシートを書き、上司を指定して階層を構築:

```markdown
# Character: Bob

## 基本情報

| 項目 | 設定 |
|------|------|
| 英名 | bob |
| 役割 | リサーチャー |
| 上司 | alice |

## 人格

新しいトピックを掘り下げるのが大好きな熱心なリサーチャー。
緻密で細部にこだわり、常にソースを引用する。

## 役割・行動方針

- 上司から割り当てられたトピックを調査する
- 調査結果を簡潔なレポートにまとめる
- 業界ニュースやトレンドを監視する
```

```bash
animaworks create-anima --from-md bob.md --role researcher --name bob
```

これでAliceがBobを管理する。Aliceはタスクを割り当て、Bobはメッセージングシステムを通じて報告する。

## CLIコマンドリファレンス

### サーバー管理

| コマンド | 説明 |
|---|---|
| `animaworks start [--host HOST] [--port PORT]` | サーバー起動（デフォルト: `0.0.0.0:18500`） |
| `animaworks stop` | サーバー停止（graceful shutdown） |
| `animaworks restart [--host HOST] [--port PORT]` | サーバー再起動 |

### 初期化

| コマンド | 説明 |
|---|---|
| `animaworks init` | ランタイムディレクトリを初期化（対話式セットアップ） |
| `animaworks init --force` | テンプレートの差分マージ（既存データを保持） |
| `animaworks init --from-md PATH [--name NAME]` | MDファイルからAnima作成 |
| `animaworks init --blank NAME` | 空のAnimaスケルトンを作成 |
| `animaworks reset [--restart]` | ランタイムディレクトリをリセット |

### Anima管理

| コマンド | 説明 |
|---|---|
| `animaworks create-anima [--from-md PATH] [--role ROLE] [--name NAME]` | Animaを新規作成 |
| `animaworks anima status [ANIMA]` | Animaプロセスの状態表示 |
| `animaworks anima restart ANIMA` | Animaプロセスを再起動 |
| `animaworks list` | 全Animaを一覧表示 |

### コミュニケーション

| コマンド | 説明 |
|---|---|
| `animaworks chat ANIMA "メッセージ" [--from NAME]` | Animaにメッセージを送信 |
| `animaworks send FROM TO "メッセージ"` | Anima間メッセージ |
| `animaworks heartbeat ANIMA` | ハートビートを手動トリガー |

### 設定・診断

| コマンド | 説明 |
|---|---|
| `animaworks config list [--section SECTION]` | 設定値を一覧表示 |
| `animaworks config get KEY` | 設定値を取得（ドット記法: `system.mode`） |
| `animaworks config set KEY VALUE` | 設定値を変更 |
| `animaworks status` | システムステータス表示 |
| `animaworks logs [ANIMA] [--lines N]` | ログ表示 |

## 実行モード

Animaごとにモデルと実行モードを選択可能。config.jsonで個別に設定する。

| モード | エンジン | 対象モデル | ツール |
|--------|----------|-----------|--------|
| A1 | Claude Agent SDK | Claudeモデル | Read/Write/Edit/Bash/Grep/Glob |
| A1 Fallback | Anthropic SDK直接 | Claude（Agent SDK未インストール時） | search_memory, read/write_file 等 |
| A2 | LiteLLM + tool_use | GPT-4o, Gemini 他 | search_memory, read/write_file, execute_command 等 |
| B | LiteLLM テキストベースツールループ | Ollama 等 | 疑似ツールコール（テキスト解析JSON） |

モードはモデル名から自動判定される。`config.json` の `model_modes` で手動オーバーライドも可能。

## 階層とロール

- `supervisor` フィールドのみで階層を定義。supervisor未設定 = トップレベル
- ロールテンプレート（`--role`）で役職別の専門プロンプト・権限・デフォルトパラメータを適用:

| ロール | デフォルトモデル | 用途 |
|--------|----------------|------|
| `engineer` | Opus | 複雑な推論、コード生成 |
| `manager` | Opus | 調整、意思決定 |
| `writer` | Sonnet | コンテンツ作成 |
| `researcher` | Haiku | 情報収集 |
| `ops` | ローカルモデル | ログ監視、定型業務 |
| `general` | Sonnet | 汎用 |

- 全方向の通信（指示・報告・連携）はMessengerによる非同期メッセージング
- 各AnimaはProcessSupervisorが独立子プロセスとして起動し、Unix Domain Socket経由で通信

## Web UI

- `http://localhost:18500/` — ダッシュボード（Anima状態、活動タイムライン、設定）
- `http://localhost:18500/workspace/` — インタラクティブ Workspace（3Dオフィス、会話画面）

## 人格の追加

1人 = 1ディレクトリ。`~/.animaworks/animas/{name}/` にMarkdownファイルを配置する:

```
animas/alice/
├── identity.md          # 性格・得意分野（不変）
├── injection.md         # 役割・理念・行動規範（差替可能）
├── permissions.md       # ツール/ファイル権限
├── heartbeat.md         # 定期チェック間隔
├── cron.md              # 定時タスク（YAML）
├── bootstrap.md         # 初回起動時の自己構築指示
├── status.json          # 有効/無効、ロール、モデル設定
├── specialty_prompt.md  # ロール別専門プロンプト
├── assets/              # キャラクター画像・3Dモデル
├── activity_log/        # 統一活動ログ（日付別JSONL）
└── skills/              # 拡張スキル（YAML frontmatter + Markdown本文）
```

またはMarkdownキャラクターシートから作成:

```bash
animaworks create-anima --from-md character_sheet.md --role engineer --name alice
```

## 技術スタック

| コンポーネント | 技術 |
|---|---|
| エージェント実行 | Claude Agent SDK / Anthropic SDK / LiteLLM |
| LLMプロバイダ | Anthropic, OpenAI, Google, Ollama (via LiteLLM) |
| Webフレームワーク | FastAPI + Uvicorn |
| タスクスケジュール | APScheduler |
| 設定管理 | Pydantic + JSON + Markdown |
| 記憶基盤 | ChromaDB + sentence-transformers（RAG / ベクトル検索） |
| グラフ活性化 | NetworkX（拡散活性化 + PageRank） |
| 人間通知 | Slack, Chatwork, LINE, Telegram, ntfy |
| 外部メッセージング | Slack Socket Mode, Chatwork Webhook |
| 画像生成 | NovelAI, fal.ai (Flux), Meshy (3D) |

## プロジェクト構成

```
animaworks/
├── main.py              # CLIエントリポイント
├── core/                # Digital Animaコアエンジン
│   ├── anima.py         #   カプセル化された人格クラス
│   ├── agent.py         #   実行モード選択・サイクル管理
│   ├── anima_factory.py #   Anima生成（テンプレート/空白/MD）
│   ├── memory/          #   記憶サブシステム
│   │   ├── manager.py   #     書庫型記憶の検索・書き込み
│   │   ├── priming.py   #     自動想起レイヤー（4チャネル並列）
│   │   ├── consolidation.py #  記憶統合（日次/週次）
│   │   ├── forgetting.py #    能動的忘却（3段階）
│   │   └── rag/         #     RAGエンジン（ChromaDB + embeddings）
│   ├── execution/       #   実行エンジン（A1/A1F/A2/B）
│   ├── tooling/         #   ツールディスパッチ・権限チェック
│   ├── prompt/          #   システムプロンプト構築（24セクション）
│   ├── supervisor/      #   プロセス隔離（Unixソケット）
│   └── tools/           #   外部ツール実装
├── cli/                 # CLIパッケージ（argparse + サブコマンド）
├── server/              # FastAPIサーバー + Web UI
│   ├── routes/          #   APIルート（ドメイン別分割）
│   └── static/          #   ダッシュボード + Workspace UI
└── templates/           # デフォルト設定・プロンプトテンプレート
    ├── roles/           #   ロールテンプレート（6種）
    └── anima_templates/ #   Animaスケルトン
```

## 著者について

AnimaWorksは、精神科医として人間の不完全さを診てきた経験と、経営者として複数の組織を動かしてきた経験から生まれた。

「不完全な個の協働が、単一の全能者より堅牢な組織を作る」— これがOrganization-as-Codeの根底にある思想。

## ドキュメント

| ドキュメント | 説明 |
|-------------|------|
| [設計思想](docs/vision.ja.md) | コア設計原則とビジョン |
| [記憶システム](docs/memory.ja.md) | 記憶アーキテクチャの詳細仕様 |
| [脳科学マッピング](docs/brain-mapping.ja.md) | 脳科学にマッピングしたアーキテクチャ解説 |
| [機能一覧](docs/features.ja.md) | 実装済み機能の包括的リスト |
| [技術仕様](docs/spec.md) | 技術仕様書 |

## ライセンス

Apache License 2.0。詳細は [LICENSE](LICENSE) を参照。
