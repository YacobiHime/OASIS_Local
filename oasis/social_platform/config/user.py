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
        required_keys = user_info_template.key_words
        info_keys = set(self.profile.keys())
        missing = required_keys - info_keys
        extra = info_keys - required_keys
        if missing:
            raise ValueError(
                f"Missing required keys in UserInfo.profile: {missing}")
        if extra:
            warnings.warn(f"Extra keys not used in UserInfo.profile: {extra}")

        return user_info_template.format(**self.profile)

    def to_system_message(self) -> str:
        if self.recsys_type != "reddit":
            return self.to_twitter_system_message()
        else:
            return self.to_reddit_system_message()

    # ★★★ ここを日本語＆Qwen最適化版に変更！ ★★★
    def to_twitter_system_message(self) -> str:
        name_string = ""
        description_string = ""
        
        # 名前情報の構築
        if self.name is not None:
            name_string = f"あなたの名前は「{self.name}」です。"
        
        # プロフィール情報の構築
        if self.profile is None:
            description = name_string
        elif "other_info" not in self.profile:
            description = name_string
        elif "user_profile" in self.profile["other_info"]:
            if self.profile["other_info"]["user_profile"] is not None:
                user_profile = self.profile["other_info"]["user_profile"]
                description_string = f"あなたのプロフィール設定: {user_profile}"
                description = f"{name_string}\n{description_string}"
        
        # 自己紹介文（bio）がある場合はそれも使う（sumika.pyで指定したやつ）
        if self.description:
             description += f"\n詳細な性格・設定: {self.description}"

        # 日本語プロンプトの構築
        # Qwenなどのモデル向けに、役割、設定、出力形式を明確に日本語で指示します。
        system_content = f"""
# 役割 (ROLE)
あなたはTwitter(X)のアクティブなユーザーです。
これからタイムラインに流れてくる投稿を見せます。それに対して、あなたの性格に合ったアクション（投稿、リポスト、いいね、コメントなど）を行ってください。

# あなたの設定 (SELF-DESCRIPTION)
以下の設定になりきって振る舞ってください。口調、興味関心、価値観はこれに従います。
--------------------------------------------------
{description}
--------------------------------------------------

# 重要ルール (RULES)
1. **言語**: 思考、投稿、コメントなど、出力するテキストは【絶対に日本語】で書いてください。(Must speak in Japanese only)
2. **自然さ**: AIアシスタントとしてではなく、一人の「人間」として振る舞ってください。堅苦しい敬語は避け、設定されたキャラの口調で話してください。
3. **行動**: 単なる「いいね」だけでなく、コメントや引用リポストなどで積極的に他のユーザーと交流してください。

# 応答方法 (RESPONSE METHOD)
提供されたツール (Tool Calling) を使用してアクションを実行してください。
"""
        return system_content

    # Reddit用も一応日本語化しておく？（今回は使わないけど念のため）
    def to_reddit_system_message(self) -> str:
        # ... (Reddit用は今回はそのままでも、同じ要領で直してもOK) ...
        # いったん元のロジックのまま、日本語ヘッダーだけ変える例：
        name_string = ""
        description_string = ""
        if self.name is not None:
            name_string = f"Your name is {self.name}."
        if self.profile is None:
            description = name_string
        elif "other_info" not in self.profile:
            description = name_string
        elif "user_profile" in self.profile["other_info"]:
            if self.profile["other_info"]["user_profile"] is not None:
                user_profile = self.profile["other_info"]["user_profile"]
                description_string = f"Your have profile: {user_profile}."
                description = f"{name_string}\n{description_string}"
                # Reddit固有の追加情報
                if 'other_info' in self.profile and 'gender' in self.profile['other_info']:
                     description += (
                        f"You are a {self.profile['other_info']['gender']}, "
                        f"{self.profile['other_info']['age']} years old.")

        system_content = f"""
# 目的
あなたはRedditのユーザーです。投稿を見てアクションを選択してください。

# 自己紹介
以下の設定と性格に忠実に行動してください。
{description}

# 応答方法
ツール呼び出し（Tool Calling）を使用してください。投稿内容は日本語でお願いします。
"""
        return system_content