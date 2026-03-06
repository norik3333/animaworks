# AnimaWorks 機能一覧

**[English version](features.md)**

> 最終更新: 2026-03-06
> 関連: [spec.ja.md](spec.ja.md), [memory.ja.md](memory.ja.md), [security.ja.md](security.ja.md), [vision.ja.md](vision.ja.md), [brain-mapping.ja.md](brain-mapping.ja.md)

AnimaWorksは、AIエージェントを「自律的な人」として扱うフレームワークである。各Animaは固有のアイデンティティ・記憶・判断基準を持ち、ハートビートやcronで人間の指示なしに行動する。組織として階層を定義し、タスクを委譲し、メッセージで協働する。脳科学に基づく記憶システムにより、限られたコンテキストウィンドウでも経験を蓄え、学び、成長できる。

本ドキュメントでは、AnimaWorksが提供する主要機能をカテゴリ別に紹介する。技術仕様の詳細は [spec.ja.md](spec.ja.md) を、設計思想は [vision.ja.md](vision.ja.md) を参照のこと。記憶システムの設計は [memory.ja.md](memory.ja.md)、脳との対応関係は [brain-mapping.ja.md](brain-mapping.ja.md)、セキュリティモデルは [security.ja.md](security.ja.md) に詳述する。

---

## 1. 自律エージェント基盤

各Animaは固有のアイデンティティ（`identity.md`）・役割（`injection.md`）・人格を持つ。人間の指示を待たず、自ら計画し行動する。

- **ハートビート**: 30分周期の定期巡回。Observe → Plan → Reflect の3フェーズで状況を把握し、計画を立て、振り返る。Heartbeatは計画のみを行い、実行が必要なタスクは `state/pending/` に書き出す。TaskExecパスがこれを検出し、独立したLLMセッションで実行する。活動時間は `heartbeat.md` で `HH:MM - HH:MM` 指定可能である（デフォルト24時間）。
- **cron**: 定時タスク。Markdown + YAML形式でスケジュールを定義し、LLM型（判断を伴う）とCommand型（確定的実行）の両方をサポートする。標準5フィールドcron式（Asia/Tokyo固定）。`trigger_heartbeat` フラグで実行後の分析スキップを制御できる。
- **ブートストラップ**: 初回起動時に自己紹介・環境把握を自動実行する。新規Animaの「誕生」を確実に完了させる。バックグラウンド実行とタイムアウト制御により、起動ブロックを防ぐ。

---

## 2. 脳科学に基づく記憶システム

AnimaWorksの記憶システムは人間の脳のメカニズムを設計パターンとして採用する。詳細は [memory.ja.md](memory.ja.md) と [brain-mapping.ja.md](brain-mapping.ja.md) を参照。

- **RAG（検索拡張生成）**: ChromaDB + multilingual-e5-small（384次元）によるベクトル検索。NetworkX を用いたグラフベース拡散活性化（Personalized PageRank）で関連記憶を活性化する。チャンキングは Markdown セクション、時系列エピソード、全ファイルに対応する。
- **プライミング（自動想起）**: メッセージ受信時に6チャネル並列で関連記憶を自動検索し、システムプロンプトに注入する。送信者プロファイル、直近活動、関連知識、スキルマッチ、未完了タスク、エピソードを対象とする。バジェットは動的調整可能である。
- **記憶統合（Consolidation）**: 日次でエピソード→知識への昇華、失敗からの手続き記憶自動生成を行う。
- **能動的忘却（Forgetting）**: シナプスホメオスタシス仮説に基づく3段階忘却。ダウンスケーリング→再編→完全忘却で、使われない記憶を整理する。procedures、skills、shared_users は保護対象である。
- **統一アクティビティログ**: 全インタラクション（メッセージ受送信、ツール使用、heartbeat、cron、人間通知等）を `activity_log/{date}.jsonl` に単一時系列で記録する。Priming の直近活動チャネルと会話履歴APIのソースとなる。
- **ストリーミングジャーナル**: WAL（Write-Ahead Log）によるクラッシュ耐性のある応答記録。異常終了時も復旧可能である。
- **common_knowledge**: 全Anima共有の知識ベース。組織構造、メッセージングガイド、タスク管理、セキュリティ、トラブルシューティング等を格納する。`read_memory_file(path="common_knowledge/...")` で参照する。

---

## 3. マルチモデル・マルチプロバイダ実行

モデル名からワイルドカードパターンマッチで実行モードを自動判定する。`models.json` でモデルごとの実行モード・コンテキストウィンドウを定義する。

