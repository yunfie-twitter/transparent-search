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

#### sites (サイト情報)
ドメイン単位の管理（favicon / robots / sitemap）を行います。

#### pages (Webページ情報)
検索対象のメインテーブル。PGroongaインデックスを適用します。

#### images (ページ内画像)
ページ内の img を抽出し、URLとページを紐付けます。

#### search_queries / clicks (検索ログ・クリック学習)
クリック率によるランキング学習（オンライン学習の簡易版）のためのログです。

## 4. アルゴリズム仕様

### 検索ランキング (Ranking Logic)
「コンテンツ一致度 + PageRank + クリック学習スコア」でソートします。

## 5. API仕様 (FastAPI)

* `GET /search` : 検索（query_id を返し、クリック学習で利用）
* `GET /suggest` : サジェスト（タイトルの前方一致）
* `POST /click` : クリックログ登録（click_score を更新）

## 6. クローラー仕様

* robots.txt を尊重（User-agent: * の Allow/Disallow を最低限対応）
* robots.txt の Sitemap 指定、もしくは /sitemap.xml を解析してURLを効率的に収集
* OGP / JSON-LD を抽出して pages に格納
* 画像URLを images に格納

### 実行例

```bash
python crawler.py https://example.com 200 10
```
