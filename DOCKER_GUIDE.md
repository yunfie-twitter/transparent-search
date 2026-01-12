# 🐳 Docker Compose セットアップガイド

## 🎯 このガイドについて

このガイドでは、Docker Compose を使用して **Transparent Search** の全サービスを同時に立ち上げる方法を説明します。

---

## ✅ 前提条件

- ✔️ **Docker** 20.10+
- ✔️ **Docker Compose** 2.0+
- ✔️ **ディスク容量** 5GB 以上
- ✔️ **メモリ** 4GB 以上

### インストール確認

```bash
docker --version
# Docker version 20.10.x or higher

docker-compose --version
# Docker Compose version 2.x.x or higher
```

---

## 🚀 クイックスタート

### 1️⃣ リポジトリをクローン

```bash
git clone https://github.com/yunfie-twitter/transparent-search.git
cd transparent-search
```

### 2️⃣ すべてのサービスを起動

```bash
docker-compose up -d
```

### 3️⃣ サービスの状態を確認

```bash
docker-compose ps
```

**期待される出力:**
```
NAME                               STATUS          PORTS
transparent-search-postgres        Up (healthy)    5432/tcp
transparent-search-redis           Up (healthy)    6379/tcp
transparent-search-backend         Up (healthy)    8080/tcp
transparent-search-frontend        Up (healthy)    8081/tcp
```

### 4️⃣ ブラウザでアクセス

```
http://localhost:8081
```

---

## 📊 サービス構成

```
┌────────────────────────────────────────────────────────┐
│              🌐 ユーザーブラウザ                       │
│             (localhost:8081)                          │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│         Express.js Proxy Server                        │
│         (frontend:8081)                               │
│    - React ビルドファイル配信                         │
│    - /api/* を http://backend:8080 へプロキシ        │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│           FastAPI Backend                              │
│           (backend:8080)                              │
│    - 検索 API                                          │
│    - PostgreSQL アクセス                               │
│    - Redis キャッシュ                                  │
└───────┬──────────────────────────────┬──────────────────┘
        │                              │
        ▼                              ▼
  ┌───────────────┐          ┌──────────────┐
  │ PostgreSQL    │          │   Redis      │
  │ (postgres)    │          │  (redis)     │
  │ Port: 5432    │          │ Port: 6379   │
  └───────────────┘          └──────────────┘
```

---

## 🔌 ネットワーク接続

### 内部ネットワーク: `search_network`

- **バックエンド → PostgreSQL**: `postgresql://postgres:5432`
- **バックエンド → Redis**: `redis://redis:6379`
- **フロントエンド → バックエンド**: `http://backend:8080`
- **ブラウザ → フロントエンド**: `http://localhost:8081`

### ホストマシンからのアクセス

```bash
# フロントエンド
http://localhost:8081

# PostgreSQL（開発用）
psql -U search_user -h localhost -p 5432 -d transparent_search

# Redis（開発用）
redis-cli -h localhost -p 6379

# API Docs（フロントエンド経由）
http://localhost:8081/api/docs
```

---

## 📝 環境変数

### Docker 内部で使用される環境変数

`.env.docker` ファイルを参照：

```env
# Backend
DATABASE_URL=postgresql://search_user:search_password@postgres:5432/transparent_search
REDIS_URL=redis://redis:6379/0
LOG_LEVEL=INFO

# Frontend
PORT=8081
NODE_ENV=production
BACKEND_URL=http://backend:8080
REACT_APP_API_BASE_URL=/api
```

### 本番環境での変更

`.env.docker` を編集してから起動：

```bash
# 例: バックエンド URL を変更
echo "BACKEND_URL=https://api.example.com" >> .env.docker

docker-compose up -d
```

---

## 🛠️ よく使うコマンド

### サービスの起動・停止

```bash
# すべてのサービスを起動
docker-compose up -d

# すべてのサービスを停止
docker-compose stop

# すべてのサービスを削除（データベースは保持）
docker-compose down

# すべてのサービスを削除（データベースも削除）
docker-compose down -v
```

### 個別サービス操作

```bash
# 特定のサービスを再起動
docker-compose restart backend
docker-compose restart frontend

# 特定のサービスのログを表示
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f postgres
docker-compose logs -f redis

# すべてのログをリアルタイム表示
docker-compose logs -f
```

### デバッグ・検査

```bash
# コンテナ内でコマンドを実行
docker-compose exec backend bash
docker-compose exec frontend sh
docker-compose exec postgres psql -U search_user -d transparent_search

# サービスの詳細情報を確認
docker-compose ps --verbose

# イメージを再ビルド
docker-compose build
docker-compose build --no-cache
```

---

## 📊 ログとモニタリング

### リアルタイムログの監視

```bash
# すべてのサービスのログ
docker-compose logs -f --tail=50

# 特定サービスのみ
docker-compose logs -f backend --tail=50

# タイムスタンプ付き
docker-compose logs -f --timestamps
```