- **Mode S (SDK)**: Claude Agent SDK。最もリッチなツール連携。Claude Code 組込みツール + MCP + 外部ツールを統合する。
- **Mode A (Autonomous)**: LiteLLM 経由の tool_use ループ。GPT、Gemini、Mistral、Vertex AI、Azure、ローカルモデル等に対応する。
- **Mode B (Basic)**: tool_use 非対応モデル向けの1ショット実行。フレームワークが記憶I/Oを代行する。
- **Mode C (Codex)**: OpenAI Codex CLI 経由。サンドボックス実行で安全性を確保する。

バックグラウンドモデルにより、heartbeat / cron / inbox は軽量モデルで実行可能である。コスト最適化に寄与する。ローカルLLM（vLLM、Ollama）も OpenAI 互換 API で統合する。

実行パスは分離されている。Chat/Inbox（メッセージ応答）、Heartbeat（定期巡回）、Cron（定時タスク）、TaskExec（pending タスク実行）はそれぞれ独立したロックを持ち、並行動作する。コンテキストティア（Full / Background-Auto / Minimal）に応じてシステムプロンプトのセクションを動的に選択する。

---

## 4. 組織構造と階層管理

`supervisor` / `subordinate` フィールドで階層を定義する。上司・部下・同僚の関係を自動算出し、システムプロンプトに注入する。

- **タスク委譲（delegate_task）**: 上司→部下への委任。部下のタスクキューに追加し、DMで通知する。進捗は `task_tracker` で追跡する。
- **組織ダッシュボード（org_dashboard）**: 全配下のプロセス状態・タスク・アクティビティをツリー表示する。部下の生存確認（ping_subordinate）、状態読み取り（read_subordinate_state）、活動監査（audit_subordinate）も可能である。
- **部下制御**: 休止/再開（disable_subordinate / enable_subordinate）、モデル変更（set_subordinate_model）、再起動（restart_subordinate）を直属部下に対して実行できる。権限チェックは supervisor フィールドで検証し、全配下へのアクセスは BFS で再帰探索する（循環参照は自動検出）。
- **通信経路ルール**: 進捗報告は上司へ、他部署連絡は上司経由。組織としての秩序を保つ。

---

## 5. メッセージングとコミュニケーション

- **Anima間DM**: `send_message` による非同期メッセージング。intent は report / delegation / question に限定する。1 run あたり最大2人、同一宛先へは1通まで。1ラウンドルール（1トピック1往復が原則、3往復以上ならBoard移行）を適用する。
- **Board（共有チャネル）**: Slack型の共有チャネル（#general, #ops 等）。append-only JSONL で蓄積する。ack・感謝・FYI・3人以上への伝達に使用する。
- **外部メッセージング統合**: Slack Socket Mode、Chatwork Webhook からメッセージを自動受信し、対象AnimaのInboxに配信する。@メンション付き / DM は即時処理、メンションなしは次回ハートビートで処理する。
- **統一アウトバウンドルーティング**: 宛先に応じて Anima内部 / Slack / Chatwork / 人間通知を自動判定する。
- **レート制限**: per-run（同一宛先再送防止）、cross-run（30通/hour, 100通/day）、行動認識（直近送信履歴の Priming 注入）の3層で制御する。
- **人間通知（call_human）**: Slack、Chatwork、LINE、Telegram、ntfy を統合する。トップレベルAnimaの責務である。

---

## 6. タスク管理

- **永続タスクキュー**: `state/task_queue.jsonl` に append-only JSONL 形式で記録する。`add_task` / `update_task` / `list_tasks` で操作する。`source: human` のタスクは最優先で処理する（MUST）。
- **タスク滞留検知**: 30分更新なしで ⚠️ STALE、期限超過で 🔴 OVERDUE をマークする。Priming セクションに要約表示し、委任判断プロンプトに連携する。
- **並列タスク実行（plan_tasks）**: DAG 依存関係を解決し、独立タスクを同時実行する。最大並列数は設定可能である（デフォルト3）。
- **タスク委譲と追跡**: 部下への委任は永続キューと DM で連携し、進捗を追跡する。

---

## 7. スキルとツール

- **内部ツール**: 記憶操作（search_memory, read_memory_file, write_memory_file）、通信（send_message, post_channel, read_channel）、タスク管理（add_task, update_task, list_tasks, plan_tasks）、スキル検索（skill）等を提供する。Mode S では Claude Code 組込みツール（Read, Write, Edit, Bash, git 等）と MCP ツール（mcp__aw__*）も利用可能である。
- **外部ツール**: Slack、Chatwork、Gmail、GitHub、AWS、Web検索、X検索、画像生成（NovelAI, fal.ai）、Whisper 文字起こし等。`permissions.md` で Per-Anima の許可を制御する。長時間ツール（⚠マーク付き）は `animaworks-tool submit` で非同期実行し、結果は `state/background_notifications/` に記録される。
- **スキルシステム**: 段階開示（名前のみ→必要時に全文読み込み）。description / trigger / keyword の3段階マッチングで関連スキルを想起する。
- **ツールプラグイン**: 自動発見、ホットリロード、統一ディスパッチ。長時間ツールは `submit` で非同期実行し、結果は次回 heartbeat で確認する。

