# 組織構造の仕組み

AnimaWorks における組織構造は、各 Anima の `status.json`（または `identity.md`）を Single Source of Truth（SSoT）として構築される。
`core/org_sync.py` がディスク上の値を `config.json` に同期し、プロンプト構築時に利用される。
本ドキュメントでは、組織構造がどのように定義・解釈・表示されるかを説明する。

## データソースと優先順位

### supervisor（上司）

組織の上下関係は、各 Anima の `supervisor` で定義される。読み取り優先順位:

1. **status.json** — `"supervisor"` キー（推奨）
2. **identity.md** — 表形式 `| 上司 | name |` の行

`supervisor` が未設定・空・「なし」等の場合はトップレベル（最上位）となる。
`config.json` の `animas.<name>.supervisor` は org_sync によって **ディスクから同期される** ため、手動編集は上書きされる。

### speciality（専門）

専門領域は以下の優先順位で解決される:

1. **status.json** — `"speciality"` または `"role"` キー
2. **config.json** — `animas.<name>.speciality`（フォールバック）

## org_sync による config.json 同期

`core/org_sync.py` の `sync_org_structure()` が以下を行う:

1. 各 Anima ディレクトリから `status.json` / `identity.md` を読み、supervisor を抽出
2. 循環参照を検出（検出された Anima は同期対象外）
3. `config.json` の `animas` をディスクの値に合わせて更新
4. ディスク上に存在しない Anima の config エントリを削除（prune）

**実行タイミング:**

- サーバー起動時（`animaworks start`）
- Anima が reconciliation で追加されたとき

## supervisor による階層定義

- `supervisor: null` または未設定 → その Anima はトップレベル（最上位）
- `supervisor: "alice"` → alice が上司

status.json での設定例（推奨）:

```json
{
  "enabled": true,
  "supervisor": null,
  "speciality": "経営戦略・全体統括"
}
```

```json
{
  "enabled": true,
  "supervisor": "alice",
  "speciality": "開発リード"
}
```

この設定で以下の階層が構築される:

```
alice（経営戦略・全体統括）
├── bob（開発リード）
│   └── dave（バックエンド開発）
└── carol（デザイン・UX）
```

重要な制約:
- supervisor に指定する名前は既知の Anima 名（英名）でなければならない
- 循環参照（alice → bob → alice）は検出され同期対象外となる
- 1人の Anima が持てる supervisor は1名のみ

## 組織コンテキストの構築プロセス

`core/prompt/builder.py` の `_build_org_context()` が、ディレクトリスキャンと config.json のマージ結果から以下の情報を算出する:

1. **上司（supervisor）**: 自分の supervisor の値。未設定なら「あなたがトップです」
2. **部下（subordinates）**: supervisor が自分の名前になっている全 Anima
3. **同僚（peers）**: 自分と同じ supervisor を持つ Anima（自分を除く）

算出結果はシステムプロンプトに「あなたの組織上の位置」として注入される:

```
## あなたの組織上の位置

あなたの専門: 開発リード

上司: alice (経営戦略・全体統括)
部下: dave (バックエンド開発)
同僚（同じ上司を持つメンバー）: carol (デザイン・UX)
```

## 自分の位置の読み取り方

システムプロンプトの「あなたの組織上の位置」セクションから、以下を確認できる:

| 項目 | 意味 | 行動への影響 |
|------|------|-------------|
| あなたの専門 | speciality の値 | この分野に関する質問や判断は自分が責任を持つ |
| 上司 | 報告先の Anima | 進捗報告・問題のエスカレーション先 |
| 部下 | 自分の配下の Anima | タスクの委任先・進捗確認の対象 |
| 同僚 | 同じ上司を持つ仲間 | 関連業務で直接連携する相手 |

### 確認すべきポイント

- 上司が「(なし — あなたがトップです)」なら、あなたは組織のトップとして全体責任を負う
- 部下が「(なし)」なら、あなたはタスク実行者として自分で手を動かす
- 同僚がいれば、関連する業務で直接調整ができる

## 組織変更時の挙動

組織構造の変更は以下の手順で反映される:

1. 対象 Anima の `status.json` を編集（`supervisor` / `speciality` の変更）
2. サーバーを再起動するか、次回の org_sync 実行を待つ
3. org_sync が `config.json` に同期し、次回のプロンプト構築で新しい組織コンテキストが使われる

注意点:
- `config.json` の `animas` を直接編集しても、org_sync 実行時にディスクの値で上書きされる
- 組織変更後は、影響を受ける Anima にメッセージで通知することを SHOULD（推奨）

## 組織構造のパターン例

以下は各 Anima の `status.json` に設定する例。org_sync が config.json に同期する。

### パターン1: フラット組織

全員がトップレベル。上下関係なし。

各 Anima の status.json:
```json
{ "supervisor": null, "speciality": "企画" }
{ "supervisor": null, "speciality": "開発" }
{ "supervisor": null, "speciality": "デザイン" }
```

```
alice（企画）
bob（開発）
carol（デザイン）
```

特徴:
- 全員が対等な立場で直接やりとりできる
- 小規模チームや、各自が独立した業務を持つ場合に適する
- 全員の同僚は「(なし)」（同じ supervisor を共有していないため）

### パターン2: 階層型組織

明確な上下関係がある。最も一般的なパターン。

各 Anima の status.json に `supervisor` と `speciality` を設定:

```
alice（CEO・全体統括）
├── bob（開発部長）
│   ├── dave（バックエンド）
│   └── eve（フロントエンド）
└── carol（営業部長）
    └── frank（顧客対応）
```

特徴:
- bob と carol は同僚（同じ supervisor = alice）
- dave と eve は同僚（同じ supervisor = bob）
- dave から frank への連絡は bob → alice → carol → frank の経路を辿る（他部署ルール）

### パターン3: 専門家＋マネージャー型

少数のマネージャーが多数の専門家を統括する。

```
manager（プロジェクト管理）
├── dev1（API開発）
├── dev2（DB設計）
├── dev3（インフラ）
└── qa（品質保証）
```

特徴:
- 全メンバーが同僚関係。直接連携が容易
- manager が全体のタスク配分と進捗管理を担当
- スタートアップやプロジェクトチームに適する

## speciality の活用

`speciality` は `status.json` の `speciality` または `role` に自由テキストで記述する。

- 組織コンテキストで各 Anima の名前の横に表示される（例: `bob (開発リード)`）
- 他の Anima がタスクの相談先や委任先を判断する手がかりになる
- 未設定の場合は「(未設定)」と表示される

効果的な speciality の書き方:
- 具体的で短い: `バックエンド開発` `顧客サポート` `データ分析`
- 曖昧すぎない: `いろいろ` → `企画・調整・進行管理`
- 複数の専門がある場合は中黒で区切る: `UI設計・フロントエンド開発`
