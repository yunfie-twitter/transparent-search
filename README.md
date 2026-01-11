# 検索エンジン構築仕様書 (Project Code: Transparent Search)

## 1. システム概要
本システムは、特定のドメインまたはWeb全体を対象としたクローラー型検索エンジンである。
**「Zero-ETL」**思想に基づき、外部の検索サーバー（Elasticsearch等）を使用せず、PostgreSQL単体で高度な日本語全文検索とランキングを実現する。

### アーキテクチャ図
```mermaid
graph LR
    A[Crawler (Python)] --> B[PostgreSQL (PGroonga)]
    C[User/Frontend] --> D[API (FastAPI)]
    D --> B
```

## 2. 技術スタック選定

| コンポーネント | 技術選定 | 選定理由 |
| --- | --- | --- |
| **API Server** | FastAPI (Python 3.12+) | 非同期処理による高スループット、型安全性。 |
| **Database** | PostgreSQL 16 + PGroonga | 日本語全文検索に特化した拡張機能。標準の tsvector よりも高速で辞書メンテ不要。 |
| **Crawler** | httpx + BeautifulSoup4 | 非同期I/O (asyncio) での並行クロールに最適。 |
| **Infrastructure** | Docker Compose | 開発・デプロイの再現性確保。 |
| **Migrations** | Alembic | スキーマバージョン管理と自動マイグレーション。 |

## 3. データベース設計仕様 (PostgreSQL)
Googleのような検索品質を出すには、「コンテンツの関連度（TF-IDF/BM25）」と「ページの人気度（PageRank）」の掛け合わせが必須です。

### テーブル定義 (Schema)

#### sites (サイト情報)
ドメイン単位の管理（favicon / robots / sitemap）を行います。

#### pages (Webページ情報)
検索対象のメインテーブル。PGroongaインデックスを適用します。

#### images (ページ内画像)
ページ内の img を抽出し、URLとページを紐付けます。

#### search_queries / clicks (検索ログ・クリック学習)
クリック率によるランキング学習（オンライン学習の簡易版）のためのログです。

#### content_classifications (コンテンツ分類)
ページのコンテンツタイプ分類（記事、ツール、フォーラム等）。

#### query_clusters / intent_classifications (検索意図分類)
ユーザー検索意図の分類（informational, transactional, navigational等）。

## 4. アルゴリズム仕様

### 検索ランキング (Ranking Logic)
「コンテンツ一致度 + PageRank + クリック学習スコア」でソートします。

## 5. API仕様 (FastAPI)

### 検索API
- `GET /search` : 検索（query_id を返し、クリック学習で利用）
- `GET /suggest` : サジェスト（タイトルの前方一致）
- `POST /click` : クリックログ登録（click_score を更新）

### クローラーAPI

#### `POST /api/crawl/start`
新しいクロールセッションを開始します。

**パラメータ:**
```
domain: 対象ドメイン（必須）
```

**レスポンス:**
```json
{
  "status": "success",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "domain": "example.com",
  "created_at": "2026-01-11T08:58:43Z"
}
```

#### `POST /api/crawl/job/create`
新しいクロールジョブを作成します。

**パラメータ:**
```
session_id: セッションID（必須）
domain: 対象ドメイン（必須）
url: クロール対象URL（必須）
depth: 現在のクロール深さ（デフォルト: 0）
max_depth: 最大クロール深さ（デフォルト: 3）
enable_js_rendering: JavaScript実行有無（デフォルト: false）
```

**レスポンス:**
```json
{
  "status": "success",
  "job_id": "550e8401-e29b-41d4-a716-446655440001",
  "url": "https://example.com",
  "priority": 50,
  "page_value_score": 0.85,
  "created_at": "2026-01-11T08:58:43Z"
}
```

#### `POST /api/crawl/job/auto` ⭐ **NEW**
登録済みサイトをランダムに選択して自動的にクロール開始します。

**パラメータ:**
```
max_jobs: 1回で作成するジョブ数（デフォルト: 1, 最大: 100）
max_depth: クロール深さ（デフォルト: 3, 最大: 15）
```

