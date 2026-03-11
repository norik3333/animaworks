# Reference — 技術リファレンス目次

AnimaWorks の詳細な技術仕様・管理者向け設定ガイドの一覧。
RAG 検索対象外。必要なときに `read_memory_file(path="reference/...")` で直接参照すること。

## 参照方法

```
read_memory_file(path="reference/00_index.md")          # この目次
read_memory_file(path="reference/anatomy/anima-anatomy.md")  # 例
```

## カテゴリ

### anatomy/ — 構成ファイル・アーキテクチャ

| ファイル | 内容 |
|---------|------|
| `anima-anatomy.md` | Anima構成ファイル完全ガイド（全ファイルの役割・変更ルール・カプセル化） |

### communication/ — 外部連携設定

| ファイル | 内容 |
|---------|------|
| `slack-bot-token-guide.md` | Slack ボットトークンの設定方法（Per-Anima vs 共有） |

### internals/ — フレームワーク内部仕様

| ファイル | 内容 |
|---------|------|
| `common-knowledge-access-paths.md` | common_knowledge の5つの参照経路とRAGインデックスの仕組み |

### operations/ — 管理・運用設定

| ファイル | 内容 |
|---------|------|
| `project-setup.md` | プロジェクト初期設定（`animaworks init`・ディレクトリ構成） |
| `model-guide.md` | モデル選択・実行モード・コンテキストウィンドウの技術詳細 |
| `mode-s-auth-guide.md` | Mode S 認証モード設定（API/Bedrock/Vertex/Max） |
| `voice-chat-guide.md` | 音声チャットのアーキテクチャ・STT/TTS・インストール |

### organization/ — 組織構造の仕組み

| ファイル | 内容 |
|---------|------|
| `structure.md` | 組織構造のデータソース・supervisor/speciality の解決方法 |

### troubleshooting/ — 認証・資格情報設定

| ファイル | 内容 |
|---------|------|
| `gmail-credential-setup.md` | Gmail Tool OAuth認証設定の手順 |

## 関連

- 日常の実用ガイド → `common_knowledge/00_index.md`
- 共通スキル → `common_skills/`