---

## 8. Web UI

- **ダッシュボード**: SPA 構成。Anima一覧、ステート表示（Sleeping / Bootstrapping / Active）、アクティビティタイムライン、スケジューラータブを提供する。
- **3Dワークスペース**: Three.js ベースの3Dオフィス。組織階層に基づくキャラクター配置。クリックで会話を開始する。
- **チャット**: SSE ストリーミング、無限スクロール、マルチモーダル画像入力、マルチスレッド、マルチタブ対応。ツール実行のリアルタイム可視化（Live Tool Activity）をサポートする。
- **音声チャット**: ブラウザ音声入力 → STT（faster-whisper）→ チャット → TTS（VOICEVOX / Style-BERT-VITS2 / ElevenLabs）→ 再生。PTT / VAD モード、barge-in（割り込み）対応。
- **セットアップウィザード**: 初回起動時の Web ベース設定。17言語対応。
- **レスポンシブデザイン**: モバイル、タブレット、iPad に対応する。

---

## 9. キャラクターアセット生成

- **画像生成パイプライン**: NovelAI、fal.ai (Flux) を統合する。
- **Vibe Transfer**: 上司の画像スタイルを部下に自動継承する。組織内で絵柄の一貫性を保つ。
- **表情差分システム**: 感情に応じたバリエーションを自動生成する。
- **3Dモデル**: Meshy 統合。GLB キャッシュ・圧縮最適化でダウンロード量を削減する。
- **Asset Reconciler**: LLM がキャラクター情報から画像プロンプトを自動合成する。

---

## 10. セキュリティ

自律エージェント向けの多層防御モデルを採用する。詳細は [security.ja.md](security.ja.md) を参照。

- **プロンプトインジェクション防御**: 来歴・信頼境界システム。trusted / medium / untrusted の3段階で、外部データ由来の命令的テキストを無視する。`origin_chain` に `external_platform` が含まれる場合、中継Animaが trusted でも全体を untrusted として扱う。
- **コマンドブロック**: ハードコード（`rm -rf /` 等）+ Per-anima `permissions.md` の2層で破壊的コマンドを防止する。パイプラインの各セグメントを個別チェックする。
- **パストラバーサル防止**: メモリ書き込み・ファイルアクセスのパス検証を行う。
- **メッセージストーム防御**: 会話深度リミッター、褒め合いループ防止で無限送信を抑制する。

---

## 11. プロセス管理

- **プロセス分離**: 各Animaを Unix ソケット付き独立子プロセスとして起動する（ProcessSupervisor）。単一障害点を避ける。
- **自動クラッシュリカバリ**: Agent SDK クラッシュ検知時に自動再起動する。`state/recovery_note.md` に復旧情報を保存する。
- **Reconciliation**: 未起動 Anima を自動検出・起動する。
- **IPC 通信**: keep-alive、バッファ管理、ストリーム対応。PID ファイル耐性、WebSocket 安定性を確保する。

---

## 12. CLI 管理

- **サーバー制御**: `animaworks start` / `stop` / `restart`
- **Anima操作**: `animaworks anima list` / `info` / `create` / `enable` / `disable` / `rename`
- **モデル・設定管理**: `animaworks anima set-model` / `set-background-model` / `reload` / `restart`
- **モデル情報**: `animaworks models list` / `show` / `info`
- **初期セットアップ**: `animaworks init`

---

## 13. 設定管理

- **2層マージ**: `config.json`（グローバル）+ `status.json`（Per-Anima SSoT）。Anima単位の設定が最優先される。
- **models.json**: モデルごとの実行モード・コンテキストウィンドウを fnmatch パターンで定義する。
- **credentials.json**: 認証情報を一元管理する。Per-Anima クレデンシャル（`CHATWORK_API_TOKEN_WRITE__<anima_name>` 等）に対応する。
- **ホットリロード**: 設定変更の自動検知・反映。cron.md の更新も次回実行時にリロードする。
- **ロールテンプレート**: engineer / manager / writer / researcher / ops / general の6ロール。モデル・max_turns・max_chains を一括設定する。

---

## 14. 運用機能

- **ディスク容量管理**: ハウスキーピングジョブによる統一ローテーション。prompt_logs、shortterm、cron_logs、DM archives 等を自動クリーンアップする。
- **トークン使用量追跡**: LLM 呼び出しの入力/出力トークンを計測・記録する。
- **LLM API リトライ**: API 呼び出し失敗時の自動リトライで障害耐性を高める。
- **ファイル書き込みアトミック性**: クラッシュ耐性のあるファイル更新。一時ファイル + リネームで整合性を保証する。
