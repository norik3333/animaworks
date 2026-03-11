# Mode S (Agent SDK) Authentication Mode Configuration Guide

How to switch the authentication method used by Mode S (Claude Agent SDK) per Anima.
Authentication mode is specified by the explicit **`mode_s_auth`** setting (not auto-detected from credential).

Implementation: `_build_env()` in `core/execution/agent_sdk.py` constructs the environment variables for the Claude Code child process.

## Authentication Modes

| Mode | mode_s_auth value | Connection | Use case |
|------|-------------------|------------|----------|
| **API Direct** | `"api"` | Anthropic API | Fastest streaming. Consumes API credits |
| **Bedrock** | `"bedrock"` | AWS Bedrock | AWS integration / use within VPC |
| **Vertex AI** | `"vertex"` | Google Vertex AI | GCP integration |
| **Max plan** | `"max"` or unset | Anthropic Max plan | Subscription auth. No API credits needed |

When `mode_s_auth` is unset (`null` or omitted), Max plan is used.

## Resolution Priority

`mode_s_auth` is resolved in this order:

1. **status.json** (per-Anima) — highest priority
2. **config.json anima_defaults** — global default

It is not auto-detected from credential content. You must set `mode_s_auth` explicitly.

## Configuration

### 1. API Direct Mode

Connect directly to Anthropic API. Provides the smoothest streaming experience.

**config.json credential:**

```json
{
  "credentials": {
    "anthropic": {
      "api_key": "sk-ant-api03-xxxxx"
    }
  }
}
```

- `api_key`: Anthropic API key. Falls back to environment variable `ANTHROPIC_API_KEY` if empty
- `base_url`: Custom endpoint (optional). When specified, passed to child process as `ANTHROPIC_BASE_URL` (for proxy or on-premises use)

**status.json (per-Anima):**

```json
{
  "model": "claude-sonnet-4-6",
  "credential": "anthropic",
  "mode_s_auth": "api"
}
```

If `mode_s_auth` is `"api"` but the credential has no `api_key` and none is set in environment variables, it falls back to Max plan.

### 2. Bedrock Mode

Connect via AWS Bedrock. Credential `keys` are passed as `extra_keys` to ModelConfig and mapped to environment variables.

**config.json credential:**

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

| keys key | Environment variable | Description |
|----------|---------------------|-------------|
| aws_access_key_id | AWS_ACCESS_KEY_ID | Required |
| aws_secret_access_key | AWS_SECRET_ACCESS_KEY | Required |
| aws_region_name | AWS_REGION | Region |
| aws_session_token | AWS_SESSION_TOKEN | Temporary auth (optional) |
| aws_profile | AWS_PROFILE | Profile name (optional) |

Items with no value in `keys` fall back to the corresponding environment variable above. In production, you can use only `AWS_PROFILE` and avoid storing keys in config.

**status.json (per-Anima):**

```json
{
  "model": "claude-sonnet-4-6",
  "credential": "bedrock",
  "execution_mode": "S",
  "mode_s_auth": "bedrock"
}
```

For Bedrock in Mode S, both `execution_mode: "S"` and `mode_s_auth: "bedrock"` are required.

### 3. Vertex AI Mode

Connect via Google Vertex AI. Credential `keys` are passed as `extra_keys` to ModelConfig and mapped to environment variables.

**config.json credential:**

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

| keys key | Environment variable | Description |
|----------|---------------------|-------------|
| vertex_project | CLOUD_ML_PROJECT_ID | GCP project ID |
| vertex_location | CLOUD_ML_REGION | Region (e.g. us-central1) |
| vertex_credentials | GOOGLE_APPLICATION_CREDENTIALS | Service account JSON path |

Items with no value in `keys` fall back to the corresponding environment variable above. When using ADC (Application Default Credentials), `vertex_credentials` can be omitted.

**status.json (per-Anima):**

```json
{
  "model": "claude-sonnet-4-6",
  "credential": "vertex",
  "execution_mode": "S",
  "mode_s_auth": "vertex"
}
```

### 4. Max Plan Mode (Default)

Uses Claude Code subscription authentication (Max plan etc.).

**config.json credential:**

```json
{
  "credentials": {
    "max": {
      "api_key": ""
    }
  }
}
```

**status.json (per-Anima):**

```json
{
  "model": "claude-sonnet-4-6",
  "credential": "max"
}
```

Omit `mode_s_auth` or set it to `"max"` for Max plan.

## Mixing Auth Modes Per Anima

To use different auth modes within the same organization, set `mode_s_auth` and `credential` per Anima in status.json:

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

| Example (role) | credential | mode_s_auth | Auth mode | Reason |
|----------------|-----------|-------------|-----------|--------|
| Max plan Anima | `"max"` | omitted | Max plan | No API cost |
| API Direct Anima | `"anthropic"` | `"api"` | API Direct | Requires fast streaming |
| Bedrock Anima | `"bedrock"` | `"bedrock"` | Bedrock | Access only from within AWS VPC |

**How to verify current configuration:** Check `credential` and `mode_s_auth` in each Anima's `status.json`:

```bash
# Check mode_s_auth for a specific Anima
cat ~/.animaworks/animas/{name}/status.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'model={d.get(\"model\")}, credential={d.get(\"credential\")}, mode_s_auth={d.get(\"mode_s_auth\")}')"

# List all Animas
for d in ~/.animaworks/animas/*/; do name=$(basename "$d"); python3 -c "import json; d=json.load(open('$d/status.json')); print(f'$name: credential={d.get(\"credential\")}, mode_s_auth={d.get(\"mode_s_auth\")}')" 2>/dev/null; done
```

## Global Default (anima_defaults)

To use Bedrock as the default for all Animas, set it in config.json `anima_defaults`:

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

Individual Animas can override `mode_s_auth` in their status.json.

## Notes

- Auth mode is passed as environment variables to the Claude Code child process via `_build_env()`
- `mode_s_auth` is not auto-detected from credential content. Explicit setting is required
- When `mode_s_auth=api` but credential has no `api_key` and none is in environment variables, it falls back to Max plan
- For Bedrock / Vertex, credential `keys` are passed as `extra_keys` and mapped to environment variables. Items not set in `keys` fall back to the environment variable of the same name
- For API mode with a custom endpoint, specifying `base_url` in credential passes it to the child process as `ANTHROPIC_BASE_URL`
- Server restart is required after configuration changes
- Mode A/B use credentials via LiteLLM as before (this setting is Mode S-specific)
