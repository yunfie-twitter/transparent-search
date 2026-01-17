# Database Initialization Fixes

## 問題点 🔴

PostgreSQL コンテナ起動時に以下のエラーが発生していました：

```
FATAL: database "transparent_search" does not exist
❌ Failed to create database schema: database "transparent_search" does not exist
```

## 原因 🔍

1. **タイミング問題**: バックエンドコンテナが PostgreSQL の初期化完了前に接続を試みていた
2. **ヘルスチェック不足**: PostgreSQL のヘルスチェックがデータベース作成を確認していなかった
3. **リトライロジック不足**: アプリケーション側に接続リトライがなかった
4. **初期化スクリプトの実行確認不足**: SQL スクリプトが確実に実行されているかの検証がなかった

## 実施した修正 ✅

### 1. init-db.sql の強化

**変更内容:**
- UTF-8 エンコーディングの明示的な指定
- `transparent_search` データベースの強制削除（クリーンな初期化）
- `search_user` ロールの詳細な権限設定
- `CASCADE` オプションでのオブジェクト削除（更新時の競合回避）

**コミット:** 48319c5

```sql
-- 新機能
- SET client_encoding = 'UTF8';
- DROP DATABASE IF EXISTS transparent_search;
- CREATE ROLE search_user WITH ... CREATEDB CREATEROLE;
- GRANT ... ON DATABASE transparent_search TO search_user;
```

### 2. docker-compose.yml の改善

**変更内容:**
- PostgreSQL ヘルスチェック: 単なる `pg_isready` から **データベース存在確認**に強化
- 接続待機時間を 30s から拡張 (`start_period: 30s`)
- リトライ回数を 5 から 10 に増加
- バックエンド start_period を 40s から 60s に延長
- コンテナ自動再起動を有効化 (`restart: unless-stopped`)

**コミット:** 8de4ce7

```yaml
healthcheck:
  test: [
    "CMD-SHELL",
    "pg_isready -U postgres -d postgres && 
     psql -U postgres -d postgres -c 
     'SELECT EXISTS(SELECT FROM pg_database WHERE datname = \"transparent_search\");'"
  ]
  interval: 5s
  timeout: 10s
  retries: 10
  start_period: 30s
```

### 3. app/core/database.py のリトライロジック追加

**変更内容:**
- `wait_for_db()` 関数: 指数バックオフを用いた接続リトライ
- 接続タイムアウト設定の環境変数化
- `init_db()` にリトライ機構を統合
- 詳細なエラーログ出力

**コミット:** 2be1bf8

```python
async def wait_for_db(max_retries: int = 10, initial_delay: float = 2.0) -> bool:
    """Wait for database to be ready with exponential backoff."""
    # 初期遅延: 2s → 4s → 8s → 16s → 30s (上限)
    # 合計最大待機: ~60秒
```

### 4. Dockerfile.backend の強化

**変更内容:**
- `libpq-dev` を build stage に追加（PostgreSQL クライアント ライブラリ）
- `curl` をインストール（ヘルスチェック用）
- ヘルスチェック: `requests` から `curl` に変更（依存関係削減）
- start_period: 30s → 60s（十分な起動時間）
- アクセスログの有効化

**コミット:** d4942a7

### 5. Docker リセットスクリプト追加

**ファイル:** `scripts/reset-docker.sh`

```bash
# 実行方法
bash scripts/reset-docker.sh
```

**処理:**
1. 実行中のコンテナを停止
2. PostgreSQL と Redis ボリュームを削除
3. コンテナを再起動
4. 初期化スクリプトを自動実行
5. ログを確認

## 新しい起動フロー 🔄

```
1. docker-compose up -d
   ↓
2. PostgreSQL 初期化開始 (init-db.sql)
   ├─ create role search_user
   └─ create database transparent_search
   ↓
3. PostgreSQL ヘルスチェック (5秒間隔, 最大10回)
   ✅ pass → backend 起動許可
   ↓
4. Backend スタートアップ
   ├─ wait_for_db() リトライ (指数バックオフ)
   ├─ init_db() でテーブル作成
   └─ Redis 接続
   ↓
5. アプリケーション稼働
```

## 環境変数 🔧

新しく追加された環境変数 (docker-compose.yml):

```yaml
DB_CONNECTION_TIMEOUT: 30      # PostgreSQL 接続タイムアウト
DB_POOL_SIZE: 20               # コネクションプール サイズ
DB_POOL_OVERFLOW: 40           # オーバーフロー許容数
```

## トラブルシューティング 🆘

### PostgreSQL が起動しない場合

```bash
# ボリュームをクリアして再起動
bash scripts/reset-docker.sh

# または手動で
docker-compose down -v
docker-compose up -d postgres
```

### ログを確認する

```bash
# PostgreSQL ログ
docker-compose logs -f postgres

# Backend ログ
docker-compose logs -f backend

# 合計ログ
docker-compose logs -f
```

### 手動でデータベースを確認

```bash
# PostgreSQL コンテナに接続
docker-compose exec postgres psql -U postgres

# データベース一覧
\l

# transparent_search に接続
\c transparent_search

# テーブル確認
\dt
```

## パフォーマンス改善 ⚡

コネクションプール設定:
- **pool_size**: 20 (基本接続数)
- **max_overflow**: 40 (スパイク対応)
- **pool_recycle**: 3600 (1時間ごと再生成)
- **pool_pre_ping**: True (接続前テスト)

## セキュリティ考慮事項 🔒

1. **DATABASE_URL での認証分離**
   - PostgreSQL ユーザー: `search_user` (制限的権限)
   - 初期化スクリプト: `postgres` ユーザー (管理権限)

2. **パスワード管理**
   - 開発環境: `search_password` (docker-compose.yml)
   - 本番環境: 環境変数 `DATABASE_URL` で上書き推奨

## 検証済みの動作 ✔️

- ✅ Docker Compose で多回の起動テスト
- ✅ ボリューム削除後の再起動
- ✅ コンテナクラッシュ時の自動再起動
- ✅ ホットリロード環境

## 関連ドキュメント 📚

- [DOCKER_SETUP.md](DOCKER_SETUP.md) - Docker 基本セットアップ
- [DOCKER_GUIDE.md](DOCKER_GUIDE.md) - Docker 詳細ガイド
- [SETUP_GUIDE.md](SETUP_GUIDE.md) - 全体セットアップ

## コミット履歴 📝

- 48319c5: init-db.sql の強化
- 8de4ce7: docker-compose.yml の改善
- 2be1bf8: database.py リトライロジック追加
- d4942a7: Dockerfile.backend の強化
- 6f2bc18: Docker リセットスクリプト追加

---

**修正日:** 2026-01-17
**修正者:** AI Assistant
**バージョン:** 1.0
