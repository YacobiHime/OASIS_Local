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
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

db_path = "./ollama_twitter.db"

def pretty_print_json(text):
    """JSON文字列を見やすく整形して返す"""
    if not isinstance(text, str):
        return str(text)
    try:
        data = json.loads(text)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except:
        return text

def get_timeline_text(conn):
    """投稿タイムラインのテキストを生成する（リポスト対応版）"""
    text = "【📱 投稿タイムライン】\n"
    try:
        # ★★★ SQL修正: 自己結合して、リポスト元の内容(original_content)を取得する ★★★
        sql = """
        SELECT 
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
        
        posts = pd.read_sql_query(sql, conn)
        
        if posts.empty:
            text += "（投稿はまだありません）\n"
        else:
            for index, row in posts.iterrows():
                text += "-" * 40 + "\n"
                text += f"⏰ Time: {row['created_at']}\n"
                text += f"👤 User: {row['user_id']}\n"
                
                content = row['content']
                original_content = row['original_content']
                quote_content = row['quote_content']
                
                # --- 表示ロジックの分岐 ---
                
                # パターン1: 引用リポスト (Quote Post)
                # 引用コメント(quote_content)があり、元の投稿IDもある場合
                # ※OASISの実装によっては、contentに元の投稿が入り、quote_contentにコメントが入る場合がある
                if row['original_post_id'] and quote_content:
                     text += f"💬 {quote_content}\n"
                     text += f"   ↳ 🔁 QT @User{row['original_user_id']}: {content if content else original_content}\n"
                
                # パターン2: 通常の投稿 (Original Post)
                # contentがあり、quote_contentがない場合
                elif content and content.strip():
                     text += f"💬 {content}\n"
                
                # パターン3: 純粋なリポスト (Repost)
                # contentが空っぽだが、original_contentがある場合
                elif original_content:
                    text += f"🔁 [リポスト] @User{row['original_user_id']} の投稿を拡散しました\n"
                    text += f"   「{original_content}」\n"
                
                # パターン4: その他（本当に空っぽなど）
                else:
                    text += "💬 (本文なし)\n"
                    
            text += "-" * 40 + "\n"
    except Exception as e:
        text += f"タイムライン取得エラー: {e}\n"
    return text

def get_action_log_text(conn):
    """行動ログのテキストを生成する（最新20件に限定してコンテキストあふれ防止）"""
    text = "\n【🤖 エージェント行動ログ (最新20件)】\n"
    try:
        actions = pd.read_sql_query(f"SELECT * FROM trace ORDER BY rowid DESC LIMIT 20", conn)
        actions = actions.iloc[::-1] # 時系列順に戻す

        if actions.empty:
            text += "（行動ログはまだありません）\n"
        else:
            for index, row in actions.iterrows():
                text += "┌" + "─" * 40 + "\n"
                text += f"│ ⏰ Time: {row['created_at']} | 👤 User: {row['user_id']}\n"
                text += f"│ ⚡ Action: {row['action']}\n"
                
                info_content = ""
                if 'info' in row and row['info']:
                    info_content = row['info']
                elif 'action_params' in row and row['action_params']:
                    info_content = row['action_params']
                
                if info_content:
                    formatted_json = pretty_print_json(info_content)
                    text += "│ 📄 Info:\n"
                    # インデントをつけて見やすく
                    for line in formatted_json.split('\n'):
                        text += f"│    {line}\n"
                text += "└" + "─" * 40 + "\n"
    except Exception as e:
        text += f"行動ログ取得エラー: {e}\n"
    return text

def generate_summary(log_text):
    """LLMを使ってログを要約する"""
    print("🤖 AIがログを要約中... (Qwen3が考え中💭)")
    try:
        # Ｐっち指定のモデル設定！
        ollama_model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type="qwen3:4b-instruct-2507-q4_K_M",
            url="http://localhost:11434/v1",
            api_key="ollama",
            model_config_dict={"temperature": 0.2},
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
        user_msg = {
            "role": "user",
            "content": prompt
        }
        
        # 実行！
        response = ollama_model.run([user_msg])
        
        # レスポンスの取り出し処理
        if hasattr(response, 'choices') and len(response.choices) > 0:
            return response.choices[0].message.content
        elif hasattr(response, 'content'):
            return response.content
        elif isinstance(response, dict) and 'choices' in response:
            return response['choices'][0]['message']['content']
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
    
    # 1. まずログのテキストを作る
    timeline_text = get_timeline_text(conn)
    action_text = get_action_log_text(conn)
    full_log_text = timeline_text + "\n" + action_text
    
    # 2. それをLLMに投げて要約してもらう
    summary = generate_summary(full_log_text)
    
    # 3. 全部くっつけて表示＆保存
    final_output = "\n" + "="*20 + " 【📝 AI要約レポート】 " + "="*20 + "\n"
    final_output += summary + "\n"
    final_output += "="*60 + "\n\n"
    final_output += full_log_text
    
    print(final_output)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_output)
        
    print(f"\n✅ 保存しました: {output_path}")
    conn.close()

if __name__ == "__main__":
    show_and_save_results()