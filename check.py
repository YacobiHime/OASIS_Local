import sqlite3
import pandas as pd
import sys
import io
import os
import json
from datetime import datetime
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage

# 文字化け対策
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


db_path = "./ollama_twitter.db"


def format_info_json(text):
    """JSON文字列から不要な情報を省き、見やすく整形して返す"""
    if not isinstance(text, str):
        return str(text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            # 表示したくない不要な項目を除外（例としてpromptなどを指定）
            keys_to_remove = ["prompt", "embeddings", "raw_response"]
            for k in keys_to_remove:
                data.pop(k, None)

            # 文字列が長すぎる場合は切り詰める（100文字で省略）
            for k, v in data.items():
                if isinstance(v, str) and len(v) > 100:
                    data[k] = v[:100] + "...(省略)"

        return json.dumps(data, indent=2, ensure_ascii=False)
    except:
        return text


def get_timeline_text(conn):
    """投稿とコメントをスレッド形式で生成する"""
    text = "【📱 投稿タイムライン (スレッド表示)】\n"
    try:
        # 1. 投稿(Post)を取得（リポスト情報含む）
        sql_posts = """
        SELECT 
            p1.post_id,
            p1.user_id, 
            p1.content, 
            p1.quote_content,
            p1.created_at,
            p1.original_post_id,
            p2.content AS original_content,
            p2.user_id AS original_user_id
        FROM post p1
        LEFT JOIN post p2 ON p1.original_post_id = p2.post_id
        ORDER BY p1.created_at
        """
        posts = pd.read_sql_query(sql_posts, conn)

        # 2. コメント(Comment)を取得
        # テーブルが存在しない場合に備えて try-except
        try:
            sql_comments = "SELECT * FROM comment ORDER BY created_at"
            comments = pd.read_sql_query(sql_comments, conn)
        except Exception:
            comments = pd.DataFrame()

        if posts.empty:
            text += "（投稿はまだありません）\n"
        else:
            for index, row in posts.iterrows():
                post_id = row["post_id"]
                text += "-" * 60 + "\n"
                text += f"⏰ Time: {row['created_at']} | 🆔 Post: {post_id}\n"
                text += f"👤 User: {row['user_id']}\n"

                # --- 投稿内容の表示ロジック ---
                content = row["content"]
                original_content = row["original_content"]
                quote_content = row["quote_content"]

                if row["original_post_id"] and quote_content:
                    # 引用リポスト
                    text += f"💬 {quote_content}\n"
                    text += f"   ↳ 🔁 QT @User{row['original_user_id']}: {content if content else original_content}\n"
                elif content and content.strip():
                    # 通常投稿
                    text += f"💬 {content}\n"
                elif original_content:
                    # リポスト
                    text += f"🔁 [リポスト] @User{row['original_user_id']} の投稿を拡散しました\n"
                    text += f"   「{original_content}」\n"
                else:
                    text += "💬 (本文なし)\n"

                # 3. この投稿についたコメントを表示 (Nested)
                if not comments.empty:
                    # この投稿(post_id)に紐づくコメントを抽出
                    post_comments = comments[comments["post_id"] == post_id]

                    if not post_comments.empty:
                        text += "\n   👇 [コメント欄]\n"
                        for c_idx, c_row in post_comments.iterrows():
                            # コメントの「中身」と「誰が書いたか」を表示
                            c_content = c_row.get("content", "")
                            c_user = c_row.get("user_id", "?")
                            c_time = c_row.get("created_at", "?")
                            text += f"   ├─ ⏰{c_time} 👤User{c_user}: {c_content}\n"

            text += "-" * 60 + "\n"
    except Exception as e:
        text += f"タイムライン取得エラー: {e}\n"
    return text


def get_action_log_text(conn):
    """行動ログのテキストを生成する（最新20件）"""
    text = "\n【🤖 エージェント行動ログ (最新20件)】\n"
    try:
        actions = pd.read_sql_query(
            "SELECT * FROM trace ORDER BY id DESC LIMIT 20", conn
        )
        actions = actions.iloc[::-1]

        if actions.empty:
            text += "（行動ログはまだありません）\n"
        else:
            for index, row in actions.iterrows():
                text += "┌" + "─" * 40 + "\n"
                text += f"│ ⏰ Time: {row['created_at']} | 👤 User: {row['user_id']}\n"

                # 状態（status）を取得してアイコンを切り替え
                status = row.get("status", "success")
                status_icon = "✅" if status == "success" else "❌"
                text += f"│ {status_icon} Action: {row['action']} (Status: {status})\n"

                # エラー内容がある場合は表示
                if row.get("error_message"):
                    text += f"│ ⚠️ Error: {row['error_message']}\n"

                info_content = ""
                if "info" in row and row["info"]:
                    info_content = row["info"]
                elif "action_params" in row and row["action_params"]:
                    info_content = row["action_params"]

                if info_content:
                    # ここで新しい関数を使用します
                    formatted_json = format_info_json(info_content)
                    text += "│ 📄 Info:\n"
                    for line in formatted_json.split("\n"):
                        text += f"│    {line}\n"
                text += "└" + "─" * 40 + "\n"
    except Exception as e:
        text += f"行動ログ取得エラー: {e}\n"
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


def show_and_save_results():
    output_dir = "result_data"
    os.makedirs(output_dir, exist_ok=True)

    now = datetime.now()
    file_name = now.strftime("%Y-%m-%d_%H-%M-%S.txt")
    output_path = os.path.join(output_dir, file_name)

    print("--------------------------------------------------")
    print(f"ファイル名を自動生成しました: {file_name}")
    print("--------------------------------------------------")
    print(f"--- 接続先DB: {db_path} ---")

    conn = sqlite3.connect(db_path)

    timeline_text = get_timeline_text(conn)
    action_text = get_action_log_text(conn)
    full_log_text = timeline_text + "\n" + action_text

    summary = generate_summary(full_log_text)

    final_output = "\n" + "=" * 20 + " 【📝 AI要約レポート】 " + "=" * 20 + "\n"
    final_output += summary + "\n"
    final_output += "=" * 60 + "\n\n"
    final_output += full_log_text

    print(final_output)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_output)

    print(f"\n✅ 保存しました: {output_path}")
    conn.close()


if __name__ == "__main__":
    show_and_save_results()
