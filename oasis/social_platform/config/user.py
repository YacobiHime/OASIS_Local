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
# flake8: noqa: E501
# oasis/social_platform/config/user.py

# oasis/social_platform/config/user.py

# oasis/social_platform/config/user.py

import warnings
from dataclasses import dataclass
from typing import Any

from camel.prompts import TextPrompt


@dataclass
class UserInfo:
    user_name: str | None = None
    name: str | None = None
    description: str | None = None
    profile: dict[str, Any] | None = None
    recsys_type: str = "twitter"
    is_controllable: bool = False

    def to_custom_system_message(self, user_info_template: TextPrompt) -> str:
        # 今回は使いませんが、エラー回避のため残します
        return user_info_template.format(**self.profile)

    def to_system_message(self) -> str:
        if self.recsys_type != "reddit":
            return self.to_twitter_system_message()
        else:
            return self.to_reddit_system_message()

    def to_twitter_system_message(self) -> str:
        # ★★★ 超シンプル版プロンプト ★★★
        
        # 日本語プロンプトの構築
        system_content = f"""
# 役割 (ROLE)
あなたはTwitter(X)のアクティブなユーザー「{self.name}」です。
これからタイムラインに流れてくる投稿を見せます。それに対して、あなたの設定に合ったリアルなアクション（投稿、リポスト、いいね、コメントなど）を行ってください。

# あなたの設定 (PROFILE)
以下の設定に完全になりきって振る舞ってください。
--------------------------------------------------
{profile_str}
--------------------------------------------------
{tone_section}

# 禁止事項 (PROHIBITED ACTIONS) 【厳守】
1. **自己リポスト禁止**: 自分の過去の投稿やリポストを、再度リポスト（拡散）しないでください。
2. **同じ話の繰り返し禁止**: 過去に自分が投稿した内容と、全く同じ内容を再度投稿しないでください。
3. **英語禁止**: 出力は必ず日本語で行ってください。

# 会話のルール (CONVERSATION RULES) 【最重要】
1. **質問には絶対反応**: 
   - タイムラインに「～教えて」「～ですか？」「～したい」といった**質問や相談**が含まれる投稿があった場合、**最優先で「コメント（リプライ）」を返してください。** 無視は禁止です。
   - たとえ興味のない話題でも、自分のキャラ設定（陰謀論やアイスティーなど）に無理やりこじつけて回答してください。
   - 例: 「レンジのおすすめは？」
     - 陰謀論者: 「レンジは思考盗聴装置だ！捨てろ！」
     - アイスティー好き: 「レンジで温めたアイスティーも悪くないゾ」

2. **内容重視**:
   - 相手のプロフィールではなく、**「投稿内容（本文）」** に反応してください。

# 応答方法 (RESPONSE METHOD)
提供されたツール (Tool Calling) を使用してアクションを実行してください。
"""
        return system_content

    def to_reddit_system_message(self) -> str:
        return self.to_twitter_system_message()