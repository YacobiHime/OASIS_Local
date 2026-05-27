"""
OASIS ペルソナ自動生成スクリプト
=================================
collect_bluesky.py で収集した raw_users.json を読み込み、
Claude/Gemini API を使って OASIS 用の profiles/bluesky_profiles.json を生成する。

使い方:
    # Claudeを使う場合
    export ANTHROPIC_API_KEY=your_key
    python generate_profiles.py --input raw_users.json --output profiles/bluesky_profiles.json --api claude

    # Geminiを使う場合
    export GEMINI_API_KEY=your_key
    python generate_profiles.py --input raw_users.json --output profiles/bluesky_profiles.json --api gemini
"""

import asyncio
import json
import argparse
import os
import re
import time

# ------------------------------------------------------------------
# LLM呼び出し（Claude / Gemini 切り替え対応）
# ------------------------------------------------------------------


async def call_claude(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


async def call_gemini(prompt: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content(prompt)
    return response.text


async def call_llm(prompt: str, api: str) -> str:
    if api == "claude":
        return await call_claude(prompt)
    elif api == "gemini":
        return await call_gemini(prompt)
    else:
        raise ValueError(f"未対応のAPI: {api}")


# ------------------------------------------------------------------
# ペルソナ生成プロンプト
# ------------------------------------------------------------------


def build_prompt(user: dict, agent_id: int) -> str:
    posts_text = "\n".join(f"- {p['text'][:100]}" for p in user["posts"][:10])
    return f"""
以下はBlueskyユーザーの実際のデータです。このユーザーの投稿スタイル・興味関心・性格を分析し、
OASISシミュレーション用のペルソナJSONを生成してください。

【ユーザーデータ】
ハンドル: @{user['handle']}
表示名: {user['display_name']}
プロフィール文: {user['description'] or '（なし）'}
フォロワー数: {user['followers_count']}
フォロー数: {user['follows_count']}
投稿数: {user['posts_count']}
直近の投稿サンプル:
{posts_text}

【出力形式】
以下のJSONのみを出力してください。説明文・マークダウン不要。
{{
  "name": "（表示名またはハンドル名をそのまま使用）",
  "bio": "（100〜150文字。年齢・職業は不明なら推測しない。投稿から読み取れる性格・口調・興味を自然な日本語で記述）",
  "id": {agent_id},
  "other_info": {{
    "handle": "@{user['handle']}",
    "followers": {user['followers_count']},
    "hobbies": "（投稿から推測される趣味・関心事を列挙）",
    "reaction_triggers": "（反応しやすそうなトピック）",
    "reaction_avoid": "（スルーしそうなトピック）",
    "follow_policy": "（どんなユーザーをフォロー/アンフォローしそうか）",
    "tone_examples": "（実際の投稿から抜粋した口調・フレーズの例を3つ）"
  }}
}}
"""


def extract_json(text: str) -> dict:
    """LLMの返答からJSONを抽出する。"""
    # ```json ... ``` の除去
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    return json.loads(text)


# ------------------------------------------------------------------
# seed投稿生成
# ------------------------------------------------------------------


def build_seed_prompt(users_summary: list[dict]) -> str:
    names = "\n".join(f"- ID:{u['id']} {u['name']}" for u in users_summary)
    return f"""
以下はSNSシミュレーションに参加するユーザーの一覧です。
このメンバーが混在するタイムラインに流れる「初期投稿（seed投稿）」を10件生成してください。

【参加ユーザー】
{names}

【条件】
- 投稿は日常・社会・テクノロジー・エンタメなど多様なトピックを含めること
- 各投稿の author_id は上記IDの中からランダムに割り当てること
- 投稿は日本語で、SNSらしい自然な文体にすること
- いいね数・リポスト数は 0〜100 の範囲でランダムに設定すること

【出力形式】
以下のJSON配列のみを出力してください。説明文・マークダウン不要。
[
  {{
    "content": "投稿本文",
    "author_id": 数値,
    "num_likes": 数値,
    "num_reposts": 数値,
    "posted_at": "2026-05-20T10:00:00"
  }}
]
"""


# ------------------------------------------------------------------
# メイン
# ------------------------------------------------------------------


async def main():
    parser = argparse.ArgumentParser(description="OASIS ペルソナ自動生成")
    parser.add_argument(
        "--input",
        type=str,
        default="raw_users.json",
        help="collect_bluesky.py の出力ファイル",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="profiles/bluesky_profiles.json",
        help="生成するプロファイルJSONのパス",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default="seeds/bluesky_seeds.json",
        help="生成するseed投稿JSONのパス",
    )
    parser.add_argument(
        "--api",
        type=str,
        default="claude",
        choices=["claude", "gemini"],
        help="使用するLLM API",
    )
    parser.add_argument(
        "--limit", type=int, default=30, help="処理するユーザー数の上限"
    )
    args = parser.parse_args()

    # 入力ファイル読み込み
    with open(args.input, "r", encoding="utf-8") as f:
        raw_users = json.load(f)

    raw_users = raw_users[: args.limit]
    print(f"📂 {len(raw_users)}人分のデータを読み込みました。API: {args.api}")

    # ペルソナ生成
    profiles = []
    for i, user in enumerate(raw_users):
        print(
            f"  [{i+1}/{len(raw_users)}] {user['display_name']} のペルソナを生成中..."
        )
        prompt = build_prompt(user, agent_id=i)
        try:
            response = await call_llm(prompt, args.api)
            profile = extract_json(response)
            profile["id"] = i  # IDを確実に上書き
            profiles.append(profile)
            print(f"    → ✅ {profile['name']}")
        except Exception as e:
            print(f"    → ❌ 失敗: {e}")
        await asyncio.sleep(0.5)  # レートリミット対策

    # プロファイル保存
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)
    print(f"\n✅ {len(profiles)}人分のペルソナを '{args.output}' に保存しました。")

    # seed投稿生成
    print(f"\n🌱 seed投稿を生成中...")
    users_summary = [{"id": p["id"], "name": p["name"]} for p in profiles]
    seed_prompt = build_seed_prompt(users_summary)
    try:
        seed_response = await call_llm(seed_prompt, args.api)
        seeds = extract_json(seed_response)
        os.makedirs(os.path.dirname(args.seeds), exist_ok=True)
        with open(args.seeds, "w", encoding="utf-8") as f:
            json.dump(seeds, f, ensure_ascii=False, indent=2)
        print(f"✅ {len(seeds)}件のseed投稿を '{args.seeds}' に保存しました。")
    except Exception as e:
        print(f"❌ seed投稿生成失敗: {e}")

    print(f"""
🎉 完了！次のステップ:

    python sumika.py --profiles {args.output}

を実行してシミュレーションを開始してください。
seed投稿は seeds/seed_posts.json の代わりに '{args.seeds}' を使うよう sumika.py を修正してください。
""")


if __name__ == "__main__":
    asyncio.run(main())
