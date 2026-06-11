# イベント駆動アーキテクチャ解説 (sumika_event.py)

> **対象ファイル**: `sumika_event.py` および `oasis/` 配下のイベント駆動関連モジュール

## 目次

1. [概要](#概要)
2. [標準版との違い](#標準版との違い)
3. [アーキテクチャ全体図](#アーキテクチャ全体図)
4. [各コンポーネントの解説](#各コンポーネントの解説)
    - [EventBus](#1-eventbus-oasiseventsevent_buspy)
    - [EventTypes (イベント種別)](#2-eventtypes-oasiseventsevent_typespy)
    - [EventDrivenPlatform](#3-eventdrivenplatform-oasissocial_platformplatform_eventspy)
    - [EventDrivenEnv](#4-eventdrivenenv-oasisenvironmentenv_event_drivenpy)
    - [InformationInjector](#5-informationinjector-oasisinformationinjectorpy)
    - [SearXNGClient](#6-searxngclient-oasisinformationsearxng_clientpy)
    - [EventAwareSocialEnvironment](#7-eventawaresocialenvironment-oasissocial_agentagent_environment_eventpy)
5. [データフロー](#データフロー)
6. [シミュレーションループの動作](#シミュレーションループの動作)
7. [設定項目 (config.json)](#設定項目-configjson)
8. [拡張ポイント](#拡張ポイント)

---

## 概要

`sumika_event.py` は、OASISシミュレーションを**イベント駆動アーキテクチャ**で動作させるエントリポイントです。標準版の `sumika.py` をベースにしつつ、以下の3つの主要機能を追加しています。

1. **EventBus によるイベント伝播** — 投稿、いいね、フォローなどのアクションがイベントとして配信される
2. **SearXNG からの外部情報自動注入** — 実際のニュース記事を定期的に取得し、シミュレーション内に流し込む
3. **通知ベースのエージェント選択的起動** — 全員が毎ターン行動するのではなく、通知が届いたエージェントのみが起動する

---

## 標準版との違い

| 項目 | `sumika.py` (標準版) | `sumika_event.py` (イベント駆動版) |
|------|----------------------|--------------------------------------|
| エージェント起動 | 全エージェントが毎ターン必ず行動 | 通知ありエージェント + ランダム少数のみ起動 |
| イベント伝播 | なし | EventBus による pub/sub |
| 外部情報注入 | なし | SearXNG からの定期ニュース取得 |
| エージェントへの通知 | なし | フォローの投稿、いいね、コメント等が通知として届く |
| Platform | `Platform` | `EventDrivenPlatform` (Platform を継承) |
| 環境クラス | `OasisEnv` | `EventDrivenEnv` (OasisEnv を継承) |
| エージェント環境 | `SocialEnvironment` | `EventAwareSocialEnvironment` |

---

## アーキテクチャ全体図

```
┌──────────────────────────────────────────────────────────────────┐
│                     sumika_event.py (エントリポイント)            │
│                                                                  │
│  1. config.json 読み込み → モデル・エージェント構築               │
│  2. EventBus / Platform / Env / Injector 生成                    │
│  3. シミュレーションループ (step_event_driven)                    │
└───────────────────────┬──────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────────┐
        ▼               ▼                   ▼
┌───────────────┐ ┌──────────────┐ ┌────────────────────┐
│  EventBus     │ │  Platform    │ │ InformationInjector│
│  (イベント    │ │  (EventDriven│ │  (SearXNG連携)     │
│   配信中枢)   │ │   Platform)  │ │                    │
│               │ │              │ │ 一定間隔で検索     │
│ ┌───────────┐ │ │ アクション   │ │ → ExternalInfo     │
│ │グローバル │ │ │ 実行時に     │ │   Event 発行       │
│ │ハンドラ   │ │ │ イベント発行 │ │                    │
│ └───────────┘ │ │              │ │ → Platform に      │
│ ┌───────────┐ │ │              │ │   ニュース投稿     │
│ │エージェン│◀─┤ │              │ │                    │
│ │ト別通知  │ │ │              │ │                    │
│ │キュー    │ │ │              │ │                    │
│ └───────────┘ │ │              │ │                    │
└───────┬───────┘ └──────────────┘ └────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────┐
│          EventDrivenEnv (ステップ管理)              │
│                                                   │
│  1. InformationInjector.maybe_inject()            │
│  2. platform.update_rec_table()                   │
│  3. _select_agents_to_wake()                      │
│     ├─ 通知ありエージェント (100%)                 │
│     └─ ランダムエージェント (baseline_wakeup_rate) │
│  4. 選ばれたエージェントだけ LLMAction を実行      │
│  5. Clock 更新                                    │
└───────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────┐
│     EventAwareSocialEnvironment (エージェント環境)  │
│                                                   │
│  to_text_prompt() をオーバーライド:                │
│  ┌──────────────────────────────┐                 │
│  │ 【🔔 通知・新着情報】        │                 │
│  │  ─ SNS 通知 ─                │                 │
│  │  ❤️ User 3 があなたの投稿に  │                 │
│  │     いいねしました           │                 │
│  │  ─ 外部情報 (SearXNG) ─      │                 │
│  │  📰 外部ニュース [AI倫理]    │                 │
│  │     タイトル: ...            │                 │
│  │     概要: ...                │                 │
│  ├──────────────────────────────┤                 │
│  │ (元のプロンプト: タイムライン│                 │
│  │  フォロワー情報など)         │                 │
│  └──────────────────────────────┘                 │
└───────────────────────────────────────────────────┘
```

---

## 各コンポーネントの解説

### 1. EventBus (`oasis/events/event_bus.py`)

シミュレーション全体で **1インスタンス** 共有される非同期イベントバスです。イベントの中継地点として機能します。

**二つの配送先:**

| 配送先 | 役割 | メソッド |
|--------|------|----------|
| グローバルハンドラ | イベント種別に紐づく共通処理（フォロワーへの転送など） | `subscribe(EventKind, handler)` |
| エージェント別通知キュー | 各エージェントの受信箱（`NotificationQueue`） | `subscribe_agent(agent_id, event_kinds)` |

**主要メソッド:**

```python
bus = EventBus()

# グローバルハンドラ登録
bus.subscribe(EventKind.POST_CREATED, my_handler)

# エージェント通知登録
bus.subscribe_agent(agent_id=5, event_kinds=[EventKind.POST_LIKED])

# イベント発行
await bus.publish(PostCreatedEvent(...))

# 未読通知ありエージェント一覧
bus.agents_with_notifications()  # → [3, 5, 7]

# 同期コンテキストからの発行
bus.publish_sync(PostLikedEvent(...))
```

**NotificationQueue:**

各エージェントに紐づく `asyncio.Queue`（最大256件）。イベントが push され、エージェントの行動時に `drain()` で一括取得されます。キューが満杯の場合は古いイベントが破棄されます。

---

### 2. EventTypes (`oasis/events/event_types.py`)

シミュレーション内で流通するすべてのイベントの定義です。`dataclass` で型安全に定義されています。

**イベント分類:**

```
EventKind (Enum)
├── プラットフォーム行動イベント
│   ├── POST_CREATED        投稿が作成された
│   ├── POST_LIKED          投稿にいいねされた
│   ├── POST_DISLIKED       投稿に低評価された
│   ├── POST_REPOSTED       投稿がリポストされた
│   ├── POST_COMMENTED      投稿にコメントされた
│   ├── POST_REPORTED       投稿が通報された
│   ├── USER_FOLLOWED       ユーザーがフォローされた
│   └── USER_UNFOLLOWED     ユーザーのフォローが外された
├── システムイベント
│   ├── REC_TABLE_UPDATED   レコメンドテーブルが更新された
│   └── TRENDING_POST       トレンド投稿が検出された
└── 外部情報注入イベント
    └── EXTERNAL_INFO       SearXNG からのニュース等
```

**各イベントが持つ情報の例 (PostLikedEvent):**

```python
@dataclass
class PostLikedEvent(BaseEvent):
    post_id: int = 0          # いいねされた投稿のID
    liker_id: int = 0         # いいねしたユーザーID
    post_author_id: int = 0   # 投稿者ID（通知先の判定に使用）
```

---

### 3. EventDrivenPlatform (`oasis/social_platform/platform_events.py`)

元の `Platform` クラスを継承し、すべてのアクションメソッドをオーバーライドしたミックスインです。**既存コードを書き換えることなく**イベント発行を後付けしています。

**動作原理:**

```
エージェントがアクションを実行
    ↓
EventDrivenPlatform.create_post() が呼ばれる
    ↓
1. super().create_post() で元の処理を実行
    ↓
2. 成功時、PostCreatedEvent を生成
    ↓
3. event_bus.publish() でイベント配信
```

**オーバーライドされているアクション一覧:**

| メソッド | 発行されるイベント |
|----------|-------------------|
| `create_post()` | `PostCreatedEvent` |
| `like_post()` | `PostLikedEvent` |
| `dislike_post()` | `PostDislikedEvent` |
| `repost()` | `PostRepostedEvent` |
| `create_comment()` | `PostCommentedEvent` |
| `report_post()` | `PostReportedEvent` |
| `follow()` | `UserFollowedEvent` |
| `unfollow()` | `UserUnfollowedEvent` |
| `update_rec_table()` | `RecTableUpdatedEvent` |

`event_bus` が `None` の場合は通常の `Platform` と全く同じ動作をします（後方互換性）。

---

### 4. EventDrivenEnv (`oasis/environment/env_event_driven.py`)

元の `OasisEnv` を継承したイベント駆動環境です。シミュレーションの **1ステップの処理フロー** を定義しています。

**`step_event_driven()` の処理フロー:**

```
Step N
  │
  ├─ 1. InformationInjector.maybe_inject(step)
  │     └─ 設定間隔ごとに SearXNG からニュース検索
  │        → ExternalInfoEvent 発行 → 全エージェントに通知
  │
  ├─ 2. platform.update_rec_table()
  │     └─ レコメンドテーブル更新 → RecTableUpdatedEvent 発行
  │
  ├─ 3. _select_agents_to_wake()
  │     ├─ 通知ありエージェント (100% 起動)
  │     └─ 残りエージェントから baseline_wakeup_rate% をランダム選択
  │
  ├─ 4. 選ばれたエージェントのアクションを asyncio.gather() で並列実行
  │
  └─ 5. Clock 更新
```

**エージェント選定ロジック (`_select_agents_to_wake`):**

```python
# 例: 10人のエージェント、baseline_wakeup_rate = 0.1 の場合

# 通知ありエージェント: 3人 → 全員起動
# 通知なしエージェント: 7人 → そのうち 10% = 0.7 → 丸めて最大1人がランダムに起動
# 合計: 3〜4人のみ起動（標準版なら10人全員が毎ターン起動）
```

**デフォルト通知ハンドラ (`register_default_handlers`):**

| イベント | 通知先 | 仕組み |
|----------|--------|--------|
| `PostCreatedEvent` | 投稿者のフォロワー全員 | DB から `follow` テーブルを検索 |
| `PostLikedEvent` | 投稿者本人 | `post_author_id` を参照 |
| `PostCommentedEvent` | 投稿者本人 | `post_author_id` を参照 |
| `PostRepostedEvent` | 投稿者本人 | `post_author_id` を参照 |
| `UserFollowedEvent` | フォローされた人 | `followee_id` を参照 |
| `ExternalInfoEvent` | 全エージェント | `EventBus.publish()` の仕様による |

---

### 5. InformationInjector (`oasis/information/injector.py`)

SearXNG 検索サーバーから定期的に情報を取得し、EventBus 経由でシミュレーション内に注入するコンポーネントです。

**動作:**

```
Step 5 (inject_interval_steps = 5 の場合)
  │
  ├─ maybe_inject(5)
  │     └─ 間隔に達した → inject_now()
  │
  ├─ トピックをラウンドロビンで選択
  │     topics = ["AI倫理", "SNS誤情報", "生成AI規制", ...]
  │     今回: "AI倫理 最新ニュース"
  │
  ├─ SearXNGClient.search("AI倫理 最新ニュース", num_results=3)
  │
  ├─ 重複URL除去 (deduplicate = True)
  │
  ├─ 検索結果ごとに:
  │     ├─ Platform にニュース投稿を作成 (news_bot_agent_id = 0)
  │     └─ ExternalInfoEvent を発行 → 全エージェントに通知
  │
  └─ 次回は topics[1] を検索
```

**主要メソッド:**

| メソッド | 説明 |
|----------|------|
| `maybe_inject(step)` | 設定間隔に達した場合のみ注入を実行 |
| `inject_now()` | 即座に1トピック分の検索・注入を実行 |
| `inject_targeted(query, agent_ids)` | 特定エージェントに向けたカスタム検索注入 |

---

### 6. SearXNGClient (`oasis/information/searxng_client.py`)

SearXNG JSON API の非同期HTTPクライアントです。`aiohttp` を使用しています。

```python
async with SearXNGClient("http://192.168.15.146:8080") as client:
    results = await client.search("AI倫理", num_results=5)
    for r in results:
        print(r.title, r.snippet, r.url)

# またはニュースカテゴリで検索
results = await client.search_news("生成AI規制", num_results=3)
```

- 接続失敗時は空リストを返す（例外を発生させない）
- デフォルトで日本語優先 (`language: "ja-JP"`)

---

### 7. EventAwareSocialEnvironment (`oasis/social_agent/agent_environment_event.py`)

各エージェントの「環境」を拡張し、**通知をLLMプロンプトに自動挿入**するミックスインです。

**`sumika_event.py` でのパッチ処理:**

```python
# 全エージェントの env を EventAwareSocialEnvironment に差し替え
for agent_id, agent in agent_graph.agent_mappings.items():
    queue = event_bus.get_agent_queue(agent_id)
    agent.env = EventAwareSocialEnvironment(
        action=SocialAction(agent_id, agent.channel),
        notification_queue=queue,
    )
```

**プロンプト生成の流れ:**

```
エージェントが行動を決定する際
    ↓
env.to_text_prompt() が呼ばれる
    ↓
1. notification_queue.drain() で未読通知を一括取得
    ↓
2. 通知をテキスト化:
   【🔔 通知・新着情報】
     ─ SNS 通知 ─
     ❤️ User 3 があなたの投稿 (Post ID: 12) にいいねしました
     💬 User 7 があなたの投稿 (Post ID: 8) にコメントしました: 「すごいね」
     ─ 外部情報 (SearXNG 検索より) ─
     📰 外部ニュース [AI倫理 最新ニュース]
        タイトル: 〇〇社がAI倫理ガイドラインを発表
        概要: ...
        URL: https://...
    ↓
3. 通知テキスト + 元のプロンプト(タイムライン等) を結合してLLMへ
```

---

## データフロー

以下は、エージェントAがエージェントBの投稿にいいねした場合のイベント伝播の流れです。

```
[Agent A] が like_post(agent_id=A, post_id=42) を実行
    │
    ▼
EventDrivenPlatform.like_post()
    │
    ├─ super().like_post()  → DB 更新 (like テーブルに追加)
    │
    ├─ DB から post_id=42 の投稿者を取得 → author_id = B
    │
    └─ event_bus.publish(PostLikedEvent(
           post_id=42,
           liker_id=A,
           post_author_id=B
       ))
           │
           ▼
       EventBus.publish()
           │
           ├─ グローバルハンドラ実行
           │   └─ _make_author_notify_handler()
           │       └─ Agent B の通知キューにイベントを push
           │
           └─ Agent B の NotificationQueue にイベントを push
               （購読設定に基づく配信）

── 次のステップ ──

EventDrivenEnv._select_agents_to_wake()
    │
    └─ Agent B は通知キューが空でない → 起動対象に選ばれる

Agent B が行動
    │
    └─ env.to_text_prompt() で通知テキストがプロンプトに挿入:
       "❤️ User A があなたの投稿 (Post ID: 42) にいいねしました"

    → LLM がこの通知を踏まえて次の行動を決定（返信する、フォローする等）
```

---

## シミュレーションループの動作

`sumika_event.py` の `run_simulation()` の全体フローです。

```
run_simulation(num_steps)
│
├─ 1. 初期化
│   ├─ 既存DBの削除 (二重起動防止)
│   ├─ W&B 初期化
│   ├─ EventBus インスタンス生成
│   ├─ EventDrivenPlatform 生成 (channel + event_bus)
│   ├─ AgentGraph 構築 (profiles JSON → SocialAgent × N)
│   ├─ InformationInjector 生成 (topics, SearXNG URL)
│   └─ EventDrivenEnv 生成 (agent_graph + platform + event_bus)
│
├─ 2. セットアップ
│   ├─ env.reset()
│   │   ├─ プラットフォーム起動
│   │   ├─ エージェント signup
│   │   └─ デフォルト通知ハンドラ登録
│   ├─ エージェントに EventAwareSocialEnvironment をパッチ
│   └─ シードポスト投入 (seeds JSON → Platform.create_post)
│
├─ 3. メインループ (Step 1 〜 num_steps)
│   │
│   for step in range(1, num_steps + 1):
│       │
│       ├─ env.step_event_driven()
│       │   ├─ InformationInjector.maybe_inject(step)
│       │   ├─ platform.update_rec_table()
│       │   ├─ _select_agents_to_wake()
│       │   │   ├─ 通知ありエージェントを収集
│       │   │   └─ baseline_wakeup_rate% のランダムエージェントを追加
│       │   ├─ asyncio.gather() で並列アクション実行
│       │   └─ Clock 更新
│       │
│       └─ W&B ログ記録 (elapsed_sec, agents_with_notifications)
│
└─ 4. クリーンアップ
    ├─ injector.close()
    ├─ env.close()
    └─ wandb.finish()
```

---

## 設定項目 (config.json)

`config.example.event.json` をベースにした設定例と各項目の説明です。

```json
{
    "ollama_url": "http://localhost:11434/v1",
    "ollama_model_sim": "joe-speedboat/Gemma-4-Uncensored-HauhauCS-Aggressive:e4b",
    "ollama_model_check": "gemma4:e4b",
    "db_path": "./ollama_twitter.db",
    "tracker_db_path": "./sumika_tracker.db",
    "model_type": "llama3",
    "recsys_type": "twitter",
    "refresh_rec_post_count": 2,
    "max_rec_post_len": 2,
    "following_post_count": 3,
    "num_steps": 20,
    "seed_path": "seeds/seed_test.json",
    "profile_path": "profiles/test.json",
    "wandb_project": "oasis-event-driven",
    "wandb_mode": "online",
    "event_driven": {
        "enabled": true,
        "baseline_wakeup_rate": 0.1,
        "inject_interval_steps": 5,
        "searxng_url": "http://192.168.15.146:8080",
        "topics": [
            "AI倫理 最新ニュース",
            "SNS誤情報 拡散",
            "生成AI 規制",
            "ソーシャルメディア 社会影響",
            "フェイクニュース 対策"
        ],
        "num_results_per_topic": 3,
        "news_bot_agent_id": 0,
        "categories": "general"
    }
}
```

### 共通設定

| パラメータ | 説明 |
|------------|------|
| `ollama_url` | Ollama API の URL |
| `ollama_model_sim` | シミュレーションに使用するモデル名 |
| `ollama_model_check` | チェックツールに使用するモデル名 |
| `db_path` | シミュレーション結果DB のパス |
| `tracker_db_path` | トラッカーDB のパス |
| `num_steps` | デフォルトステップ数 |
| `seed_path` | シード投稿JSONのパス |
| `profile_path` | エージェントプロファイルJSONのパス |
| `wandb_project` | W&B プロジェクト名 |
| `wandb_mode` | W&B モード (`online` / `offline` / `disabled`) |

### イベント駆動設定 (`event_driven`)

| パラメータ | 型 | 説明 |
|------------|----|------|
| `enabled` | bool | イベント駆動モードの有効/無効 |
| `baseline_wakeup_rate` | float | 通知なしエージェントの毎ステップ起動率 (0.0〜1.0)。低いほど省リソースだが反応が遅くなる |
| `inject_interval_steps` | int | SearXNG情報注入の間隔（ステップ数） |
| `searxng_url` | string | SearXNGサーバーのURL |
| `topics` | string[] | SearXNGで順番に検索するトピック一覧（ラウンドロビン） |
| `num_results_per_topic` | int | 1トピックあたりの最大取得件数 |
| `news_bot_agent_id` | int | ニュース投稿に使用するエージェントID（プロファイルに存在するIDであること） |
| `categories` | string | SearXNG検索カテゴリ (`general` / `news` / `science` など) |

---

## 拡張ポイント

このアーキテクチャは以下のように拡張できます。

### 新しいイベント種別の追加

1. `oasis/events/event_types.py` に `EventKind` と dataclass を追加
2. `oasis/social_platform/platform_events.py` で対応するアクションをオーバーライド
3. `oasis/environment/env_event_driven.py` の `register_default_handlers()` でハンドラを登録

### エージェントごとの関心ベース通知

`InformationInjector.inject_targeted()` を使用して、特定のエージェントにのみ関連情報を配信できます。

```python
# 例: AIに興味のあるエージェントにのみ技術ニュースを配信
await injector.inject_targeted(
    query="LLM 最新動向",
    agent_ids=[3, 5, 8],
    num_results=2,
)
```

### カスタム通知ハンドラ

`EventBus.subscribe()` でグローバルハンドラを追加し、イベント発生時の独自処理（統計記録、外部通知など）を実装できます。

```python
bus.subscribe(EventKind.POST_CREATED, my_analytics_handler)
```
