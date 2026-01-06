import asyncio
import os
import json
from camel.models import ModelFactory
from camel.types import ModelPlatformType
import oasis
from oasis import (
    generate_reddit_agent_graph,
    DefaultPlatformType,
    LLMAction
)

async def main():
    # 1. ローカルLLM (Ollama + Llama 3.2) の設定
    target_model = "llama3.2"
    print(f"Setting up local LLM (Ollama with {target_model})...")
    
    local_model = ModelFactory.create(
        model_platform=ModelPlatformType.OLLAMA,
        model_type=target_model,
        url="http://localhost:11434/v1",
        model_config_dict={"temperature": 0.4, "max_tokens": 4096},
    )

    # 2. データベースとプロファイルのパス設定
    db_path = "./data/local_reddit_gemma.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")

    # --- 【修正点】人数を減らす処理を追加 ---
    original_profile_path = "./data/reddit/user_data_36.json"
    small_profile_path = "./data/reddit/user_data_mini.json"
    
    # 元のファイルから5人分だけ抜き出して保存する
    if os.path.exists(original_profile_path):
        with open(original_profile_path, 'r', encoding='utf-8') as f:
            users = json.load(f)
        
        # 最初の5人だけにする
        small_users = users[:5]
        
        with open(small_profile_path, 'w', encoding='utf-8') as f:
            json.dump(small_users, f, indent=4)
        print(f"Created mini profile with 5 agents at: {small_profile_path}")
    else:
        raise FileNotFoundError(f"Original profile not found: {original_profile_path}")
    
    # 使うファイルをミニ版に切り替え
    profile_path = small_profile_path
    # ---------------------------------------

    # 3. エージェントグラフの生成
    available_actions = [
        "create_post", "like_post", "repost", "quote_post",
        "dislike_post", "undo_dislike_post",
        "search_posts", "search_user", "trend", "refresh", "do_nothing",
        "create_comment", "like_comment", "dislike_comment", 
        "follow", "unfollow", "mute", "unmute"
    ]

    print(f"Generating agent graph using {target_model}...")
    agent_graph = await generate_reddit_agent_graph(
        profile_path=profile_path,
        model=local_model,
        available_actions=available_actions,
    )

    # 4. OASIS環境の初期化
    print("Initializing OASIS environment...")
    
    env = oasis.make(
        platform=DefaultPlatformType.REDDIT,
        agent_graph=agent_graph,
        database_path=db_path,
    )

    # 5. シミュレーション実行ループ (5ステップ)
    print("Resetting environment...")
    await env.reset()
    
    num_steps = 5
    for i in range(num_steps):
        print(f"\n--- Simulation Step {i+1}/{num_steps} ---")
        
        # エージェントごとの行動決定
        actions = {}
        for agent_id, agent in env.agent_graph.get_agents():
            actions[agent] = LLMAction()
        
        # 行動実行
        try:
            result = await env.step(actions)
            # 戻り値がNoneでないか確認してから展開
            if result is None:
                print("Warning: Environment returned None (possible timeout). Stopping simulation.")
                break
            obs, rewards, done, info = result
            print(f"Step {i+1} processed successfully.")
            
        except Exception as e:
            print(f"Error during step {i+1}: {e}")
            break

    await env.close()
    print("\nSimulation finished.")
    print(f"Data saved to: {db_path}")

if __name__ == "__main__":
    asyncio.run(main())