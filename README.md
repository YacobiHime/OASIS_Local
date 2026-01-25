# OASIS Local Simulation with Ollama (Twitter/X)

このプロジェクトは、マルチエージェント社会シミュレーションフレームワーク「OASIS」を、ローカルLLM環境（Ollama）で動作させるためのものです。
外部のAPIを使用せず、ローカルPC上で自律的なAIエージェントによるSNS（Twitter/X）のシミュレーションを行います。

## 環境構成

* **OS**: Windows (PowerShell) 推奨
* **Python**: 3.10
* **Package Manager**: `uv`
* **LLM Backend**: Ollama
* **Model**: `qwen3:4b-instruct-2507-q8_0` (デフォルト設定)
* ※ `sumika.py` と `check_db.py` でこのモデル名が指定されています。環境に合わせてコード内のモデル名を変更しても動作します。



## 事前準備

### 1. Ollamaのインストールとモデルの準備

Ollamaがインストールされ、起動している必要があります。
PowerShellで以下のコマンドを実行し、モデルをダウンロードします（またはコード内のモデル名を既存のモデルに変更してください）。

```powershell
ollama pull qwen3:4b-instruct-2507-q8_0

```

### 2. Python環境のセットアップ (uv使用)

```powershell
# 仮想環境の作成
uv venv .venv --python 3.10

# 仮想環境の有効化
.venv\Scripts\activate

# 依存関係のインストール
uv pip install -e .
uv pip install "camel-ai[all]"

```

## ファイル構成

* **実行スクリプト**
* `sumika.py`: **Twitter (X) シミュレーション用**のメインスクリプト。
* JSONプロファイルからエージェントを生成し、自律行動（投稿・リプライ・いいね・拡散など）を行います。
* 引数でプロファイルファイルを指定可能です。


* `run_llama_twitter.py`: 旧バージョンのシミュレーションスクリプト（Llama 3.2使用）。


* **ツール**
* `check_db.py`: シミュレーション結果（SQLiteデータベース）の中身を確認・保存するスクリプト。
* タイムラインをスレッド形式で表示します。
* LLMを使用して「何が起きたか」の要約レポートを自動生成します。
* 実行結果を `result_data/` フォルダに自動保存します。




* **データ・設定**
* `profiles/`: エージェントのプロファイルJSONを格納するフォルダ（例: `test.json`）。
* `ollama_twitter.db`: シミュレーション結果が保存されるデータベース。
* `result_data/`: `check_db.py` で出力されたログファイル保存先。



## 実行方法

### 1. 文字コードの設定（重要）

Twitterシミュレーションでは絵文字を使用するため、実行前に必ず以下のコマンドでUTF-8モードを有効にしてください。

```powershell
$env:PYTHONUTF8 = "1"

```

### 2. シミュレーションの実行 (`sumika.py`)

以下のコマンドでシミュレーションを開始します。

```powershell
# デフォルト設定（profiles/test.json を使用）
python sumika.py

# プロファイルファイルを指定して実行する場合
python sumika.py --profiles profiles/chaos.json

```

実行すると、エージェントたちが初期投稿に対して反応したり、自身の興味に基づいて新しい投稿を行ったりします。

### 3. 結果の確認と保存 (`check_db.py`)

シミュレーション終了後、以下のコマンドでデータベースの中身を確認できます。

```powershell
python check_db.py

```

* **機能**:
* タイムラインの表示（リプライや引用リポストもツリー状に表示）
* エージェントの行動ログ表示
* **AIによる状況要約**（「誰と誰が仲が良いか」「どんな話題が出たか」などをLLMが分析してコメントします）


* `result_data/` フォルダ内に「日時付きのログファイル（例: `2026-01-25_12-00-00.txt`）」が自動保存されます。

## Git管理について

以下のファイル・フォルダは `.gitignore` によりGitの管理対象から除外されています。

* `result_data/` (実験ログ)
* `*.db` (データベースファイル)
* `*.log` (ログファイル)
* `.venv/` (仮想環境)

## 権利 / 出典

* OASIS: [https://github.com/camel-ai/oasis](https://github.com/camel-ai/oasis)
* CAMEL-AI: [https://www.camel-ai.org/](https://www.camel-ai.org/)