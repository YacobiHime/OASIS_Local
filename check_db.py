import sqlite3
import pandas as pd
import sys
import io
import os
import json # これを追加
from datetime import datetime

# 文字化け対策
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

db_path = "./ollama_twitter.db"

def show_and_save_results():
    output_dir = "result_data"
    os.makedirs(output_dir, exist_ok=True)
    
    now = datetime.now()
    file_name = now.strftime("%Y-%m-%d_%H-%M-%S.txt")
    
    print("--------------------------------------------------")
    print(f"ファイル名を自動生成しました: {file_name}")
    print("--------------------------------------------------")
    
    output_path = os.path.join(output_dir, file_name)
    
    buffer_text = ""
    def print_log(text):
        nonlocal buffer_text
        print(text)
        buffer_text += text + "\n"

    # --- 【追加機能】JSONの中の絵文字を復元する関数 ---
    def decode_json_info(text):
        try:
            # 一度JSONとして読み込んで、"ensure_ascii=False"（そのまま表示）で書き戻す
            data = json.loads(text)
            return json.dumps(data, ensure_ascii=False)
        except:
            return text
    # ------------------------------------------------

    print_log(f"--- 接続先DB: {db_path} ---\n")
    conn = sqlite3.connect(db_path)
    
    try:
        # (1) 投稿内容
        print_log("【投稿されたツイート（時系列）】")
        posts = pd.read_sql_query("SELECT user_id, content, created_at FROM post ORDER BY created_at", conn)
        print_log(posts.to_string(index=False))
        print_log("\n" + "="*50 + "\n")

        # (2) 行動ログ
        print_log("【行動ログ (Traceテーブル)】")
        cursor = conn.execute("SELECT * FROM trace LIMIT 1")
        columns = [description[0] for description in cursor.description]
        print_log(f"検出されたカラム名: {columns}")
        
        actions = pd.read_sql_query(f"SELECT * FROM trace ORDER BY rowid DESC LIMIT 10", conn)
        
        # 【ここが修正ポイント】
        # 'info' という列がある場合、中のコード(\uXXXX)を絵文字に戻す処理をする
        if 'info' in actions.columns:
            actions['info'] = actions['info'].apply(decode_json_info)
        # 'action_params' という列名の場合もあるので念のため
        if 'action_params' in actions.columns:
            actions['action_params'] = actions['action_params'].apply(decode_json_info)

        print_log(actions.to_string(index=False))
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(buffer_text)
            
        print(f"\n✅ 保存しました: {output_path}")

    except Exception as e:
        print(f"エラー: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    show_and_save_results()