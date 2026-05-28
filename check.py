import sqlite3
import pandas as pd
import sys
import io
import os
import json
import shutil
from datetime import datetime
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage

# 文字化け対策
# sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


db_path = "./ollama_twitter.db"
tracker_db_path = "./sumika_tracker.db"
ENABLE_SUMMARY = False  # ★ Falseにすると要約をスキップ


def format_info_json(text, action_type=""):
    """JSON文字列から不要な情報を省き、見やすく整形して返す"""
    if not isinstance(text, str):
        return str(text)
    # refreshはpostsリストが長いので1行サマリーだけ返す
    if action_type == "refresh":
        try:
            data = json.loads(text)
            posts = data.get("posts", [])
            return f"（タイムライン取得: {len(posts)}件の投稿を表示）"
        except:
            return "（タイムライン取得）"
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            keys_to_remove = ["prompt", "embeddings", "raw_response", "posts"]
            for k in keys_to_remove:
                data.pop(k, None)
            for k, v in data.items():
                if isinstance(v, str) and len(v) > 80:
                    data[k] = v[:80] + "...(省略)"
        return json.dumps(data, indent=2, ensure_ascii=False)
    except:
        return text


def build_turn_to_time(conn, minutes_per_turn=5):
    """
    action_logのターン番号→実時刻マッピングを構築する。
    同一ターンに複数のexecuted_atがある場合は最小値（最初の実行時刻）を使用。
    minutes_per_turn: 1ターン何分に相当するか（表示上のオフセット用）
    """
    turn_to_time = {}
    try:
        cur = conn.cursor()
        cur.execute("SELECT turn, MIN(executed_at) FROM action_log GROUP BY turn")
        for row in cur.fetchall():
            turn, executed_at = row
            if executed_at:
                try:
                    dt = datetime.fromisoformat(executed_at)
                    turn_to_time[turn] = dt
                except:
                    pass
    except:
        pass
    return turn_to_time


def format_time(turn, turn_to_time, minutes_per_turn=5):
    """
    ターン番号を Twitter風時刻文字列に変換する。
    turn_to_timeにそのターンの実時刻があればそれを使用。
    なければターン0の時刻 + turn * minutes_per_turn で推定。
    """
    if turn in turn_to_time:
        dt = turn_to_time[turn]
    elif 0 in turn_to_time:
        from datetime import timedelta

        dt = turn_to_time[0] + timedelta(minutes=turn * minutes_per_turn)
    else:
        return f"Turn{turn}"

    # 午前/午後形式に変換
    hour = dt.hour
    minute = dt.minute
    if hour < 12:
        ampm = "午前"
        display_hour = hour if hour != 0 else 12
    else:
        ampm = "午後"
        display_hour = hour - 12 if hour != 12 else 12

    return f"{dt.year}年{dt.month}月{dt.day}日・{ampm}{display_hour}:{minute:02d}"


# 1ターン何分に相当するか（ここを変更すると投稿間の時間間隔が変わる）
MINUTES_PER_TURN = 5


