import asyncio
import os
import json
import argparse  # ★追加：引数処理用
from camel.models import ModelFactory
from camel.types import ModelPlatformType

import oasis
from oasis import ActionType, LLMAction, ManualAction, AgentGraph, SocialAgent, UserInfo

# ★追加：JSON読み込み用関数
def load_profiles(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            profiles = json.load(f)
            print(f"📂 プロファイル '{file_path}' を読み込みました。")
            return profiles
    except FileNotFoundError:
        print(f"❌ エラー: ファイル '{file_path}' が見つかりません。")
        exit(1)
    except json.JSONDecodeError:
        print(f"❌ エラー: '{file_path}' のJSON形式が正しくありません。")
        exit(1)

async def main():
    # ---------------------------------------------------------
    # 0. コマンドライン引数の設定
    # ---------------------------------------------------------
    parser = argparse.ArgumentParser(description="OASIS Twitter Simulation")
    # --profiles 引数でJSONファイルを指定（デフォルトは chaos.json にしておくね）
    parser.add_argument(
        "--profiles", 
        type=str, 
        default="profiles/chaos.json", 
        help="Path to the user profiles JSON file"
    )
    args = parser.parse_args()

    # プロファイルをロード
    profiles = load_profiles(args.profiles)

    # ---------------------------------------------------------
    # 1. モデル設定 
    # ---------------------------------------------------------
    ollama_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type="qwen3:4b-instruct-2507-q4_K_M",
        url="http://localhost:11434/v1",
        api_key="ollama",
        model_config_dict={"temperature": 0.2},
    )

    # ---------------------------------------------------------
    # 2. アクション設定
    # ---------------------------------------------------------
    available_actions = [
        ActionType.CREATE_POST,    # 投稿
        ActionType.CREATE_COMMENT, # リプライ
        ActionType.LIKE_POST,      # いいね
        ActionType.REPOST,         # リポスト（拡散）
        ActionType.FOLLOW,         # フォロー
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
            user_name=profile["name"].lower(), # 簡易的に名前を使用
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
    db_path = "./ollama_twitter.db"
    os.environ["OASIS_DB_PATH"] = os.path.abspath(db_path)
    
    if os.path.exists(db_path):
        os.remove(db_path)

    env = oasis.make(
        agent_graph=agent_graph,
        platform=oasis.DefaultPlatformType.TWITTER, 
        database_path=db_path,
    )
    await env.reset()

    print("🤖: Twitter（X）シミュレーション開始！")

    # 最初のきっかけ作り（ID:0 の住人に初投稿させる）
    # ※JSONの0番目の人が「森本」さん以外でも動くように動的に取得
    first_agent = env.agent_graph.get_agent(0)
    first_agent_name = profiles[0]["name"]
    
    starter_action = {
        first_agent: [
            ManualAction(
                action_type=ActionType.CREATE_POST,
                action_args={
                    "content": f"Twitterはじめました！みんなフォローしてね～ #初投稿 ({first_agent_name})"
                }
            )
        ]
    }
    await env.step(starter_action)

    # ---------------------------------------------------------
    # 5. 時間を動かす (5ターン)
    # ---------------------------------------------------------
    simulation_rounds = 5
    for i in range(simulation_rounds):
        print(f"\n⏱️ --- ターン {i + 1} / {simulation_rounds} ---")
        
        actions = {
            agent: LLMAction()
            for _, agent in env.agent_graph.get_agents()
        }
        await env.step(actions)

    print("✅ シミュレーション終了！")
    await env.close()

if __name__ == "__main__":
    asyncio.run(main())