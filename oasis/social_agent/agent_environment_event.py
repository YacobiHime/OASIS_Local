"""
oasis/social_agent/agent_environment_event.py
----------------------------------------------
SocialEnvironment を拡張し、エージェントが持つ未読通知と
外部情報 (SearXNG 経由の ExternalInfoEvent) を
to_text_prompt() に自動挿入するミックスイン。

使い方:
    from oasis.social_agent.agent_environment_event import EventAwareSocialEnvironment

    env = EventAwareSocialEnvironment(
        action=social_action,
        notification_queue=bus.get_agent_queue(agent_id),
    )
    prompt = await env.to_text_prompt()
"""
from __future__ import annotations

from typing import Optional

from oasis.social_agent.agent_environment import SocialEnvironment
from oasis.social_agent.agent_action import SocialAction
from oasis.events.event_bus import NotificationQueue
from oasis.events.event_types import (
    EventKind,
    PostCreatedEvent,
    PostLikedEvent,
    PostCommentedEvent,
    PostRepostedEvent,
    UserFollowedEvent,
    ExternalInfoEvent,
)


class EventAwareSocialEnvironment(SocialEnvironment):
    """
    通知キューと外部情報コンテキストを持つ拡張版 SocialEnvironment。
    """

    def __init__(
        self,
        action: SocialAction,
        notification_queue: Optional[NotificationQueue] = None,
    ) -> None:
        super().__init__(action)
        self.notification_queue = notification_queue

    # ─────────────────────────────────────
    # 通知テキスト生成
    # ─────────────────────────────────────

    def get_notifications_text(self) -> str:
        """
        未読通知をすべて取り出してテキスト化して返す。
        呼び出すたびにキューが消費される点に注意。
        """
        if self.notification_queue is None:
            return ""

        events = self.notification_queue.drain()
        if not events:
            return ""

        lines = ["【🔔 通知・新着情報】"]
        external_items = []
        notif_items = []

        for event in events:
            if event.kind == EventKind.EXTERNAL_INFO:
                assert isinstance(event, ExternalInfoEvent)
                external_items.append(
                    f"  📰 外部ニュース [{event.query}]\n"
                    f"     タイトル: {event.title}\n"
                    f"     概要: {event.snippet[:100]}...\n"
                    f"     URL: {event.url}"
                )
            elif event.kind == EventKind.POST_CREATED:
                assert isinstance(event, PostCreatedEvent)
                notif_items.append(
                    f"  🆕 User {event.author_id} が新しく投稿しました "
                    f"(Post ID: {event.post_id}): 「{event.content[:60]}」"
                )
            elif event.kind == EventKind.POST_LIKED:
                assert isinstance(event, PostLikedEvent)
                notif_items.append(
                    f"  ❤️  User {event.liker_id} があなたの投稿 "
                    f"(Post ID: {event.post_id}) にいいねしました"
                )
            elif event.kind == EventKind.POST_COMMENTED:
                assert isinstance(event, PostCommentedEvent)
                notif_items.append(
                    f"  💬 User {event.commenter_id} があなたの投稿 "
                    f"(Post ID: {event.post_id}) にコメントしました: 「{event.content[:60]}」"
                )
            elif event.kind == EventKind.POST_REPOSTED:
                assert isinstance(event, PostRepostedEvent)
                notif_items.append(
                    f"  🔁 User {event.reposter_id} があなたの投稿 "
                    f"(Post ID: {event.original_post_id}) をリポストしました"
                )
            elif event.kind == EventKind.USER_FOLLOWED:
                assert isinstance(event, UserFollowedEvent)
                notif_items.append(
                    f"  👤 User {event.follower_id} があなたをフォローしました"
                )
            else:
                notif_items.append(f"  ℹ️  {event.kind.value}")

        if notif_items:
            lines.append("  ─ SNS 通知 ─")
            lines.extend(notif_items)
        if external_items:
            lines.append("  ─ 外部情報 (SearXNG 検索より) ─")
            lines.extend(external_items)

        return "\n".join(lines) + "\n"

    # ─────────────────────────────────────
    # to_text_prompt のオーバーライド
    # ─────────────────────────────────────

    async def to_text_prompt(
        self,
        include_posts: bool = True,
        include_followers: bool = True,
        include_follows: bool = True,
    ) -> str:
        base_prompt = await super().to_text_prompt(
            include_posts=include_posts,
            include_followers=include_followers,
            include_follows=include_follows,
        )
        notif_text = self.get_notifications_text()
        if notif_text:
            return notif_text + "\n" + base_prompt
        return base_prompt