def get_timeline_text(conn, tracker_conn=None):
    """投稿とコメントをスレッド形式で生成する"""
    text = "【📱 投稿タイムライン (スレッド表示)】\n"

    # インプレッション集計（tracker_connがあれば）
    impression_count = {}
    comment_impression_count = {}
    if tracker_conn:
        try:
            cur = tracker_conn.cursor()
            cur.execute(
                "SELECT content FROM action_log WHERE action_type = 'refresh' AND content IS NOT NULL"
            )
            for row in cur.fetchall():
                try:
                    data = json.loads(row[0])
                    for post in data.get("posts", []):
                        pid = post.get("post_id")
                        if pid is not None:
                            impression_count[pid] = impression_count.get(pid, 0) + 1
                        for comment in post.get("comments", []):
                            cid = comment.get("comment_id")
                            if cid is not None:
                                comment_impression_count[cid] = (
                                    comment_impression_count.get(cid, 0) + 1
                                )
                except:
                    continue
        except:
            pass

    # ターン番号→実時刻マッピングを構築
    turn_to_time = build_turn_to_time(conn, MINUTES_PER_TURN)

    # user_id → name マッピングを構築
    user_name_map = {}
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, name FROM mirror_user")
        for uid, uname in cur.fetchall():
            user_name_map[uid] = uname if uname else f"User{uid}"
    except Exception:
        pass

    def uid_to_name(uid):
        return user_name_map.get(uid, f"User{uid}")

    try:
        sql_posts = """
        SELECT 
            p1.post_id, p1.user_id, p1.content, p1.quote_content,
            p1.created_at, p1.num_likes, p1.num_shares, p1.num_reports,
            p1.original_post_id,
            p2.content AS original_content,
            p2.user_id AS original_user_id
        FROM mirror_post p1
        LEFT JOIN mirror_post p2 ON p1.original_post_id = p2.post_id
        ORDER BY p1.created_at
        """
        posts = pd.read_sql_query(sql_posts, conn)

        try:
            comments = pd.read_sql_query(
                "SELECT * FROM mirror_comment ORDER BY created_at", conn
            )
        except Exception:
            comments = pd.DataFrame()

        if posts.empty:
            text += "（投稿はまだありません）\n"
        else:
            for index, row in posts.iterrows():
                post_id = row["post_id"]
                post_comments = (
                    comments[comments["post_id"] == post_id]
                    if not comments.empty
                    else pd.DataFrame()
                )
                comment_count = len(post_comments)

                text += "═" * 60 + "\n"
                text += f"📌 Post:{post_id} | 👤 {uid_to_name(row['user_id'])}\n"

                content = row["content"]
                original_content = row["original_content"]
                quote_content = row["quote_content"]

                if row["original_post_id"] and quote_content:
                    text += f"   💬 {quote_content}\n"
                    text += f"      ↳ 🔁 QT @{uid_to_name(row['original_user_id'])}: {content if content else original_content}\n"
                elif content and content.strip():
                    text += f"   💬 {content}\n"
                elif original_content:
                    text += f"   🔁 [リポスト] @{uid_to_name(row['original_user_id'])}:「{original_content}」\n"
                else:
                    text += "   💬 (本文なし)\n"

                imp = impression_count.get(post_id, 0)
                time_str = format_time(
                    row["created_at"], turn_to_time, MINUTES_PER_TURN
                )
                text += f"   ⏰ {time_str}  👁️ {imp}件の表示\n"
                text += f"   💬{comment_count}  🔁{row.get('num_shares',0)}  ❤️{row.get('num_likes',0)}\n"

                if not post_comments.empty:
                    text += "   ┄" * 20 + "\n"

                    # comment_idをキーにした辞書を作成
                    comments_dict = {
                        int(c_row.get("comment_id")): c_row
                        for _, c_row in post_comments.iterrows()
                        if c_row.get("comment_id") is not None
                    }

                    # ツリー表示用の再帰関数
                    def render_comment(c_row, depth=0):
                        indent = "   " + "   " * depth
                        prefix = "├─" if depth == 0 else "└─"
                        c_imp = comment_impression_count.get(c_row.get("comment_id"), 0)
                        c_time_str = format_time(
                            c_row.get("created_at", 0), turn_to_time, MINUTES_PER_TURN
                        )
                        result = f"{indent}{prefix} ⏰{c_time_str} 👤{uid_to_name(c_row.get('user_id'))} ❤️{c_row.get('num_likes',0)}  👁️{c_imp}\n"
                        result += f"{indent}│  {c_row.get('content','')}\n"
                        # 子コメントを再帰表示
                        c_id = c_row.get("comment_id")
                        for _, child in post_comments.iterrows():
                            if child.get("parent_comment_id") == c_id:
                                result += render_comment(child, depth + 1)
                        return result

                    # ルートコメント（parent_comment_idがNullのもの）から表示
                    for _, c_row in post_comments.iterrows():
                        parent = c_row.get("parent_comment_id")
                        if parent is None or str(parent) == "nan":
                            text += render_comment(c_row, depth=0)

            text += "═" * 60 + "\n"
    except Exception as e:
        text += f"タイムライン取得エラー: {e}\n"
    return text


