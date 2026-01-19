import sqlite3
import pandas as pd
import sys
import io

# 文字化け対策
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# DBパス
db_path = "./data/local_twitter_simulation.db"

def show_results():
    print(f"--- 接続先DB: {db_path} ---\n")
    conn = sqlite3.connect(db_path)
    
    try:
        # 1. 投稿内容（再確認）
        print("【投稿されたツイート（時系列）】")
        posts = pd.read_sql_query("SELECT user_id, content, created_at FROM post ORDER BY created_at", conn)
        # 時間の表示バグがあっても中身が読めるようにそのまま表示
        print(posts.to_string(index=False))
        print("\n" + "="*50 + "\n")

        # 2. 行動ログ（修正部分）
        print("【行動ログ (Traceテーブル)】")
        
        # まずカラム名を取得して確認
        cursor = conn.execute("SELECT * FROM trace LIMIT 1")
        columns = [description[0] for description in cursor.description]
        print(f"検出されたカラム名: {columns}")
        
        # 全カラムを取得して表示
        actions = pd.read_sql_query(f"SELECT * FROM trace ORDER BY rowid DESC LIMIT 10", conn)
        print(actions.to_string(index=False))

    except Exception as e:
        print(f"エラー: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    show_results()
    