import asyncio
import os
import json
from camel.models import ModelFactory
from camel.types import ModelPlatformType
import oasis
from oasis import (
    generate_x_agent_graph,  # 変更点1: Reddit用からX用に変更
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
    # X用のDB名に変更しておくと分かりやすいです
    db_path = "./data/local_x_gemma.db" 
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")

    # --- 人数を減らす処理 ---
    # 注: 元データがReddit用の場合でも、基本的な名前やBioが含まれていればX用として流用可能です。
    # ただし、データ構造に互換性がない場合は、X用のユーザーデータを用意する必要があります。
    original_profile_path = "./data/reddit/user_data_36.json" 
    small_profile_path = "./data/x/user_data_mini.json"  # パスをX用に変更推奨
    
    # 保存先ディレクトリがない場合は作成
    os.makedirs(os.path.dirname(small_profile_path), exist_ok=True)

    if os.path.exists(original_profile_path):
        with open(original_profile_path, 'r', encoding='utf-8') as f:
            users = json.load(f)
        
        # 最初の5人だけにする
        small_users = users[:5]
        
        with open(small_profile_path, 'w', encoding='utf-8') as f:
            json.dump(small_users, f, indent=4)
        print(f"Created mini profile with 5 agents at: {small_profile_path}")
    else:
        # 元ファイルがない場合のエラーハンドリング（ここは環境に合わせて調整してください）
        print(f"Original profile not found: {original_profile_path}. Please ensure source data exists.")
        return 
    
    profile_path = small_profile_path
    # ---------------------------------------

    # 3. エージェントグラフの生成
    # X (Twitter) 用のアクションセット
    # ドキュメントに基づき、Xのアクション空間は以下を含みます:
    # create_post, repost, like_post, dislike_post, follow, create_comment, like_comment, dislike_comment
    available_actions = [
        "create_post", "repost", "like_post", "dislike_post", # dislikeはXではあまり一般的ではないですがOASISには実装されています
        "undo_dislike_post", "quote_post", # 引用リポスト
        "search_posts", "search_user", "trend", "refresh", "do_nothing",
        "create_comment", "like_comment", "dislike_comment", 
        "follow", "unfollow", "mute", "unmute"
    ]

    print(f"Generating X (Twitter) agent graph using {target_model}...")
    
    # 変更点2: X用のグラフ生成関数を使用
    agent_graph = await generate_x_agent_graph(
        profile_path=profile_path,
        model=local_model,
        available_actions=available_actions,
    )

    # 4. OASIS環境の初期化
    print("Initializing OASIS environment for X...")
    
    env = oasis.make(
        platform=DefaultPlatformType.X, # 変更点3: プラットフォームをXに変更
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