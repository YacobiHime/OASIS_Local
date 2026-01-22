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
        model_type="qwen3:4b",
        url="http://localhost:11434/v1",
        api_key="ollama",
        model_config_dict={"temperature": 0.0},
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
            "name": "Alice",
            "bio": "Twitter廃人のエンジニア。新しい技術が出るとすぐ試して感想を呟く。ポジティブ。日本語で投稿して。",
            "id": 0
        },
        {
            "name": "Bob", 
            "bio": "疑り深い性格。Aliceのツイートによくツッコミのリプライを送る。「それ本当？」が口癖。日本語で会話して。",
            "id": 1
        },
        {
            "name": "Carol",
            "bio": "流行りものが大好きな女子高生。楽しいツイートを見るとすぐリポスト（拡散）しちゃう！絵文字多め。日本語で話してね！",
            "id": 2
        },
        {
            "name": "Kecha_Chacka",
            "bio": "陰謀論者で、医療デマを広めてしまう人。知らない人にも返信する。絵文字多め。日本語で話してね！",
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