def get_action_log_text(conn):
    """行動ログのテキストを生成する（最新30件・refreshは1行省略）"""
    text = "\n【🤖 エージェント行動ログ (最新30件)】\n"
    turn_to_time = build_turn_to_time(conn, MINUTES_PER_TURN)

    # user_id → name マッピングを構築
    user_name_map = {}
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, name FROM mirror_user")
        for uid, uname in cur.fetchall():
            user_name_map[uid] = uname if uname else f"User{uid}"
    except Exception:
        pass

    def uid_to_name(uid):
        return user_name_map.get(uid, f"User{uid}")

    try:
        actions = pd.read_sql_query(
            "SELECT * FROM mirror_trace ORDER BY id DESC LIMIT 30", conn
        )
        actions = actions.iloc[::-1]

        if actions.empty:
            text += "（行動ログはまだありません）\n"
        else:
            for index, row in actions.iterrows():
                action_type = row.get("action", "")
                status = row.get("status", "success")
                status_icon = "✅" if status == "success" else "❌"

                # refreshは1行だけ表示
                if action_type == "refresh":
                    time_str = format_time(
                        row["created_at"], turn_to_time, MINUTES_PER_TURN
                    )
                    text += f"  🔄 {time_str} {uid_to_name(row['user_id'])} refresh {status_icon}\n"
                    continue

                text += "┌" + "─" * 40 + "\n"
                time_str = format_time(
                    row["created_at"], turn_to_time, MINUTES_PER_TURN
                )
                text += f"│ ⏰ {time_str} | 👤 {uid_to_name(row['user_id'])}\n"
                text += f"│ {status_icon} Action: {action_type} (Status: {status})\n"

                if row.get("error_message"):
                    text += f"│ ⚠️ Error: {row['error_message']}\n"

                info_content = row.get("info") or row.get("action_params") or ""
                if info_content:
                    formatted_json = format_info_json(info_content, action_type)
                    text += "│ 📄 Info:\n"
                    for line in formatted_json.split("\n"):
                        text += f"│    {line}\n"
                text += "└" + "─" * 40 + "\n"
    except Exception as e:
        text += f"行動ログ取得エラー: {e}\n"
    return text


def get_impression_text(tracker_conn):
    """action_logのrefreshからインプレッション数を集計して返す"""
    text = "\n【👁️ インプレッション集計】\n"
    try:
        cur = tracker_conn.cursor()
        cur.execute(
            "SELECT content FROM action_log WHERE action_type = 'refresh' AND content IS NOT NULL"
        )
        rows = cur.fetchall()

        impression_count = {}
        post_contents = {}

        for row in rows:
            try:
                data = json.loads(row[0])
                for post in data.get("posts", []):
                    pid = post.get("post_id")
                    if pid is not None:
                        impression_count[pid] = impression_count.get(pid, 0) + 1
                        if pid not in post_contents:
                            content = post.get("content", "")
                            post_contents[pid] = (
                                content[:40] + "..." if len(content) > 40 else content
                            )
            except:
                continue

        if not impression_count:
            text += "（インプレッションデータがありません）\n"
        else:
            text += f"{'Post':>5} {'インプレ':>8}  投稿内容\n"
            text += "-" * 60 + "\n"
            for pid in sorted(impression_count.keys()):
                content_preview = post_contents.get(pid, "")
                text += f"{pid:>5} {impression_count[pid]:>8}回  {content_preview}\n"
    except Exception as e:
        text += f"インプレッション取得エラー: {e}\n"
    return text


