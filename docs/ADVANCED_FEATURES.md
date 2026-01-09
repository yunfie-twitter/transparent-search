# 高度な機能ガイド

## 概要

3つの強力な自動分析機能が統合されました：

1. **トラッカー検出＆危険度スコアリング**  
   ページ内のプライバシー侵害的なトラッキングスクリプトを検出

2. **コンテンツタイプ自動判定**  
   テキスト記事、漫画、動画、画像、フォーラム、ツール等を自動分類

3. **検索意図ラベリング**  
   クエリから「質問型」「調査型」「購買型」等の意図を自動判定

---

## 1. トラッカー検出（Tracker Detection）

### 概要

各ページをクロール時に、以下を自動検出：
- Googleアナリティクス、Facebook Pixel 等のトラッキングスクリプト
- セッション記録（Hotjar、FullStory）等の高リスク追跡
- 広告ネットワーク（Criteo、Google Ads）
- ソーシャルピクセル

### 検出方法

**4つの検出パターン：**

1. **Script Tags** (`<script src="...">`)
   - URLのドメインが既知トラッカーマッチ

2. **Tracking Pixels** (`<img src="...?pixel...">`)
   - 1x1ピクセルなど、明らかなビーコン

3. **iframes**
   - YouTube、Vimeo、広告ネットワークの判定

4. **Inline Scripts**
   - スクリプト内の特定パターン検出
   - 例：`ga(`, `gtag(`, `fbq(` など

### リスクレベル（1-5）

| レベル | カテゴリ | 例 | リスク |
|--------|---------|----|---------|
| 1 | 最小限 | 基本的なアナリティクス | ユーザー数・基本行動 |
| 2 | 低 | Google Analytics、Amplitude | クリック・ページビュー |
| 3 | 中 | Segment、Twitter Pixel | 詳細な行動プロファイリング |
| 4 | 高 | Google Ads、Facebook Pixel | クロスサイト追跡、リターゲティング |
| 5 | 極度 | Hotjar、FullStory、SessionCam | **セッション記録・スクリーンショット** |

### Tracker Risk Score 計算

```
risk_score = 1.0 - (平均リスクレベル / 5) - (トラッカー数 * 0.05)

リスク分類：
- 0.9+ : "clean" (クリーン)
- 0.7~0.9 : "minimal_trackers"
- 0.5~0.7 : "moderate_trackers"
- 0.3~0.5 : "heavy_trackers"
- <0.3 : "severe_tracking_risk" (⚠️ 要注意)
```

### DB テーブル

```sql
-- 検出されたトラッカー
SELECT
    p.title, p.url, p.tracker_risk_score,
    COUNT(pt.id) as tracker_count,
    STRING_AGG(t.name, ', ') as trackers
FROM pages p
LEFT JOIN page_trackers pt ON p.id = pt.page_id
LEFT JOIN trackers t ON pt.tracker_id = t.id
WHERE p.tracker_risk_score < 0.3  -- 高リスク
GROUP BY p.id;
```

### 検索スコアへの組み込み

```
FinalScore = BaseScore * (1.0 - 0.3 * (1.0 - tracker_risk_score))

リスク高 (0.2) → スコア 70% に減
リスク低 (0.9) → スコア 97% に減
クリーン (1.0) → スコア 100% (減衰なし)
```

---

## 2. コンテンツタイプ自動判定（Content Classification）

### サポートするタイプ

| タイプ | 特徴 | 判定指標 |
|--------|------|----------|
| **text_article** | ブログ、技術記事、解説ページ | テキスト>1000字、見出し構造、段落 |
| **manga** | ウェブ漫画、Webtoon | 画像多い、連載構造、prev/next |
| **video** | YouTube、ニコ動、自前プレイヤー | `<video>` または iframe 含む |
| **image** | 画像素材、ギャラリー | 画像>20個、テキスト<300字 |
| **forum** | 掲示板、Q&A、SNS | コメント、ユーザー生成コンテンツ |
| **tool** | Webアプリ、Webツール | フォーム、入力欄、インタラクティブ |
| **unknown** | 分類不可 | 信頼度<0.3 |

### 判定メトリクス

```python
Metrics = {
    'text_length': ページ内テキスト長,
    'image_ratio': 画像数 / コンテンツブロック数,
    'has_video': <video>または動画iframe,
    'has_form': フォーム要素の有無,
    'image_count': 画像総数,
    'code_block_count': <pre><code>ブロック数,
    'comment_indicators': コメント関連要素,
    'has_toc': 目次構造,
    'is_series': 前話/次話リンク,
}
```

### スコアリング例

**テキスト記事:**
```
text_length > 1000      +0.3
image_ratio 0.1~0.4    +0.2
heading構造            +0.2
目次あり              +0.15
段落>10個              +0.15
= 0.95 (高信頼度)
```

**漫画:**
```
image_ratio > 0.6      +0.3
image>5 & text<500    +0.3
連載構造               +0.4
= 1.0 (完全一致)
```

### DB テーブル

```sql
SELECT
    content_type,
    type_confidence,
    text_length,
    image_count,
    has_video,
    classified_at
FROM content_classifications
WHERE page_id = 42;
```

### タイプ別の最適化評価軸（今後）

