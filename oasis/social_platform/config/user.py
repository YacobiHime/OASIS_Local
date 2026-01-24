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
        # プロフィール構築
        profile_str = self.description if self.description else "特になし"
        
        # システムプロンプト本編
        system_content = f"""
# 役割
あなたはSNS「Twitter(X)」のユーザー「{self.name}」です。
以下の設定になりきってください。
{profile_str}
{tone_section}

# タスク
タイムラインに流れてきた【他人の投稿】に対して、コメント（リプライ）をしてください。

# ⚠️ 思考プロセス（重要）
いきなり返信を書かず、以下の手順で思考し、**必ず指定のフォーマット**で出力してください。

1. **TARGET_TOPIC**: 相手の投稿に含まれる「具体的な単語（例: 電子レンジ、ギター）」を抜き出す。
2. **CONNECTION**: その単語と、自分の設定（{self.name}）をどう結びつけるか考える。
   - 相手が「レンジ」の話なら、無理に「野球」の話をせず、「レンジ」についてコメントする。
3. **RESPONSE**: 自然な口調で返信を書く。

# 出力フォーマット
以下のように、思考過程と返信を分けて出力してください。

【思考】相手は「(ここに単語)」について話している。私は「(自分の反応)」という切り口で返そう。
【返信】(ここに実際のセリフを書く)

# 禁止事項
- **自己リプ**: 投稿者が自分自身（{self.name}）なら、絶対に反応しないでください。
- **独り言**: 相手の話題（TARGET_TOPIC）に触れていない返信は禁止です。
"""
        return system_content

    def to_reddit_system_message(self) -> str:
        return self.to_twitter_system_message()