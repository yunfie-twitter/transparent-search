# 集合知スコア実装ガイド（更新版）

## 概要

**集合知スコア** は、実際のユーザー行動データから「どのページがこのクエリで本当に役に立つのか」を自動で学習するシステムです。

**新機能統合:**
- ✅ **トラッカー危険度スコアリング** - プライバシー重視のページランキング
- ✅ **コンテンツタイプ自動判定** - 記事/動画/ツール等を自動分類
- ✅ **検索意図自動検出** - ユーザーの真の目的を認識
- ✅ **Intent × Content マッチング** - 意図に最適なコンテンツを優先

### 最終スコア計算式

```
FinalScore = (
    BaseSearchScore + 
    α * CollectiveIntelligenceScore + 
    IntentMatchBonus
) × TrackerFactor × DomainTrustScore
```

---

## Phase 1: 実装済みの部分

### 1.1 DB スキーマ

**基本6テーブル**

| テーブル | 役割 |
|---------|------|
| `sessions` | ユーザーセッション（IP/UA単位） |
| `search_events` | 検索クエリの記録 |
| `click_events` | ページクリックと滞在時間 |
| `page_success_matrix` | `(QueryCluster, PageID)` ごとの成功率マトリクス |
| `query_clusters` | クエリの正規化グループ |
| `anomaly_detections` | ボット・スパムの検出ログ |

**拡張テーブル（新機能対応）**

| テーブル | 役割 |
|---------|------|
| `trackers` | 検出されたトラッカー情報（Google Analytics等） |
| `page_trackers` | ページごとのトラッカー紐付け |
| `content_classifications` | ページのコンテンツタイプ判定 |
| `intent_classifications` | クエリの検索意図ラベル |

**Key Columns（ページテーブル）**
- `tracker_risk_score`: 0.1～1.0（低いほどリスク高い）
- `last_crawled_at`: 最後のクロール時刻

### 1.2 イベント追跡ロジック

```python
# セッション管理
await EventTracker.get_or_create_session(db, ip_address, user_agent)

# イベント記録
await EventTracker.record_search_event(db, session_id, query, ...)
await EventTracker.record_click_event(db, search_event_id, page_id, ...)
await EventTracker.record_re_search(db, prev_search_id, time_ms)

# バッチ処理
await EventTracker.update_success_matrix(db)  # 1時間ごと
await EventTracker.detect_anomalies(db)  # 15分ごと
await EventTracker.apply_time_decay(db, lambda_decay=0.1)  # 1日1回
await EventTracker.calculate_session_trust(db, session_id)  # 随時
```

### 1.3 クローラー統合

**新機能の自動実行**

```python
# app/advanced_crawler.py 内
await TrackerDetector.detect_trackers(html, url)
await ContentClassifier.classify(html, url, page_id, db)
await IntentDetector.detect_intent(query)  # 検索時
```

**ログ出力例**
```
[OK] https://example.com | Trackers: 3 | Risk: 0.72 | Content: text_article (0.95)
```

---

## Phase 2: 検索API統合

### 2.1 新エンドポイント

#### 基本検索（自動的に新機能を適用）

```bash
GET /search?q=python%20for%20loop
```

**自動実行される処理:**
1. **検索意図検出** → `primary_intent = 'research'`
2. **推奨コンテンツ決定** → `preferred_content_type = 'text_article'`
3. **インテント×コンテンツマッチング** → スコア加算
4. **トラッカーリスク適用** → スコア減衰

**レスポンス例**

```json
{
  "meta": {
    "query": "python for loop",
    "took_ms": 45,
    "count": 10,
    "intent": {
      "primary": "research",
      "confidence": 0.95,
      "preferred_content_type": "text_article"
    }
  },
  "data": [
    {
      "id": 42,
      "title": "The for statement - Python Docs",
      "url": "https://docs.python.org/3/tutorial/controlflow.html",
      "score": 8.342,
      "content_type": "text_article",
      "content_confidence": 0.98,
      "tracker_risk_score": 0.92,
      "explain": {
        "pgroonga_base": 7.2,
        "title_bonus": 10,
        "intent_match_bonus": 1.0,
        "tracker_factor": 0.976,
        "tracker_risk_score": 0.92
      }
    }
  ]
}
```

#### フィルタリング付き検索

