# Advanced Search Pipeline

## 概要

Transparent Search は、ユーザー クエリに対して高度な検索パイプラインを実装しています。通常の検索から曖昧なクエリまで、すべてのケースに対応可能です。

## 検索パイプライン

```
Input Query
    ↓
[1] Normalizer
    • 小文字化
    • トリム
    • 特殊文字処理
    ↓
[2] Intent Classifier
    • ユーザーの意図検出
    • 検索タイプ分類 (question/navigation/product_research など)
    • 信頼度スコア
    ↓
[3] BM25 Full-Text Search
    • PGroonga による全文検索
    • Title, H1, Content マッチング
    • 関連度スコア計算
    ↓
[4] Fuzzy Matching & Reranking
    • タイポ/スペルミス許容
    • トークンベースマッチング
    • シーケンスマッチング
    ↓
[5] Ambiguity Control (曖昧度制御)
    • マッチの確実性評価
    • 曖昧な結果にペナルティ
    • ユーザー指定の曖昧度感度で調整
    ↓
Final Ranked Results
```

## エンドポイント

### 1. 標準検索 (Keyword-based)

```bash
GET /search?q=<query>
```

**パラメータ:**
- `q` (str): 検索クエリ
- `limit` (int): 結果数 (デフォルト: 10)
- `offset` (int): ページネーション (デフォルト: 0)
- `explain` (bool): スコア詳細を含める
- `filter_tracker_risk` (str): トラッカーリスク: clean/minimal/moderate/heavy/severe
- `content_types` (str): コンテンツタイプフィルタ (カンマ区切り)

**レスポンス例:**

```json
{
  "meta": {
    "query": "Python async",
    "took_ms": 124,
    "count": 10,
    "intent": {
      "primary": "question",
      "confidence": 0.87
    }
  },
  "data": [
    {
      "id": 12345,
      "title": "Async/Await in Python",
      "url": "https://example.com/async",
      "score": 45.67,
      "domain": "example.com",
      "favicon": "https://example.com/favicon.ico",
      "content_type": "text_article",
      "tracker_risk_score": 0.3
    }
  ]
}
```

### 2. 曖昧検索 (Fuzzy Search)

```bash
GET /search/fuzzy?q=<query>&ambiguity=<0.0-1.0>
```

**新規パラメータ:**
- `ambiguity` (float): 曖昧度制御
  - `0.0`: 曖昧な結果も含める (広い検索)
  - `0.5`: バランス型 (デフォルト)
  - `1.0`: 完全一致のみ (厳密な検索)

**レスポンス例:**

```json
{
  "meta": {
    "query": "pyton async",
    "took_ms": 156,
    "count": 8,
    "ambiguity_control": 0.5,
    "intent": {
      "primary": "question",
      "confidence": 0.85
    }
  },
  "data": [
    {
      "title": "Python Async/Await Tutorial",
      "url": "https://example.com/python-async",
      "relevance_score": 0.92,
      "explain": {
        "fuzzy_match": {
          "title_match": 0.95,
          "content_match": 0.88,
          "url_match": 0.82,
          "domain_relevance": 0.9
        },
        "ambiguity_control": 0.5,
        "intent": "question"
      }
    }
  ]
}
```

### 3. マッチング説明 (Debug)

```bash
GET /search/fuzzy/explain/python?result_title=Python+Async&result_url=https://example.com/async
```

**レスポンス:**

```json
{
  "query": "python",
  "result": "Python Async/Await Tutorial",
  "explanation": {
    "title_match": 1.0,
    "content_match": 0.88,
    "url_match": 0.82,
    "domain_relevance": 0.9
  },
  "interpretation": {
    "title_match": "⚡ Excellent match",
    "content_match": "✓ Good match",
    "url_match": "✓ Good match",
    "domain_relevance": "✓ Good match"
  }
}
```

## コンテンツタイプ分類

高度な ML のようなパターンマッチングで 9 つのコンテンツタイプを自動分類:

| タイプ | パターン例 | スコア |
|------|----------|-------|
| `text_article` | /blog/, /article/, /news/ | 0-1 |
| `video` | youtube, vimeo, `<video>` | 0-1 |
| `image` | /gallery/, imgur, flickr | 0-1 |
| `forum` | reddit, stackoverflow, /forum/ | 0-1 |
| `tool` | /app/, /calculator/, API | 0-1 |
| `product` | /shop/, amazon, ebay, 価格 | 0-1 |
| `documentation` | /docs/, /manual/, code blocks | 0-1 |
| `manga` | mangadex, /manga/, /chapter/ | 0-1 |
| `academic` | arxiv, scholar, doi | 0-1 |

**分類方法:**

1. **URL パターンマッチング** (30 ポイント)
2. **コンテンツパターンマッチング** (40 ポイント)
3. **Schema.org / JSON-LD** (30 ポイント)

合計 100 ポイント中のスコアを信頼度に正規化 (0-1)。

## Favicon 取得

複数のフォールバック戦略を使用:

```
1. HTML head tags
   • rel="icon"
   • rel="shortcut icon"
   • rel="apple-touch-icon"
   ↓ (見つからない場合)
2. /favicon.ico
   ↓ (見つからない場合)
3. /apple-touch-icon.png
   ↓ (見つからない場合)
4. 一般的な代替パス
   • /favicon.png
   • /assets/favicon.ico
   • /images/favicon.ico
   など
```

## JS レンダリング

