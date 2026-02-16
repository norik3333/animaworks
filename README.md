# AnimaWorks

**AIを「ツール」ではなく「人」として扱うフレームワーク**

AnimaWorksは、AIエージェントを組織の一員として自律的に動作させる Digital Anima フレームワーク。各エージェントが自分の記憶・判断基準・内部時計を持ち、不完全な情報を自分の言葉で伝え合う――人間の組織と同じ原理で動く。

## 3つの核心

- **カプセル化** — 内部の思考・記憶は外から見えない。他者とはテキスト会話だけでつながる
- **書庫型記憶** — 記憶を切り詰めてプロンプトに詰め込むのではなく、必要な時に自分で書庫を検索して思い出す
- **自律性** — 指示を待つのではなく、自分の時計（ハートビート・cron）で動き、自分の理念で判断する

## アーキテクチャ

```
┌──────────────────────────────────────────────────────┐
│            Digital Anima: (Alice)                    │
├──────────────────────────────────────────────────────┤
│  Identity ────── 自分が誰か（常駐）                     │
│  Agent Core ──── 3つの実行モード                        │
│    ├ A1: Claude Agent SDK（Claude モデル専用）           │
│    ├ A2: LiteLLM + tool_use（GPT-4o, Gemini 等）       │
│    └ B:  LiteLLM 1ショット（Ollama 等、補助モード）      │
│  Memory ──────── 書庫型。自律検索で想起                  │
│  Permissions ─── ツール/ファイル/コマンド制限             │
│  Communication ─ テキスト＋ファイル参照                  │
│  Lifecycle ───── メッセージ/ハートビート/cron             │
│  Injection ───── 役割/理念/行動規範（注入式）             │
└──────────────────────────────────────────────────────┘
```

## 記憶システム

従来のAIエージェントは記憶を切り詰めてプロンプトに詰め込む（＝直近の記憶しかない健忘）。AnimaWorks の書庫型記憶は、人間が書庫から資料を引き出すように **必要な時に必要な記憶だけを自分で検索して取り出す。**

| ディレクトリ | 脳科学モデル | 内容 |
|---|---|---|
| `episodes/` | エピソード記憶 | 日別の行動ログ |
| `knowledge/` | 意味記憶 | 教訓・ルール・学んだ知識 |
| `procedures/` | 手続き記憶 | 作業手順書 |
| `state/` | ワーキングメモリ | 今の状態・未完了タスク |
| `state/conversation.json` | 会話記憶 | ローリング履歴（自動圧縮） |
| `shortterm/` | 短期記憶 | セッション継続（コンテキスト引き継ぎ） |

## インストール

```bash
cd ~/dev/animaworks && python3 -m venv .venv && .venv/bin/pip install -e . && mkdir -p ~/.local/bin && ln -sf $(pwd)/.venv/bin/animaworks ~/.local/bin/animaworks
```

### 必要環境

- Python 3.12+
- Anthropic API キー (`export ANTHROPIC_API_KEY=sk-ant-...`)

### 環境変数

```bash
# 必須
export ANTHROPIC_API_KEY=sk-ant-...

# オプション
export ANIMAWORKS_DATA_DIR=~/.animaworks    # ランタイムデータ（デフォルト: ~/.animaworks）
```

### 初期化

テンプレートからランタイムディレクトリを生成する。

```bash
animaworks init
```

`~/.animaworks/` に company ビジョンとサンプル人格の設定ファイルが展開される。

## 実行方法

```bash
animaworks start                # サーバー起動
animaworks stop                 # サーバー停止
animaworks restart              # サーバー再起動
animaworks start --port 8080    # ポート指定
```

デフォルトで `http://localhost:18500` でサーバーが起動する。
PIDファイル (`~/.animaworks/server.pid`) で多重起動を防止し、graceful shutdown を行う。

### Docker

```bash
docker-compose up
```

## CLIコマンドリファレンス

### サーバー管理

| コマンド | 説明 |
|---|---|
| `animaworks start [--host HOST] [--port PORT]` | サーバー起動（デフォルト: `0.0.0.0:18500`） |
| `animaworks stop` | サーバー停止（SIGTERM → graceful shutdown） |
| `animaworks restart [--host HOST] [--port PORT]` | サーバー再起動（stop → start） |
| `animaworks serve` | `start` のエイリアス |

### 初期化・リセット

| コマンド | 説明 |
|---|---|
| `animaworks init` | ランタイムディレクトリを初期化（初回のみ、対話式セットアップ） |
| `animaworks init --force` | テンプレートの差分マージ（既存データを保持） |
| `animaworks init --template NAME` | テンプレートから Anima を作成（非対話） |
| `animaworks init --from-md PATH [--name NAME]` | MD ファイルから Anima を作成（非対話） |
| `animaworks init --blank NAME` | 空の Anima を作成（非対話） |
| `animaworks init --skip-anima` | インフラのみ初期化（Anima 作成をスキップ） |
| `animaworks reset [--restart]` | サーバー停止 → ランタイムディレクトリ削除 → 再初期化。`--restart` でサーバーも再起動 |

### Anima 管理

| コマンド | 説明 |
|---|---|
| `animaworks create-anima [--template NAME] [--from-md PATH] [--name NAME]` | Anima を新規作成 |
| `animaworks anima status [ANIMA]` | Anima プロセスの状態表示（省略で全員） |
| `animaworks anima restart ANIMA` | Anima プロセスを再起動 |
| `animaworks list [--local]` | 全 Anima を一覧表示 |

### コミュニケーション

