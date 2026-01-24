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
        # --- 変数の定義（ここが抜けていました！） ---
        
        # 1. 基本のプロフィール（Bio）
        profile_str = self.description if self.description else "特になし"

        # 2. 詳細情報（もしあれば使う）
        tone_section = ""
        if self.profile and isinstance(self.profile, dict):
            other_info = self.profile.get("other_info", {})
            
            # もしJSONに詳細データが残っていれば、それもプロフィールに追加
            details = []
            param_map = {
                "age": "年齢", "gender": "性別", "nationality": "国籍",
                "affiliation": "所属", "skills": "特技", "hobbies": "趣味"
            }
            for key, label in param_map.items():
                if key in other_info and other_info[key]:
                    details.append(f"- {label}: {other_info[key]}")
            
            if details:
                profile_str += "\n" + "\n".join(details)

            # 口調データがあれば追加
            if "tone" in other_info and other_info["tone"]:
                tone_section = f"\n# 口調・セリフ例\n以下の口調を参考にしてください:\n{other_info['tone']}"

        # --- プロンプトの構築（強力なルール付き） ---
        system_content = f"""
# 役割 (ROLE)
あなたはTwitter(X)のアクティブなユーザー「{self.name}」です。
これからタイムラインに流れてくる投稿を見せます。それに対して、あなたの設定に合ったリアルなアクション（投稿、リポスト、いいね、コメントなど）を行ってください。

# あなたの設定 (PROFILE)
以下の設定になりきって振る舞ってください。
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
   - 興味のない話題でも、自分の設定（職業や性格）の視点から無理やり回答してください。

2. **内容重視**:
   - 相手のプロフィールではなく、**「投稿内容（本文）」** に反応してください。

# 応答方法 (RESPONSE METHOD)
提供されたツール (Tool Calling) を使用してアクションを実行してください。
"""
        return system_content

    def to_reddit_system_message(self) -> str:
        return self.to_twitter_system_message()