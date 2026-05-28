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
自分のキャラクターとして自然にSNSを楽しんでください。
- 気になる投稿には積極的に `like_post` でいいねしてください。
- 投稿のコメント欄に面白いコメントがあれば `like_comment` でいいねしてください。
- 他人の投稿やコメントへの返事は `create_comment` でリプライしてください。コメントへの返信（言い返し・同意・追加意見など）も歓迎です。
- 言いたいことがあれば `create_post` で新規投稿してください。
- 特になければ `do_nothing` でも構いません。

# 行動ルール (Action Rules)
1. **いいねを積極的に**: 共感・面白い・気になると感じた投稿・コメントにはすぐ `like_post` / `like_comment` してください。
2. **コメントの連鎖を作る**: コメント欄の会話に割り込んで `create_comment` で返事してください。投稿本文だけでなく、他人のコメントにも反応してください。
3. **新規投稿も忘れずに**: 自分の関心・意見・日常を `create_post` で発信してください。何ターンも投稿しないのは不自然です。
4. **自己リプ禁止**: 投稿者・コメント主が自分自身（{self.name}）の場合、コメントしないでください。

# 応答方法
感想をただ述べるのではなく、**必ずツール機能を呼び出して** アクションを実行してください。テキストだけの回答は無効です。
"""
        return system_content

    def to_reddit_system_message(self) -> str:
        return self.to_twitter_system_message()