# OASIS Local Simulation with Ollama (Twitter/X)

このプロジェクトは、マルチエージェント社会シミュレーションシステム「OASIS」を、ローカルLLM環境（Ollama）で動作させるためのものです。
外部のAPIを使用せず、ローカルPC上で自律的なAIエージェントによるSNS（Twitter/X）のシミュレーションを行います。

## 環境構成

* **OS**: Windows (PowerShell) 推奨
* **Python**: 3.10 または 3.11
* **パッケージ管理**: pip (Python標準)
* **LLMバックエンド**: Ollama
* **モデル**: `gemma4:e2b` (標準設定)
* ※ `sumika.py` と `check.py` でこのモデル名が指定されています。環境に合わせてコード内のモデル名を変更しても動作します。

## 事前準備

### 1. Ollamaの準備とモデルの取得

Ollamaが導入され、起動している必要があります。
PowerShellで以下のコマンドを実行し、モデルを取得します（またはコード内のモデル名を既存のモデルに変更してください）。

```powershell
ollama pull gemma4:e2b
```

### 2. Python環境の構築

Python 3.10 または 3.11 を使用し、以下の手順で環境を整えます。

```powershell
# 仮想環境の作成
python -m venv .venv

# 仮想環境の有効化
source .venv/bin/activate #linux
.venv\Scripts\activate # powershell

# 必須パッケージの導入
pip install camel-oasis
```

**※重要**: `camel-ai[all]` などの余計なパッケージを導入するとエラーの原因となります。必ず `camel-oasis` のみを導入してください。

## ファイル構成

* **実行プログラム**
* `sumika.py`: **Twitter (X) シミュレーション用**の主実行ファイル。
* 設定ファイル（JSON）からエージェントを生成し、自律行動（投稿・返信・いいね・拡散など）を行います。
* 引数で設定ファイルを指定可能です。

* `run_llama_twitter.py`: 以前使用していたシミュレーション用プログラム（Llama 3.2使用）。

* **ツール**
* `check.py`: シミュレーション結果（データベース）の中身を確認・保存するプログラム。
* タイムラインを階層状に表示します。
* LLMを使用して「何が起きたか」の要約報告書を自動生成します。
* 実行結果を `result_data/` フォルダに自動保存します。

* **Blueskyデータ収集ツール**（実データを使ったシミュレーション用）
* `collect_bluesky.py`: BlueskyのJetstreamから日本語ユーザーの投稿・プロフィールを収集し、`raw_users.json` に保存します。
* `make_gemini_prompt.py`: `raw_users.json` を読み込み、GeminiチャットにコピペするだけでOASIS用ペルソナ・seed投稿を生成できるプロンプトを `gemini_prompt.txt` に出力します。

* **データ・設定**
* `profiles/`: エージェントの属性情報を格納するフォルダ（例: `test1.json`, `bluesky_profiles.json`）。
* `seeds/`: シミュレーション開始時の初期投稿を格納するフォルダ（例: `seed_posts.json`, `bluesky_seeds.json`）。
* `raw_users.json`: `collect_bluesky.py` で収集したBlueskyユーザーの生データ。
* `gemini_prompt.txt`: `make_gemini_prompt.py` で生成したGeminiへの入力プロンプト。
* `ollama_twitter.db`: シミュレーション結果が保存されるデータベース。
* `result_data/`: `check.py` で出力された記録ファイルの保存先。

## 実行方法

### 1. 文字コードの設定（重要）

絵文字を正しく扱うため、実行前に必ず以下のコマンドでUTF-8モードを有効にしてください。

```powershell
$env:PYTHONUTF8 = "1"
```

### 2. シミュレーションの実行 (`sumika.py`)

以下のコマンドでシミュレーションを開始します。

```powershell
# 標準設定（profiles/test.json を使用）
python sumika.py
python sumika.py --turns 50

# ssh接続で仮想マシンを使う場合
nohup python sumika.py --turns 15 > oasis.log 2>&1 &
```

実行すると、エージェントたちが初期の投稿に対して反応したり、自身の関心に基づいて新しい投稿を行ったりします。

### 3. 結果の確認と保存 (`check.py`)

シミュレーション終了後、以下のコマンドでデータベースの中身を確認できます。

```powershell
python check.py
```

* **機能**:
* タイムラインの表示（返信や引用再投稿も階層状に表示）
* エージェントの行動記録の表示
* **AIによる状況要約**: 「誰と誰が仲が良いか」「どんな話題が出たか」などをLLMが分析して解説します。

* `result_data/` フォルダ内に「日時付きの記録ファイル（例: `2026-01-25_12-00-00.txt`）」が自動保存されます。

## Bluesky実データを使ったシミュレーション

手作りのペルソナの代わりに、Blueskyの実ユーザーデータからエージェントと初期投稿を自動生成できます。

### 1. 追加パッケージの導入

```powershell
pip install atproto websockets langdetect
```

### 2. Blueskyからユーザーデータを収集する

Blueskyへのアカウント登録・認証は**不要**です。公開データのみを使用します。

```powershell
python collect_bluesky.py --count 30 --posts 20 --output raw_users.json
```

Jetstreamから日本語投稿をリアルタイムにサンプリングし、30人分のプロフィールと投稿履歴を収集します。完了まで3〜5分程度かかります。

主なオプション:

| オプション | 説明 | デフォルト |
|---|---|---|
| `--count` | 収集するユーザー数 | 30 |
| `--posts` | 1ユーザーあたりの最大取得投稿数 | 20 |
| `--output` | 出力ファイルパス | `raw_users.json` |
| `--timeout` | Jetstream収集のタイムアウト秒数 | 180 |

### 3. Gemini用プロンプトを生成する

```powershell
python make_gemini_prompt.py --input raw_users.json --limit 30
```

`gemini_prompt.txt` が生成され、クリップボードにも自動コピーされます。
このファイルの内容をそのまま [Gemini](https://gemini.google.com/) のチャットに貼り付けてください。

Geminiから返ってきた出力を以下のように保存します:

* **【出力1】** → `profiles/bluesky_profiles.json`
* **【出力2】** → `seeds/bluesky_seeds.json`

`seeds/` フォルダが存在しない場合は作成してください:

```powershell
mkdir seeds
```

### 4. Blueskyデータでシミュレーションを実行する

`sumika.py` の seed 読み込みパスを `seeds/bluesky_seeds.json` に変更した上で実行します:

```powershell
python sumika.py --profiles profiles/bluesky_profiles.json
```

> **注意**: `sumika.py` 内の `seed_posts.json` の参照箇所を `bluesky_seeds.json` に書き換えてください。

---

## バージョン管理について

以下のファイル・フォルダは `.gitignore` により管理対象から除外されています。

* `result_data/` (実験記録)
* `*.db` (データベースファイル)
* `*.log` (記録ファイル)
* `.venv/` (仮想環境)

## 権利 / 出典

* OASIS: [https://github.com/camel-ai/oasis](https://github.com/camel-ai/oasis)
* CAMEL-AI: [https://www.camel-ai.org/](https://www.camel-ai.org/)