"""
oasis/social_platform/platform_events.py
-----------------------------------------
Platform クラスへのイベント発行機能を後付けするミックスイン。

元の platform.py を直接書き換える代わりに、
このミックスインを継承した EventDrivenPlatform を提供する。
既存コードとの互換性を最大限維持しつつ、各アクションの
成功時に対応するイベントを EventBus に publish する。

使い方:
    from oasis.social_platform.platform_events import EventDrivenPlatform
    platform = EventDrivenPlatform(
        db_path="sim.db",
        event_bus=bus,
        ...  # 他の Platform 引数はそのまま
    )
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from oasis.social_platform.platform import Platform
from oasis.social_platform.typing import RecsysType
from oasis.events.event_bus import EventBus
from oasis.events.event_types import (
    PostCreatedEvent,
    PostLikedEvent,
    PostDislikedEvent,
    PostRepostedEvent,
    PostCommentedEvent,
    PostReportedEvent,
    UserFollowedEvent,
    UserUnfollowedEvent,
    RecTableUpdatedEvent,
)

logger = logging.getLogger("oasis.platform.events")


class EventDrivenPlatform(Platform):
    """
    Platform のすべてのアクションをオーバーライドし、
    成功時に対応するイベントを EventBus に publish する。

    event_bus が None の場合は通常の Platform と同じ動作をする。
    """

    def __init__(self, *args, event_bus: Optional[EventBus] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_bus: Optional[EventBus] = event_bus

    # ─────────────────────────────────────
    # ユーティリティ
    # ─────────────────────────────────────

    def _sim_time(self):
        if self.recsys_type == RecsysType.REDDIT:
            return self.sandbox_clock.time_transfer(datetime.now(), self.start_time)
        return self.sandbox_clock.get_time_step()

    async def _pub(self, event) -> None:
        if self.event_bus is not None:
            await self.event_bus.publish(event)

    def _get_post_author(self, post_id: int) -> Optional[int]:
        """post_id から投稿者の user_id を返す。失敗時は None。"""
        try:
            self.pl_utils._execute_db_command(
                "SELECT user_id FROM post WHERE post_id = ?", (post_id,)
            )
            row = self.db_cursor.fetchone()
            return row[0] if row else None
        except Exception:
            return None

    # ─────────────────────────────────────
    # アクションのオーバーライド
    # ─────────────────────────────────────

    async def create_post(self, agent_id: int, content: str):
        result = await super().create_post(agent_id, content)
        if result.get("success"):
            await self._pub(PostCreatedEvent(
                sim_time=self._sim_time(),
                post_id=result["post_id"],
                author_id=agent_id,
                content=content,
            ))
        return result

    async def like_post(self, agent_id: int, post_id: int):
        result = await super().like_post(agent_id, post_id)
        if result.get("success"):
            author_id = self._get_post_author(post_id) or 0
            await self._pub(PostLikedEvent(
                sim_time=self._sim_time(),
                post_id=post_id,
                liker_id=agent_id,
                post_author_id=author_id,
            ))
        return result

    async def dislike_post(self, agent_id: int, post_id: int):
        result = await super().dislike_post(agent_id, post_id)
        if result.get("success"):
            author_id = self._get_post_author(post_id) or 0
            await self._pub(PostDislikedEvent(
                sim_time=self._sim_time(),
                post_id=post_id,
                disliker_id=agent_id,
                post_author_id=author_id,
            ))
        return result

    async def repost(self, agent_id: int, post_id: int):
        result = await super().repost(agent_id, post_id)
        if result.get("success"):
            author_id = self._get_post_author(post_id) or 0
            await self._pub(PostRepostedEvent(
                sim_time=self._sim_time(),
                original_post_id=post_id,
                new_post_id=result.get("post_id", 0),
                reposter_id=agent_id,
                original_author_id=author_id,
            ))
        return result

    async def create_comment(self, agent_id: int, comment_message: tuple):
        result = await super().create_comment(agent_id, comment_message)
        if result.get("success"):
            if len(comment_message) >= 2:
                post_id, content = comment_message[0], comment_message[1]
            else:
                post_id, content = comment_message[0], ""
            author_id = self._get_post_author(post_id) or 0
            await self._pub(PostCommentedEvent(
                sim_time=self._sim_time(),
                comment_id=result["comment_id"],
                post_id=post_id,
                commenter_id=agent_id,
                post_author_id=author_id,
                content=content,
            ))
        return result

    async def report_post(self, agent_id: int, report_message: tuple):
        result = await super().report_post(agent_id, report_message)
        if result.get("success"):
            post_id, reason = report_message
            await self._pub(PostReportedEvent(
                sim_time=self._sim_time(),
                post_id=post_id,
                reporter_id=agent_id,
                reason=reason,
            ))
        return result

    async def follow(self, agent_id: int, followee_id: int):
        result = await super().follow(agent_id, followee_id)
        if result.get("success"):
            await self._pub(UserFollowedEvent(
                sim_time=self._sim_time(),
                follower_id=agent_id,
                followee_id=followee_id,
            ))
        return result

    async def unfollow(self, agent_id: int, followee_id: int):
        result = await super().unfollow(agent_id, followee_id)
        if result.get("success"):
            await self._pub(UserUnfollowedEvent(
                sim_time=self._sim_time(),
                follower_id=agent_id,
                followee_id=followee_id,
            ))
        return result

    async def update_rec_table(self):
        result = await super().update_rec_table()
        await self._pub(RecTableUpdatedEvent(sim_time=self._sim_time()))
        return result