| コマンド | 説明 |
|---|---|
| `animaworks chat ANIMA "メッセージ" [--local] [--from NAME]` | Anima にメッセージを送信 |
| `animaworks send FROM TO "メッセージ" [--thread-id ID] [--reply-to ID]` | Anima 間メッセージ |
| `animaworks heartbeat ANIMA [--local]` | ハートビートを手動トリガー |

### 設定・診断

| コマンド | 説明 |
|---|---|
| `animaworks config list [--section SECTION] [--show-secrets]` | 設定値を一覧表示 |
| `animaworks config get KEY [--show-secrets]` | 設定値を取得（ドット記法: `system.gateway.port`） |
| `animaworks config set KEY VALUE` | 設定値を変更 |
| `animaworks status` | システムステータス表示 |
| `animaworks logs [ANIMA] [--all] [--lines N] [--date YYYYMMDD]` | ログ表示 |
| `animaworks index` | 記憶インデックスの管理 |

## 実行モード

Anima ごとにモデルと実行モードを選択できる。config.json の `animas.{name}.model` で指定。

| モード | エンジン | 対象モデル | ツール |
|--------|----------|-----------|--------|
| A1 | Claude Agent SDK | Claude モデル | Read/Write/Edit/Bash/Grep/Glob |
| A2 | LiteLLM + tool_use | GPT-4o, Gemini, 他 | search_memory, read/write_file, execute_command 等 |
| B | LiteLLM 1ショット | Ollama 等 | なし（フレームワーク補助） |

## 階層と委任

- config.json で `role`（commander / worker）と `supervisor` を Anima ごとに定義
- 委任（上→下）は同期、エスカレーション（下→上）は非同期（Messenger）
- 全 Anima は DigitalAnima カプセル内で動作。独立デーモンは作らない

## Web UI

- `http://localhost:18500/` --- シンプルビューアー
- `http://localhost:18500/workspace/` --- インタラクティブ Workspace（3Dオフィス、会話画面）

## 人格の追加

1人 ＝ 1ディレクトリ。`~/.animaworks/animas/{name}/` に Markdown ファイルを配置するだけ。
モデル・実行モード等の設定は `~/.animaworks/config.json` で一元管理。

```
animas/alice/
├── identity.md      # 性格・得意分野（不変）
├── injection.md     # 役割・理念・行動規範（差替可能）
├── permissions.md   # ツール/ファイル権限
├── heartbeat.md     # 定期チェック間隔・活動時間
├── cron.md          # 自分の定時タスク
├── bootstrap.md     # 初回起動時の自己構築指示
└── skills/          # 拡張スキル
```

Identity を差し替えれば同じフレームワークで全く異なる AI 社員が動く。

## 技術スタック

| コンポーネント | 技術 |
|---|---|
| エージェント実行 | Claude Agent SDK (Mode A1) / LiteLLM (Mode A2/B) |
| LLM プロバイダ | Anthropic, OpenAI, Google, Ollama (via LiteLLM) |
| Web フレームワーク | FastAPI + Uvicorn |
| タスクスケジュール | APScheduler |
| 設定管理 | Pydantic + TOML + Markdown |

## プロジェクト構成

```
animaworks/
├── main.py              # CLI エントリポイント
├── core/                # Digital Anima コアエンジン
│   ├── anima.py        #   カプセル化された人格クラス
│   ├── agent.py         #   実行モード選択・サイクル管理
│   ├── memory.py        #   書庫型記憶の検索・書き込み
│   ├── conversation_memory.py # 会話記憶（ローリング圧縮）
│   ├── shortterm_memory.py #  短期記憶（セッション継続）
│   ├── messenger.py     #   Anima間メッセージ送受信
│   ├── lifecycle.py     #   ハートビート・cron管理
│   ├── config.py        #   Pydantic統合設定モデル
│   ├── prompt_builder.py #  システムプロンプト構築
│   ├── tool_handler.py  #   ツール実行ディスパッチ
│   ├── tool_schemas.py  #   ツールスキーマ定義
│   ├── external_tools.py #  外部ツール連携
│   ├── context_tracker.py # コンテキスト使用量監視
│   ├── anima_factory.py #  Anima生成（テンプレート/空白/MD）
│   ├── init.py          #   ランタイム初期化
│   ├── schemas.py       #   Pydanticデータモデル
│   ├── paths.py         #   パス解決
│   ├── execution/       #   実行エンジン
│   │   ├── agent_sdk.py #     Mode A1: Claude Agent SDK
│   │   ├── litellm_loop.py #  Mode A2: LiteLLM + tool_use
│   │   ├── assisted.py  #     Mode B: フレームワーク補助
│   │   └── anthropic_fallback.py # Anthropic SDK直接
│   └── tools/           #   外部ツール実装
│       ├── web_search.py, x_search.py, slack.py
│       ├── chatwork.py, gmail.py, github.py
│       ├── transcribe.py, aws_collector.py
│       └── local_llm.py
├── server/              # サーバー（FastAPI アプリケーション）
│   └── static/workspace/ # インタラクティブ Workspace UI
├── gateway/             # (deprecated) 分散ゲートウェイ
├── worker/              # (deprecated) 分散ワーカー
├── broker/              # (deprecated) 分散メッセージブローカー
└── templates/           # デフォルト設定・プロンプトテンプレート
    ├── animas/{name}/  #   Anima ディレクトリ（名前で識別）
    └── prompts/         #   再利用可能なプロンプト
```

## 設計思想の詳細

詳しい設計理念は [vision.md](docs/vision.md)、技術仕様は [spec.md](docs/spec.md) を参照。
