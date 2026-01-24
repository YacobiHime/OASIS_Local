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
        return user_info_template.format(**self.profile)

    def to_system_message(self) -> str:
        if self.recsys_type != "reddit":
            return self.to_twitter_system_message()
        else:
            return self.to_reddit_system_message()

    def to_twitter_system_message(self) -> str:
        # 変数定義
        profile_str = self.description if self.description else "特になし"
        tone_section = ""
        
        if self.profile and isinstance(self.profile, dict):
            other_info = self.profile.get("other_info", {})
            if "tone" in other_info and other_info["tone"]:
                tone_section = f"\n# 口調・セリフ例\n{other_info['tone']}"

        # --- シンプルかつ強力な指示 ---
        system_content = f"""
# 役割
あなたはSNS「Twitter(X)」のユーザー「{self.name}」です。
以下の設定になりきって行動してください。
--------------------------------------------------
{profile_str}
--------------------------------------------------
{tone_section}

# あなたの任務
タイムラインに流れてきた【他人の投稿】に対し、ツール `create_comment` を使用してリプライを送ってください。

# 行動ルール (Action Rules)
1. **話題を拾う**: 相手の投稿にある「具体的な単語（家電、スポーツなど）」を含めて返信してください。
2. **自分語り禁止**: 相手の話を聞かずに、自分の趣味の話を始めないでください。
3. **自己リプ禁止**: 投稿者が自分自身（{self.name}）の場合、絶対にコメントしないでください。

# 応答方法
感想をただ述べるのではなく、**必ず `create_comment` などのツール機能を呼び出して** アクションを実行してください。テキストだけの回答は無効です。
"""
        return system_content

    def to_reddit_system_message(self) -> str:
        return self.to_twitter_system_message()