```bash
# トラッカーリスク「クリーン」のみ
GET /search?q=privacy&filter_tracker_risk=clean

# 特定コンテンツタイプのみ
GET /search?q=tutorial&content_types=text_article,video

# 詳細スコアリング表示
GET /search?q=docker&explain=true
```

#### デバッグエンドポイント

```bash
# クエリの意図分析
GET /search/debug/intent?q=how%20to%20install%20docker

レスポンス:
{
  "query": "how to install docker",
  "intent_analysis": {
    "primary_intent": "research",
    "intent_confidence": 0.95,
    "typical_user_expertise": "beginner",
    "all_intent_scores": {
      "question": 0.6,
      "research": 0.95,
      "debugging": 0.2,
      ...
    }
  },
  "recommended_content_type": "text_article",
  "intent_match_examples": {
    "text_article": 1.0,
    "forum": 0.8,
    "video": 0.7,
    "tool": 0.5
  }
}
```

```bash
# トラッカーリスク分布
GET /search/debug/tracker-risk

レスポンス:
{
  "distribution": [
    {"category": "clean", "count": 234, "avg_score": 0.95},
    {"category": "minimal", "count": 1203, "avg_score": 0.79},
    {"category": "moderate", "count": 2104, "avg_score": 0.62},
    {"category": "heavy", "count": 1876, "avg_score": 0.41},
    {"category": "severe", "count": 342, "avg_score": 0.18}
  ]
}
```

```bash
# コンテンツタイプ分布
GET /search/debug/content-types

レスポンス:
{
  "distribution": [
    {"content_type": "text_article", "count": 3421, "avg_confidence": 0.92},
    {"content_type": "forum", "count": 1203, "avg_confidence": 0.87},
    {"content_type": "video", "count": 892, "avg_confidence": 0.94},
    {"content_type": "tool", "count": 543, "avg_confidence": 0.89},
    {"content_type": "manga", "count": 287, "avg_confidence": 0.96},
    {"content_type": "image", "count": 156, "avg_confidence": 0.91},
    {"content_type": "unknown", "count": 312, "avg_confidence": 0.28}
  ]
}
```

### 2.2 スコア計算の詳細

#### トラッカーファクター（Tracker Factor）

```
tracker_factor = 1.0 - 0.3 * (1.0 - tracker_risk_score)

例：
- tracker_risk_score = 0.2 (severe) → factor = 0.73 (スコア27%減衰)
- tracker_risk_score = 0.5 (moderate) → factor = 0.85 (スコア15%減衰)
- tracker_risk_score = 0.9 (clean) → factor = 0.97 (スコア3%減衰)
- tracker_risk_score = 1.0 (perfect) → factor = 1.0 (影響なし)
```

#### インテント×コンテンツマッチボーナス

```
intent_match_bonus:
- 意図と完全一致時: 1.0 → スコア +2.0
- 強い相関時: 0.85 → スコア +1.7
- 弱い相関時: 0.6 → スコア +1.2
- 関連なし時: 0.5 → スコア +1.0

例（クエリ: "how to install docker" → intent: research）:
- text_article (完全一致) → match_bonus = 1.0
- forum (強い相関) → match_bonus = 0.85
- video (弱い相関) → match_bonus = 0.7
- tool (関連なし) → match_bonus = 0.5
```

#### 最終スコア計算

```python
total_score = (
    (pgroonga_relevance * 1.5 +
     title_bonus +
     url_bonus +
     h1_bonus +
     exact_bonus +
     freshness_score +
     quality_score +
     pagerank_contribution +
     click_contribution +
     intent_match_bonus * 2.0) 
     * trust_score
) * tracker_factor

= BASE_COMPONENTS * DOMAIN_TRUST * TRACKER_PENALTY
```

---

## Phase 3: スコア最適化（今後）

### 3.1 機械学習による意図推定

```python
# 現在: ルールベース (95% 精度)
# 将来: LLM/微調整モデル (99%+ 精度)

intent_model = load_model('intent_classifier_v2.pkl')
recommended_intent = intent_model.predict([
    query,
    user_profile,
    temporal_context,
    domain_context,
])
```

### 3.2 ユーザー行動学習

