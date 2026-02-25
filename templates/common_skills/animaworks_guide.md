---
name: animaworks-guide
description: >-
  AnimaWorksフレームワークのアーキテクチャ・設計思想・操作方法を解説する共通ナレッジ。
  記憶システム(RAG/Priming/Consolidation)、実行モード(S/A/B)、
  プロンプト構築、ツール権限、ロールテンプレート等の内部構造への質問に参照する。
  「AnimaWorks」「システムの使い方」「動作原理」「仕組み」「フレームワーク」「アーキテクチャ」
---

# スキル: AnimaWorks システムガイド

## AnimaWorks とは

AIを「ツール」ではなく「人」として扱うフレームワーク。
各 Digital Anima は自分の視野・記憶・判断基準を持ち、テキストベースの会話で連携する。

### 3つの核心

1. **カプセル化** — 内部の思考・記憶は外から見えない。他者とはテキスト会話だけでつながる
2. **書庫型記憶** — 記憶をプロンプトに詰め込むのではなく、必要な時に自分で書庫を検索して思い出す
3. **自律性** — 指示を待たず、ハートビート・cronで自分から動き、自分の理念で判断する

---

## 記憶システム（書庫型）

あなたの記憶は全てファイルとして保存されている。プロンプトには要約しか含まれないため、判断前に必ず書庫を検索すること。

| ディレクトリ | 種類 | 用途 |
|-------------|------|------|
| `episodes/` | エピソード記憶 | 日別の行動ログ（YYYY-MM-DD.md） |
| `knowledge/` | 意味記憶 | 学んだこと・対応方針・ノウハウ |
| `procedures/` | 手続き記憶 | 作業手順書 |
| `skills/` | スキル | 実行可能な手順付き能力 |
| `state/` | ワーキングメモリ | 現在のタスク・未完了事項 |
| `shortterm/` | 短期記憶 | セッション引き継ぎ用（一時的） |

### 記憶の検索パターン

1. 相手の名前やトピックで `knowledge/` を Grep 検索
2. 過去の出来事を確認するなら `episodes/` を検索
3. 手順が不明なら `procedures/` を Read で確認
4. `[IMPORTANT]` タグの教訓を特に重視する

### 記憶の書き込みパターン

1. 行動後に `episodes/{今日の日付}.md` にログを追記（`## HH:MM {タイトル}` 形式）
2. 新しい学びは `knowledge/` に書き込み
3. 重要な教訓には `[IMPORTANT]` タグを付ける
4. `state/current_task.md` を常に最新に保つ

---

## 3つのライフサイクルトリガー

Digital Anima が起動するタイミングは3つある。

### 1. メッセージ受信

他の社員や上司からメッセージが届くと起動する。
- 受信メッセージの内容を読み、適切に対応する
- 返信はメッセージング機能を使う

### 2. ハートビート（定期チェック）

設定された間隔（例: 30分ごと）で自動起動する。
- Inboxの未読メッセージを確認
- 進行中タスクのブロッカーを確認
- 何もなければ何もしない（`HEARTBEAT_OK`）

### 3. Cron（スケジュールタスク）

設定された時間に自動起動する。
- 例: 毎朝9:00に業務計画を立てる
- 例: 毎週金曜17:00に週次振り返りをする
- Cronタスクは必ず成果物を出力すること

---

## メッセージング

他の社員とのコミュニケーションはメッセージ送受信で行う。

### 送信方法

AnimaWorks CLIの `send` コマンドを使って Bash で実行する:
```bash
python {main_py_path} send {自分の名前} {相手の名前} "メッセージ内容"
```

### ルール

- テキスト + ファイル参照のみ。内部状態の直接共有は禁止
- 自分の言葉で圧縮・解釈して伝える
- 長い内容はファイルとして置き「ここに置いた」と伝える

---

## スキルの使い方

スキルは `skills/` ディレクトリにある手順付きMarkdownファイル。

