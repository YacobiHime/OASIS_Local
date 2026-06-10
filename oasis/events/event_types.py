"""
oasis/events/event_types.py
---------------------------
イベントドリブンOASISで流通するすべてのイベントの定義。
dataclassを使ってシンプルかつ型安全に保つ。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EventKind(Enum):
    # --- プラットフォーム上の行動イベント ---
    POST_CREATED       = "post_created"
    POST_LIKED         = "post_liked"
    POST_DISLIKED      = "post_disliked"
    POST_REPOSTED      = "post_reposted"
    POST_COMMENTED     = "post_commented"
    POST_REPORTED      = "post_reported"
    USER_FOLLOWED      = "user_followed"
    USER_UNFOLLOWED    = "user_unfollowed"

    # --- システムイベント ---
    REC_TABLE_UPDATED  = "rec_table_updated"
    TRENDING_POST      = "trending_post"

    # --- 外部情報注入イベント ---
    EXTERNAL_INFO      = "external_info"     # SearXNG から取得したニュース等


@dataclass
class BaseEvent:
    kind: EventKind
    # イベント発生時のシミュレーション時刻 (int ステップ or float)
    sim_time: Any = None
    # 追加メタデータ (自由形式)
    meta: dict = field(default_factory=dict)


# ─────────────────────────────────────────
# プラットフォーム行動イベント
# ─────────────────────────────────────────

@dataclass
class PostCreatedEvent(BaseEvent):
    kind: EventKind = field(default=EventKind.POST_CREATED, init=False)
    post_id: int = 0
    author_id: int = 0
    content: str = ""


@dataclass
class PostLikedEvent(BaseEvent):
    kind: EventKind = field(default=EventKind.POST_LIKED, init=False)
    post_id: int = 0
    liker_id: int = 0
    post_author_id: int = 0   # 投稿者へ通知するために保持


@dataclass
class PostDislikedEvent(BaseEvent):
    kind: EventKind = field(default=EventKind.POST_DISLIKED, init=False)
    post_id: int = 0
    disliker_id: int = 0
    post_author_id: int = 0


@dataclass
class PostRepostedEvent(BaseEvent):
    kind: EventKind = field(default=EventKind.POST_REPOSTED, init=False)
    original_post_id: int = 0
    new_post_id: int = 0
    reposter_id: int = 0
    original_author_id: int = 0


@dataclass
class PostCommentedEvent(BaseEvent):
    kind: EventKind = field(default=EventKind.POST_COMMENTED, init=False)
    comment_id: int = 0
    post_id: int = 0
    commenter_id: int = 0
    post_author_id: int = 0
    content: str = ""


@dataclass
class PostReportedEvent(BaseEvent):
    kind: EventKind = field(default=EventKind.POST_REPORTED, init=False)
    post_id: int = 0
    reporter_id: int = 0
    reason: str = ""


@dataclass
class UserFollowedEvent(BaseEvent):
    kind: EventKind = field(default=EventKind.USER_FOLLOWED, init=False)
    follower_id: int = 0
    followee_id: int = 0


@dataclass
class UserUnfollowedEvent(BaseEvent):
    kind: EventKind = field(default=EventKind.USER_UNFOLLOWED, init=False)
    follower_id: int = 0
    followee_id: int = 0


# ─────────────────────────────────────────
# システムイベント
# ─────────────────────────────────────────

@dataclass
class RecTableUpdatedEvent(BaseEvent):
    kind: EventKind = field(default=EventKind.REC_TABLE_UPDATED, init=False)


@dataclass
class TrendingPostEvent(BaseEvent):
    kind: EventKind = field(default=EventKind.TRENDING_POST, init=False)
    post_id: int = 0
    score: float = 0.0
    topic_hint: str = ""   # 何についての投稿か (任意)


# ─────────────────────────────────────────
# 外部情報注入イベント (SearXNG)
# ─────────────────────────────────────────

@dataclass
class ExternalInfoEvent(BaseEvent):
    """SearXNG 検索結果 1 件をラップするイベント。"""
    kind: EventKind = field(default=EventKind.EXTERNAL_INFO, init=False)
    # 検索に使ったクエリ
    query: str = ""
    # 記事タイトル
    title: str = ""
    # スニペット / 本文要約
    snippet: str = ""
    # 元URL
    url: str = ""
    # どのエージェント(user_id リスト)に配信するか。空 = ブロードキャスト
    target_agent_ids: list = field(default_factory=list)
    # 注入済みのシードポスト ID (Platform 側で設定)
    injected_post_id: Optional[int] = None