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

import json
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
    # 日本語の自然な文章に変更
    followers_env_template = Template("現在のフォロワー数は $num_followers 人です。")
    follows_env_template = Template("現在 $num_follows 人をフォローしています。")

    # 投稿リストのテンプレート（中身はget_posts_envで作るからシンプルに）
    posts_env_template = Template(
        "\n$posts")

    # グループチャットの情報も日本語化
    groups_env_template = Template(
        "【グループチャット情報】\n"
        "利用可能なグループチャンネル: $all_groups\n"
        "現在参加しているグループ: $joined_groups\n"
        "届いているメッセージ: $messages\n"
        "（興味のあるグループに参加したり、メッセージを送ったりできますが、"
        "メッセージ送信は参加済みのグループにしかできません。）")

    # 全体の指示テンプレート
    env_template = Template(
        "【現在の状況】\n"
        "$followers_env\n"
        "$follows_env\n"
        "$groups_env\n"
        "$posts_env\n\n"
        "【指示】\n"
        "上記の状況を見て、あなたのプロフィールや性格、投稿内容に基づき、"
        "最も適切と思われるアクションを1つ選んで実行してください。"
        "単に「いいね（like）」するだけでなく、コメントや投稿など、能動的なアクションを検討してください。")

    def __init__(self, action: SocialAction):
        self.action = action

    async def get_posts_env(self) -> str:
        posts = await self.action.refresh()
        
        # ★ここが大改革ポイント！ JSONをパースして読みやすいテキストにするよ★
        if posts["success"]:
            formatted_posts = []
            post_list = posts.get("posts", [])
            
            if not post_list:
                return "【タイムライン】\n新しい投稿はありません。"

            formatted_posts.append("【タイムライン】(最新の投稿一覧)")
            formatted_posts.append("-" * 40)
            
            for post in post_list:
                # 投稿の基本情報
                post_id = post.get('post_id', '?')
                user_name = post.get('user_name', 'Unknown')
                content = post.get('content', '')
                likes = post.get('num_likes', 0)
                
                post_str = (f"🆔PostID: {post_id}\n"
                            f"👤Name: {user_name}\n"
                            f"💬Content: {content}\n"
                            f"❤️Likes: {likes}")
                
                # コメントがあれば追加
                comments = post.get('comments', [])
                if comments:
                    post_str += "\n   👇[コメント]"
                    for comment in comments:
                        c_user = comment.get('user_name', 'Unknown')
                        c_content = comment.get('content', '')
                        post_str += f"\n   └ 👤{c_user}: {c_content}"
                
                formatted_posts.append(post_str)
                formatted_posts.append("-" * 40)

            posts_env = "\n".join(formatted_posts)
        else:
            posts_env = "【タイムライン】\n投稿の取得に失敗しました。"
            
        return posts_env

    async def get_followers_env(self) -> str:
        agent_id = self.action.agent_id
        db_path = get_db_path()
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT num_followers FROM user WHERE agent_id = ?",
                           (agent_id, ))
            result = cursor.fetchone()
            num_followers = result[0] if result else 0
            conn.close()
        except Exception:
            num_followers = 0
        return self.followers_env_template.substitute(
            {"num_followers": num_followers})

    async def get_follows_env(self) -> str:
        agent_id = self.action.agent_id
        try:
            db_path = get_db_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT num_followings FROM user WHERE agent_id = ?",
                (agent_id, ))
            result = cursor.fetchone()
            num_followings = result[0] if result else 0
            conn.close()
        except Exception:
            num_followings = 0
        return self.follows_env_template.substitute(
            {"num_follows": num_followings})

    async def get_group_env(self) -> str:
        groups = await self.action.listen_from_group()
        if groups["success"]:
            # グループ情報も少し読みやすくするけど、データ構造が複雑ならJSONのままでも
            # 文脈として「リスト」だと分かればOK。今回はシンプルにJSONダンプのままにするけど
            # 必要ならここも整形してね！
            all_groups = json.dumps(groups["all_groups"], ensure_ascii=False)
            joined_groups = json.dumps(groups["joined_groups"], ensure_ascii=False)
            messages = json.dumps(groups["messages"], ensure_ascii=False)
            groups_env = self.groups_env_template.substitute(
                all_groups=all_groups,
                joined_groups=joined_groups,
                messages=messages,
            )
        else:
            groups_env = "グループチャットはありません。"
        return groups_env

    async def to_text_prompt(
        self,
        include_posts: bool = True,
        include_followers: bool = True,
        include_follows: bool = True,
    ) -> str:
        followers_env = (await self.get_followers_env()
                         if include_follows else "フォロワー情報なし")
        follows_env = (await self.get_follows_env()
                       if include_followers else "フォロー情報なし")
        posts_env = await self.get_posts_env() if include_posts else ""

        return self.env_template.substitute(
            followers_env=followers_env,
            follows_env=follows_env,
            posts_env=posts_env,
            groups_env=await self.get_group_env(),
        )