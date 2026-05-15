import asyncio
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.toolkits import FunctionTool

# ---------------------------------------------------------
# 1. テスト用のダミー関数（ツール）を定義
# ---------------------------------------------------------
# 実際のシミュレーション環境（OASIS）を動かさなくてもテストできるように、
# LLMが呼び出すためのダミーの関数を用意しておきます。

def create_comment(post_id: int, content: str) -> str:
    """
    対象の投稿にコメント（リプライ）します。
    Args:
        post_id (int): コメント対象の投稿ID
        content (str): コメントのテキスト（日本語）
    """
    return f"Success: post_id={post_id} に '{content}' とコメントしました。"

def create_post(content: str) -> str:
    """
    新しく投稿を作成します。
    Args:
        content (str): 投稿のテキスト（日本語）
    """
    return f"Success: '{content}' と投稿しました。"

async def main():
    # ---------------------------------------------------------
    # 2. モデルの設定 (sumika.py と同じ vLLM を指定)
    # ---------------------------------------------------------
    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type="gemma4:e4b",                  # ← ダウンロードしたGemmaのモデル名に合わせます
        url="http://192.168.15.150:11434/v1",     # Ollamaのポート番号（11434）
        api_key="ollama"                          # エラー回避用のダミーキー
    )

    # ---------------------------------------------------------
    # 3. LLMへの入力テキスト（森本の設定）を作成
    # ---------------------------------------------------------
    system_msg = BaseMessage.make_assistant_message(
        role_name="system",
        content="""# 役割
あなたはSNS「Twitter(X)」のユーザー「森本」です。
以下の設定になりきって行動してください。
--------------------------------------------------
心優しきシステムエンジニア。日本語で話します。
--------------------------------------------------

# 口調・セリフ例
・それは大変でしたね、大丈夫ですか？
・技術的には可能だと思いますよ。
・穏やかにいきましょう。

# あなたの任務
タイムラインに流れてきた【他人の投稿】に対し、ツール `create_comment` を使用してリプライを送ってください。

# 行動ルール (Action Rules)
1. **話題を拾う**: 相手の投稿にある「具体的な単語（家電、スポーツなど）」を含めて返信してください。
2. **自分語り禁止**: 相手の話を聞かずに、自分の趣味の話を始めないでください。
3. **自己リプ禁止**: 投稿者が自分自身（森本）の場合、絶対にコメントしないでください。

# 応答方法
必ず以下のJSON形式のみを出力してください。それ以外のテキスト（挨拶や説明など）は一切不要です。
{"action": "create_comment", "args": {"post_id": 1, "content": "ここにコメント内容"}}"""
    )

    # LLMを管理するエージェントを作成し、設定と関数を渡します
    tools = [FunctionTool(create_comment), FunctionTool(create_post)]
    agent = ChatAgent(
        system_message=system_msg,
        model=model,
        tools=tools
    )

    # ---------------------------------------------------------
    # 4. 状況の入力（タイムラインの様子）を作成
    # ---------------------------------------------------------
    # テストとして、システムエンジニアの森本さんが反応しやすそうな投稿を
    # タイムラインの状況として入力してみます。
    user_msg = BaseMessage.make_user_message(
        role_name="User",
        content="""プラットフォームの状況を観察し、ソーシャルメディア上のアクションを行ってください。「いいね」だけでなく、投稿やコメントなど、多様なアクションを積極的に行ってください。【重要】投稿内容やコメントは、必ず「日本語」で出力してください。英語は使用禁止です。(Output must be in Japanese only.)
現在の環境情報: 
[post_id: 1] 田所: サーバーの調子が悪くて、昨日からずっと謎のエラー吐いてるんだけど...誰か助けて... (likes: 0, dislikes: 0)"""
    )

    print("🤖: LLMに思考させています...")
    
    # ---------------------------------------------------------
    # 5. 実行と結果の表示
    # ---------------------------------------------------------
    response = await agent.astep(user_msg)
    
    print("\n=== LLMの出力結果 ===")
    # LLMが意図通りに関数（ツール）を呼び出したかどうかを確認します
    if response.info.get('tool_calls'):
        for tool_call in response.info['tool_calls']:
            print(f"呼び出した関数: {tool_call.tool_name}")
            print(f"作成された内容: {tool_call.args}")
    else:
        print("【失敗】関数が呼び出されず、テキストだけが返ってきました:")
        print(response.msg.content)

if __name__ == "__main__":
    asyncio.run(main())