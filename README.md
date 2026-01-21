# OASIS Local Simulation with Ollama (Twitter/X)

このプロジェクトは、マルチエージェント社会シミュレーションフレームワーク「OASIS」を、ローカルLLM環境（Ollama）で動作させるためのものです。
外部のAPIを使用せず、ローカルPC上で自律的なAIエージェントによるSNS（Twitter/X や Reddit）のシミュレーションを行います。

## 環境構成

* **OS**: Windows (PowerShell)
* **Python**: 3.10
* **Package Manager**: `uv`
* **LLM Backend**: Ollama
* **Model**: Llama 3.2 (3B)

## 事前準備

### 1. Ollamaのインストールとモデルの準備
Ollamaがインストールされ、起動している必要があります。
PowerShellで以下のコマンドを実行し、モデルをダウンロードします。

```powershell
ollama pull llama3.2

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
* `run_llama_twitter.py`: **Twitter (X) シミュレーション用**のメインスクリプト。
* 日本語エージェントによる投稿・検索・リプライ等の自律行動を行います。
* 絵文字を含む投稿に対応しています。


* `run_gemma_reddit.py`: Redditシミュレーション用のスクリプト（旧バージョン）。


* **ツール**
* `check_db.py`: シミュレーション結果（SQLiteデータベース）の中身を確認・保存するスクリプト。
* 実行結果を `result_data/` フォルダにテキストファイルとして自動保存します。




* **データ・出力**
* `data/local_twitter_simulation.db`: シミュレーション結果が保存されるデータベース。
* `result_data/`: `check_db.py` で出力されたログファイルが保存されるフォルダ（Git管理対象外）。



## 実行方法

### 1. 文字コードの設定（重要）

Twitterシミュレーションでは絵文字を使用するため、実行前に必ず以下のコマンドでUTF-8モードを有効にしてください。

```powershell
$env:PYTHONUTF8 = "1"

```

### 2. シミュレーションの実行

以下のコマンドでシミュレーションを開始します。

```powershell
python run_llama_twitter.py

```

実行すると、エージェントたちが初期投稿に対して反応したり、自身の興味に基づいて新しい投稿を行ったりします。

### 3. 結果の確認と保存

シミュレーション終了後、以下のコマンドでデータベースの中身を確認できます。

```powershell
python check_db.py

```

* 画面に投稿内容とエージェントの行動ログが表示されます。
* 同時に、`result_data/` フォルダ内に「日時付きのログファイル（例: `2026-01-21_12-00-00.txt`）」が自動保存されます。

## Git管理について

以下のファイル・フォルダは `.gitignore` によりGitの管理対象から除外されています。

* `result_data/` (実験ログ)
* `*.db` (データベースファイル)
* `*.log` (ログファイル)

## 権利 / 出典
- OASIS: https://github.com/camel-ai/oasis
- CAMEL-AI: https://www.camel-ai.org/
