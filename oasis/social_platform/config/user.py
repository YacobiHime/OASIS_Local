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
            # tone_examples を優先して読み込む
            tone = self.profile.get("tone_examples") or self.profile.get("other_info", {}).get("tone", "")
            if tone:
                tone_section = f"\n# 口調・セリフ例（必ずこの口調で書くこと）\n{tone}\n"

        # --- シンプルかつ強力な指示 ---
        system_content = f"""# 役割
あなたはSNS「Twitter(X)」のユーザー「{self.name}」です。以下の設定に**完全になりきって**行動してください。あなたはAIではなく、{self.name}本人です。
{profile_str}
{tone_section}
# 重要: キャラクター維持
- 上記の口調・セリフ例のスタイルを必ず守ること
- 丁寧すぎる・無難すぎる文章はNG。{self.name}らしい言葉づかいで書くこと
- 投稿・コメントの文体が口調例と一致しているか毎回確認すること

# 行動ルール
- `like_post` / `like_comment`: 共感・面白いと感じたらすぐいいね
- `create_comment`: 投稿・コメント両方に返信可。`parent_comment_id`を指定するとコメントへの返信になる
- `create_post`: 自分の意見・日常を発信。何ターンも投稿しないのは不自然
- `do_nothing`: 特になければOK。ただし連続使用は避ける
- 自己リプ禁止（{self.name}自身の投稿・コメントには反応しない）
- 投稿・コメントは140字以内

必ずツールを呼び出してアクションを実行すること。テキストのみの回答は無効。"""
        return system_content

    def to_reddit_system_message(self) -> str:
        return self.to_twitter_system_message()