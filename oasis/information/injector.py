"""
oasis/information/injector.py
------------------------------
SearXNG から定期的に情報を取得し、EventBus 経由でシミュレーション内に注入する。

主な役割:
1. 設定されたトピック一覧を順番に SearXNG へ投げる
2. 取得した記事を ExternalInfoEvent としてバスに publish
3. 任意で Platform にシードポストとして投稿する
   (ニュースボット エージェントが代わりに投稿する設計も可)

使い方:
    injector = InformationInjector(
        event_bus=bus,
        searxng_url="http://192.168.15.146:8080",
        topics=["AI ethics", "SNS misinformation"],
        inject_interval_steps=5,  # 何ステップごとに注入するか
        num_results_per_topic=3,
        platform=platform,        # シードポスト投稿する場合は渡す
        news_bot_agent_id=0,      # 投稿に使うユーザID
    )
    # シミュレーションループ内で
    await injector.maybe_inject(current_step)
"""
from __future__ import annotations

import logging
import random
from typing import Optional

from oasis.events.event_types import ExternalInfoEvent
from oasis.events.event_bus import EventBus
from oasis.information.searxng_client import SearXNGClient

logger = logging.getLogger("oasis.information.injector")


class InformationInjector:
    """
    SearXNG から情報を取得して EventBus に流し込む注入器。

    Parameters
    ----------
    event_bus : EventBus
        注入先のイベントバス
    searxng_url : str
        SearXNG の URL (例: "http://192.168.15.146:8080")
    topics : list[str]
        定期検索するトピック一覧
    inject_interval_steps : int
        何シミュレーションステップごとに注入を試みるか
    num_results_per_topic : int
        1 トピックあたり取得する件数
    platform : optional
        シードポスト自動投稿する場合は Platform インスタンスを渡す
    news_bot_agent_id : int
        シードポスト投稿に使うエージェント ID (platform が渡された場合のみ使用)
    target_agent_ids : list[int]
        指定した場合、そのエージェントにのみ通知する。空 = ブロードキャスト
    categories : str
        SearXNG 検索カテゴリ ("general", "news" など)
    deduplicate : bool
        同じ URL を 2 度以上注入しない (デフォルト True)
    """

    def __init__(
        self,
        event_bus: EventBus,
        searxng_url: str,
        topics: list[str],
        inject_interval_steps: int = 5,
        num_results_per_topic: int = 3,
        platform=None,
        news_bot_agent_id: int = 0,
        target_agent_ids: Optional[list[int]] = None,
        categories: str = "general",
        deduplicate: bool = True,
    ) -> None:
        self.bus = event_bus
        self.client = SearXNGClient(searxng_url)
        self.topics = list(topics)
        self.interval = inject_interval_steps
        self.num_results = num_results_per_topic
        self.platform = platform
        self.bot_agent_id = news_bot_agent_id
        self.target_agent_ids = target_agent_ids or []
        self.categories = categories
        self.deduplicate = deduplicate

        self._seen_urls: set[str] = set()
        self._topic_index: int = 0        # ラウンドロビン用
        self._last_inject_step: int = -1

    # ─────────────────────────────────────
    # メインエントリ
    # ─────────────────────────────────────

    async def maybe_inject(self, current_step: int) -> int:
        """
        current_step が inject_interval_steps の倍数のときだけ注入を実行する。

        Returns
        -------
        int
            今回注入したイベント数 (0 = スキップ or 結果なし)
        """
        if current_step - self._last_inject_step < self.interval:
            return 0
        self._last_inject_step = current_step
        return await self.inject_now(current_step)

    async def inject_now(self, sim_time=None) -> int:
        """
        即座に 1 トピック分の検索を行い、イベントを注入する。
        """
        if not self.topics:
            return 0

        query = self.topics[self._topic_index % len(self.topics)]
        self._topic_index += 1

        logger.info("InformationInjector: searching query=%r", query)
        results = await self.client.search(
            query,
            num_results=self.num_results,
            categories=self.categories,
        )

        injected = 0
        for result in results:
            if self.deduplicate and result.url in self._seen_urls:
                continue
            self._seen_urls.add(result.url)

            # シードポスト自動投稿 (platform が渡された場合)
            post_id: Optional[int] = None
            if self.platform is not None:
                post_content = self._format_post(query, result)
                try:
                    res = await self.platform.create_post(
                        self.bot_agent_id, post_content
                    )
                    post_id = res.get("post_id")
                except Exception as exc:
                    logger.warning("Failed to create seed post: %s", exc)

            event = ExternalInfoEvent(
                sim_time=sim_time,
                query=query,
                title=result.title,
                snippet=result.snippet,
                url=result.url,
                target_agent_ids=list(self.target_agent_ids),
                injected_post_id=post_id,
            )
            await self.bus.publish(event)
            injected += 1

        logger.info(
            "InformationInjector: injected %d events for query=%r", injected, query
        )
        return injected

    async def inject_targeted(
        self,
        query: str,
        agent_ids: list[int],
        sim_time=None,
        num_results: Optional[int] = None,
    ) -> int:
        """
        指定エージェントに向けて特定クエリの情報を即注入する
        (関心プロファイルに基づいたパーソナライズ注入などに使う)。
        """
        results = await self.client.search(
            query,
            num_results=num_results or self.num_results,
            categories=self.categories,
        )
        injected = 0
        for result in results:
            event = ExternalInfoEvent(
                sim_time=sim_time,
                query=query,
                title=result.title,
                snippet=result.snippet,
                url=result.url,
                target_agent_ids=agent_ids,
            )
            await self.bus.publish(event)
            injected += 1
        return injected

    async def close(self) -> None:
        await self.client.close()

    # ─────────────────────────────────────
    # ヘルパ
    # ─────────────────────────────────────

    @staticmethod
    def _format_post(query: str, result) -> str:
        """検索結果から SNS 投稿テキストを生成する。"""
        title = result.title[:60] if result.title else query
        snippet = result.snippet[:120] if result.snippet else ""
        url = result.url
        return f"【ニュース】{title}\n{snippet}\n{url}"