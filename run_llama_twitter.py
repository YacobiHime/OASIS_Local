import asyncio
import os
import json
import sqlite3
import pandas as pd
import time
# 【追加】文字化け対策のためのライブラリ
import sys
import io

# 【追加】WindowsのコンソールでUTF-8（絵文字など）を強制的に表示できるようにする設定
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from camel.models import ModelFactory
from camel.types import ModelPlatformType
import oasis
from oasis import (
    generate_twitter_agent_graph,
    DefaultPlatformType,
    LLMAction
)

# --- 初期投稿データを投入する関数 ---
def seed_initial_posts(db_path):
    print(f"Seeding initial posts to {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    current_time = int(time.time())
    
    # 投稿データに絵文字（☕）を含めて動作確認します
    initial_posts = [
        (1, 0, "Hello Twitter world! This is the first post.", current_time, 0, 0),
        (2, 1, "I love AI and simulations. #tech", current_time - 10, 0, 0),
        (3, 2, "Does anyone know how to solve the logistics problem? #transportation", current_time - 20, 0, 0),
        (4, 3, "Just had a great coffee! ☕", current_time - 30, 0, 0)
    ]
    
    try:
        cursor.executemany(
            "INSERT INTO post (post_id, user_id, content, created_at, num_likes, num_dislikes) VALUES (?, ?, ?, ?, ?, ?)",
            initial_posts
        )
        conn.commit()
        print("Successfully inserted 4 seed posts with numeric timestamps.")
    except Exception as e:
        print(f"Error seeding posts: {e}")
    finally:
        conn.close()

async def main():
    # 1. ローカルLLM設定
    target_model = "llama3.2"
    print(f"Setting up local LLM (Ollama with {target_model})...")
    
    local_model = ModelFactory.create(
        model_platform=ModelPlatformType.OLLAMA,
        model_type=target_model,
        url="http://localhost:11434/v1",
        model_config_dict={"temperature": 0.4, "max_tokens": 4096},
    )

    # 2. データベース設定
    db_path = "./data/local_twitter_simulation.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")

    # --- ユーザーデータ(CSV)準備 ---
    original_profile_path = "./data/reddit/user_data_36.json"
    small_profile_path = "./data/twitter/user_data_mini.csv"
    os.makedirs(os.path.dirname(small_profile_path), exist_ok=True)
    
    users_data = []
    if os.path.exists(original_profile_path):
        with open(original_profile_path, 'r', encoding='utf-8') as f:
            full_users = json.load(f)
            users_data = full_users[:5]
    else:
        users_data = [
            {"agent_id": i, "user_name": f"user{i}", "name": f"User {i}", "bio": "AI Agent", "created_at": "2023-01-01"}
            for i in range(5)
        ]

    df = pd.DataFrame(users_data)
    if 'bio' in df.columns:
        df['user_char'] = df['bio']
    else:
        df['user_char'] = "A generic social media user."
    if 'description' not in df.columns and 'bio' in df.columns:
        df['description'] = df['bio']
        
    df.to_csv(small_profile_path, index=False, encoding='utf-8')
    print(f"Created profile CSV at: {small_profile_path}")
    
    profile_path = small_profile_path

    # 3. エージェントグラフ生成
    available_actions = [
        "create_post", "repost", "like_post", "unlike_post",
        "search_posts", "search_user", "trend", "refresh", "do_nothing",
        "create_comment", "like_comment", 
        "follow", "unfollow", "mute", "unmute"
    ]

    print(f"Generating Twitter agent graph using {target_model}...")
    agent_graph = await generate_twitter_agent_graph(
        profile_path=profile_path,
        model=local_model,
        available_actions=available_actions,
    )

    # 4. OASIS環境初期化
    print("Initializing OASIS environment for Twitter...")
    env = oasis.make(
        platform=DefaultPlatformType.TWITTER,
        agent_graph=agent_graph,
        database_path=db_path,
    )

    # リセットとデータ投入
    print("Resetting environment...")
    await env.reset()
    seed_initial_posts(db_path)
    
    # 5. シミュレーション実行ループ
    num_steps = 5
    for i in range(num_steps):
        print(f"\n--- Simulation Step {i+1}/{num_steps} ---")
        
        actions = {}
        for agent_id, agent in env.agent_graph.get_agents():
            actions[agent] = LLMAction()
        
        try:
            result = await env.step(actions)
            
            if result is None:
                print("Warning: Environment returned None. Stopping simulation.")
                break
                
            obs, rewards, done, info = result
            print(f"Step {i+1} processed successfully.")
            
        except Exception as e:
            print(f"Error during step {i+1}: {e}")
            import traceback
            traceback.print_exc()
            break

    await env.close()
    print("\nSimulation finished.")
    print(f"Check results with: sqlite3 {db_path} 'SELECT * FROM post;'")

if __name__ == "__main__":
    asyncio.run(main())