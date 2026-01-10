# Crawl Cancellation & Monitoring Guide

## 概要

Transparent Search は、実行中のクロール操作をリアルタイムで監視し、途中で停止できる機能を提供しています。

## アーキテクチャ

### コンポーネント

1. **crawler_state.py** - Redis を使用したクロール状態管理
   - クロール開始時の初期化
   - キャンセルフラグの設定・確認
   - 進捗情報の更新
   - クロール完了時の状態保存

2. **advanced_crawler.py** - キャンセル対応のクローラー
   - 各ページ処理時にキャンセルフラグをチェック
   - バッチレベルでの中断チェック
   - 進捗情報をリアルタイム更新

3. **admin.py** - Admin API エンドポイント
   - クロール状態の確認
   - クロール停止リクエスト
   - 状態情報のクリーンアップ

## API エンドポイント

### 1. クロール状態を確認

```bash
GET /admin/crawl/{crawl_id}/status
```

**レスポンス例:**

```json
{
  "crawl_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "domain": "example.com",
  "started_at": "2026-01-10T08:00:00",
  "ended_at": null,
  "cancelled_at": null,
  "progress": {
    "pages_crawled": 45,
    "pages_failed": 2,
    "pages_skipped": 8,
    "current_url": "https://example.com/page-45",
    "last_updated": "2026-01-10T08:05:23"
  },
  "cancelled": false
}
```

### 2. クロールを停止

```bash
POST /admin/crawl/{crawl_id}/cancel
```

**レスポンス例:**

