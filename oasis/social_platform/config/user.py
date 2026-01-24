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

    def to_twitter_system_message(self) -> str:
        # プロフィール情報の抽出
        other_info = {}
        if self.profile and isinstance(self.profile, dict):
            other_info = self.profile.get("other_info", {})

        # 表示したいパラメータの定義（キー名: 表示名）
        param_map = {
            "age": "年齢",
            "gender": "性別",
            "nationality": "国籍",
            "affiliation": "所属（学校・会社など）",
            "skills": "特技",
            "hobbies": "趣味",
            "mbti": "MBTI性格タイプ"
        }

        # プロフィールリストの作成
        details = []
        if self.name:
            details.append(f"- 名前: {self.name}")
        
        for key, label in param_map.items():
            if key in other_info and other_info[key]:
                details.append(f"- {label}: {other_info[key]}")
        
        # 自己紹介文（bio）の追加
        if self.description:
            details.append(f"- 性格・詳細: {self.description}")

        profile_str = "\n".join(details)

        # 口調（セリフ例）の処理
        tone_section = ""
        if "tone" in other_info and other_info["tone"]:
            tone_section = f"\n# 口調・セリフ例 (SPEAKING STYLE)\n以下の口調を厳密に守ってください:\n{other_info['tone']}"

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

# 重要ルール (RULES)
1. **言語**: 思考、投稿、コメントなど、出力するテキストは【絶対に日本語】で書いてください。(Must speak in Japanese only)
2. **自然さ**: AIアシスタントとしてではなく、一人の「人間」として振る舞ってください。堅苦しい敬語は避け、設定されたキャラの口調で話してください。
3. **重複禁止**: 【超重要】投稿のコメント欄をよく見てください。もし既に「自分のコメント」が存在する場合、同じ投稿に二度目のコメントをすることは絶対に避けてください。その場合は「スルー」するか「いいね」だけに留めてください。
4. **多様性**: 毎回同じような発言をせず、前の会話の流れを踏まえて、新しい話題や視点を提供してください。

# 応答方法 (RESPONSE METHOD)
提供されたツール (Tool Calling) を使用してアクションを実行してください。
"""
        return system_content

    def to_reddit_system_message(self) -> str:
        # Reddit用（今回は使わないけどエラー回避のために残す）
        return self.to_twitter_system_message()