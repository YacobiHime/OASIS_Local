import asyncio
import os
from camel.models import ModelFactory
from camel.types import ModelPlatformType

import oasis
from oasis import ActionType, LLMAction, ManualAction, AgentGraph, SocialAgent, UserInfo

async def main():
    # ---------------------------------------------------------
    # Pっち専用：Ollama接続設定 (OpenAIのフリ作戦！)
    # ---------------------------------------------------------
    ollama_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type="llama3.2",                    # Ollamaでpullしたモデル名
        url="http://localhost:11434/v1",          # Ollamaの住所
        api_key="ollama",                         # 何でもいいから入れておく
        model_config_dict={"temperature": 0.0},   # 0にすると動作が安定するよ
    )

    # アクションの定義（Reddit風の例）
    available_actions = [
        ActionType.CREATE_POST,
        ActionType.LIKE_POST,
        ActionType.FOLLOW,
    ]

    # ★ここから下のインデント（字下げ）を修正したよ！★
    profiles = [
        {
            "name": "Alice",
            "bio": "Ollamaが大好きで、新しい技術に目がないAIエンジニア。ポジティブ。常に日本語で投稿やコメントをしてください。",
            "id": 0
        },
        {
            "name": "Bob", 
            "bio": "疑り深い性格。ネットの情報はすぐには信じない。「それ本当？」が口癖。日本語で会話します。",
            "id": 1
        },
        {
            "name": "Carol",
            "bio": "流行りものが大好きな女子高生。楽しいことが好きで、絵文字をよく使う。日本語で話してね！",
            "id": 2
        }
    ]

    agent_graph = AgentGraph()
    
    print("🤖: 住人を登録中...")

    # 2. ループで一気に登録する
    for profile in profiles:
        user_info = UserInfo(
            user_name=profile["name"].lower(),
            name=profile["name"],
            description=profile["bio"], # ここがAIの「性格」になるよ！
            profile=None,
            recsys_type="reddit",
        )
        
        agent = SocialAgent(
            agent_id=profile["id"],
            user_info=user_info,
            agent_graph=agent_graph,
            model=ollama_model,       # みんな同じOllamaモデルを使うよ
            available_actions=available_actions,
        )
        
        agent_graph.add_agent(agent)
        print(f"✨ {profile['name']} さんが入居しました！")

    # ---------------------------------------------------------
    # データベース設定 (ここもmainの中に入れる！)
    # ---------------------------------------------------------
    db_path = "./ollama_simulation.db"
    os.environ["OASIS_DB_PATH"] = os.path.abspath(db_path)
    
    # 古いデータがあったら消す
    if os.path.exists(db_path):
        os.remove(db_path)

    # 環境スタート！
    env = oasis.make(
        agent_graph=agent_graph,
        platform=oasis.DefaultPlatformType.REDDIT,
        database_path=db_path,
    )
    await env.reset()
    
    print("🤖: Aliceに最初の投稿をさせます！")

    # Alice (Agent 0) に強制的に投稿させる「手動アクション」
    alice_agent = env.agent_graph.get_agent(0)
    
    starter_action = {
        alice_agent: [
            ManualAction(
                action_type=ActionType.CREATE_POST,
                action_args={
                    "content": "みんな、はじめまして！OASISの居心地はどう？ #自己紹介"
                }
            )
        ]
    }
    # まずこのアクションを実行して、世界に投稿を作る！
    await env.step(starter_action)

    print("🤖: 3人で会話スタート！")

    # 3. 全員に行動させてみる
    actions = {
        agent: LLMAction()
        for _, agent in env.agent_graph.get_agents()
    }
    
    await env.step(actions)
    await env.close()

if __name__ == "__main__":
    asyncio.run(main())