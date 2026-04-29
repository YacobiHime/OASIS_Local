# OASIS Local Simulation with Ollama (Twitter/X)

このプロジェクトは、マルチエージェント社会シミュレーションシステム「OASIS」を、ローカルLLM環境（Ollama）で動作させるためのものです。
外部のAPIを使用せず、ローカルPC上で自律的なAIエージェントによるSNS（Twitter/X）のシミュレーションを行います。

## 環境構成

* **OS**: Windows (PowerShell) 推奨
* **Python**: 3.10 または 3.11
* **パッケージ管理**: pip (Python標準)
* **LLMバックエンド**: Ollama
* **モデル**: `qwen3:4b-instruct-2507-q8_0` (標準設定)
* ※ `sumika.py` と `check_db.py` でこのモデル名が指定されています。環境に合わせてコード内のモデル名を変更しても動作します。

## 事前準備

### 1. Ollamaの準備とモデルの取得

Ollamaが導入され、起動している必要があります。
PowerShellで以下のコマンドを実行し、モデルを取得します（またはコード内のモデル名を既存のモデルに変更してください）。

```powershell
ollama pull qwen3:4b-instruct-2507-q8_0
```

### 2. Python環境の構築

Python 3.10 または 3.11 を使用し、以下の手順で環境を整えます。

```powershell
# 仮想環境の作成
python -m venv .venv

# 仮想環境の有効化
.venv\Scripts\activate

# 必須パッケージの導入
pip install camel-oasis
```

**※重要**: `camel-ai[all]` などの余計なパッケージを導入するとエラーの原因となります。必ず `camel-oasis` のみを導入してください。

## ファイル構成

* **実行プログラム**
* `sumika.py`: **Twitter (X) シミュレーション用**の主実行ファイル。
* 設定ファイル（JSON）からエージェントを生成し、自律行動（投稿・返信・いいね・拡散など）を行います。
* 引数で設定ファイルを指定可能です。

* `run_llama_twitter.py`: 以前のシミュレーション用プログラム（Llama 3.2使用）。

* **ツール**
* `check_db.py`: シミュレーション結果（データベース）の中身を確認・保存するプログラム。
* タイムラインを階層状に表示します。
* LLMを使用して「何が起きたか」の要約報告書を自動生成します。
* 実行結果を `result_data/` フォルダに自動保存します。

* **データ・設定**
* `profiles/`: エージェントの属性情報を格納するフォルダ（例: `test.json`）。
* `ollama_twitter.db`: シミュレーション結果が保存されるデータベース。
* `result_data/`: `check_db.py` で出力された記録ファイルの保存先。

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

# 設定ファイルを指定して実行する場合
python sumika.py --profiles profiles/test1.json
```

実行すると、エージェントたちが初期の投稿に対して反応したり、自身の関心に基づいて新しい投稿を行ったりします。

### 3. 結果の確認と保存 (`check_db.py`)

シミュレーション終了後、以下のコマンドでデータベースの中身を確認できます。

```powershell
python check_db.py
```

* **機能**:
* タイムラインの表示（返信や引用再投稿も階層状に表示）
* エージェントの行動記録の表示
* **AIによる状況要約**: 「誰と誰が仲が良いか」「どんな話題が出たか」などをLLMが分析して解説します。

* `result_data/` フォルダ内に「日時付きの記録ファイル（例: `2026-01-25_12-00-00.txt`）」が自動保存されます。

## バージョン管理について

以下のファイル・フォルダは `.gitignore` により管理対象から除外されています。

* `result_data/` (実験記録)
* `*.db` (データベースファイル)
* `*.log` (記録ファイル)
* `.venv/` (仮想環境)

## 権利 / 出典

* OASIS: [https://github.com/camel-ai/oasis](https://github.com/camel-ai/oasis)
* CAMEL-AI: [https://www.camel-ai.org/](https://www.camel-ai.org/)
