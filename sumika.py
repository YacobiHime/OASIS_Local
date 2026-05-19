import asyncio
import os
import json
import argparse
import sqlite3
from datetime import datetime

from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.models import ModelManager

import oasis
from oasis import ActionType, LLMAction, ManualAction, AgentGraph, SocialAgent, UserInfo


def init_tracker_db(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS post_meta (
            post_id       INTEGER PRIMARY KEY,
            author_id     INTEGER,
            content       TEXT,
            posted_at     TEXT,
            num_likes     INTEGER DEFAULT 0,
            num_reposts   INTEGER DEFAULT 0,
            num_quotes    INTEGER DEFAULT 0,
            num_impressions INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comment_meta (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id       INTEGER,
            author_id     INTEGER,
            content       TEXT,
            posted_at     TEXT,
            num_likes     INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS action_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            turn        INTEGER,
            agent_id    INTEGER,
            action_type TEXT,
            target_id   INTEGER,
            content     TEXT,
            executed_at TEXT
        )
    """)
    conn.commit()
    return conn


def insert_seed_post(conn, post_id, seed):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO post_meta
        (post_id, author_id, content, posted_at, num_likes, num_reposts, num_quotes, num_impressions)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            post_id,
            seed["author_id"],
            seed["content"],
            seed["posted_at"],
            seed.get("num_likes", 0),
            seed.get("num_reposts", 0),
            seed.get("num_quotes", 0),
            seed.get("num_impressions", 0),
        ),
    )
    for comment in seed.get("comments", []):
        cur.execute(
            """
            INSERT INTO comment_meta
            (post_id, author_id, content, posted_at, num_likes)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                post_id,
                comment["author_id"],
                comment["content"],
                comment["posted_at"],
                comment.get("num_likes", 0),
            ),
        )
    conn.commit()