```python
# 同じ意図でのクリック成功率から学習
(
  query_cluster_id,
  primary_intent
) → {
  'avg_dwell_time': 45000,
  'success_rate': 0.82,
  'preferred_content_types': ['text_article', 'forum'],
  'user_expertise_level': 'intermediate',
}

# 次のユーザーに同じ意図のクエリが来た場合、
# この統計情報から結果を最適化
```

### 3.3 インテント別の結果順位最適化

```python
intent_specific_weights = {
    'question': {
        'content_type_weight': 0.3,  # コンテンツ重視
        'recency_weight': 0.1,
        'authority_weight': 0.4,
    },
    'transactional': {
        'content_type_weight': 0.5,  # ツール重視
        'price_weight': 0.3,
        'recency_weight': 0.2,
    },
    'product_research': {
        'content_type_weight': 0.4,  # レビュー重視
        'recency_weight': 0.3,  # 最新レビュー
        'authority_weight': 0.2,
    },
}
```

---

## 運用ワークフロー

### スケジュール

| 実行頻度 | タスク | 所要時間 |
|--------|--------|--------|
| **リアルタイム** | クエリログ記録、意図検出 | <10ms |
| **クロール時** | トラッカー検出、コンテンツ分類 | ~160ms/ページ |
| **毎時** | `update_success_matrix` | 5～30秒 |
| **15分ごと** | 異常検出 | <5秒 |
| **1日1回** | 時間減衰適用、統計更新 | 1～5分 |

### Cron Jobs

```bash
# .env または docker-compose.yml
CELERY_BEAT_SCHEDULE={
    'update-success-matrix': {
        'task': 'tasks.update_success_matrix',
        'schedule': crontab(minute=0),  # 毎時
    },
    'detect-anomalies': {
        'task': 'tasks.detect_anomalies',
        'schedule': crontab(minute='*/15'),  # 15分ごと
    },
    'apply-time-decay': {
        'task': 'tasks.apply_time_decay',
        'schedule': crontab(hour=3, minute=0),  # 毎日3時
    },
}
```

---

## パフォーマンス考慮事項

### DB インデックス

```sql
-- トラッカー検索
CREATE INDEX idx_tracker_risk ON pages(tracker_risk_score DESC) 
WHERE tracker_risk_score < 0.5;

-- コンテンツタイプ検索
CREATE INDEX idx_content_type ON content_classifications(content_type);
CREATE INDEX idx_content_conf ON content_classifications(type_confidence DESC);

-- 意図検索
CREATE INDEX idx_intent ON intent_classifications(primary_intent);
CREATE INDEX idx_intent_conf ON intent_classifications(intent_confidence DESC);

-- クエリクラスタ統合検索
CREATE INDEX idx_page_intent ON pages(id)
INCLUDE (tracker_risk_score, last_crawled_at);
```

### キャッシング戦略

```python
# キャッシュ層: Redis
# キー: f"intent:{query_hash}"
# TTL: 1時間

redis_client.setex(
    f"intent:{sha256(q)}",
    3600,
    json.dumps(intent_data),
)

# コンテンツ分類キャッシュ
# キー: f"content_class:{page_id}"
# TTL: 7日間
redis_client.setex(
    f"content_class:{page_id}",
    604800,
    json.dumps(classification_data),
)
```

---

## トラブルシューティング

### Q: tracker_risk_score が NULL で表示される
A: クローラーが `TrackerDetector.detect_trackers()` を実行していない。クロール時ログを確認。

### Q: Intent 検出がずれている
A: パターンマッチングのみのため、複雑なクエリは失敗可能。`/search/debug/intent` で確認後、INTENT_PATTERNS に追加。

### Q: コンテンツ分類の精度が低い
A: メトリクス重視度の調整が必要。`ContentClassifier._score_*()` メソッドの係数を調整。

### Q: 検索結果がトラッカーばかりで偏っている
A: `tracker_factor` の減衰率 (0.3) が強すぎる可能性。`1.0 - 0.2 * (...)` に変更。

---

## 参考資料

- PGroonga 全文検索: https://pgroonga.github.io/
- 時間減衰モデル: https://en.wikipedia.org/wiki/Exponential_decay
- 信頼度スコアリング: https://arxiv.org/abs/1908.04156
- プライバシー・トラッカー: https://privacytools.io/
- 検索意図研究: https://www.researchgate.net/publication/283255261_Search_Intent
