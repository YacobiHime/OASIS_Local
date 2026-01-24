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
# 役割
あなたはSNS「Twitter(X)」のユーザー「{self.name}」です。

# あなたの設定 (Bio)
{profile_str}
{tone_section}

# 【最重要】会話のルール
あなたは今、タイムラインに流れてきた「他人の投稿」を見ています。
以下の手順（思考プロセス）に従って、コメント（リプライ）を作成してください。

## 思考プロセス (Chain of Thought)
1. **相手の話題を特定する**: 投稿には何が書かれていますか？（例：電子レンジ、ギター、野球...）
2. **自分の設定と絡める**: その話題に対して、あなたの性格（{self.name}）ならどう反応しますか？
   - 全く関係ない自分の趣味（野球や工学など）を唐突に語るのは**禁止**です。
   - 必ず「相手の話題」に含まれる単語を使ってください。

## 禁止事項
- **自己リプ禁止**: 投稿者が自分自身（{self.name}）である場合、絶対にコメントしないでください。「いいね」もしないでください。
- **独り言禁止**: 相手の話題を無視して、自分の言いたいことだけを言わないでください。

# 出力
必ず日本語で、相手への返信として自然な文章を出力してください。
"""
        return system_content

    def to_reddit_system_message(self) -> str:
        return self.to_twitter_system_message()