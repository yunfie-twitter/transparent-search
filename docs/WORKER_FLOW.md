# Crawl Worker と Job フロー

## 🔄 アプリケーション起動フロー

```
起動シーケンス
    ↓
┌─────────────────────────────────────────────────────────┐
│ startup.py (Pre-startup 初期化)                         │
│ - データベース初期化                                    │
│ - Redis キャッシュ接続                                  │
│ - Pending ジョブを確認                                  │
│ - テストジョブ作成（必要な場合）                        │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ main.py - Uvicorn 起動                                  │
│ startup event トリガー                                  │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ main.py - Startup Event Handler                         │
│ - DB インスタンス確認                                   │
│ - Redis 接続確認                                        │
│ - Pending ジョブの最終確認                              │
│ - crawl_worker.worker_loop() を asyncio.Task で起動    │
└─────────────────────────────────────────────────────────┘
    ↓
✅ API サーバー起動完了
    ↓
┌─────────────────────────────────────────────────────────┐
│ crawl_worker.worker_loop() - 自動ポーリング開始       │
│ 5秒ごと：pending ジョブをチェック                      │
└─────────────────────────────────────────────────────────┘
```

## 📋 Job ステータス遷移

```
ジョブ作成（api/crawl/start など）
        ↓
   pending
        ↓
┌─────────────────────────────────────────┐
│ Worker が pickup し、処理開始            │
│ - max_concurrent_jobs を確認            │
│ - 並行数 < max の場合、job を取得       │
│ - status を「processing」に更新         │
└─────────────────────────────────────────┘
        ↓
 processing （実際のクロール実行中）
        ↓
┌──────────────────┬──────────────────┐
│   成功            │    失敗          │
│                  │                  │
v                  v                  v
completed       failed         ⏳ リトライ
                                     ↓
                               pending
                                     ↓
                              [再度処理]
```

## 🚀 Pending → Auto Processing フロー

### シナリオ 1: startup.py でテストジョブ作成

```bash
# 1. コンテナ起動
docker-compose up

# ログ出力:
# startup.py:
# 2026-01-11 14:31:02 - 🤓 Creating test crawl session and jobs...
# 2026-01-11 14:31:02 - ✅ Created session: 32e6f70d-75b6-4d5c-8b3a-c7dca0f246ff
# 2026-01-11 14:31:02 - ✅ Created job: 49220cac-ae3e-486b-9e69-1c8c6afd18fc
# 2026-01-11 14:31:02 - 🔄 Will process 1 pending job(s) when worker starts

# main.py startup event:
# 2026-01-11 14:31:03 - 🤖 Starting crawl worker...
# 2026-01-11 14:31:03 - 🚀 Crawl worker started (max_concurrent=3, poll_interval=5s)

# main.py health check (約5秒後):
# 2026-01-11 14:31:08 - 📬 Found 1 pending jobs (available slots: 3)
# 2026-01-11 14:31:08 - 📥 Starting 1 jobs (active: 0/3)
# 2026-01-11 14:31:08 - 🔄 Processing job 49220cac: https://momon-ga.com (depth: 0)
```

### シナリオ 2: API 経由でジョブ作成

```bash
# POST /api/crawl/start
curl -X POST "http://localhost:8080/api/crawl/start?domain=example.com&page_limit=50"

# レスポンス:
# {
#   "status": "success",
#   "session_id": "abc123...",
#   "domain": "example.com",
#   "configuration": { "page_limit": 50, "max_depth": 3 }
# }

# → Job が pending 状態で DB に保存される
# → Worker の次のポーリング周期（5秒以内）で自動的に処理開始

# ポーリング開始:
# 2026-01-11 14:31:13 - 📬 Found 1 pending jobs (available slots: 3)
# 2026-01-11 14:31:13 - 📥 Starting 1 jobs (active: 0/3)
# 2026-01-11 14:31:13 - 🔄 Processing job abc123de: https://example.com (depth: 0)
```

## 🎯 ワーカーの動作詳細

### ポーリングサイクル

```python
while worker.is_running:
    # 1. 利用可能なスロット数を確認
    available_slots = max_concurrent_jobs - len(active_jobs)
    
    if available_slots > 0:
        # 2. 利用可能な数だけ pending ジョブを取得
        pending_jobs = get_pending_jobs(limit=available_slots)
        
        if pending_jobs:
            # 3. 各ジョブをタスク化して並行処理
            for job in pending_jobs:
                task = asyncio.create_task(process_job(job))
                active_jobs[job.job_id] = task
        else:
            # 4. Pending ジョブなし → アダプティブポーリング
            adaptive_poll_interval += 2  # 最大30秒まで増加
    
    # 5. 完了したタスクをクリーンアップ
    completed = [job_id for job_id, task in active_jobs.items() if task.done()]
    for job_id in completed:
        del active_jobs[job_id]
    
    # 6. ポーリング間隔まで待機
    await asyncio.sleep(adaptive_poll_interval)
```

