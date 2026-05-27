"""
Bluesky 日本語ユーザー収集スクリプト
=====================================
Jetstreamから日本語投稿をサンプリングし、
ユーザーの投稿履歴・プロフィールを収集して raw_users.json に保存する。

使い方:
    pip install atproto websockets langdetect
    python collect_bluesky.py --count 30 --posts 20 --output raw_users.json
"""

import asyncio
import json
import argparse
import time
import websockets
from atproto import Client

# 言語判定（軽量）
try:
    from langdetect import detect

    USE_LANGDETECT = True
except ImportError:
    USE_LANGDETECT = False
    print(
        "⚠️  langdetect 未インストール。文字コード判定（ひらがな/カタカナ）にフォールバックします。"
    )


# ------------------------------------------------------------------
# 日本語判定
# ------------------------------------------------------------------
def is_japanese(text: str) -> bool:
    """テキストが日本語かどうかを判定する。"""
    if not text or len(text.strip()) < 5:
        return False
    # ひらがな・カタカナが含まれていれば日本語と判定（高速・確実）
    for ch in text:
        if "\u3040" <= ch <= "\u30ff":
            return True
    if USE_LANGDETECT:
        try:
            return detect(text) == "ja"
        except Exception:
            return False
    return False


# ------------------------------------------------------------------
# Jetstream経由でDIDを収集
# ------------------------------------------------------------------
async def collect_dids_from_jetstream(
    target_count: int, timeout_sec: int = 120
) -> list[str]:
    """
    BlueskyのJetstreamからリアルタイムに日本語投稿を受信し、
    投稿者のDIDをtarget_count件収集して返す。
    """
    # Jetstream公式エンドポイント（postsのみ）
    uri = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"

    dids: set[str] = set()
    print(
        f"🔥 Jetstreamに接続中... (目標: {target_count}人, タイムアウト: {timeout_sec}秒)"
    )

    start = time.time()
    try:
        async with websockets.connect(uri, ping_interval=20) as ws:
            while len(dids) < target_count:
                if time.time() - start > timeout_sec:
                    print(f"⏱️  タイムアウト。{len(dids)}人分のDIDを収集しました。")
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    event = json.loads(raw)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    continue

                # postイベントのみ処理
                if event.get("kind") != "commit":
                    continue
                commit = event.get("commit", {})
                if commit.get("collection") != "app.bsky.feed.post":
                    continue
                if commit.get("operation") not in ("create",):
                    continue

                record = commit.get("record", {})
                text = record.get("text", "")

                if not is_japanese(text):
                    continue

                did = event.get("did", "")
                if did and did not in dids:
                    dids.add(did)
                    print(
                        f"  ✅ [{len(dids)}/{target_count}] {did} : {text[:40].replace(chr(10), ' ')}"
                    )

    except Exception as e:
        print(f"❌ Jetstream接続エラー: {e}")

    return list(dids)


# ------------------------------------------------------------------
# ユーザー情報・投稿履歴を取得
# ------------------------------------------------------------------
def fetch_user_data(client: Client, did: str, max_posts: int = 20) -> dict | None:
    """
    指定DIDのプロフィールと投稿履歴を取得してdictで返す。
    取得失敗時はNoneを返す。
    """
    try:
        # プロフィール取得
        profile = client.app.bsky.actor.get_profile({"actor": did})
        handle = profile.handle
        display_name = profile.display_name or handle
        description = profile.description or ""

        # 投稿一覧取得
        feed_resp = client.app.bsky.feed.get_author_feed(
            {
                "actor": did,
                "limit": max_posts,
                "filter": "posts_no_replies",
            }
        )

        posts = []
        for item in feed_resp.feed:
            post = item.post
            record = post.record
            # 日本語投稿のみ
            text = getattr(record, "text", "") or ""
            if not is_japanese(text):
                continue
            posts.append(
                {
                    "text": text,
                    "created_at": getattr(record, "created_at", ""),
                    "like_count": post.like_count or 0,
                    "repost_count": post.repost_count or 0,
                    "reply_count": post.reply_count or 0,
                }
            )

        if not posts:
            return None  # 日本語投稿がなければスキップ

        return {
            "did": did,
            "handle": handle,
            "display_name": display_name,
            "description": description,
            "followers_count": profile.followers_count or 0,
            "follows_count": profile.follows_count or 0,
            "posts_count": profile.posts_count or 0,
            "posts": posts,
        }

    except Exception as e:
        print(f"  ⚠️  {did} の取得失敗: {e}")
        return None


# ------------------------------------------------------------------
# メイン
# ------------------------------------------------------------------
async def main():
    parser = argparse.ArgumentParser(description="Bluesky 日本語ユーザー収集")
    parser.add_argument(
        "--count", type=int, default=30, help="収集するユーザー数（デフォルト: 30）"
    )
    parser.add_argument(
        "--posts",
        type=int,
        default=20,
        help="1ユーザーあたりの最大取得投稿数（デフォルト: 20）",
    )
    parser.add_argument(
        "--output", type=str, default="raw_users.json", help="出力ファイルパス"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Jetstream収集のタイムアウト秒数（デフォルト: 180）",
    )
    args = parser.parse_args()

    # Step 1: DID収集（認証不要）
    # 候補を多めに集める（プロフィール取得時に弾かれることがあるため）
    candidate_count = args.count * 3
    dids = await collect_dids_from_jetstream(candidate_count, timeout_sec=args.timeout)

    if not dids:
        print("❌ DIDを1件も収集できませんでした。ネットワーク接続を確認してください。")
        return

    # Step 2: プロフィール・投稿取得（認証不要）
    print(f"\n📥 {len(dids)}人分のプロフィール・投稿を取得中...")
    client = Client()  # 認証なしでも公開データは取得可能

    results = []
    for i, did in enumerate(dids):
        if len(results) >= args.count:
            break
        print(f"  [{i+1}/{len(dids)}] {did} を取得中...")
        data = fetch_user_data(client, did, max_posts=args.posts)
        if data:
            results.append(data)
            print(
                f"    → ✅ {data['display_name']} (@{data['handle']}) : {len(data['posts'])}件の日本語投稿"
            )
        # レートリミット対策
        await asyncio.sleep(0.3)

    # Step 3: 保存
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 完了！ {len(results)}人分のデータを '{args.output}' に保存しました。")
    print(
        f"次のステップ: generate_profiles.py を使ってOASIS用ペルソナJSONを生成してください。"
    )


if __name__ == "__main__":
    asyncio.run(main())