def generate_summary(log_text):
    """LLMを使ってログを要約する"""
    print("🤖 AIがログを要約中... (Qwen3が考え中💭)")
    try:
        ollama_model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type="gemma4:e4b",
            url="http://192.168.15.150:11434/v1",  # Ollamaのポート番号（11434）
            api_key="ollama",  # エラー回避用のダミーキー
        )

        prompt = f"""
あなたはSNSシミュレーションのログ分析官です。
以下のログ（タイムラインと行動履歴）を読み、何が起きているか要約してください。

# ログ内容
{log_text}

# 要約のポイント
1. **話題**: どんな会話やトレンドが発生しているか
2. **交流**: 誰と誰が仲良くしているか、または対立しているか
3. **ハイライト**: 特に面白い発言や、AIのエラーっぽい挙動があれば指摘
4. **雰囲気**: 全体的に平和か、殺伐としているか、カオスか

出力は日本語で、箇条書きを使って簡潔にまとめてください。
"""
        user_msg = {"role": "user", "content": prompt}

        response = ollama_model.run([user_msg])

        if hasattr(response, "choices") and len(response.choices) > 0:
            return response.choices[0].message.content
        elif hasattr(response, "content"):
            return response.content
        elif isinstance(response, dict) and "choices" in response:
            return response["choices"][0]["message"]["content"]
        else:
            return str(response)

    except Exception as e:
        return f"⚠️ 要約の生成に失敗しました: {e}"


def merge_databases():
    """ollama_twitter.dbのデータをsumika_tracker.dbにミラーコピーする"""
    if not os.path.exists(db_path):
        print(f"⚠️ {db_path} が見つかりません。スキップします。")
        return

    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(tracker_db_path)
    dst_cur = dst.cursor()

    tables = ["user", "post", "comment", "like", "trace"]

    for table in tables:
        mirror = f"mirror_{table}"
        try:
            # 既存のミラーテーブルを削除して再作成
            dst_cur.execute(f"DROP TABLE IF EXISTS {mirror}")

            # ソーステーブルの構造を取得
            src_cur = src.execute(f"PRAGMA table_info({table})")
            columns = src_cur.fetchall()
            if not columns:
                continue

            col_defs = ", ".join(f"{col[1]} {col[2]}" for col in columns)
            dst_cur.execute(f"CREATE TABLE {mirror} ({col_defs})")

            # データをコピー
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            if rows:
                placeholders = ", ".join("?" * len(columns))
                dst_cur.executemany(
                    f"INSERT INTO {mirror} VALUES ({placeholders})", rows
                )

            dst.commit()
            print(f"  ✅ {mirror}: {len(rows)}件コピー")
        except Exception as e:
            print(f"  ⚠️ {mirror} のコピー失敗: {e}")

    src.close()
    dst.close()


def show_and_save_results():
    output_dir = "result_data"
    os.makedirs(output_dir, exist_ok=True)

    print("🔄 DBをマージ中...")
    merge_databases()  # ★追加
    print("✅ マージ完了\n")

    now = datetime.now()
    file_name = now.strftime("%Y-%m-%d_%H-%M-%S.txt")
    output_path = os.path.join(output_dir, file_name)

    print("--------------------------------------------------")
    print(f"ファイル名を自動生成しました: {file_name}")
    print("--------------------------------------------------")
    print(f"--- 接続先DB: {db_path} ---")

    conn = sqlite3.connect(tracker_db_path)

    timeline_text = get_timeline_text(conn, tracker_conn=conn)
    action_text = get_action_log_text(conn)
    impression_text = get_impression_text(conn)
    conn.close()

    full_log_text = (
        timeline_text + "\n" + action_text + "\n" + impression_text
    )  # ★impression_text追加

    if ENABLE_SUMMARY:
        summary = generate_summary(full_log_text)
    else:
        summary = "（AI要約はスキップされました）"

    final_output = "\n" + "=" * 20 + " 【📝 AI要約レポート】 " + "=" * 20 + "\n"
    final_output += summary + "\n"
    final_output += "=" * 60 + "\n\n"
    final_output += full_log_text

    print(final_output)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_output)

    print(f"\n✅ 保存しました: {output_path}")


if __name__ == "__main__":
    show_and_save_results()