# ★追加：JSON読み込み用関数
def load_profiles(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            profiles = json.load(f)
            print(f"📂 プロファイル '{file_path}' を読み込みました。")
            return profiles
    except FileNotFoundError:
        print(f"❌ エラー: ファイル '{file_path}' が見つかりません。")
        exit(1)
    except json.JSONDecodeError:
        print(f"❌ エラー: '{file_path}' のJSON形式が正しくありません。")
        exit(1)


async def main():
    # ---------------------------------------------------------
    # 0. コマンドライン引数の設定
    # ---------------------------------------------------------
    parser = argparse.ArgumentParser(description="OASIS Twitter Simulation")
    parser.add_argument(
        "--profiles",
        type=str,
        default="profiles/test1.json",
        help="Path to the user profiles JSON file",
    )
    args = parser.parse_args()

    # プロファイルをロード
    profiles = load_profiles(args.profiles)

    # ---------------------------------------------------------
    # 1. モデル設定
    # ---------------------------------------------------------

    ollama_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type="gemma4:e4b",
        url="http://192.168.15.150:11434/v1",  # Ollamaのポート番号（11434）
        api_key="ollama",  # エラー回避用のダミーキー
    )
    # 複数のエージェントでこのモデルを共有するための設定
    shared_model_manager = ModelManager(
        models=[ollama_model],
        scheduling_strategy="round_robin",
    )

    # ollama_model = ModelFactory.create(
    # model_platform=ModelPlatformType.OPENAI,
    # model_type="gemma4:e2b",
    # url="http://localhost:11434/v1",
    # api_key="ollama",
    # model_config_dict={
    #     "temperature": 0.2,
    #     "presence_penalty": 1.2  # 過剰思考を抑制するための設定値。1.0 から 1.5 の間に設定。それでも長いなら最大値の2.0に設定。
    #     },
    # )

    # ---------------------------------------------------------
    # 2. アクション設定
    # ---------------------------------------------------------
    available_actions = [
        ActionType.CREATE_POST,  # 投稿
        ActionType.CREATE_COMMENT,  # リプライ
        ActionType.LIKE_POST,  # いいね
        ActionType.REPOST,  # リポスト（拡散）
        ActionType.FOLLOW,  # フォロー
    ]

    # ---------------------------------------------------------
    # 3. 住人登録
    # ---------------------------------------------------------
    agent_graph = AgentGraph()
    print(f"🤖: {len(profiles)}人の住人を登録中...")

    for profile in profiles:
        # other_info を安全に取得
        other_info = profile.get("other_info", {})

        user_info = UserInfo(
            user_name=profile["name"].lower(),  # 簡易的に名前を使用
            name=profile["name"],
            description=profile["bio"],
            # ★ここ重要！JSONから読み込んだ詳細プロフィール(other_info)を渡す
            profile={"other_info": other_info},
            recsys_type="twitter",
        )
        agent = SocialAgent(
            agent_id=profile["id"],
            user_info=user_info,
            agent_graph=agent_graph,
            model=shared_model_manager,
            available_actions=available_actions,
        )

        agent_graph.add_agent(agent)
        print(f"✨ {profile['name']} さんが入居しました！(ID: {profile['id']})")

    # ---------------------------------------------------------
    # 4. 環境構築
    # ---------------------------------------------------------
    db_path = "./ollama_twitter.db"
    os.environ["OASIS_DB_PATH"] = os.path.abspath(db_path)

    if os.path.exists(db_path):
        os.remove(db_path)

    tracker_db_path = "./sumika_tracker.db"
    if os.path.exists(tracker_db_path):
        os.remove(tracker_db_path)

    env = oasis.make(
        agent_graph=agent_graph,
        platform=oasis.DefaultPlatformType.TWITTER,
        database_path=db_path,
    )
    await env.reset()
    tracker_conn = init_tracker_db("sumika_tracker.db")

    print("🤖: Twitter（X）シミュレーション開始！")

    # 最初のきっかけ作り（ID:0 の住人に初投稿させる）
    # seed_posts.jsonを読み込んで初期投稿を一括投稿
    def load_seed_posts(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ シードファイル '{file_path}' が見つかりません。スキップします。")
            return []

    seed_posts = load_seed_posts("seeds/seed_posts.json")

    for i, seed in enumerate(seed_posts):
        author = env.agent_graph.get_agent(seed["author_id"])
        seed_action = {
            author: [
                ManualAction(
                    action_type=ActionType.CREATE_POST,
                    action_args={"content": seed["content"]},
                )
            ]
        }
        executed_at = datetime.now().isoformat()
        await env.step(seed_action)

        # ★action_logにseed投稿を記録
        post_id = i + 1
        tr_cur = tracker_conn.cursor()
        tr_cur.execute(
            """
            INSERT INTO action_log
            (turn, agent_id, action_type, target_id, content, executed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                0,  # ターン0（シミュレーション開始前）
                seed["author_id"],
                "create_post",
                post_id,
                json.dumps(
                    {"post_id": post_id, "content": seed["content"]}, ensure_ascii=False
                ),
                executed_at,
            ),
        )
        tracker_conn.commit()

    # ---------------------------------------------------------
    # 5. 時間を動かす (nターン)
    # ---------------------------------------------------------
    simulation_rounds = 5
    for i in range(simulation_rounds):
        print(f"\n⏱️ --- ターン {i + 1} / {simulation_rounds} ---")
        actions = {agent: LLMAction() for _, agent in env.agent_graph.get_agents()}

        # ステップ前のtraceの最大IDを記録
        tr_cur = tracker_conn.cursor()
        oasis_cur = sqlite3.connect(os.path.abspath(db_path))
        snap = oasis_cur.execute("SELECT MAX(id) FROM trace").fetchone()
        before_max_id = snap[0] if snap[0] else 0

        executed_at = datetime.now().isoformat()
        await env.step(actions)

        # ステップ後に追加されたtraceを取得して独自DBに記録
        new_rows = oasis_cur.execute(
            "SELECT user_id, action, info, status FROM trace WHERE id > ?",
            (before_max_id,),
        ).fetchall()
        oasis_cur.close()

        for row in new_rows:
            user_id, action, info, status = row
            tr_cur.execute(
                """
                INSERT INTO action_log
                (turn, agent_id, action_type, target_id, content, executed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    i + 1,
                    user_id,
                    action,
                    None,
                    info,
                    executed_at,
                ),
            )
        tracker_conn.commit()

    print("✅ シミュレーション終了！")
    await env.close()
    tracker_conn.close()


if __name__ == "__main__":
    asyncio.run(main())
