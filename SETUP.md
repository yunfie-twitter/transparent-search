# セットアップガイド

## 環境設定

### 1. .env ファイルの作成

`.env.example` をコピーして `.env` ファイルを作成します：

```bash
cp .env.example .env
```

### 2. 環境変数の設定

`.env` ファイルを編集して、必要に応じて値を変更してください：

```env
# Database Configuration
POSTGRES_USER=user
POSTGRES_PASSWORD=your_secure_password  # 本番環境では必ず変更
POSTGRES_DB=search_engine
POSTGRES_PORT=5432

# Redis Configuration
REDIS_PORT=6379

# API Configuration
API_PORT=8000
API_HOST=0.0.0.0

# Database URL (for application)
DATABASE_URL=postgresql+asyncpg://user:your_password@db/search_engine
REDIS_URL=redis://redis:6379

# Crawler Configuration
CRAWLER_UA=TransparentSearchBot/1.0
```

### 3. Docker Compose で起動

```bash
# コンテナをビルド・起動
docker compose up

# バックグラウンドで起動
docker compose up -d

# ログを確認
docker compose logs -f api
```

### 4. API の動作確認

```bash
curl http://localhost:8000/
```

## 環境変数一覧

| 変数名 | デフォルト値 | 説明 |
|--------|------------|------|
| `POSTGRES_USER` | user | PostgreSQL ユーザー名 |
| `POSTGRES_PASSWORD` | password | PostgreSQL パスワード |
| `POSTGRES_DB` | search_engine | PostgreSQL データベース名 |
| `POSTGRES_PORT` | 5432 | PostgreSQL ポート番号 |
| `REDIS_PORT` | 6379 | Redis ポート番号 |
| `API_PORT` | 8000 | FastAPI ポート番号 |
| `API_HOST` | 0.0.0.0 | FastAPI ホストアドレス |
| `DATABASE_URL` | postgresql+asyncpg://user:password@db/search_engine | データベース接続文字列 |
| `REDIS_URL` | redis://redis:6379 | Redis 接続文字列 |
| `CRAWLER_UA` | TransparentSearchBot/1.0 | クローラー User-Agent |

## 注意事項

- **`.env` ファイルは `.gitignore` に含まれており、Git リポジトリには commit されません**
- 本番環境では `POSTGRES_PASSWORD` などのシークレット値を必ず変更してください
- `.env.example` ファイルはテンプレートとして保持されます

## トラブルシューティング

### コンテナが起動しない場合

1. `.env` ファイルが存在することを確認
2. ポート番号が重複していないか確認
3. Docker イメージを再ビルド：
   ```bash
   docker compose down
   docker compose build --no-cache
   docker compose up
   ```
