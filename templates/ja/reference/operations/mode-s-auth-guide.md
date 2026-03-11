# Mode S（Agent SDK）認証モード設定ガイド

Mode S（Claude Agent SDK）で使用する認証方式を Anima ごとに切り替える方法。
認証モードは **`mode_s_auth`** という明示的な設定で指定する（credential の自動判定ではない）。

実装: `core/execution/agent_sdk.py` の `_build_env()` が Claude Code 子プロセスの環境変数を構築する。

## 認証モード一覧

| モード | mode_s_auth 値 | 接続先 | 用途 |
|--------|----------------|--------|------|
| **API 直接** | `"api"` | Anthropic API | 最速ストリーミング。API クレジット消費 |
| **Bedrock** | `"bedrock"` | AWS Bedrock | AWS 統合・VPC 内利用 |
| **Vertex AI** | `"vertex"` | Google Vertex AI | GCP 統合 |
| **Max plan** | `"max"` または未設定 | Anthropic Max plan | サブスクリプション認証。API クレジット不要 |

`mode_s_auth` が未設定（`null` または省略）の場合は Max plan になる。

## 設定の優先順位

`mode_s_auth` は次の順で解決される:

1. **status.json**（Anima 個別）— 最優先
2. **config.json anima_defaults** — グローバルデフォルト

credential の内容からは自動判定されない。明示的に `mode_s_auth` を指定すること。

## 設定方法

### 1. API 直接モード

Anthropic API に直接接続する。ストリーミングが最もスムーズ。

**config.json の credential 設定:**

```json
{
  "credentials": {
    "anthropic": {
      "api_key": "sk-ant-api03-xxxxx"
    }
  }
}
```

- `api_key`: Anthropic API キー。空の場合は環境変数 `ANTHROPIC_API_KEY` にフォールバック
- `base_url`: カスタムエンドポイント（任意）。指定時は `ANTHROPIC_BASE_URL` として子プロセスに渡される（プロキシやオンプレミス利用時）

**status.json（Anima 個別）:**

```json
{
  "model": "claude-sonnet-4-6",
  "credential": "anthropic",
  "mode_s_auth": "api"
}
```

`mode_s_auth` が `"api"` で credential に `api_key` がなく環境変数にもない場合、Max plan にフォールバックする。

### 2. Bedrock モード

AWS Bedrock 経由で接続する。credential の `keys` が `extra_keys` として ModelConfig に渡され、環境変数にマッピングされる。

**config.json の credential 設定:**

```json
{
  "credentials": {
    "bedrock": {
      "api_key": "",
      "keys": {
        "aws_access_key_id": "AKIA...",
        "aws_secret_access_key": "...",
        "aws_region_name": "us-east-1",
        "aws_session_token": "",
        "aws_profile": ""
      }
    }
  }
}
```

| keys キー | 環境変数 | 説明 |
|-----------|----------|------|
| aws_access_key_id | AWS_ACCESS_KEY_ID | 必須 |
| aws_secret_access_key | AWS_SECRET_ACCESS_KEY | 必須 |
| aws_region_name | AWS_REGION | リージョン |
| aws_session_token | AWS_SESSION_TOKEN | 一時認証（任意） |
| aws_profile | AWS_PROFILE | プロファイル名（任意） |

`keys` に値がない項目は、上記の対応する環境変数にフォールバックする。本番では `AWS_PROFILE` のみ設定し、キーを config に書かない運用も可能。

**status.json（Anima 個別）:**

```json
{
  "model": "claude-sonnet-4-6",
  "credential": "bedrock",
  "execution_mode": "S",
  "mode_s_auth": "bedrock"
}
```

Bedrock を Mode S で使う場合は `execution_mode: "S"` と `mode_s_auth: "bedrock"` の両方を指定する。

### 3. Vertex AI モード

Google Vertex AI 経由で接続する。credential の `keys` が `extra_keys` として ModelConfig に渡され、環境変数にマッピングされる。

**config.json の credential 設定:**

```json
{
  "credentials": {
    "vertex": {
      "api_key": "",
      "keys": {
        "vertex_project": "my-gcp-project",
        "vertex_location": "us-central1",
        "vertex_credentials": "/path/to/service-account.json"
      }
    }
  }
}
```