1. やりたいことがスキルに該当するか確認する
2. 該当するスキルファイルを `Read` で読む
3. 記載された手順に従って実行する
4. 実行結果を `episodes/` にログとして記録する

共通スキル（`common_skills/`）は全社員が利用可能。個人スキル（`skills/`）はその社員固有の能力。

---

## ディレクトリ構成の全体像

```
~/.animaworks/                  # ランタイムデータルート
├── company/
│   └── vision.md               # 会社のミッション・ビジョン
├── animas/
│   └── {あなたの名前}/
│       ├── identity.md          # あなたは誰か
│       ├── injection.md         # 役割・理念・行動規範
│       ├── permissions.md       # 権限（読み書きできる範囲）
│       ├── config.md            # モデル設定
│       ├── heartbeat.md         # 定期チェック設定
│       ├── cron.md              # スケジュールタスク設定
│       ├── episodes/            # 行動ログ
│       ├── knowledge/           # 学んだこと
│       ├── procedures/          # 手順書
│       ├── skills/              # 個人スキル
│       └── state/               # 現在の状態
│           ├── current_task.md
│           └── pending.md
├── common_skills/               # 全社員共通スキル
├── shared/
│   └── inbox/                   # メッセージ受信箱
└── tmp/
    └── attachments/             # 添付ファイル一時保存
```

---

## CLIコマンドリファレンス

AnimaWorks は以下のCLIコマンドで操作される（上司が使うもの）:

### 基本操作

| コマンド | 説明 |
|---------|------|
| `animaworks init` | ランタイムディレクトリの初期化 |
| `animaworks start` | サーバー起動 |
| `animaworks stop` | サーバー停止 |
| `animaworks restart` | サーバー再起動 |
| `animaworks chat {名前} "メッセージ"` | 社員にメッセージ送信 |
| `animaworks send {送信者} {宛先} "メッセージ"` | 社員間メッセージ |
| `animaworks heartbeat {名前}` | 手動ハートビート起動 |
| `animaworks status` | システム状態確認 |

### anima サブコマンド（Anima管理）

| コマンド | 説明 |
|---------|------|
| `animaworks anima list` | 全Anima一覧（role表示付き） |
| `animaworks anima create --from-md {ファイル} [--role {role}]` | MDキャラクターシートからAnima新規作成 |
| `animaworks anima enable {名前}` | Animaを有効化（休養から復帰） |
| `animaworks anima disable {名前}` | Animaを無効化（休養） |
| `animaworks anima delete {名前}` | Animaを削除（ZIPアーカイブ後） |
| `animaworks anima restart {名前}` | Animaプロセスを再起動 |
| `animaworks anima status [{名前}]` | Animaのプロセス状態を確認 |
| `animaworks anima set-role {名前} {role}` | Animaのroleを変更 |

#### `anima set-role` 詳細

roleを変更すると以下が自動更新される:

- `status.json` — role・モデル・max_turns 等をロールテンプレートの標準値に更新
- `specialty_prompt.md` — ロール別専門ガイドライン（コーディング原則・リサーチ手法等）に差し替え
- `permissions.md` — ロール別のツール・コマンド許可範囲に差し替え

サーバー起動中であれば自動でプロセス再起動される。

```bash
# rinのroleをengineerに変更（テンプレート再適用 + 自動restart）
animaworks anima set-role rin engineer

# status.jsonのroleフィールドのみ変更（テンプレートは触らない）
animaworks anima set-role rin engineer --status-only

# ファイル更新のみ・再起動しない
animaworks anima set-role rin engineer --no-restart
```

有効なrole: `engineer`, `researcher`, `manager`, `writer`, `ops`, `general`

---

## 注意事項

- このスキルは全社員共通。個人のスキルは各自の `skills/` に格納されている
- AnimaWorks のソースコード（プロジェクトディレクトリ）は開発用であり、通常業務ではアクセスしない
- ランタイムデータ（`~/.animaworks/`）のみが活動範囲
