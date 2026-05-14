import requests
import json

# UbuntuサーバーのIPアドレスとポートを指定
url = "http://192.168.15.150:8000/v1/chat/completions"
headers = {"Content-Type": "application/json"}

# AIへのテストメッセージ
data = {
    "messages": [
        {"role": "user", "content": "こんにちは！ノートPCからの通信テストです。簡単に自己紹介をお願いします。"}
    ]
}

print("AIの思考と返答を待っています...")

# 通信の実行
try:
    response = requests.post(url, headers=headers, data=json.dumps(data))
    
    # 結果の表示
    if response.status_code == 200:
        result = response.json()
        print("\n🤖 AIの回答:")
        print(result["choices"][0]["message"]["content"])
    else:
        print(f"\n❌ エラーが発生しました: 状態コード {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"\n❌ 通信に失敗しました。サーバーが起動しているか確認してください。\n詳細: {e}")