Playwright を使用した動的コンテンツのサポート:

### フォールバック シーケンス

```
1. 通常の HTTP リクエスト
   ↓ (失敗または空の結果)
2. Playwright でレンダリング
   • JavaScript 実行
   • Network idle 待機
   • セレクタ待機 (オプション)
   ↓ (成功)
3. 通常クロールと同じ処理
```

### 設定

```python
# Playwright ブラウザ初期化
await js_renderer.initialize()

# ページレンダリング
html = await js_renderer.render(
    url="https://example.com",
    wait_for_selector=".content",  # オプション
    wait_for_timeout=5000
)

# スクリーンショット付き
html, screenshot = await js_renderer.render_with_screenshots(
    url="https://example.com",
    screenshot_path="/tmp/page.png"
)

# JavaScript データ抽出
data = await js_renderer.extract_data(
    url="https://example.com",
    script="return { title: document.title, links: document.links.length }"
)
```

## 被リンク (Backlinks)

### 位置づけ

- **補助指標** としても機能
- **メイン指標ではない**
- 他の信号 (content quality, match relevance) が優先

### 使用方法

```sql
-- 被リンク情報の保存
INSERT INTO backlinks (source_page_id, target_url, anchor_text, created_at)
VALUES (...)

-- ランキング計算時に補助
WHERE ...
ORDER BY (
  bm25_score * 0.6 +  -- メイン
  backlink_count * 0.1 +  -- 補助
  content_quality * 0.3
)
```

## Intent Detector (意図分類)

自動的に検索意図を判定:

| 意図 | キーワード例 | 推奨コンテンツ |
|------|-------------|---------------|
| `question` | what, how, why, can | text_article, forum |
| `navigation` | login, home, download | tool |
| `product_research` | buy, price, review | product, forum |
| `research` | study, academic, paper | academic, text_article |
| `debugging` | error, bug, fix | forum, text_article |
| `transactional` | shop, buy, cart | product, tool |

## 曖昧度スコア (Ambiguity Score)

### 定義

```
Ambiguity = 1 - Confidence
```

低い曖昧度 (0.0-0.3) → 明確な一致
中程度の曖昧度 (0.3-0.7) → 部分的一致
高い曖昧度 (0.7-1.0) → 不確実な一致

### 計算方法

```python
# 各フィールドのマッチスコア
title_match = 0.95
content_match = 0.80
url_match = 0.65

# 平均
match_score = (0.95 + 0.80 + 0.65) / 3 = 0.80

# 分散 (バラつき)
variance = ((0.95-0.80)^2 + (0.80-0.80)^2 + (0.65-0.80)^2) / 3
variance = (0.0225 + 0 + 0.0225) / 3 = 0.015

# 曖昧度
ambiguity = min(variance, 1.0) = 0.015
```

分散が大きい = スコアがばらついている = 曖昧
ペナルティ = ambiguity × ambiguity_control × 0.1

## ユースケース

### 1. 正確な検索

```bash
curl "http://localhost:8080/search/fuzzy?q=React+hooks&ambiguity=1.0"
```

→ "React hooks" に完全に一致する結果のみ

### 2. 緩い検索 (タイポ許容)

```bash
curl "http://localhost:8080/search/fuzzy?q=reackt+hokks&ambiguity=0.0"
```

→ 「React hooks」のタイポでも引っかかる

### 3. バランス型 (推奨)

```bash
curl "http://localhost:8080/search/fuzzy?q=async+python&ambiguity=0.5"
```

→ 関連度が高い結果を優先しつつ、タイポも許容

### 4. コンテンツタイプフィルタ

```bash
curl "http://localhost:8080/search?q=python+tutorial&content_types=text_article,video"
```

→ 記事とビデオのみ表示

### 5. デバッグ

```bash
curl "http://localhost:8080/search/fuzzy/explain/python?result_title=Python+Async&result_url=https://example.com/async" | jq
```

→ マッチング理由を詳細表示

## インストール & セットアップ

### 1. 依存関係インストール

```bash
pip install -r app/requirements.txt
```

### 2. Playwright ブラウザ インストール

```bash
playwright install chromium
```

### 3. 環境変数

```bash
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/search"
export REDIS_URL="redis://localhost:6379"
export CRAWLER_UA="TransparentSearchBot/1.0"
```

### 4. 起動

```bash
docker compose up
```

## パフォーマンス

| 操作 | 平均応答時間 | 備考 |
|------|-----------|------|
| 標準検索 | 50-200ms | キャッシュあり時 10ms |
| 曖昧検索 | 100-300ms | リランキング含む |
| Favicon 取得 | 500-2000ms | フォールバック複数試行 |
| JS レンダリング | 5000-15000ms | 非同期、オプション |

## トラッカーリスク スコア

### 計算方法

```
0-2 個: clean (0.0)
3-4 個: minimal (0.3)
5-6 個: moderate (0.6)
7-8 個: heavy (0.8)
9+ 個: severe (1.0)
```

検出トラッカー:
- Google Analytics
- Facebook Pixel
- Google Ads
- Mixpanel, Amplitude
- Hotjar, Intercom
- Rollbar, Sentry

## 今後の改善

- [ ] Vector Search (FAISS/Milvus)
- [ ] Learning to Rank (LTR) モデル
- [ ] ユーザー行動に基づくパーソナライズ
- [ ] A/B テスト フレームワーク
- [ ] リアルタイム検索トレンド
- [ ] ユーザーフィードバックループ
