# OASIS Local Simulation with Ollama (Twitter/X)

このプロジェクトは、マルチエージェント社会シミュレーションシステム「OASIS」を、ローカルLLM環境（Ollama）で動作させるためのものです。
外部のAPIを使用せず、ローカルPC上で自律的なAIエージェントによるSNS（Twitter/X）のシミュレーションを行います。

## 環境構成

* **OS**: Windows (PowerShell) / Linux 推奨
* **Python**: 3.10 または 3.11
* **パッケージ管理**: pip (Python標準)
* **LLMバックエンド**: Ollama
* **モデル**: `config.json` で指定（デフォルト: `joe-speedboat/Gemma-4-Uncensored-HauhauCS-Aggressive:e4b`）
* ※ 設定は `config.json` で一元管理されています。環境に合わせて変更してください。

## 設定ファイルの準備

`config.json` は IP アドレス等のローカル情報を含むため Git 管理対象外です。
初回セットアップ時にテンプレートからコピーして作成してください。

```bash
# 通常の sumika.py を使う場合
cp config.example.json config.json

# イベント駆動版 sumika_event.py を使う場合
cp config.example.event.json config.json
```

デフォルトでは `http://localhost:11434/v1` が設定されています。
リモートサーバー等の Ollama を利用する場合は `config.json` の `ollama_url` を編集するか、
環境変数 `OLLAMA_URL` を設定してください（環境変数が優先されます）。

```bash
# Linux / macOS
export OLLAMA_URL="http://192.168.x.x:11434/v1"

# PowerShell
$env:OLLAMA_URL = "http://192.168.x.x:11434/v1"

# または .env ファイルを作成して記述（.env は .gitignore 済み）
echo 'OLLAMA_URL=http://192.168.x.x:11434/v1' > .env
```

## 事前準備

### 1. Ollamaの準備とモデルの取得

Ollamaが導入され、起動している必要があります。
`config.json` で指定したモデルを取得してください。

```powershell
# デフォルト設定の場合
ollama pull joe-speedboat/Gemma-4-Uncensored-HauhauCS-Aggressive:e4b

# または別のモデルを使用する場合、config.json を編集してください
```

### 2. Python環境の構築

Python 3.10 または 3.11 を使用し、以下の手順で環境を整えます。

```powershell
# 仮想環境の作成
python -m venv .venv

# 仮想環境の有効化
source .venv/bin/activate  # Linux
.venv\Scripts\activate     # PowerShell

# 必須パッケージの導入
pip install camel-oasis
```

**※重要**: `camel-ai[all]` などの余計なパッケージを導入するとエラーの原因となります。必ず `camel-oasis` のみを導入してください。

（オプション）実験の追跡を行う場合は、以下も導入してください：

```powershell
pip install wandb
```

### 3. イベント駆動版を使う場合の追加パッケージ

`sumika_event.py`（SearXNG連携）を使用する場合、以下のパッケージも導入してください：

```powershell
pip install aiohttp
```

また、SearXNG 検索サーバーがネットワーク上で利用可能である必要があります。

## ファイル構成

### 実行プログラム

* **`sumika.py`**: **Twitter (X) シミュレーション用**の主実行ファイル（標準版）。
  設定ファイル（JSON）からエージェントを生成し、全エージェントが毎ターン自律行動（投稿・返信・いいね・拡散など）を行います。
* **`sumika_event.py`**: **イベント駆動版**のシミュレーション実行ファイル。
  EventBus によるイベント伝播、SearXNG からの外部情報自動注入、通知ベースの選択的エージェント起動を行います。詳しくは [EVENT_DRIVEN_ARCHITECTURE.md](EVENT_DRIVEN_ARCHITECTURE.md) を参照。
* `run_llama_twitter.py`: 以前使用していたシミュレーション用プログラム（Llama 3.2使用）。

### ツール

* `check.py`: シミュレーション結果（データベース）の中身を確認・保存するプログラム。
  タイムラインを階層状に表示します。LLMを使用して「何が起きたか」の要約報告書を自動生成します。
  実行結果を `result_data/` フォルダに自動保存します。**差分更新機能**: 2回目以降の実行では、新しいデータのみが追加されます。
* `deploy.py`: デプロイ用スクリプト。

### Blueskyデータ収集ツール（実データを使ったシミュレーション用）

* `collect_bluesky.py`: BlueskyのJetstreamから日本語ユーザーの投稿・プロフィールを収集し、`raw_users.json` に保存します。
* `make_gemini_prompt.py`: `raw_users.json` を読み込み、GeminiチャットにコピペするだけでOASIS用ペルソナ・seed投稿を生成できるプロンプトを `gemini_prompt.txt` に出力します。
* `generate_profiles.py`: プロファイル生成ツール。

### データ・設定

* `config.json`: **シミュレーションの設定ファイル**（Ollama URL、モデル名、DBパスなどを指定）。Git管理対象外。
* `config.example.json`: 標準版（`sumika.py`）用の設定テンプレート。
* `config.example.event.json`: イベント駆動版（`sumika_event.py`）用の設定テンプレート。SearXNG URL、トピック一覧などを含む。
* `profiles/`: エージェントの属性情報を格納するフォルダ（例: `test.json`, `bluesky_profiles.json`）。
* `seeds/`: シミュレーション開始時の初期投稿を格納するフォルダ（例: `seed_posts.json`, `bluesky_seeds.json`）。
* `raw_users.json`: `collect_bluesky.py` で収集したBlueskyユーザーの生データ。
* `gemini_prompt.txt`: `make_gemini_prompt.py` で生成したGeminiへの入力プロンプト。
* `ollama_twitter.db`: シミュレーション結果が保存されるデータベース。
* `sumika_tracker.db`: シミュレーションの追跡データ（ターン統計、行動ログ）。
* `result_data/`: `check.py` で出力された記録ファイルの保存先。

