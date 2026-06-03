# =========== Copyright 2023 @ CAMEL-AI.org. All Rights Reserved. ===========
# Licensed under the Apache License, Version 2.0 (the “License”);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an “AS IS” BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =========== Copyright 2023 @ CAMEL-AI.org. All Rights Reserved. ===========
from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from string import Template

from oasis.social_agent.agent_action import SocialAction
from oasis.social_platform.database import get_db_path


class Environment(ABC):

    @abstractmethod
    def to_text_prompt(self) -> str:
        r"""Convert the environment to text prompt."""
        raise NotImplementedError


class SocialEnvironment(Environment):
    # コンパクトな全体テンプレート（グループチャットは使用時のみ追加）
    env_template = Template(
        "フォロワー:$num_followers / フォロー中:$num_follows\n" "$posts_env"
    )

    def __init__(self, action: SocialAction):
        self.action = action

    # ★ コンテンツを指定文字数で切り詰めるヘルパー
    @staticmethod
    def _trim(text: str, max_len: int = 80) -> str:
        if not text:
            return ""
        text = text.replace("\n", " ")
        return text[:max_len] + "…" if len(text) > max_len else text

    async def get_posts_env(self) -> str:
        MAX_COMMENTS = 3  # 1投稿あたりのコメント表示上限
        MAX_CONTENT = 80  # 本文・コメントの文字数上限

        posts = await self.action.refresh()

        if not posts.get("success"):
            return "【TL】取得失敗"

        post_list = posts.get("posts", [])
        if not post_list:
            return "【TL】新着なし"

        lines = ["【TL】"]
        for post in post_list:
            pid = post.get("post_id", "?")
            uid = post.get("user_id", "?")
            body = self._trim(post.get("content", ""), MAX_CONTENT)
            likes = post.get("num_likes", 0)

            lines.append(f"[P{pid}] User{uid}: {body} (♥{likes})")

            # トップレベルコメントのみ、上限件数まで表示
            comments = post.get("comments", [])
            top = [c for c in comments if not c.get("parent_comment_id")]
            for c in top[:MAX_COMMENTS]:
                cid = c.get("comment_id", "?")
                c_uid = c.get("user_id", "?")
                c_body = self._trim(c.get("content", ""), MAX_CONTENT)
                lines.append(f"  └[C{cid}] User{c_uid}: {c_body}")

        return "\n".join(lines)

    async def get_followers_env(self) -> int:
        agent_id = self.action.agent_id
        db_path = get_db_path()
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT num_followers FROM user WHERE agent_id = ?", (agent_id,)
            )
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
        except Exception:
            return 0

    async def get_follows_env(self) -> int:
        agent_id = self.action.agent_id
        try:
            db_path = get_db_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT num_followings FROM user WHERE agent_id = ?", (agent_id,)
            )
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
        except Exception:
            return 0

    async def to_text_prompt(
        self,
        include_posts: bool = True,
        include_followers: bool = True,
        include_follows: bool = True,
    ) -> str:
        num_followers = await self.get_followers_env() if include_followers else 0
        num_follows = await self.get_follows_env() if include_follows else 0
        posts_env = await self.get_posts_env() if include_posts else ""

        return self.env_template.substitute(
            num_followers=num_followers,
            num_follows=num_follows,
            posts_env=posts_env,
        )
