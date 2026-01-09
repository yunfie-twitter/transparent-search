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

## 3. データベース設計仕様 (PostgreSQL)
Googleのような検索品質を出すには、「コンテンツの関連度（TF-IDF/BM25）」と「ページの人気度（PageRank）」の掛け合わせが必須です。

### テーブル定義 (Schema)

#### 1. pages (Webページ情報)
検索対象のメインテーブル。PGroongaインデックスを適用します。

```sql
CREATE TABLE pages (
    id SERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    content TEXT, -- HTMLタグ除去済みの本文
    pagerank_score DOUBLE PRECISION DEFAULT 1.0, -- ページランク用スコア
    last_crawled_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- PGroonga Extension有効化
CREATE EXTENSION IF NOT EXISTS pgroonga;

-- 全文検索用インデックス (タイトルと本文を重み付けしてインデックス化)
CREATE INDEX pgroonga_content_index ON pages 
USING pgroonga (title, content);
```

#### 2. links (リンク関係 - PageRank計算用)
ページ間のリンク構造を保持し、再帰的な重要度計算に使用します。

```sql
CREATE TABLE links (
    src_page_id INTEGER REFERENCES pages(id),
    dst_page_id INTEGER REFERENCES pages(id),
    PRIMARY KEY (src_page_id, dst_page_id)
);
```

## 4. アルゴリズム仕様

### 検索ランキング (Ranking Logic)
単なるキーワードマッチではなく、「スコア = (コンテンツ一致度 × 重み) + (PageRankスコア × 重み)」 でソートします。

**SQL実装イメージ:**
```sql
SELECT 
    id, title, url,
    (pgroonga_score(tableoid, ctid) * 1.5) + (pagerank_score * 0.5) AS total_score
FROM pages
WHERE title &@~ '検索キーワード' OR content &@~ '検索キーワード'
ORDER BY total_score DESC
LIMIT 20;
```
* `&@~` 演算子: PGroongaの全文検索マッチ（表記ゆれ対応）

### 簡易PageRank更新バッチ
クローラーがリンクを収集した後、定期的に以下のSQL関数を実行してスコアを更新します（Googleの初期アルゴリズムの簡易版）。

```sql
-- 簡易実装: 反復計算でスコアを配分
UPDATE pages p
SET pagerank_score = 0.15 + 0.85 * (
    SELECT COALESCE(SUM(src.pagerank_score / link_count.cnt), 0)
    FROM links l
    JOIN pages src ON src.id = l.src_page_id
    JOIN (SELECT src_page_id, COUNT(*) as cnt FROM links GROUP BY src_page_id) link_count 
    ON link_count.src_page_id = src.id
    WHERE l.dst_page_id = p.id
);
```

## 5. API仕様 (FastAPI)
エンドポイントはシンプルに保ち、レスポンス速度を最優先します。

**GET /search**

* **Params:**
    * `q`: 検索クエリ (必須)
    * `limit`: 件数 (default: 10)
    * `offset`: ページネーション用
* **Response:**
    * 検索時間、ヒット件数、結果リスト（タイトル、URL、スニペット）

**実装ポイント:**
FastAPIの Dependency Injection を使い、DBセッション管理を行います。

```python
@app.get("/search")
async def search(q: str, db: AsyncSession = Depends(get_db)):
    start_time = time.time()
    # SQLModel または SQLAlchemy でクエリ実行
    # PGroonga特有の演算子は text() で直接記述が必要な場合あり
    results = await db.execute(text(...), {"q": q})
    # ...
    return {
        "meta": {"took": time.time() - start_time},
        "data": results
    }
```

## 6. インフラ構築 (Docker Compose)
PGroongaを含んだイメージを使用するのが最大のポイントです。これで日本語対応の手間がゼロになります。

**docker-compose.yml**
```yaml
services:
  db:
    image: groonga/pgroonga:3.1.5-alpine-16
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
      POSTGRES_DB: search_engine
    volumes:
      - pg_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d search_engine"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build: ./app
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://user:password@db/search_engine
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./app:/code # ホットリロード用

volumes:
  pg_data:
```

## Pro Tips for "Transparent Edge"
* **非同期クローラー:** クローラー側は `asyncio` をフル活用し、DNS解決待ち時間を極小化してください。
* **スニペット生成:** PGroongaには `pgroonga_snippet_html()` という関数があり、検索語句をハイライトしたHTML断片をDB側で高速に生成できます。これをAPIレスポンスにそのまま含めると、フロントエンドの実装が非常に楽になります。
