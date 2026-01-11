# クロール実行フロー診断ガイド

## 🔧 すべての修正内容

### 1️⃣ crawl_worker.py (修正完了)
- ✅ `process_job()` で job status を "processing" に更新 + `db.commit()` 追加
- ✅ 詳細なエラーログ追加
- ✅ タスク完了時の例外ハンドリング改善

### 2️⃣ crawler.py (修正完了)
- ✅ `execute_crawl_job()` で `await db.commit()` を明示的に追加
- ✅ `analyze_page()` で analysis 保存後に `await db.commit()`
- ✅ `update_crawl_job_status()` で status 更新後に `await db.commit()`

### 3️⃣ main.py (修正完了)
- ✅ lifespan コンテキストマネージャーで Worker を統合
- ✅ startup で Worker タスク開始
- ✅ shutdown で Worker 停止と待機

### 4️⃣ startup.py (修正完了)
- ✅ テストジョブ作成ロジック簡潔化
- ✅ 条件分岐改善 (total == 0 の場合のみ作成)

---

## 🚀 実行フロー

```
1. docker-compose up
   ↓
2. startup.py 実行
   - DB 初期化
   - Redis 接続
   - Pending ジョブをチェック (total == 0 なら test job 作成)
   ↓
3. Uvicorn (main.py) 起動
   - lifespan startup 開始
   - Worker.is_running = True
   - asyncio.create_task(worker_loop()) 実行
   ↓
4. Worker ポーリング開始 (5秒間隔)
   - pending jobs をクエリ
   - 利用可能スロットがあれば process_job() タスク化
   ↓
5. Job 処理
   - status → "processing" + db.commit()
   - execute_crawl_job() 実行
   - リンク抽出 → 子 job 作成 (pending)
   - status → "completed" + db.commit()
   ↓
6. API で監視
   - GET /health → worker_status, active_jobs
   - GET /api/crawl/worker/status → detailed metrics
   - GET /api/crawl/worker/session/{id} → progress
```

---

## 🔍 デバッグ手順

### Step 1: ログ確認

```bash
docker-compose up
```

ログを見て:
```
✅ Database initialized
✅ Redis cache connected
📝 Creating test crawl session and jobs...
✅ Created session: xxx
✅ Created job: yyy for https://momon-ga.com
📋 Updated Job Stats: total=1, pending=1, processing=0, completed=0, failed=0
🚀 Starting Transparent Search application...
🔧 Worker configuration: max_concurrent=3, poll_interval=5s
✅ Crawl worker task created
```

ここまでで **Worker が起動されている** ことを確認

### Step 2: Worker ポーリング開始確認 (~5秒後)

ログで以下を確認:
```
📬 Found 1 pending jobs (available slots: 3)
📥 Starting 1 jobs (active: 0/3)
🔄 Processing job xxxxxxxx: https://momon-ga.com (depth: 0)
```

### Step 3: クロール実行確認

```
🌐 [xxxxxxxx] Fetching: https://momon-ga.com
🔍 [xxxxxxxx] Extracting links from https://momon-ga.com
✅ [xxxxxxxx] Filtered to 12 internal links
📬 [xxxxxxxx] Adding 12 URLs to pending queue...
✨ [xxxxxxxx] Pending queue updated: 12 new jobs created
🎉 [xxxxxxxx] Completed: https://momon-ga.com
✅ Job xxxxxxxx completed in 1245ms → 12 URLs queued
```

### Step 4: API で確認

```bash
# Worker 全体状態
curl http://localhost:8080/api/crawl/worker/status | jq .

# 期待値:
{
  "status": "success",
  "worker": {
    "is_running": true,
    "active_jobs": 2,  # 処理中のジョブ
    "available_slots": 1,
    "max_concurrent_jobs": 3,
    "global_queue": {
      "pending": 11,  # 残りの pending jobs
      "processing": 2
    },
    "metrics": {
      "total_processed": 1,
      "total_successful": 1,
      "total_failed": 0,
      "total_queued": 12,
      "success_rate": "100.0%",
      "avg_job_time_ms": "1245ms",
      "uptime_seconds": "10.5s"
    }
  }
}
```

---

## ❌ トラブルシューティング

### Issue 1: Pending ジョブが処理されない

**確認項目:**