```json
{
  "status": "success",
  "message": "Crawl 550e8400-e29b-41d4-a716-446655440000 cancellation requested",
  "crawl_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 3. クロール状態をクリーンアップ

```bash
DELETE /admin/crawl/{crawl_id}
```

**レスポンス例:**

```json
{
  "status": "success",
  "message": "Crawl 550e8400-e29b-41d4-a716-446655440000 state deleted",
  "crawl_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 4. ヘルスチェック

```bash
GET /admin/health
```

## 使用例

### CLI での使用

#### 1. クロール開始（バックグラウンド）

```bash
# Terminal 1: クロール開始
python -m app.advanced_crawler https://example.com 1000 5 10
```

このコマンドで **crawl_id** が表示されます：

```
[*] Crawl ID: 550e8400-e29b-41d4-a716-446655440000
[*] Crawl delay: 1.5s
[*] Features: Tracker Detection, Cancellation Support
```

#### 2. クロール進捗を監視（別のターミナル）

```bash
# Terminal 2: 進捗確認
curl http://localhost:8080/admin/crawl/550e8400-e29b-41d4-a716-446655440000/status | jq
```

5秒ごとに確認:

```bash
watch -n 5 'curl -s http://localhost:8080/admin/crawl/550e8400-e29b-41d4-a716-446655440000/status | jq .progress'
```

#### 3. クロール停止

```bash
# Terminal 2 または 3: クロール中止
curl -X POST http://localhost:8080/admin/crawl/550e8400-e29b-41d4-a716-446655440000/cancel
```

結果（クローラーログより）:

```
[CANCEL] Crawl cancelled, stopped at https://example.com/page-127
[DONE] Attempted=127, Success=125, Failed=1, Skipped=1
```

#### 4. クリーンアップ

```bash
# Terminal 2 または 3: 状態削除
curl -X DELETE http://localhost:8080/admin/crawl/550e8400-e29b-41d4-a716-446655440000
```

### Python での使用

```python
import asyncio
import uuid
from app.advanced_crawler import crawl_recursive
from app.crawler_state import crawler_state

async def managed_crawl():
    # クロール ID を生成
    crawl_id = str(uuid.uuid4())
    
    # クロール実行
    task = asyncio.create_task(
        crawl_recursive(
            "https://example.com",
            max_pages=1000,
            max_depth=5,
            concurrency=10,
            crawl_id=crawl_id,
        )
    )
    
    try:
        # 60秒後に自動停止
        await asyncio.wait_for(task, timeout=60.0)
    except asyncio.TimeoutError:
        print(f"Timeout reached, cancelling crawl {crawl_id}")
        await crawler_state.cancel_crawl(crawl_id)
        await task  # クリーンアップを待つ

asyncio.run(managed_crawl())
```

## 動作フロー

### クロール開始

```
1. crawler_state.start_crawl(crawl_id, domain)
   ├─ Redis に状態初期化
   └─ status = "running"

2. crawl_recursive() メインループ開始
   └─ 各バッチ処理前にキャンセルをチェック
```

### キャンセルリクエスト

```
1. POST /admin/crawl/{crawl_id}/cancel
   └─ crawler_state.cancel_crawl(crawl_id)
      └─ Redis の cancelled フラグを True に設定

2. クローラーが is_cancelled() をチェック
   └─ True なら即座に処理を停止
   └─ 既処理のページはデータベースに保存済み
```

### 進捗更新

```
各ページ処理後:

1. crawler_state.update_progress()
   ├─ pages_crawled 更新
   ├─ current_url 更新
   ├─ last_updated 更新
   └─ Redis TTL を延長 (1時間)

2. API /admin/crawl/{crawl_id}/status で確認可能
```

## Redis キー構造

```
Key: crawler:{crawl_id}
Value: JSON
{
  "crawl_id": "...",
  "domain": "example.com",
  "status": "running|completed|cancelled|failed",
  "started_at": "2026-01-10T08:00:00",
  "ended_at": null,
  "cancelled_at": null,
  "pages_crawled": 45,
  "pages_failed": 2,
  "pages_skipped": 8,
  "current_url": "https://example.com/page-45",
  "cancelled": false,
  "last_updated": "2026-01-10T08:05:23"
}
TTL: 3600秒 (1時間)
```

## エラー処理

### Redis 接続失敗

- キャンセル機能は無効化されるが、クローラーは通常通り実行継続
- ログ: `⚠️ Redis connection failed: ...`

### Crawl ID が見つからない

```bash
$ curl http://localhost:8080/admin/crawl/invalid-id/status
# HTTP 404 Not Found
{
  "detail": "Crawl not found"
}
```

## ベストプラクティス

### 1. 定期的に状態をモニタリング

```bash
# 10秒ごとに進捗確認
while true; do
  curl -s http://localhost:8080/admin/crawl/$CRAWL_ID/status | \
    jq '{status: .status, crawled: .progress.pages_crawled, failed: .progress.pages_failed}'
  sleep 10
done
```

### 2. 自動停止タイムアウト設定

```python
import asyncio

async def crawl_with_timeout(url, timeout_seconds=3600):
    task = asyncio.create_task(
        crawl_recursive(url, crawl_id=...)
    )
    try:
        await asyncio.wait_for(task, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        print("Max crawl time reached, cancelling...")
        await crawler_state.cancel_crawl(crawl_id)
```

### 3. 終了後のクリーンアップ

```bash
# クロール完了後、状態を削除
sleep 60  # クロール終了を待つ
curl -X DELETE http://localhost:8080/admin/crawl/$CRAWL_ID
```

## トラブルシューティング

### キャンセルが効かない場合

1. **Redis接続確認**:
   ```bash
   redis-cli ping
   # PONG が返ってくればOK
   ```

2. **Crawl ID 確認**:
   ```bash
   redis-cli keys "crawler:*"
   # アクティブなクロールIDが表示される
   ```

3. **手動キャンセル**:
   ```bash
   redis-cli
   > get crawler:{crawl_id}
   # JSON が表示される
   ```

### 進捗が更新されない場合

- ネットワーク遅延でページクロールが進んでいない可能性
- `current_url` が変わっているか確認
- ログで `[SKIP]` や `[FAIL]` が続いていないか確認

## パフォーマンス考慮事項

- **Redis TTL**: デフォルト 1時間（クロール中は自動延長）
- **状態更新頻度**: 各ページ処理後（ネットワークオーバーヘッド最小）
- **キャンセルチェック**: バッチレベル + ページレベル（即座に対応）

## サンプルダッシュボード（curl + jq）

```bash
#!/bin/bash
CRAWL_ID="$1"
echo "=== Crawl Status Dashboard ==="
while true; do
  clear
  echo "Crawl ID: $CRAWL_ID"
  curl -s http://localhost:8080/admin/crawl/$CRAWL_ID/status | jq '{
    status: .status,
    domain: .domain,
    started_at: .started_at,
    pages_crawled: .progress.pages_crawled,
    pages_failed: .progress.pages_failed,
    pages_skipped: .progress.pages_skipped,
    current_url: .progress.current_url,
    cancelled: .cancelled
  }'
  echo ""
  echo "Commands:"
  echo "  Cancel: curl -X POST http://localhost:8080/admin/crawl/$CRAWL_ID/cancel"
  echo "  Delete: curl -X DELETE http://localhost:8080/admin/crawl/$CRAWL_ID"
  sleep 5
done
```

実行:

```bash
bash monitor.sh 550e8400-e29b-41d4-a716-446655440000
```
