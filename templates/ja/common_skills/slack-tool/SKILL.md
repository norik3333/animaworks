---
name: slack-tool
description: >-
  Slack連携ツール。メッセージ送信・取得・検索・未返信確認・チャンネル一覧・絵文字リアクション。
  「Slack」「スラック」「チャンネル」「スレッド」「リアクション」
tags: [communication, slack, external]
---

# Slack ツール

Slackのメッセージ送受信・検索・リアクションを行う外部ツール。

## use_tool での呼び出し

```json
{"tool": "use_tool", "arguments": {"tool_name": "slack", "action": "ACTION", "args": {...}}}
```

## アクション一覧

### send — メッセージ送信
```json
{"tool_name": "slack", "action": "send", "args": {"channel": "#チャンネル名", "message": "送信テキスト", "thread": "スレッドts(任意)"}}
```

### messages — メッセージ取得
```json
{"tool_name": "slack", "action": "messages", "args": {"channel": "#チャンネル名", "limit": 20}}
```

### search — メッセージ検索
```json
{"tool_name": "slack", "action": "search", "args": {"keyword": "検索ワード", "channel": "#チャンネル名(任意)", "limit": 50}}
```

### unreplied — 未返信メッセージ確認
```json
{"tool_name": "slack", "action": "unreplied", "args": {}}
```

### channels — チャンネル一覧
```json
{"tool_name": "slack", "action": "channels", "args": {}}
```

### react — 絵文字リアクション
```json
{"tool_name": "slack", "action": "react", "args": {"channel": "#チャンネル名", "emoji": "thumbsup", "message_ts": "メッセージのタイムスタンプ"}}
```
- `emoji`: Slack の絵文字名（コロンなし。例: `thumbsup`, `eyes`, `white_check_mark`）
- `message_ts`: リアクション対象メッセージのタイムスタンプ（`messages` アクションの結果から取得可能）

## CLI使用法（Sモード）

```bash
animaworks-tool slack send CHANNEL MESSAGE [--thread TS]
animaworks-tool slack messages CHANNEL [-n 20]
animaworks-tool slack search KEYWORD [-c CHANNEL] [-n 50]
animaworks-tool slack unreplied [--json]
animaworks-tool slack channels
```

> `react` アクションは CLI 未対応。`use_tool` または MCP 経由で使用する。

## 注意事項

- Slack Bot Token は credentials に事前設定が必要
- チャンネルは #付きの名前またはチャンネルIDで指定
- リアクションには `reactions:write` スコープが必要
