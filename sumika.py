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
from oasis.social_platform.platform import Platform
from oasis.clock.clock import Clock

import wandb

# ---------------------------------------------------------
# 設定ファイルの読み込み（環境変数 OLLAMA_URL 優先）
# ---------------------------------------------------------
with open("config.json", "r", encoding="utf-8") as _f:
    CONFIG = json.load(_f)

# 環境変数で上書き
if os.environ.get("OLLAMA_URL"):
    CONFIG["ollama_url"] = os.environ["OLLAMA_URL"]


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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS turn_stats (
            turn          INTEGER PRIMARY KEY,
            elapsed_sec   REAL,
            started_at    TEXT,
            finished_at   TEXT
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
def load_profiles(folder_path):
    """フォルダ内のすべてのJSONファイルを読み込んでマージ、IDを連番に割り当て"""
    profiles = []
    try:
        if not os.path.isdir(folder_path):
            raise RuntimeError(f"'{folder_path}' はディレクトリではありません。")

        json_files = [f for f in os.listdir(folder_path) if f.endswith(".json")]
        if not json_files:
            raise RuntimeError(f"'{folder_path}' にJSONファイルがありません。")

        for json_file in sorted(json_files):
            file_path = os.path.join(folder_path, json_file)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        profiles.extend(data)
                    else:
                        profiles.append(data)
                print(f"📂 プロファイル '{json_file}' を読み込みました。")
            except json.JSONDecodeError:
                print(
                    f"⚠️ '{json_file}' のJSON形式が正しくありません。スキップします。"
                )

        # 元のプロファイルJSONのIDを維持する（initial_followsの参照を正しくするため）
        # IDが重複している場合のみ、連番を割り当てる
        seen_ids = set()
        id_counter = 0
        for profile in profiles:
            if "id" not in profile or profile["id"] in seen_ids:
                # IDがない、または重複している場合は新しいIDを割り当て
                while id_counter in seen_ids:
                    id_counter += 1
                profile["id"] = id_counter
                seen_ids.add(id_counter)
                id_counter += 1
            else:
                # 既存のIDを使用
                seen_ids.add(profile["id"])

        print(f"✅ 合計 {len(profiles)} 個のプロファイルを読み込みました。")
        return profiles
    except Exception as e:
        raise RuntimeError(f"プロファイル読み込みエラー: {e}")


async def compress_agent_memory(
    agent, ollama_model, turn: int, threshold: int = 10, keep_recent: int = 3
):
    """
    エージェントのメモリが一定数を超えたら、LLMで要約して圧縮する。
    システムメッセージは保持し、それ以外を要約1件に置き換える。
    """
    # システムメッセージ以外のレコードを取得
    from camel.messages import BaseMessage
    from camel.types import OpenAIBackendRole
    from camel.memories import MemoryRecord

    records = agent.memory.retrieve()
    non_system = [
        r.memory_record
        for r in records
        if r.memory_record.role_at_backend != OpenAIBackendRole.SYSTEM
    ]

    if len(non_system) < threshold:
        return  # まだ圧縮不要

    # 要約レコードと通常レコードを分離
    SUMMARY_MARKER = "[過去の記憶まとめ"
    summaries = [r for r in non_system if r.message.content.startswith(SUMMARY_MARKER)]
    non_summary = [
        r for r in non_system if not r.message.content.startswith(SUMMARY_MARKER)
    ]

    # 圧縮対象: 通常レコードの古い部分 + 要約は常に圧縮対象
    to_keep = non_summary[-keep_recent:] if keep_recent > 0 else []
    old_non_sum = non_summary[:-keep_recent] if keep_recent > 0 else non_summary
    to_compress = summaries + old_non_sum  # 要約は必ず再圧縮

    if not to_compress:
        return

    # 圧縮対象のテキストを結合
    history_text = "\n".join(
        f"[{r.role_at_backend.value}] {r.message.content}" for r in to_compress
    )

    prompt = (
        f"SNSユーザー「{agent.user_info.name}」の行動履歴を3行以内で要約してください。"
        f"重要な出来事・関係・感情のみ。余分な説明不要。\n\n{history_text}"
    )

    try:
        user_msg = [{"role": "user", "content": prompt}]
        # タイムアウト付きで実行
        response = await asyncio.wait_for(
            ollama_model.arun(user_msg), timeout=120.0  # 2分でタイムアウト
        )
        summary_text = response.choices[0].message.content
    except asyncio.TimeoutError:
        print(f"  ⚠️ メモリ圧縮タイムアウト (agent={agent.social_agent_id}): スキップ")
        return
    except Exception as e:
        print(f"  ⚠️ メモリ圧縮失敗 (agent={agent.social_agent_id}): {e}")
        return

    # システムメッセージだけ残してクリア
    system_records = [
        r.memory_record
        for r in records
        if r.memory_record.role_at_backend == OpenAIBackendRole.SYSTEM
    ]
    agent.memory.clear()
    for rec in system_records:
        agent.memory.write_record(rec)

    # 要約を assistant メッセージとして注入
    summary_msg = BaseMessage.make_assistant_message(
        role_name="assistant",
        content=f"[過去の記憶まとめ (ターン{turn}時点)]\n{summary_text}",
    )
    agent.memory.write_record(
        MemoryRecord(
            message=summary_msg,
            role_at_backend=OpenAIBackendRole.ASSISTANT,
        )
    )

    # 最近のレコードを復元
    for rec in to_keep:
        agent.memory.write_record(rec)

    print(
        f"  🧠 {agent.user_info.name} のメモリを圧縮しました "
        f"({len(to_compress)}件 → 要約1件, 最近{len(to_keep)}件保持)"
    )


async def main():
    # ---------------------------------------------------------
    # メモリ圧縮の設定
    # ---------------------------------------------------------
    # この件数を超えたターンで圧縮を実行する（システムメッセージ除く）
    MEMORY_COMPRESS_THRESHOLD = 6  # 10→6: コンテキスト節約のため早めに圧縮
    # 圧縮後も最新N件のレコードはそのまま保持する
    MEMORY_KEEP_RECENT = 2  # 3→2: 直近2件のみ保持
    # N ターンごとにメモリ圧縮チェックを行う（1 = 毎ターン）
    MEMORY_COMPRESS_INTERVAL = 1  # 3→1: 毎ターンチェック（小モデル対策）

    # ---------------------------------------------------------
    # 0. コマンドライン引数の設定
    # ---------------------------------------------------------
    parser = argparse.ArgumentParser(description="OASIS Twitter Simulation")
    parser.add_argument(
        "--profiles",
        type=str,
        default="profiles",
        help="Path to the user profiles folder",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=5,
        help="シミュレーションのターン数",
    )
    parser.add_argument(
        "--no-wandb",
        action="store_true",
        help="Weights & Biasesを無効化",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="既存のDBを削除せず再開する（seed投稿もスキップ）",
    )
    args = parser.parse_args()

    # プロファイルをロード
    profiles = load_profiles(args.profiles)

    # ---------------------------------------------------------
    # Weights & Biases の初期化
    # ---------------------------------------------------------
    wandb_enabled = not args.no_wandb
    if wandb_enabled:
        try:
            wandb.init(
                project="oasis-simulation",
                name=f"sim-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                config={
                    "num_agents": len(profiles),
                    "num_turns": args.turns,
                    "model": CONFIG["ollama_model_sim"],
                    "memory_compress_threshold": MEMORY_COMPRESS_THRESHOLD,
                    "memory_keep_recent": MEMORY_KEEP_RECENT,
                    "memory_compress_interval": MEMORY_COMPRESS_INTERVAL,
                },
            )
            print(f"📊 W&B初期化完了: {wandb.run.name}")
        except Exception as e:
            print(f"⚠️ W&B初期化に失敗: {e}")
            print("  → W&Bなしで継続します")
            wandb_enabled = False
    else:
        print("📊 W&Bは無効化されています")

    # ---------------------------------------------------------
    # 1. モデル設定
    # ---------------------------------------------------------

    ollama_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type=CONFIG["ollama_model_sim"],
        url=CONFIG["ollama_url"],
        api_key="ollama",
        timeout=300.0,  # 5分でタイムアウト
        max_retries=2,  # 失敗時2回リトライ
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
        # --- 公式 Twitter デフォルトセット ---
        ActionType.CREATE_POST,  # 投稿
        ActionType.LIKE_POST,  # いいね
        ActionType.REPOST,  # リポスト（拡散）
        ActionType.FOLLOW,  # フォロー
        ActionType.QUOTE_POST,  # 引用リポスト（コメント付き拡散）
        ActionType.DO_NOTHING,  # 何もしない ★これがないとLLMが毎ターン必ず発言してしまう
        # --- Twitter的に自然な追加アクション ---
        ActionType.CREATE_COMMENT,  # リプライ
        ActionType.LIKE_COMMENT,  # コメントにいいね
        ActionType.SEARCH_POSTS,  # キーワード検索（能動的な情報収集）
        ActionType.TREND,  # トレンド確認（流行を見てから行動）
        ActionType.UNFOLLOW,  # フォロー解除（関係の変化を表現）
        ActionType.MUTE,  # ミュート（嫌いなユーザーを無視）
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
            model=ollama_model,
            available_actions=available_actions,
        )

        agent_graph.add_agent(agent)
        print(f"✨ {profile['name']} さんが入居しました！(ID: {profile['id']})")

    # ---------------------------------------------------------
    # 4. 環境構築
    # ---------------------------------------------------------
    db_path = CONFIG["db_path"]
    tracker_db_path = CONFIG["tracker_db_path"]
    os.environ["OASIS_DB_PATH"] = os.path.abspath(db_path)

    if not args.resume:
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists(tracker_db_path):
            os.remove(tracker_db_path)
    else:
        print(f"♻️  resumeモード: 既存のDBを引き継ぎます")

    platform = Platform(
        db_path=db_path,
        recsys_type="twitter",
        # 1回のrefreshで表示される投稿数（デフォルト1→4）
        refresh_rec_post_count=4,
        # 推薦バッファの最大投稿数（デフォルト2→8）
        max_rec_post_len=8,
        # 自分の投稿に自分でいいね・低評価できないよう禁止
        allow_self_rating=False,
    )
    env = oasis.make(
        agent_graph=agent_graph,
        platform=platform,
        database_path=db_path,
    )
    await env.reset()
    tracker_conn = init_tracker_db(tracker_db_path)

    # ---------------------------------------------------------
    # 初期フォロー関係の注入（env.reset() 完了後に実行）
    # ---------------------------------------------------------
    print("🔗 初期フォロー関係を設定中...")
    follow_conn = sqlite3.connect(os.path.abspath(db_path))
    follow_count = 0

    try:
        follow_conn.execute("BEGIN")
        for profile in profiles:
            follower_id = profile["id"]
            for followee_id in profile.get("initial_follows", []):
                # 自己フォローはスキップ
                if follower_id == followee_id:
                    continue
                # 対象IDが存在するか確認
                if not any(p["id"] == followee_id for p in profiles):
                    print(
                        f"  ⚠️ initial_follows: ID={followee_id} は存在しません。スキップ。"
                    )
                    continue
                try:
                    # followテーブルに挿入
                    follow_conn.execute(
                        "INSERT OR IGNORE INTO follow (follower_id, followee_id, created_at) VALUES (?, ?, ?)",
                        (follower_id, followee_id, 0),
                    )
                    # num_followings / num_followers を更新
                    follow_conn.execute(
                        "UPDATE user SET num_followings = num_followings + 1 WHERE user_id = ?",
                        (follower_id,),
                    )
                    follow_conn.execute(
                        "UPDATE user SET num_followers = num_followers + 1 WHERE user_id = ?",
                        (followee_id,),
                    )
                    # AgentGraphにもエッジを追加（推薦システム用）
                    env.agent_graph.add_edge(follower_id, followee_id)
                    follow_count += 1
                except Exception as e:
                    print(f"  ⚠️ フォロー設定失敗 ({follower_id}→{followee_id}): {e}")

        follow_conn.execute("COMMIT")
    except Exception as e:
        follow_conn.execute("ROLLBACK")
        print(f"  ⚠️ フォロー関係のコミットに失敗: {e}")

    follow_conn.close()
    print(f"✅ 初期フォロー関係: {follow_count}件設定しました。")

    print("🤖: Twitter（X）シミュレーション開始！")

    # ---------------------------------------------------------
    # seed投稿・コメントを読み込んで投稿＋DB直接書き換えで初期値を注入
    # ---------------------------------------------------------
    def load_json_file(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ '{file_path}' が見つかりません。スキップします。")
            return []

    def load_all_from_folder(folder_path):
        """フォルダ内のすべてのJSONファイルを読み込んでマージ"""
        all_items = []
        try:
            if not os.path.isdir(folder_path):
                print(f"⚠️ '{folder_path}' はディレクトリではありません。")
                return []

            json_files = [f for f in os.listdir(folder_path) if f.endswith(".json")]
            for json_file in sorted(json_files):
                file_path = os.path.join(folder_path, json_file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            all_items.extend(data)
                        else:
                            all_items.append(data)
                    print(f"📄 '{json_file}' を読み込みました。")
                except json.JSONDecodeError:
                    print(
                        f"⚠️ '{json_file}' のJSON形式が正しくありません。スキップします。"
                    )
        except Exception as e:
            print(f"⚠️ フォルダ読み込みエラー: {e}")
        return all_items

    seed_posts = load_all_from_folder("seeds")
    seed_comments = load_json_file("seeds/seed_comments.json")

    post_id_map = {}  # post_index → 実際のpost_id

    if args.resume:
        # resumeモード: seed投稿・コメントの注入をスキップ
        print("♻️  resumeモード: seed投稿・コメントの注入をスキップします。")
    else:
        # 新規モード: seed投稿を注入（env.step 完了後にDB操作を行う）
        # OASISのDBに直接アクセスするコネクション（いいね数などの上書き用）
        oasis_conn = sqlite3.connect(os.path.abspath(db_path))

        for i, seed in enumerate(seed_posts):
            # --- step 実行 ---
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

            # --- step 完了後にDB操作（last_insert_rowid で実際のIDを取得） ---
            try:
                actual_post_id = oasis_conn.execute(
                    "SELECT last_insert_rowid()"
                ).fetchone()[0]
            except Exception:
                actual_post_id = i + 1  # フォールバック

            post_id_map[i] = actual_post_id

            # OASISのpostテーブルにいいね数・リポスト数を直接書き込む
            try:
                oasis_conn.execute("BEGIN")
                oasis_conn.execute(
                    "UPDATE post SET num_likes=?, num_shares=? WHERE post_id=?",
                    (
                        seed.get("num_likes", 0),
                        seed.get("num_reposts", 0),
                        actual_post_id,
                    ),
                )
                oasis_conn.execute("COMMIT")
            except Exception as e:
                oasis_conn.execute("ROLLBACK")
                print(f"  ⚠️ post初期値の書き込み失敗 (post_id={actual_post_id}): {e}")

            # action_logにseed投稿を記録
            tr_cur = tracker_conn.cursor()
            tr_cur.execute(
                """
                INSERT INTO action_log
                (turn, agent_id, action_type, target_id, content, executed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    0,
                    seed["author_id"],
                    "create_post",
                    actual_post_id,
                    json.dumps(
                        {"post_id": actual_post_id, "content": seed["content"]}, ensure_ascii=False
                    ),
                    executed_at,
                ),
            )
            tracker_conn.commit()
            print(f"  📝 seed投稿 {actual_post_id}: {seed['content'][:30]}...")

        # seed_commentsをOASISのcommentテーブルに直接INSERT
        print(f"💬 seed_commentsを注入中 ({len(seed_comments)}件)...")
        try:
            oasis_conn.execute("BEGIN")
            for sc in seed_comments:
                post_index = sc.get("post_index", 0)
                post_id = post_id_map.get(post_index)
                if post_id is None:
                    print(
                        f"  ⚠️ post_index={post_index} に対応する投稿がありません。スキップ。"
                    )
                    continue
                parent_comment_id = sc.get("parent_comment_id", None)
                try:
                    oasis_conn.execute(
                        """
                        INSERT INTO comment
                        (post_id, parent_comment_id, user_id, content, num_likes, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            post_id,
                            parent_comment_id,
                            sc["author_id"],
                            sc["content"],
                            sc.get("num_likes", 0),
                            0,  # created_at=0（ターン0扱い）
                        ),
                    )
                    reply_info = (
                        f" (→ comment_id={parent_comment_id}への返信)"
                        if parent_comment_id
                        else ""
                    )
                    print(
                        f"  💬 コメント追加{reply_info} → post_id={post_id}: {sc['content'][:30]}..."
                    )
                except Exception as e:
                    print(f"  ⚠️ コメント追加失敗: {e}")
            oasis_conn.execute("COMMIT")
        except Exception as e:
            oasis_conn.execute("ROLLBACK")
            print(f"  ⚠️ seed_comments注入エラー: {e}")

        oasis_conn.close()

    # ---------------------------------------------------------
    # 5. 時間を動かす (nターン)
    # ---------------------------------------------------------
    elapsed_history = []  # 全ターンの実行時間を蓄積（分布ログ用）

    # ターンループ外で一度だけ接続を作成し、使い回す（Task 6: DB接続永続化）
    stats_conn = sqlite3.connect(os.path.abspath(db_path))

    try:
        simulation_rounds = args.turns
        for i in range(simulation_rounds):
            turn_num = i + 1
            print(f"\n⏱️ --- ターン {turn_num} / {simulation_rounds} ---")
            actions = {agent: LLMAction() for _, agent in env.agent_graph.get_agents()}

            # ステップ前のtraceの最大IDを記録（永続化したstats_connを使用）
            tr_cur = tracker_conn.cursor()
            try:
                snap = stats_conn.execute("SELECT MAX(id) FROM trace").fetchone()
                before_max_id = snap[0] if snap[0] else 0
            except Exception as e:
                print(f"  ⚠️ trace ID取得エラー: {e}")
                before_max_id = 0

            # ターン時間の計測
            turn_started_at = datetime.now()
            executed_at = turn_started_at.isoformat()
            elapsed_sec = 0.0

            # メインステップ
            try:
                await env.step(actions)
                turn_finished_at = datetime.now()
                elapsed_sec = (turn_finished_at - turn_started_at).total_seconds()
                print(f"  ⏱️ ターン {turn_num} 完了: {elapsed_sec:.1f}秒")
                try:
                    tr_cur.execute(
                        "INSERT OR REPLACE INTO turn_stats (turn, elapsed_sec, started_at, finished_at) VALUES (?, ?, ?, ?)",
                        (
                            turn_num,
                            elapsed_sec,
                            turn_started_at.isoformat(),
                            turn_finished_at.isoformat(),
                        ),
                    )
                    tracker_conn.commit()
                except Exception as e:
                    print(f"  ⚠️ ターン統計記録エラー: {e}")
            except Exception as e:
                print(
                    f"  ⚠️ ターン{turn_num}: ステップ実行中にエラーが発生しました: {e}"
                )
                print(f"  → 次の処理に進みます...")
                elapsed_sec = (datetime.now() - turn_started_at).total_seconds()

            elapsed_history.append(elapsed_sec)

            # メモリ圧縮チェック（MEMORY_COMPRESS_INTERVALターンごと）
            if turn_num % MEMORY_COMPRESS_INTERVAL == 0:
                print(f"  🧠 メモリ圧縮チェック中...")
                for agent_id, agent in env.agent_graph.get_agents():
                    try:
                        await compress_agent_memory(
                            agent,
                            ollama_model,
                            turn_num,
                            threshold=MEMORY_COMPRESS_THRESHOLD,
                            keep_recent=MEMORY_KEEP_RECENT,
                        )
                    except Exception as result:
                        print(f"  ⚠️ Agent {agent_id} のメモリ圧縮に失敗: {result}")

            # ステップ後のtraceを取得してDBに記録 & W&B用統計を収集
            # （永続化したstats_connを使用）
            action_counts = {}
            total_posts = total_likes = total_comments = total_follows = 0
            new_rows = []
            try:
                cur_post = stats_conn.cursor()

                new_rows = cur_post.execute(
                    "SELECT user_id, action, info, status FROM trace WHERE id > ?",
                    (before_max_id,),
                ).fetchall()
                for row in new_rows:
                    action_counts[row[1]] = action_counts.get(row[1], 0) + 1

                total_posts = cur_post.execute("SELECT COUNT(*) FROM post").fetchone()[
                    0
                ]
                total_likes = (
                    cur_post.execute("SELECT SUM(num_likes) FROM post").fetchone()[0]
                    or 0
                )
                total_comments = cur_post.execute(
                    "SELECT COUNT(*) FROM comment"
                ).fetchone()[0]
                total_follows = cur_post.execute(
                    "SELECT COUNT(*) FROM follow"
                ).fetchone()[0]
            except Exception as e:
                print(f"  ⚠️ 統計取得エラー: {e}")

            # action_log に記録
            try:
                for row in new_rows:
                    user_id, action, info, status = row
                    try:
                        tr_cur.execute(
                            """
                            INSERT INTO action_log
                            (turn, agent_id, action_type, target_id, content, executed_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (turn_num, user_id, action, None, info, executed_at),
                        )
                    except Exception as e:
                        print(f"  ⚠️ ログ記録エラー (user_id={user_id}): {e}")
                tracker_conn.commit()
            except Exception as e:
                print(f"  ⚠️ コミットエラー: {e}")

            # ---------------------------------------------------------
            # W&Bにターン統計をログ
            # step は指定せず wandb に自動管理させる（明示stepは2ターン目以降が無視される問題を回避）
            # ---------------------------------------------------------
            if wandb_enabled:
                try:
                    ACTION_LABEL_JA = {
                        "refresh":              "行動/タイムライン更新",
                        "create_post":          "行動/投稿",
                        "like_post":            "行動/投稿いいね",
                        "unlike_post":          "行動/投稿いいね取消",
                        "dislike_post":         "行動/投稿よくない",
                        "undo_dislike_post":    "行動/投稿よくない取消",
                        "follow":               "行動/フォロー",
                        "unfollow":             "行動/フォロー解除",
                        "repost":               "行動/リポスト",
                        "quote_post":           "行動/引用投稿",
                        "create_comment":       "行動/コメント",
                        "like_comment":         "行動/コメントいいね",
                        "unlike_comment":       "行動/コメントいいね取消",
                        "dislike_comment":      "行動/コメントよくない",
                        "undo_dislike_comment": "行動/コメントよくない取消",
                    }
                    log_data = {
                        "統計/経過時間(秒)":       elapsed_sec,
                        "統計/累計投稿数":          total_posts,
                        "統計/累計いいね数":        total_likes,
                        "統計/累計コメント数":      total_comments,
                        "統計/累計フォロー数":      total_follows,
                        "統計/処理時間分布":        wandb.Histogram(elapsed_history),
                        **{ACTION_LABEL_JA.get(k, f"行動/{k}"): v
                           for k, v in action_counts.items()},
                    }
                    wandb.log(log_data, step=turn_num)
                    print(
                        f"  📊 W&Bログ送信: turn={turn_num}, elapsed={elapsed_sec:.1f}s, posts={total_posts}, actions={action_counts}"
                    )
                except Exception as e:
                    print(f"  ⚠️ W&Bログエラー: {e}")
                    import traceback

                    traceback.print_exc()

        print("✅ シミュレーション終了！")

        # ---------------------------------------------------------
        # W&Bの終了処理
        # ---------------------------------------------------------
        if wandb_enabled:
            try:
                wandb.finish()
                print("📊 W&Bログ完了")
            except Exception as e:
                print(f"⚠️ W&B終了エラー: {e}")

    except KeyboardInterrupt:
        print("\n⚠️ 中断されました。クリーンアップします...")
    except RuntimeError as e:
        print(f"❌ 実行時エラー: {e}")

    finally:
        await env.close()
        tracker_conn.close()
        stats_conn.close()
        print("🔒 DB接続をクローズしました。")


if __name__ == "__main__":
    asyncio.run(main())