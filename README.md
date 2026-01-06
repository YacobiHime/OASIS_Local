# OASIS Local Simulation with Ollama (Llama 3.2)

このプロジェクトは、マルチエージェント社会シミュレーションフレームワーク「OASIS」を、ローカルLLM環境（Ollama）で動作させるためのものです。
外部のAPIを使用せず、ローカルPC上で自律的なAIエージェントによるSNS（Reddit風）のシミュレーションを行います。

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
- `run_gemma_reddit.py`: シミュレーション実行用メインスクリプト。
  -Llama 3.2 モデルを使用するように設定済み。
  -動作軽量化のため、エージェント数を36人から5人に自動縮小する機能を含みます。
- `check_db.py`: 実行結果（SQLiteデータベース）の中身を確認するためのスクリプト。
- `data/local_reddit_gemma.db`: シミュレーション結果が保存されるデータベース（実行後に生成）。

## 実行方法
### 1. シミュレーションの実行
```powershell
# 文字コード設定 (UTF-8強制)
$env:PYTHONUTF8 = "1"

# シミュレーション開始
python run_gemma_reddit.py
```
実行すると、エージェント5人による投稿、検索、フォローなどの行動がシミュレーションされます。

### 2. 結果の確認
シミュレーション終了後、データベースに記録された行動ログを確認します。
```powershell
python check_db.py
```
## トラブルシューティング
- ValueError: ... does not support tools エラーが出る場合
  - スクリプト内のモデル指定が llama3.2 (または llama3.1) になっているか確認してください。Gemma 3 (Ollama版) は現在ツール機能に対応していません。
- Async step timed out エラーが出る場合
  - エージェント数が多すぎてPCの処理が追いついていません。run_gemma_reddit.py 内で生成される user_data_mini.json の人数（デフォルト5人）を減らしてみてください。
- UnicodeDecodeError が出る場合
  - 実行前に必ず $env:PYTHONUTF8 = "1" を実行してください。

## 権利 / 出典
- OASIS: https://github.com/camel-ai/oasis
- CAMEL-AI: https://www.camel-ai.org/
