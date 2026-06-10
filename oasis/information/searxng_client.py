"""
oasis/information/searxng_client.py
------------------------------------
研究室内の SearXNG 検索サーバへの非同期クライアント。

使い方:
    async with SearXNGClient("http://192.168.15.146:8080") as client:
        results = await client.search("AI ethics", num_results=5)
        for r in results:
            print(r.title, r.snippet, r.url)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

logger = logging.getLogger("oasis.information.searxng")


@dataclass
class SearchResult:
    title: str
    snippet: str        # content / description
    url: str
    engine: str = ""
    score: float = 0.0
    # 元の生 dict (必要ならアクセス可能)
    raw: dict = field(default_factory=dict, repr=False)


class SearXNGClient:
    """
    SearXNG JSON API のシンプルな非同期クライアント。

    Parameters
    ----------
    base_url : str
        例: "http://192.168.15.146:8080"
    timeout : float
        1 リクエストのタイムアウト秒数 (デフォルト 10 秒)
    """

    DEFAULT_PARAMS = {
        "format": "json",
        "language": "ja-JP",   # 日本語優先 (en-US に変更可)
        "safesearch": "0",
    }

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    # ─────────────────────────────────────
    # Context manager
    # ─────────────────────────────────────

    async def __aenter__(self) -> "SearXNGClient":
        self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self

    async def __aexit__(self, *_) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ─────────────────────────────────────
    # 検索
    # ─────────────────────────────────────

    async def search(
        self,
        query: str,
        num_results: int = 5,
        categories: str = "general",
        extra_params: Optional[dict] = None,
    ) -> list[SearchResult]:
        """
        SearXNG に検索をかけ、結果を SearchResult のリストで返す。

        Parameters
        ----------
        query : str
            検索クエリ
        num_results : int
            返す最大件数
        categories : str
            SearXNG カテゴリ ("general", "news", "science" など)
        extra_params : dict, optional
            追加クエリパラメータ

        Returns
        -------
        list[SearchResult]
            検索結果。接続失敗時は空リストを返す (例外は発生しない)。
        """
        session = await self._ensure_session()
        params = {
            **self.DEFAULT_PARAMS,
            "q": query,
            "categories": categories,
        }
        if extra_params:
            params.update(extra_params)

        try:
            async with session.get(
                f"{self.base_url}/search", params=params
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        "SearXNG returned HTTP %d for query=%r", resp.status, query
                    )
                    return []
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            logger.error("SearXNG request failed: %s", exc)
            return []
        except Exception as exc:
            logger.error("SearXNG unexpected error: %s", exc)
            return []

        results: list[SearchResult] = []
        for item in data.get("results", [])[:num_results]:
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    snippet=item.get("content", item.get("description", "")),
                    url=item.get("url", ""),
                    engine=", ".join(item.get("engines", [])),
                    score=float(item.get("score", 0)),
                    raw=item,
                )
            )
        logger.debug("SearXNG query=%r → %d results", query, len(results))
        return results

    async def search_news(
        self, query: str, num_results: int = 5
    ) -> list[SearchResult]:
        """ニュースカテゴリで検索するショートカット。"""
        return await self.search(
            query, num_results=num_results, categories="news"
        )