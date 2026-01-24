import asyncio
import os
from camel.models import ModelFactory
from camel.types import ModelPlatformType

import oasis
from oasis import ActionType, LLMAction, ManualAction, AgentGraph, SocialAgent, UserInfo

async def main():
    # ---------------------------------------------------------
    # 1. モデル設定 
    # ---------------------------------------------------------
    ollama_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type="qwen3:4b-instruct-2507-q4_K_M",
        url="http://localhost:11434/v1",
        api_key="ollama",
        model_config_dict={"temperature": 0.4},
    )

    # ---------------------------------------------------------
    # 2. アクション設定 (ここをTwitter用に変更！)
    # ---------------------------------------------------------
    available_actions = [
        ActionType.CREATE_POST,    # 投稿
        ActionType.CREATE_COMMENT, # リプライ
        ActionType.LIKE_POST,      # いいね
        ActionType.REPOST,         # ★追加：リポスト（拡散）！
        ActionType.FOLLOW,         # フォロー
    ]

    # ---------------------------------------------------------
    # 3. 住人登録 (ここもTwitter用に微調整！)
    # ---------------------------------------------------------
    profiles = [
        {
            "name": "森本裕介",
            # ★英語禁止！と強く書く
            "bio": "Twitter廃人のエンジニア。ポジティブ。どんな時も【絶対に日本語だけで】つぶやきます。英語は禁止です。Japanese language only.",
            "id": 0
        },
        {
            "name": "佐々木朗希", 
            "bio": "疑り深い性格。「それ本当？」が口癖。【必ず日本語で】リプライを返します。英語は使いません。Japanese language only.",
            "id": 1
        },
        {
            "name": "山本由伸",
            "bio": "流行りものが大好きな女子高生。絵文字をたくさん使う。【日本語のギャル語】で話して。英語は絶対に使わないで！ Speak in Japanese Gal-go.",
            "id": 2
        },
        {
            "name": "ケチャ・チャッカ",
            "bio": "陰謀論者。医療デマを強く信じ、他人に説教しようとする。【常に日本語で】会話に参加します。英語禁止。Japanese only.", 
            "id": 3
        }
    ]

    agent_graph = AgentGraph()
    print("🤖: 住人を登録中...")

    for profile in profiles:
        user_info = UserInfo(
            user_name=profile["name"].lower(),
            name=profile["name"],
            description=profile["bio"],
            profile=None,
            # ★ここ重要！レコメンドをTwitterモードにする
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
        print(f"✨ {profile['name']} さんが入居しました！")

    # ---------------------------------------------------------
    # 4. 環境構築 (プラットフォームをTWITTERに変更！)
    # ---------------------------------------------------------
    db_path = "./ollama_twitter.db"  # DBファイル名も変えておこう
    os.environ["OASIS_DB_PATH"] = os.path.abspath(db_path)
    
    if os.path.exists(db_path):
        os.remove(db_path)

    env = oasis.make(
        agent_graph=agent_graph,
        # ★ここ！REDDIT -> TWITTER に変更
        platform=oasis.DefaultPlatformType.TWITTER, 
        database_path=db_path,
    )
    await env.reset()

    print("🤖: Twitter（X）シミュレーション開始！")

    # 最初のきっかけ作り（Aliceの初ツイート）
    alice_agent = env.agent_graph.get_agent(0)
    starter_action = {
        alice_agent: [
            ManualAction(
                action_type=ActionType.CREATE_POST,
                action_args={
                    "content": "OASISでTwitterはじめました！みんなフォローしてね～ #初投稿"
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