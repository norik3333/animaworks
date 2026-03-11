---
name: notion-tool
description: >-
  Notion連携ツール。ページ・データベースの検索・取得・作成・更新。
  「Notion」「ノーション」「ページ作成」「データベース」
tags: [productivity, notion, external]
---

# Notion ツール

Notion API 経由でページ・データベースの検索・取得・作成・更新を行う外部ツール。

## use_tool での呼び出し

```json
{"tool": "use_tool", "arguments": {"tool_name": "notion", "action": "ACTION", "args": {...}}}
```

## アクション一覧

### search — ワークスペース検索
```json
{"tool_name": "notion", "action": "search", "args": {"query": "検索ワード", "page_size": 10}}
```

### get_page — ページメタデータ取得
```json
{"tool_name": "notion", "action": "get_page", "args": {"page_id": "ページID"}}
```

### get_page_content — ページ本文取得
```json
{"tool_name": "notion", "action": "get_page_content", "args": {"page_id": "ページID"}}
```

### get_database — データベースメタデータ取得
```json
{"tool_name": "notion", "action": "get_database", "args": {"database_id": "データベースID"}}
```

### query — データベースクエリ
```json
{"tool_name": "notion", "action": "query", "args": {"database_id": "データベースID", "filter": {}, "sorts": [], "page_size": 10}}
```
- `filter`: Notion API フィルタ JSON（任意）
- `sorts`: ソート条件の配列（任意）

### create_page — ページ作成
```json
{"tool_name": "notion", "action": "create_page", "args": {"parent_page_id": "親ページID", "properties": {"title": [{"text": {"content": "タイトル"}}]}}}
```
- `parent_page_id` または `parent_database_id` のいずれかが必須
- `children`: ページ本文ブロック配列（任意）

### update_page — ページ更新
```json
{"tool_name": "notion", "action": "update_page", "args": {"page_id": "ページID", "properties": {}}}
```

### create_database — データベース作成
```json
{"tool_name": "notion", "action": "create_database", "args": {"parent_page_id": "親ページID", "title": "DB名", "properties": {}}}
```

## CLI使用法（Sモード）

```bash
animaworks-tool notion search [検索ワード] -j
animaworks-tool notion get-page PAGE_ID -j
animaworks-tool notion get-page-content PAGE_ID -j
animaworks-tool notion get-database DATABASE_ID -j
animaworks-tool notion query DATABASE_ID [--filter JSON] [--sorts JSON] [-n 10] -j
animaworks-tool notion create-page --parent-page-id ID --properties JSON -j
animaworks-tool notion update-page PAGE_ID --properties JSON -j
animaworks-tool notion create-database --parent-page-id ID --title "名前" --properties JSON -j
```

## 注意事項

- Notion API Token は credentials に事前設定が必要
- ページ/データベースの ID はハイフン付き・なしどちらも可
- properties の構造は Notion API のスキーマに従う
