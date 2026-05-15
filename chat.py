import openai

def main():
    # OpenAI互換の接続設定
    client = openai.OpenAI(
        base_url="http://192.168.15.150:8000/v1",
        api_key="sk-dummy"
    )

    # 会話の履歴を保存する配列
    messages = [
        {"role": "system", "content": "あなたは親切で役立つ対話相手です。"}
    ]

    print("チャットを開始します。（「終了」と入力するか、Ctrl+Cで終わります）")
    print("-" * 50)

    while True:
        try:
            # 文字入力を受け付ける
            user_input = input("あなた: ")
            
            # 終了の確認
            if user_input.strip() == "終了":
                print("会話を終了します。")
                break
            
            # 空の入力は無視する
            if not user_input.strip():
                continue

            # 入力内容を履歴に追加
            messages.append({"role": "user", "content": user_input})

            # モデルに送信して返答を受け取る
            response = client.chat.completions.create(
                model="gemma-4",
                messages=messages,
                stream=True # 少しずつ文字を表示するための設定
            )

            print("Bot: ", end="")
            full_response = ""
            
            # 文字が生成されるたびに少しずつ画面に出力する
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    print(content, end="", flush=True)
                    full_response += content
            
            print("\n")

            # 返答を会話履歴に追加し、次回のやり取りに活かす
            messages.append({"role": "assistant", "content": full_response})

        except KeyboardInterrupt:
            print("\n会話を終了します。")
            break
        except Exception as e:
            print(f"\n問題が発生しました: {e}")
            break

if __name__ == "__main__":
    main()