### イベント駆動アーキテクチャモジュール (`oasis/`)

| パス | 役割 |
|------|------|
| `oasis/events/event_bus.py` | 非同期イベントバス（pub/sub + エージェント別通知キュー） |
| `oasis/events/event_types.py` | 全イベントの dataclass 定義（PostCreated, UserFollowed, ExternalInfo 等） |
| `oasis/social_platform/platform_events.py` | `EventDrivenPlatform` — Platform の全アクションをオーバーライドし、イベントを発行 |
| `oasis/environment/env_event_driven.py` | `EventDrivenEnv` — 通知ベースの選択的エージェント起動ロジック |
| `oasis/information/injector.py` | `InformationInjector` — SearXNG から定期的に外部情報を注入 |
| `oasis/information/searxng_client.py` | `SearXNGClient` — SearXNG JSON API の非同期クライアント |
| `oasis/social_agent/agent_environment_event.py` | `EventAwareSocialEnvironment` — 通知をエージェントのプロンプトに自動挿入 |

## 実行方法

### 1. 文字コードの設定（重要）

絵文字を正しく扱うため、実行前に必ず以下のコマンドでUTF-8モードを有効にしてください。

```powershell
# PowerShell
$env:PYTHONUTF8 = "1"
```

### 2. シミュレーションの実行

#### 標準版 (`sumika.py`)

```powershell
# 標準設定（5ターン実行）
python sumika.py

# ターン数を指定
python sumika.py --turns 50

# SSH接続で仮想マシンを使う場合
nohup python sumika.py --turns 15 > oasis.log 2>&1 &

# W&Bによる実験追跡を無効化する場合
python sumika.py --turns 50 --no-wandb

# 既存のDBを引き継いで再開する場合（resumeモード）
python sumika.py --turns 10 --resume
```

**主な機能:**
- **タイムアウト保護**: LLM応答が遅い場合、5分でタイムアウトして次の処理に進みます
- **メモリ圧縮**: エージェントの記憶が一定量を超えると自動的に要約・圧縮されます（並列処理で高速化）
- **Ctrl+C対応**: 中断時もDB接続が正しくクローズされます
- **差分更新**: `check.py` 実行時にDBがマージされ、既存データが引き継がれます

#### イベント駆動版 (`sumika_event.py`)

```powershell
# 設定テンプレートをコピーして config.json を作成
cp config.example.event.json config.json

# config.json の searxng_url を環境に合わせて編集
# 実行
python sumika_event.py --turns 20
```

**標準版との違い:**
- **イベント駆動**: 全エージェントが毎ターン行動するのではなく、通知が届いたエージェント + ランダムに選ばれた少数のエージェントのみが起動
- **外部情報注入**: SearXNG 経由で定期的にニュース記事を取得し、シミュレーション内に「ニュースボット」として投稿
- **通知システム**: 投稿・いいね・フォロー等のイベントが関連エージェントにリアルタイム通知される
- **W&B連携**: ステップごとの実行時間・通知ありエージェント数を自動ログ

**`config.json` のイベント駆動設定 (`event_driven` セクション):**

| パラメータ | 説明 | デフォルト |
|---|---|---|
| `enabled` | イベント駆動モードを有効にする | `true` |
| `baseline_wakeup_rate` | 通知なしエージェントの毎ステップ起動率 | `0.1` |
| `inject_interval_steps` | SearXNG情報注入の間隔（ステップ数） | `5` |
| `topics` | SearXNGで検索するトピック一覧 | `["AI倫理", ...]` |
| `num_results_per_topic` | 1トピックあたりの取得件数 | `3` |
| `searxng_url` | SearXNGサーバーのURL | `"http://192.168.15.146:8080"` |
| `news_bot_agent_id` | ニュース投稿に使うエージェントID | `0` |
| `categories` | SearXNG検索カテゴリ | `"general"` |

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

`sumika.py` は `seeds/` フォルダ内のすべてのJSONファイルを自動的に読み込みます。

```powershell
# profilesフォルダとseedsフォルダにデータを配置後
python sumika.py --turns 50
```

**配置例:**
```
profiles/
  └── bluesky_profiles.json  ← エージェント属性
seeds/
  ├── bluesky_seeds.json      ← 初期投稿
  └── seed_comments.json      ← 初期コメント
```

---

## バージョン管理について

以下のファイル・フォルダは `.gitignore` により管理対象から除外されています。

* `config.json` (設定ファイル)
* `result_data/` (実験記録)
* `*.db` (データベースファイル)
* `*.log` (記録ファイル)
* `.venv/` (仮想環境)

## 権利 / 出典

* OASIS: [https://github.com/camel-ai/oasis](https://github.com/camel-ai/oasis)
* CAMEL-AI: [https://www.camel-ai.org/](https://www.camel-ai.org/)
