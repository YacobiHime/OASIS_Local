"""
oasis/events/event_bus.py
--------------------------
非同期イベントバス。

設計方針:
- pub/sub: `subscribe(EventKind, handler)` でグローバルハンドラを登録
- per-agent inbox: `subscribe_agent(agent_id, event_kinds)` で
  特定エージェントの通知キューにイベントを届ける
- `publish(event)` は同期的にハンドラを呼ぶが、
  コルーチンハンドラは asyncio.create_task で非同期実行
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable, Union

from oasis.events.event_types import BaseEvent, EventKind

logger = logging.getLogger("oasis.events.bus")

Handler = Callable[[BaseEvent], Union[None, Awaitable[None]]]


class NotificationQueue:
    """エージェント 1 体分の通知受信ボックス。"""

    def __init__(self, agent_id: int, maxsize: int = 256):
        self.agent_id = agent_id
        self._queue: asyncio.Queue[BaseEvent] = asyncio.Queue(maxsize=maxsize)

    def put_nowait(self, event: BaseEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                f"NotificationQueue for agent {self.agent_id} is full. "
                "Dropping event: %s", event.kind
            )

    def drain(self) -> list[BaseEvent]:
        """キューに溜まっている通知をすべて取り出す (非破壊ではなく消費)。"""
        items = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return items

    def __len__(self) -> int:
        return self._queue.qsize()


class EventBus:
    """
    シミュレーション全体で 1 インスタンス共有するイベントバス。

    使い方:
        bus = EventBus()

        # グローバルサブスクライバ (RecsysUpdater など)
        bus.subscribe(EventKind.POST_CREATED, my_handler)

        # エージェント通知
        bus.subscribe_agent(agent_id=5,
                            event_kinds=[EventKind.POST_LIKED,
                                         EventKind.USER_FOLLOWED])

        # 発行
        await bus.publish(PostCreatedEvent(post_id=1, author_id=5, content="hi"))
    """

    def __init__(self) -> None:
        # EventKind -> list[Handler]
        self._global_handlers: dict[EventKind, list[Handler]] = defaultdict(list)
        # agent_id -> NotificationQueue
        self._agent_queues: dict[int, NotificationQueue] = {}
        # agent_id -> set[EventKind] (購読しているイベント種別)
        self._agent_subscriptions: dict[int, set[EventKind]] = defaultdict(set)

    # ─────────────────────────────────────
    # グローバルサブスクライバ
    # ─────────────────────────────────────

    def subscribe(self, kind: EventKind, handler: Handler) -> None:
        """特定のイベント種別にグローバルハンドラを登録する。"""
        self._global_handlers[kind].append(handler)

    def subscribe_many(self, kinds: list[EventKind], handler: Handler) -> None:
        for kind in kinds:
            self.subscribe(kind, handler)

    # ─────────────────────────────────────
    # エージェント通知
    # ─────────────────────────────────────

    def register_agent(self, agent_id: int) -> NotificationQueue:
        """エージェントの通知キューを作成・登録する。"""
        if agent_id not in self._agent_queues:
            self._agent_queues[agent_id] = NotificationQueue(agent_id)
        return self._agent_queues[agent_id]

    def subscribe_agent(
        self, agent_id: int, event_kinds: list[EventKind]
    ) -> NotificationQueue:
        """エージェントが指定イベント種別の通知を受け取れるようにする。"""
        queue = self.register_agent(agent_id)
        self._agent_subscriptions[agent_id].update(event_kinds)
        return queue

    def get_agent_queue(self, agent_id: int) -> NotificationQueue | None:
        return self._agent_queues.get(agent_id)

    def agents_with_notifications(self) -> list[int]:
        """1 件以上の未読通知を持つエージェント ID リストを返す。"""
        return [
            aid for aid, q in self._agent_queues.items() if len(q) > 0
        ]

    def get_all_queue_sizes(self) -> dict[int, int]:
        """全エージェントの未読通知数を {agent_id: size} で返す。"""
        return {aid: len(q) for aid, q in self._agent_queues.items()}

    # ─────────────────────────────────────
    # イベント発行
    # ─────────────────────────────────────

    async def publish(self, event: BaseEvent) -> None:
        """
        イベントを発行する。
        1. グローバルハンドラを非同期で呼び出す
        2. 該当イベント種別を購読しているエージェントの通知キューへ push
        3. ExternalInfoEvent は target_agent_ids に明示指定された
           エージェントへのみ、または空なら全エージェントへ
        """
        logger.debug("publish: %s", event.kind)

        # グローバルハンドラ呼び出し (await で確実に完了させる)
        for handler in self._global_handlers.get(event.kind, []):
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result

        # エージェント通知の配送
        from oasis.events.event_types import ExternalInfoEvent, EventKind  # noqa: F401

        if isinstance(event, ExternalInfoEvent):
            targets = event.target_agent_ids or list(self._agent_queues.keys())
            for aid in targets:
                q = self._agent_queues.get(aid)
                if q is not None:
                    q.put_nowait(event)
        else:
            # 通常イベント: そのイベント種別を購読しているエージェントへ
            for aid, kinds in self._agent_subscriptions.items():
                if event.kind in kinds:
                    q = self._agent_queues.get(aid)
                    if q is not None:
                        q.put_nowait(event)

    def publish_sync(self, event: BaseEvent) -> None:
        """
        同期コンテキスト (Platform のアクションメソッド等) から
        イベントを発行するためのヘルパ。
        実行中の event loop があれば create_task、なければ
        グローバルハンドラだけ同期実行してキューへ push する。
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            # テスト等でループが無い場合はベストエフォート
            for handler in self._global_handlers.get(event.kind, []):
                result = handler(event)
                # コルーチンは無視 (ループなし)

            from oasis.events.event_types import ExternalInfoEvent  # noqa: F401
            if isinstance(event, ExternalInfoEvent):
                targets = (
                    event.target_agent_ids or list(self._agent_queues.keys())
                )
                for aid in targets:
                    q = self._agent_queues.get(aid)
                    if q:
                        q.put_nowait(event)
            else:
                for aid, kinds in self._agent_subscriptions.items():
                    if event.kind in kinds:
                        q = self._agent_queues.get(aid)
                        if q:
                            q.put_nowait(event)