### ジョブ処理フロー

```python
async def process_job(job: CrawlJob) -> bool:
    # 1. 実際のクロール実行
    result = await crawler_service.execute_crawl_job(...)
    
    if result:
        # 2. 抽出された URL をチェック
        urls_to_crawl = result.get("urls_to_crawl", [])
        
        if urls_to_crawl and job.depth < job.max_depth:
            # 3. 次の深度のジョブを自動作成
            await queue_child_jobs(
                session_id=job.session_id,
                depth=job.depth + 1,
                urls=urls_to_crawl
            )
        
        # 4. ジョブを completed にマーク
        return True
    else:
        return False
```

## 📊 メトリクスとモニタリング

### Worker Status エンドポイント

```bash
curl http://localhost:8080/api/crawl/worker/status | jq .
```

**レスポンス例**:
```json
{
  "status": "success",
  "worker": {
    "is_running": true,
    "active_jobs": 2,
    "available_slots": 1,
    "max_concurrent_jobs": 3,
    "poll_interval": 5,
    "global_queue": {
      "pending": 15,
      "processing": 2
    },
    "metrics": {
      "total_processed": 45,
      "total_successful": 43,
      "total_failed": 2,
      "total_queued": 187,
      "success_rate": "95.6%",
      "avg_job_time_ms": "1245ms",
      "uptime_seconds": "234.5s"
    }
  }
}
```

### Session Statistics エンドポイント

```bash
curl "http://localhost:8080/api/crawl/worker/session/{session_id}" | jq .
```

**レスポンス例**:
```json
{
  "status": "success",
  "session": {
    "session_id": "abc123...",
    "domain": "example.com",
    "status": "active",
    "progress": "42.5%",
    "total_jobs": 40,
    "completed_jobs": 17,
    "pending_jobs": 18,
    "processing_jobs": 5,
    "failed_jobs": 0,
    "avg_depth": 1.2
  }
}
```

## 🔌 設定パラメータ

### crawl_worker のデフォルト設定

```python
crawl_worker = CrawlWorker(
    max_concurrent_jobs=3,      # 同時処理ジョブ数
    poll_interval=5             # ポーリング間隔（秒）
)
```

### カスタマイズ

```python
# 同時処理ジョブ数を増やす
crawl_worker.max_concurrent_jobs = 5

# ポーリング間隔を短くする
crawl_worker.poll_interval = 2
```

## ⚠️ トラブルシューティング

### ジョブが処理されない

1. **Worker が実行中か確認**
   ```bash
   curl http://localhost:8080/health | jq '.components.crawl_worker'
   # 「operational」であることを確認
   ```

2. **Pending ジョブが存在するか確認**
   ```bash
   curl http://localhost:8080/health | jq '.database_stats'
   # pending > 0 であることを確認
   ```

3. **Worker ログを確認**
   ```bash
   docker-compose logs -f transparent_search_app | grep "crawl_worker"
   ```

### 処理が遅い

1. **同時処理数を増やす**
   ```python
   # max_concurrent_jobs を増やす（デフォルト: 3）
   ```

2. **ポーリング間隔を短くする**
   ```python
   # poll_interval を減らす（デフォルト: 5秒）
   ```

### メモリ使用量が多い

1. **同時処理数を減らす**
   ```python
   # max_concurrent_jobs を減らす
   ```

2. **キャッシュをクリア**
   ```bash
   curl -X POST "http://localhost:8080/api/crawl/invalidate?domain=example.com"
   ```

## 📝 まとめ

**自動処理フロー:**

1. ✅ `startup.py` → テストジョブ作成（pending 状態）
2. ✅ `main.py` → Uvicorn 起動 + Worker 起動
3. ✅ `crawl_worker.worker_loop()` → 5秒ごとにポーリング
4. ✅ Pending ジョブを自動検出 → 処理開始
5. ✅ クロール完了 → 子ジョブ作成
6. ✅ メトリクス更新 → API で監視可能

**追加ジョブの処理も同じ流れ:**

- API で `/api/crawl/start` を叩く
  ↓
- Job が pending で保存される
  ↓
- Worker が次のポーリング周期で自動処理
  ↓
- `/api/crawl/worker/status` で進捗監視可能