```bash
# 1. Worker が起動しているか
curl http://localhost:8080/health | jq '.worker'
# → "operational" であること

# 2. Pending ジョブが存在するか
curl http://localhost:8080/health | jq '.database_stats'
# → pending > 0 であること

# 3. Worker ログを確認
docker-compose logs -f transparent_search_app | grep "Found.*pending"
# → "Found 1 pending jobs" が出力されること
```

**解決方法:**

1. **Worker が起動していない場合:**
   ```bash
   docker-compose logs transparent_search_app | grep "Crawl worker"
   # エラーがあるか確認
   ```

2. **Pending ジョブがない場合:**
   ```bash
   # API で新しいジョブを作成
   curl -X POST "http://localhost:8080/api/crawl/start?domain=example.com"
   ```

3. **5秒以上待機してからログ確認**
   - ポーリング間隔が 5 秒のため、起動後 5 秒以上経過が必要

### Issue 2: Job が pending のまま

```bash
# DB に直接問い合わせ
docker exec transparent_search_postgres psql -U app_user -d transparent_search -c \
  "SELECT job_id, status, url FROM crawl_job LIMIT 10;"

# 期待値: status が pending から completed に変わる
```

**原因:**
- ❌ Worker が実際に実行されていない
- ❌ HTTP 関連のエラー (DNS 解決失敗など)
- ❌ DB commit が実行されていない

**解決:**
```bash
# ログで詳細確認
docker-compose logs -f transparent_search_app | grep -E "Error|Failed|❌"

# Worker 再起動
docker-compose restart transparent_search_app
```

### Issue 3: "completed" なのに子ジョブがない

**確認:**
```bash
# 子ジョブが作成されたか確認
docker exec transparent_search_postgres psql -U app_user -d transparent_search -c \
  "SELECT depth, COUNT(*) FROM crawl_job GROUP BY depth;"

# 期待値:
# depth | count
# ------|-------
#   0   |   1   (親ジョブ)
#   1   |  12   (子ジョブ)
```

**原因:**
- max_depth に到達している
- リンク抽出に失敗している

**確認:**
```bash
log | grep "Max depth\|Link extraction failed\|Filtered to 0"
```

### Issue 4: メモリ/CPU 使用率が高い

**調整:**
```python
# crawl_worker.py
crawl_worker = CrawlWorker(
    max_concurrent_jobs=2,  # 3 から 2 に減らす
    poll_interval=10        # 5 から 10 に増やす
)
```

---

## 📊 ヘルスチェック

### リアルタイム監視

```bash
# 5秒ごとに状態表示
watch -n 5 'curl -s http://localhost:8080/health | jq '

# または
while true; do
  echo "=== $(date) ==="
  curl -s http://localhost:8080/api/crawl/worker/status | jq '.worker.metrics'
  sleep 5
done
```

### DB ダイレクト確認

```bash
# Job 一覧
docker exec transparent_search_postgres psql -U app_user -d transparent_search -c \
  "SELECT status, COUNT(*) FROM crawl_job GROUP BY status;"

# セッション進捗
docker exec transparent_search_postgres psql -U app_user -d transparent_search -c \
  "SELECT session_id, domain, created_at FROM crawl_session ORDER BY created_at DESC LIMIT 5;"

# 最新のジョブ
docker exec transparent_search_postgres psql -U app_user -d transparent_search -c \
  "SELECT job_id, url, status, depth, created_at FROM crawl_job ORDER BY created_at DESC LIMIT 10;"
```

---

## ✅ 期待される動作

### 正常な場合

```
08:00:00 - App start
08:00:02 - Worker start
08:00:05 - First job picked (pending → processing)
08:00:10 - Job completed (processing → completed)
08:00:10 - Child jobs created (12 × pending)
08:00:15 - Child jobs start processing (pending → processing)
08:00:20 - Child jobs completed (processing → completed)
```

### 各エンドポイントの期待値

| エンドポイント | 期待値 |
|---|---|
| GET / | redis connected |
| GET /health | worker: operational |
| GET /admin | active_jobs増加 |
| GET /api/crawl/worker/status | total_processed > 0 |
| GET /api/crawl/worker/session/{id} | progress 増加 |

---

## 🎯 Next Steps

1. ✅ `docker-compose down -v && docker-compose up`
2. ✅ ログで Worker 起動確認
3. ✅ 5~10 秒待機
4. ✅ Job processing ログ確認
5. ✅ API で progress 確認
6. ✅ DB で job status 変化確認

これでクロール処理が自動化されます! 🚀
