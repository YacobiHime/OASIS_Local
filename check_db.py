import sqlite3
import os

# データベースのパス
db_path = "./data/local_reddit_gemma.db"

def main():
    if not os.path.exists(db_path):
        print("データベースが見つかりません。シミュレーションを実行しましたか？")
        return

    # データベースに接続
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print(f"--- データベース接続: {db_path} ---")
        
        # 保存されているテーブル（データの種類）を確認
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"\n保存されているテーブル一覧: {tables}")

        # エージェントの行動記録（traceテーブル）を表示
        print("\n--- エージェントの行動ログ (trace) ---")
        cursor.execute("SELECT * FROM trace")
        rows = cursor.fetchall()
        
        if not rows:
            print("まだ行動ログが記録されていません。")
        else:
            for row in rows:
                # 読みやすいように表示
                print(f"Agent ID: {row[1]}, Action: {row[2]}, Content: {row[3]}")

    except Exception as e:
        print(f"エラーが発生しました: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()