**レスポンス:**
```json
{
  "status": "success",
  "message": "Auto-crawl started for 2 site(s)",
  "total_domains": 5,
  "crawled_domains": 2,
  "jobs": [
    {
      "domain": "example.com",
      "session_id": "550e8400-...",
      "job_id": "550e8401-...",
      "url": "https://example.com"
    },
    {
      "domain": "example.org",
      "session_id": "550e8402-...",
      "job_id": "550e8403-...",
      "url": "https://example.org"
    }
  ]
}
```

**使用例:**
```bash
# ランダムに1つクロール開始
curl -X POST http://localhost:8080/api/crawl/job/auto?max_jobs=1

# ランダムに3つ同時にクロール開始（深さ5）
curl -X POST http://localhost:8080/api/crawl/job/auto?max_jobs=3&max_depth=5
```

#### `POST /api/crawl/job/status`
クロールジョブのステータスを更新します。

**パラメータ:**
```
job_id: ジョブID（必須）
status: 新しいステータス (pending, running, completed, failed)（必須）
```

#### `POST /api/crawl/invalidate`
ドメインのキャッシュを無効化します。

**パラメータ:**
```
domain: 対象ドメイン（必須）
```

#### `GET /api/crawl/stats`
ドメインのクロール統計情報を取得します。

**パラメータ:**
```
domain: 対象ドメイン（必須）
```

**レスポンス:**
```json
{
  "status": "success",
  "domain": "example.com",
  "total_sessions": 5,
  "total_jobs": 42
}
```

## 6. クローラー仕様

* robots.txt を尊重（User-agent: * の Allow/Disallow を最低限対応）
* robots.txt の Sitemap 指定、もしくは /sitemap.xml を解析してURLを効率的に収集
* OGP / JSON-LD を抽出して pages に格納
* 画像URLを images に格納

### 実行例

```bash
python crawler.py https://example.com 200 10
```

## 7. セットアップ・実行方法

### 前提条件
- Docker & Docker Compose
- Python 3.12+
- PostgreSQL 16 + PGroonga

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/yunfie-twitter/transparent-search.git
cd transparent-search

# 環境設定
cp .env.example .env

# コンテナ起動（マイグレーション自動実行）
docker-compose up --build
```

### データベースマイグレーション

```bash
# マイグレーション確認
docker-compose exec app alembic current

# マイグレーション履歴表示
docker-compose exec app alembic history

# 最新版まで実行
docker-compose exec app alembic upgrade head
```

### API動作確認

```bash
# ヘルスチェック
curl http://localhost:8080/health

# 自動クロール開始
curl -X POST http://localhost:8080/api/crawl/job/auto?max_jobs=1
```

## 8. マイグレーション履歴

| ID | 説明 | ステータス |
|----|------|----------|
| 001 | 初期マイグレーション | ✅ 完了 |
| 002 | パフォーマンスインデックス | ✅ 完了 |
| 003 | 検索用テーブル（PGroonga） | ✅ 完了 |

詳細は [docs/DATABASE_MIGRATION.md](docs/DATABASE_MIGRATION.md) を参照してください。

## 9. トラブルシューティング

### エラー: `relation "pages" does not exist`

**原因:** データベースマイグレーションが未実行です。

**解決:**
```bash
docker-compose down
docker-compose up --build
docker-compose exec app alembic upgrade head
```

### エラー: `ImportError: cannot import name 'X' from 'app.Y'`

**原因:** モジュール構造またはインポートパスが間違っています。

**解決:** 
1. サブディレクトリに `__init__.py` が存在するか確認
2. インポートパスが絶対パス（`from app.module import X`）か確認

詳細は [docs/DATABASE_MIGRATION.md](docs/DATABASE_MIGRATION.md#トラブルシューティング) を参照してください。

## 10. ライセンス

MIT License

## 11. 作成者

[@yunfie-twitter](https://github.com/yunfie-twitter)
