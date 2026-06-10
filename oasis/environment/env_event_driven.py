"""
oasis/environment/env_event_driven.py
--------------------------------------
OasisEnv を拡張したイベントドリブン環境。

主な変更点:
1. `step_event_driven()` メソッドを追加
   - 通知キューに 1 件以上の未読通知があるエージェントだけを起動
   - 残りのエージェントはランダムに一定割合だけ起動
2. `register_default_handlers()` でエージェント通知購読を自動設定
3. `InformationInjector` を組み込み、ステップごとに SearXNG 注入を行う

後方互換性: 元の `step()` メソッドはそのまま使える。
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional, Union

from oasis.environment.env import OasisEnv
from oasis.environment.env_action import LLMAction, ManualAction
from oasis.events.event_bus import EventBus
from oasis.events.event_types import (
    EventKind,
    PostCreatedEvent,
    UserFollowedEvent,
    PostLikedEvent,
    PostCommentedEvent,
    PostRepostedEvent,
)
from oasis.social_agent.agent import SocialAgent
from oasis.social_agent.agent_graph import AgentGraph
from oasis.social_platform.platform import Platform
from oasis.social_platform.typing import ActionType, DefaultPlatformType

logger = logging.getLogger("oasis.env.event_driven")


class EventDrivenEnv(OasisEnv):
    """
    イベント・情報ドリブン環境。

    Parameters
    ----------
    agent_graph : AgentGraph
    platform : Platform or DefaultPlatformType
        EventDrivenPlatform を推奨 (イベント発行が有効になる)
    event_bus : EventBus
        シミュレーション全体で共有するイベントバス
    database_path : str, optional
    semaphore : int
    baseline_wakeup_rate : float
        通知がなくても毎ステップ起動するエージェントの割合 (0.0〜1.0)
    information_injector : optional
        InformationInjector インスタンス (省略可)
    """

    def __init__(
        self,
        agent_graph: AgentGraph,
        platform: Union[DefaultPlatformType, Platform],
        event_bus: EventBus,
        database_path: Optional[str] = None,
        semaphore: int = 128,
        baseline_wakeup_rate: float = 0.1,
        information_injector=None,
    ) -> None:
        super().__init__(
            agent_graph=agent_graph,
            platform=platform,
            database_path=database_path,
            semaphore=semaphore,
        )
        self.event_bus = event_bus
        self.baseline_wakeup_rate = baseline_wakeup_rate
        self.information_injector = information_injector
        self._step_count: int = 0

    # ─────────────────────────────────────
    # 初期化: エージェント通知購読の自動設定
    # ─────────────────────────────────────

    async def reset(self) -> None:
        """プラットフォーム起動とエージェント登録、通知購読の設定。"""
        await super().reset()
        self.register_default_handlers()

    def register_default_handlers(self) -> None:
        """
        全エージェントをデフォルト通知設定で EventBus に登録する。

        - 自分がフォローしているユーザが投稿 → 通知
        - 自分の投稿にいいね・コメント・リポスト → 通知
        - 外部情報 (ExternalInfoEvent) → 全員に通知
        グローバルハンドラで「誰に届けるか」を動的に決定する。
        """
        # エージェントキューの登録 (全員)
        for agent_id, agent in self.agent_graph.agent_mappings.items():
            self.event_bus.register_agent(int(agent_id))

        # PostCreated → フォロワーに届ける
        self.event_bus.subscribe(
            EventKind.POST_CREATED,
            self._make_post_created_handler(),
        )

        # PostLiked / PostCommented / PostReposted → 投稿者に届ける
        for kind in [EventKind.POST_LIKED, EventKind.POST_COMMENTED,
                     EventKind.POST_REPOSTED]:
            self.event_bus.subscribe(kind, self._make_author_notify_handler())

        # UserFollowed → フォローされた人に届ける
        self.event_bus.subscribe(
            EventKind.USER_FOLLOWED,
            self._make_followee_notify_handler(),
        )

        # ExternalInfo → EventBus 内で全エージェントに配送 (event_bus.publish の仕様)

        logger.info("EventDrivenEnv: default handlers registered for %d agents",
                    len(self.event_bus._agent_queues))

    # ─────────────────────────────────────
    # イベントドリブン ステップ
    # ─────────────────────────────────────

    async def step_event_driven(
        self,
        manual_actions: Optional[dict] = None,
    ) -> None:
        """
        イベントドリブンなシミュレーション 1 ステップ。

        1. InformationInjector による外部情報注入 (設定されている場合)
        2. レコメンドテーブル更新
        3. 通知ありエージェント + ベースライン割合エージェントを起動
        4. Clock 更新

        Parameters
        ----------
        manual_actions : dict, optional
            {SocialAgent: ManualAction | LLMAction} を追加で渡せる
            (元の step() と同じ形式)
        """
        self._step_count += 1
        step = self._step_count

        # 1. 外部情報注入
        if self.information_injector is not None:
            injected = await self.information_injector.maybe_inject(step)
            if injected:
                logger.info("Step %d: injected %d external info events", step, injected)

        # 2. レコメンドテーブル更新
        await self.platform.update_rec_table()
        logger.info("Step %d: rec table updated", step)

        # 3. 起動エージェントを決定
        agents_to_wake = self._select_agents_to_wake()

        # manual_actions があればそちらのエージェントも追加
        if manual_actions:
            for agent in manual_actions:
                if agent not in agents_to_wake:
                    agents_to_wake[agent] = LLMAction()

        logger.info(
            "Step %d: waking %d / %d agents",
            step,
            len(agents_to_wake),
            len(self.agent_graph.agent_mappings),
        )

        # 4. タスク実行
        tasks = []
        for agent, action in agents_to_wake.items():
            if isinstance(action, list):
                for a in action:
                    tasks.append(self._build_task(agent, a))
            else:
                tasks.append(self._build_task(agent, action))

        await asyncio.gather(*tasks)
        logger.info("Step %d: all actions done", step)

        # 5. Clock 更新
        if self.platform_type == DefaultPlatformType.TWITTER:
            self.platform.sandbox_clock.time_step += 1

    # ─────────────────────────────────────
    # 起動エージェント選定
    # ─────────────────────────────────────

    def _select_agents_to_wake(self) -> dict:
        """
        通知ありエージェント + ベースライン割合のランダムエージェントを
        {agent: LLMAction} の辞書で返す。
        """
        all_agents = {
            int(aid): agent
            for aid, agent in self.agent_graph.agent_mappings.items()
        }

        # 通知があるエージェント
        notified_ids = set(self.event_bus.agents_with_notifications())

        # ベースラインランダム
        remaining = [
            (aid, agent)
            for aid, agent in all_agents.items()
            if aid not in notified_ids
        ]
        baseline_n = max(0, int(len(remaining) * self.baseline_wakeup_rate))
        baseline_sample = random.sample(remaining, min(baseline_n, len(remaining)))
        baseline_ids = {aid for aid, _ in baseline_sample}

        wake_ids = notified_ids | baseline_ids
        return {
            all_agents[aid]: LLMAction()
            for aid in wake_ids
            if aid in all_agents
        }

    # ─────────────────────────────────────
    # タスクビルダ
    # ─────────────────────────────────────

    def _build_task(self, agent: SocialAgent, action):
        if isinstance(action, ManualAction):
            if action.action_type == ActionType.INTERVIEW:
                return self._perform_interview_action(
                    agent, action.action_args.get("prompt", "")
                )
            return agent.perform_action_by_data(
                action.action_type, **action.action_args
            )
        # LLMAction
        return self._perform_llm_action(agent)

    # ─────────────────────────────────────
    # イベントハンドラファクトリ
    # ─────────────────────────────────────

    def _make_post_created_handler(self):
        """PostCreatedEvent → 投稿者のフォロワー全員の通知キューに push"""
        platform = self.platform
        event_bus = self.event_bus

        async def handler(event: PostCreatedEvent):
            try:
                # フォロワーを DB から取得
                platform.pl_utils._execute_db_command(
                    "SELECT follower_id FROM follow WHERE followee_id = ?",
                    (event.author_id,),
                )
                rows = platform.db_cursor.fetchall()
                for (follower_id,) in rows:
                    q = event_bus.get_agent_queue(follower_id)
                    if q:
                        q.put_nowait(event)
            except Exception as exc:
                logger.warning("post_created_handler error: %s", exc)

        return handler

    def _make_author_notify_handler(self):
        """Like / Comment / Repost → 投稿者 (post_author_id) の通知キューに push"""
        event_bus = self.event_bus

        def handler(event):
            author_id = getattr(event, "post_author_id", None)
            if author_id is None:
                return
            q = event_bus.get_agent_queue(author_id)
            if q:
                q.put_nowait(event)

        return handler

    def _make_followee_notify_handler(self):
        """UserFollowedEvent → フォローされた人 (followee_id) に push"""
        event_bus = self.event_bus

        def handler(event: UserFollowedEvent):
            q = event_bus.get_agent_queue(event.followee_id)
            if q:
                q.put_nowait(event)

        return handler