### 起動順序の確認

```bash
# 各サービスが健康であるか確認
docker-compose ps

# 特定サービスの health status
docker-compose exec backend curl -f http://localhost:8080/health || echo "Unhealthy"
```

### パフォーマンスモニタリング

```bash
# CPU/メモリ使用率
docker stats

# 特定コンテナのみ
docker stats transparent-search-backend
```

---

## 🔍 トラブルシューティング

### ❌ "Error: No such container"

```bash
# すべてのコンテナを削除してリセット
docker-compose down -v

# 再度起動
docker-compose up -d
```

### ❌ "Connection refused"

```bash
# PostgreSQL が起動しているか確認
docker-compose logs postgres

# health status を確認
docker-compose ps

# ネットワークをリセット
docker-compose down
docker network prune -f
docker-compose up -d
```

### ❌ "Port 8081 is already in use"

```bash
# 別のポートを使用
PORT=3000 docker-compose up -d

# または既存のプロセスを停止
lsof -i :8081
kill -9 <PID>
```

### ❌ "Build failed"

```bash
# キャッシュをクリアして再ビルド
docker-compose build --no-cache
docker-compose up -d

# または既存イメージを削除
docker-compose down
docker system prune -a
docker-compose up -d
```

### ❌ "Out of memory"

Docker の メモリ上限を増やす：
- **Mac**: Docker Desktop → Settings → Resources → Memory
- **Linux**: `/etc/docker/daemon.json` を編集
- **Windows**: Docker Desktop → Settings → Resources → Memory

```json
{
  "memory": 4294967296
}
```

---

## 🔐 セキュリティノート

### 本番環境での推奨事項

```bash
# 1. デフォルトのパスワードを変更
sed -i 's/search_password/YOUR_SECURE_PASSWORD/g' docker-compose.yml

# 2. PostgreSQL のバインドアドレスを制限
# docker-compose.yml の PostgreSQL ポートを削除または制限
ports:
  - "127.0.0.1:5432:5432"  # localhost only

# 3. Redis のバインドアドレスを制限
ports:
  - "127.0.0.1:6379:6379"  # localhost only

# 4. バックエンドを公開しない
# docker-compose.yml から backend の ports を削除

# 5. CORS を制限
# main.py の allow_origins を設定
```

---

## 📦 イメージサイズの最適化

### イメージサイズの確認

```bash
docker images

# 出力例:
# REPOSITORY                    TAG       SIZE
# transparent-search-backend    latest    680MB
# transparent-search-frontend   latest    245MB
```

### 未使用リソースのクリーンアップ

```bash
# ダングリングイメージを削除
docker image prune

# 使用されていないボリュームを削除
docker volume prune

# 使用されていないネットワークを削除
docker network prune

# 完全なシステムクリーンアップ
docker system prune -a --volumes
```

---

## 📈 スケーリング

### 複数のバックエンドインスタンス（Nginx 使用時）

```yaml
# docker-compose.yml
backend:
  build: .
  # ...
  deploy:
    replicas: 3
```

起動：
```bash
docker-compose up -d --scale backend=3
```

---

## 🔄 更新とアップグレード

### コードの更新後

```bash
# ソースコードを更新
git pull origin main

# イメージを再ビルド
docker-compose build

# 新しいイメージで再起動
docker-compose up -d
```

### 本番環境での無停止更新

```bash
# Blue-Green Deployment
# 1. 新しい環境を起動
docker-compose -f docker-compose.new.yml up -d

# 2. テスト
curl http://localhost:8082  # 新環境

# 3. 切り替え（Nginx を使用）
# nginx config を更新して upstream を切り替え

# 4. 古い環境を停止
docker-compose down
```

---

## 📚 参考資料

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [SETUP_GUIDE.md](./SETUP_GUIDE.md) - ローカル開発ガイド
- [README_FRONTEND.md](./README_FRONTEND.md) - フロントエンドドキュメント

---

## 🎯 起動確認チェックリスト

```bash
# ✅ すべてのサービスが起動しているか
docker-compose ps
# Status: Up (healthy) for all services

# ✅ フロントエンドにアクセスできるか
curl http://localhost:8081
# Response: HTML content

# ✅ API が応答しているか
curl http://localhost:8081/api/docs
# Response: Swagger UI

# ✅ ヘルスチェック
curl http://localhost:8081/health
# Response: {"status": "healthy", ...}

# ✅ 検索が機能するか
curl "http://localhost:8081/api/search?q=test&limit=10"
# Response: {"data": [...], "meta": {...}}
```

---

## 🎊 完成！

✨ すべてのサービスが Docker Compose で同時に起動しました！

次のステップ：
1. http://localhost:8081 で検索を試す
2. http://localhost:8081/api/docs で API を確認
3. 必要に応じてカスタマイズ

🚀 Happy searching!