#### テキスト記事向け
- 読了可能性（ページ分割少、導線良好）
- 論理構造・結論到達
- 反証・デメリット記載（反証耐性）
- 一次情報へのリンク距離

#### 動画向け
- 再生安定性（バッファ、解像度切替）
- チャプター・目次
- 字幕可否
- 広告侵入頻度

#### 漫画向け
- 読書導線（前後話リンク）
- 画像品質（解像度・圧縮率）
- 読書中広告の侵入度

---

## 3. 検索意図ラベリング（Intent Detection）

### サポートする意図タイプ

| 意図 | パターン | 例 |
|------|---------|-----|
| **question** | 「What/Why/How?」で始まる | "How to install docker?" |
| **navigation** | 特定サイトへのアクセス | "facebook login", "github" |
| **transactional** | 購買・取引目的 | "buy python book", "shop" |
| **debugging** | エラー解決 | "python error fix", "クラッシュ" |
| **research** | 学習・調査 | "tutorial", "documentation" |
| **product_research** | 製品比較・レビュー | "best VPN review", "compare" |
| **informational** | 一般情報取得 | デフォルト意図 |

### ルールベースの検出

```python
INTENT_PATTERNS = {
    'question': [
        r'^(\w+\s)?(?:what|which|who|when|where|why|how)',
        r'(\?)$',
    ],
    'debugging': [
        r'\b(?:error|bug|fix|issue|crash)',
    ],
    'transactional': [
        r'\b(?:buy|purchase|price|shop)',
    ],
}
```

### 日本語対応

```python
'question': r'\s(?:とは|ですか)'
'debugging': r'\b(?:エラー|バグ|動かない|クラッシュ)'
'product_research': r'\b(?:レビュー|おすすめ|比較|違い)'
```

### 専門性レベル判定

```python
EXPERTISE_LEVELS = {
    'beginner': [
        r'\b(?:for beginners|introduction|basics)',
        r'\b(?:初心者向け|入門|わかりやすい)',
    ],
    'intermediate': r'\b(?:advanced|tutorial|guide)',
    'expert': [
        r'\b(?:RFC|whitepaper|architecture)',
        r'\b(?:仕様書|ホワイトペーパー)',
    ],
}
```

### 信頼度スコア

```
各パターンマッチ +0.3
複数マッチ       → cap 1.0

confidence < 0.3 → "informational" (デフォルト)
```

### DB テーブル

```sql
SELECT
    qc.canonical_query,
    ic.primary_intent,
    ic.intent_confidence,
    ic.typical_user_expertise,
    ic.best_performing_content_type
FROM intent_classifications ic
JOIN query_clusters qc ON ic.query_cluster_id = qc.id;
```

### 学習メカニズム（今後）

**ユーザー行動からの意図学習：**

```python
query_intent_success = {
    (query_cluster_id, primary_intent): {
        'avg_dwell_time': 45000,  # ms
        'success_rate': 0.82,
        'user_expertise': 'intermediate',
        'preferred_content_type': 'text_article',
    }
}
```

次のユーザーが同じクエリで検索した場合、
この統計情報を基に結果を最適化。

---

## 統合方法

### クローラー（自動実行）

```python
# crawl_recursive() 内で自動実行
await TrackerDetector.detect_trackers(html, url)
await ContentClassifier.classify(html, url, page_id, db)
await IntentDetector.store_intent(db, query_cluster_id, intent, confidence)
```

### 検索API（リアルタイム適用）

```sql
-- tracker_risk_scoreでペナルティ
FinalScore = BaseScore * tracker_risk_factor

-- content_typeとintent の整合性
WHERE (
    content_type NOT IN ('manga', 'video')  -- 調査意図ならテキスト優先
    OR intent_type = 'product_research'
)
```

---

## パフォーマンス考慮事項

### 検出のオーバーヘッド

| タスク | 時間 | 最適化 |
|--------|------|--------|
| Tracker detection | ~50ms | BeautifulSoupキャッシュ |
| Content classification | ~100ms | メトリクス事前計算 |
| Intent detection | ~10ms | Regex キャッシュ |
| **合計** | **~160ms** | 1時間ごとバッチ |

### DB クエリ最適化

```sql
-- インデックス追加
CREATE INDEX trackers_risk_idx ON trackers(risk_level DESC);
CREATE INDEX content_type_idx ON content_classifications(content_type);
CREATE INDEX intent_idx ON intent_classifications(primary_intent);
```

---

## 将来の拡張

### Phase 2
- [ ] トラッカー数に基づく自動ペナルティ調整
- [ ] コンテンツ品質スコア（テキスト量・画像品質等）
- [ ] 意図別の最適結果順位化

### Phase 3
- [ ] 機械学習による意図推定（精度向上）
- [ ] ユーザー行動ログからの意図学習
- [ ] IntentMatch × TypeScore の完全実装
- [ ] A/B テスティングダッシュボード

---

## 参考リソース

- BeautifulSoup ドキュメント: https://www.crummy.com/software/BeautifulSoup/
- 既知トラッカー一覧: https://privacytools.io/
- コンテンツ分類のベストプラクティス: https://en.wikipedia.org/wiki/Web_content#Types