| keys キー | 環境変数 | 説明 |
|-----------|----------|------|
| vertex_project | CLOUD_ML_PROJECT_ID | GCP プロジェクト ID |
| vertex_location | CLOUD_ML_REGION | リージョン（例: us-central1） |
| vertex_credentials | GOOGLE_APPLICATION_CREDENTIALS | サービスアカウント JSON パス |

`keys` に値がない項目は、上記の対応する環境変数にフォールバックする。ADC（Application Default Credentials）利用時は `vertex_credentials` を省略可能。

**status.json（Anima 個別）:**

```json
{
  "model": "claude-sonnet-4-6",
  "credential": "vertex",
  "execution_mode": "S",
  "mode_s_auth": "vertex"
}
```

### 4. Max plan モード（デフォルト）

Claude Code のサブスクリプション認証（Max plan 等）を使用する。

**config.json の credential 設定:**

```json
{
  "credentials": {
    "max": {
      "api_key": ""
    }
  }
}
```

**status.json（Anima 個別）:**

```json
{
  "model": "claude-sonnet-4-6",
  "credential": "max"
}
```

`mode_s_auth` を省略するか `"max"` にすると Max plan になる。

## Anima ごとの使い分け例

同じ組織内で認証モードを混在させる場合、各 Anima の status.json で `mode_s_auth` と `credential` を指定する:

```json
{
  "credentials": {
    "anthropic": { "api_key": "sk-ant-api03-xxxxx" },
    "max": { "api_key": "" },
    "bedrock": {
      "api_key": "",
      "keys": {
        "aws_access_key_id": "AKIA...",
        "aws_secret_access_key": "...",
        "aws_region_name": "us-east-1"
      }
    }
  }
}
```

| 例（役割） | credential | mode_s_auth | 認証モード | 理由 |
|-----------|-----------|-------------|-----------|------|
| Max plan 利用の Anima | `"max"` | 省略 | Max plan | API コスト不要 |
| API 直接利用の Anima | `"anthropic"` | `"api"` | API 直接 | 高速ストリーミングが必要 |
| Bedrock 利用の Anima | `"bedrock"` | `"bedrock"` | Bedrock | AWS VPC 内からのみアクセス |

**現在の構成を確認する方法:** 各 Anima の `status.json` で `credential` と `mode_s_auth` を確認する:

```bash
# 特定 Anima の mode_s_auth 確認
cat ~/.animaworks/animas/{name}/status.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'model={d.get(\"model\")}, credential={d.get(\"credential\")}, mode_s_auth={d.get(\"mode_s_auth\")}')"

# 全 Anima の一覧
for d in ~/.animaworks/animas/*/; do name=$(basename "$d"); python3 -c "import json; d=json.load(open('$d/status.json')); print(f'$name: credential={d.get(\"credential\")}, mode_s_auth={d.get(\"mode_s_auth\")}')" 2>/dev/null; done
```

## グローバルデフォルト（anima_defaults）

全 Anima で Bedrock をデフォルトにしたい場合、config.json の `anima_defaults` に設定する:

```json
{
  "anima_defaults": {
    "mode_s_auth": "bedrock"
  },
  "credentials": {
    "bedrock": { "api_key": "", "keys": { "aws_access_key_id": "...", ... } }
  }
}
```

個別 Anima の status.json で `mode_s_auth` を上書きできる。

## 注意事項

- 認証モードは `_build_env()` で Claude Code 子プロセスの環境変数として渡される
- `mode_s_auth` は credential の内容から自動判定されない。明示指定が必須
- `mode_s_auth=api` で credential に `api_key` がなく環境変数にもない場合、Max plan にフォールバックする
- Bedrock / Vertex では credential の `keys` が `extra_keys` として渡され、環境変数にマッピングされる。`keys` 未設定の項目は同名の環境変数にフォールバック
- API モードでカスタムエンドポイントを使う場合、credential の `base_url` を指定すると `ANTHROPIC_BASE_URL` として子プロセスに渡される
- 設定変更後はサーバー再起動が必要
- Mode A/B では従来通り LiteLLM が credential を使用する（この設定は Mode S 専用）
