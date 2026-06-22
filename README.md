# OASIS Local Simulation with Ollama (Twitter/X)

このプロジェクトは、マルチエージェント社会シミュレーションシステム「OASIS」を、ローカルLLM環境（Ollama）で動作させるためのものです。
外部のAPIを使用せず、ローカルPC上で自律的なAIエージェントによるSNS（Twitter/X）のシミュレーションを行います。

> **補足**: `docs/` 以下は上流 OASIS（[camel-ai/oasis](https://github.com/camel-ai/oasis)）ライブラリの汎用APIリファレンスです。本リポジトリ（OASIS_Local）の実装については、この README を参照してください。

## 環境構成

* **OS**: Windows (PowerShell) / Linux / macOS
* **Python**: 3.10 または 3.11
* **パッケージ管理**: pip (Python標準)
* **LLMバックエンド**: Ollama
* **モデル**: `config.json` で指定（デフォルト: `joe-speedboat/Gemma-4-Uncensored-HauhauCS-Aggressive:e4b`）
* ※ 設定は `config.json` で一元管理されています。環境に合わせて変更してください。

## 設定ファイルの準備

`config.json` は IP アドレス等のローカル情報を含むため Git 管理対象外です。
初回セットアップ時にテンプレートからコピーして作成してください。

```bash
cp config.example.json config.json
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
source .venv/bin/activate #linux
.venv\Scripts\activate # powershell

# 必須パッケージの導入
pip install camel-oasis
```

**※重要**: `camel-ai[all]` などの余計なパッケージを導入するとエラーの原因となります。必ず `camel-oasis` のみを導入してください。

（オプション）実験の追跡を行う場合は、以下も導入してください：

```powershell
pip install wandb
```

## ファイル構成

* **実行プログラム**
* `sim.py`: **Twitter (X) シミュレーション用**の主実行ファイル。
* 設定ファイル（JSON）からエージェントを生成し、自律行動（投稿・返信・いいね・拡散など）を行います。
* `--profiles` でプロファイルフォルダを、`--turns` でターン数を指定可能です。

* **ツール**
* `check.py`: シミュレーション結果（データベース）の中身を確認・保存するプログラム。
* タイムラインを階層状に表示します。
* LLMを使用して「何が起きたか」の要約報告書を自動生成します。
* 実行結果を `result_data/` フォルダに自動保存します。
* **差分更新機能**: 2回目以降の実行では、新しいデータのみが追加されます（全件コピーではなく）。

* **Blueskyデータ収集・ペルソナ生成ツール**（実データを使ったシミュレーション用）
* `collect_bluesky.py`: BlueskyのJetstreamから日本語ユーザーの投稿・プロフィールを収集し、`raw_users.json` に保存します。
* `make_gemini_prompt`: `raw_users.json` を読み込み、GeminiチャットにコピペするだけでOASIS用ペルソナ・seed投稿を生成できるプロンプトを `gemini_prompt.txt` に出力します。
* `generate_profiles.py`: Claude/Gemini API を使って `raw_users.json` からペルソナ・seed投稿を自動生成します（APIキーが必要）。

* **データ・設定**
* `config.json`: **シミュレーションの設定ファイル**（Ollama URL、モデル名、DBパス、推薦システム、イベント駆動設定などを指定）。Git 管理対象外。
* `profiles/`: エージェントのペルソナ情報を格納するフォルダ。本番用は `sim.json`（20人の架空ペルソナ）。フォルダ内の全 `.json` が読み込まれます。
* `seeds/`: シミュレーション開始時の初期投稿を格納するフォルダ。本番用は `seed_sim.json`。フォルダ内の全 `.json` が読み込まれます。
* `raw_users.json`: `collect_bluesky.py` で収集したBlueskyユーザーの生データ。Git 管理対象外。
* `gemini_prompt.txt`: `make_gemini_prompt` で生成したGeminiへの入力プロンプト。Git 管理対象外。
* `ollama_twitter.db`: シミュレーション結果が保存されるデータベース（`config.json` の `db_path`）。
* `sumika_tracker.db`: シミュレーションの追跡データ（ターン統計、行動ログ）（`config.json` の `tracker_db_path`）。
* `result_data/`: `check.py` で出力された記録ファイルの保存先。

## ペルソナ・seed の構成

### ペルソナ（`profiles/*.json`）

`profiles/` フォルダ内の **すべての `.json`** を読み込んでマージします（複数ファイル可）。各ペルソナのスキーマ:

| フィールド | 必須 | 説明 |
|---|:---:|---|
| `id` | ✓ | ペルソナの識別子（整数・連番推奨）。`initial_follows` や seed の `author_id` がこの id を参照します |
| `name` | ✓ | 表示名 |
| `bio` | ✓ | 性格・立場・行動指針。システムプロンプトに組み込まれ、発言内容を決定づけます |
| `tone_examples` | ✓ | 口調・セリフ例（改行区切りで複数）。発言の文体を固定します |
| `initial_follows` | — | 初期フォロー先の `id` 配列。対立相手を含めると議論が盛り上がります |
| `active_threshold` | — | 後述のタイムエンジン（24要素）。省略時は毎ターン必ず行動します |
| `other_info` | — | 任意の補足情報 |

> **ヒント**: `bio` に「同調・過剰肯定・励ましは禁止」のような行動制約を書き、`tone_examples` に個性的な口調例を並べると、キャラクターが立ち自然な発言になりやすくなります。

### seed 初期投稿（`seeds/*.json`）

`seeds/` フォルダ内の **すべての `.json`** を読み込んでマージします。各投稿のスキーマ:

| フィールド | 必須 | 説明 |
|---|:---:|---|
| `content` | ✓ | 投稿本文 |
| `author_id` | ✓ | 投稿者のペルソナ `id`（**存在しない id はエラーになります**） |
| `num_likes` | — | いいね数（省略時 0） |
| `num_reposts` | — | リポスト数（省略時 0） |
| `posted_at` | — | 投稿日時（例: `2026-06-22T10:00:00`） |

### タイムエンジン（時間帯別アクティブ判定）

ペルソナの `active_threshold` は **24要素（0時〜23時）の行動確率（0.0〜1.0）配列** です。
シミュレーションは全体で1日（24時間）を均等に進み、各ターンの現在時刻 `current_hour` に対応する確率で、各エージェントがそのターン行動するかを抽選します。

* 深夜を低く（0.01〜0.05）、昼〜夕方を高く（0.4〜0.8）設定すると、現実的な活動リズムを再現できます。
* 朝型・夜型など、ペルソナごとにピーク時間をずらすと生活リズムに差が出ます。
* 省略時は `[1.0] * 24`（毎ターン必ず行動）になります。

## 設定項目（config.json）

`config.json` の主要項目:

| 項目 | 説明 |
|---|---|
| `ollama_url` | Ollama のエンドポイント（環境変数 `OLLAMA_URL` が優先） |
| `ollama_model_sim` | シミュレーション本体で使うモデル |
| `ollama_model_check` | `check.py` の要約報告などで使うモデル |
| `llm_concurrency` | LLM 呼び出しの並列数（`0` で無制限） |
| `db_path` | 投稿・コメント等を保存するDB |
| `tracker_db_path` | ターン統計・行動ログを保存する追跡DB |
| `recsys_type` | 推薦システム（`"twitter"` or `"twhin-bert"`） |
| `num_steps` | 既定のターン数（実行時の `--turns` が優先されます） |
| `event_driven` | イベント駆動ニュース注入の設定（下記） |

> **注意**: `config.json` に `profile_path` / `seed_path` という項目がありますが、`sim.py` では**未使用**です。実際の読込先は `--profiles` 引数（デフォルト `profiles/`）と `seeds/` フォルダです。

### イベント駆動ニュース注入（event_driven）

`config.json` の `event_driven` ブロックで、SearXNG からニュースを取得し、指定エージェント経由でタイムラインに定期的に注入できます。

| 項目 | 説明 |
|---|---|
| `enabled` | イベント駆動の有効/無効 |
| `baseline_wakeup_rate` | ベースラインのウェイクアップ率 |
| `inject_interval_steps` | ニュース注入の間隔（ターン数） |
| `topics` | 取得するニュース話題のリスト |
| `num_results_per_topic` | 話題あたりの取得件数 |
| `searxng_url` | SearXNG のエンドポイント |
| `news_bot_agent_id` | ニュースを投稿するエージェントの `id` |
| `categories` | SearXNG の検索カテゴリ |

## 実行方法

### 1. 文字コードの設定（重要）

絵文字を正しく扱うため、実行前に必ず以下のコマンドでUTF-8モードを有効にしてください。

```powershell
$env:PYTHONUTF8 = "1"
```

### 2. シミュレーションの実行 (`sim.py`)

以下のコマンドでシミュレーションを開始します。

```powershell
# 標準設定（profiles/ と seeds/ を読み込み、5ターン実行）
python sim.py

# ターン数を指定
python sim.py --turns 50

# プロファイルフォルダを明示的に指定
python sim.py --profiles profiles --turns 50

# ssh接続で仮想マシンを使う場合
nohup python sim.py --turns 15 > oasis.log 2>&1 &

# W&Bによる実験追跡を無効化する場合
python sim.py --turns 50 --no-wandb

# 既存のDBを引き継いで再開する場合（resumeモード・seed注入をスキップ）
python sim.py --turns 10 --resume
```

**主な機能:**
- **タイムアウト保護**: LLM応答が遅い場合、5分でタイムアウトして次の処理に進みます
- **メモリ圧縮**: エージェントの記憶が一定量を超えると自動的に要約・圧縮されます（並列処理で高速化）
- **タイムエンジン**: ペルソナの `active_threshold` に基づき、時間帯別に行動有無を抽選します
- **イベント駆動**: `event_driven` 設定でニュースを定期的に注入します
- **Ctrl+C対応**: 中断時もDB接続が正しくクローズされます
- **差分更新**: `check.py` 実行時にDBがマージされ、既存データが引き継がれます

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

### 3. ペルソナ・seed投稿を生成する

生成方法は2通りあります。

**A. Geminiチャットにコピペ（APIキー不要）**

```powershell
python make_gemini_prompt --input raw_users.json --limit 30
```

`gemini_prompt.txt` が生成され、クリップボードにも自動コピーされます。
このファイルの内容をそのまま [Gemini](https://gemini.google.com/) のチャットに貼り付けてください。

Geminiから返ってきた出力を以下のように保存します:

* **【出力1】** → `profiles/bluesky_profiles.json`
* **【出力2】** → `seeds/bluesky_seeds.json`

**B. APIで自動生成（Claude/Gemini の APIキーが必要）**

```powershell
export ANTHROPIC_API_KEY=...   # または export GEMINI_API_KEY=...
python generate_profiles.py --input raw_users.json --output profiles/bluesky_profiles.json --seeds seeds/bluesky_seeds.json --api claude --limit 30
```

`seeds/` フォルダが存在しない場合は作成してください:

```powershell
mkdir seeds
```

### 4. Blueskyデータでシミュレーションを実行する

`sim.py` は `profiles/` と `seeds/` フォルダ内のすべてのJSONファイルを自動的に読み込みます。

```powershell
# profilesフォルダとseedsフォルダにデータを配置後
python sim.py --turns 50
```

**配置例:**
```
profiles/
  └── bluesky_profiles.json  ← エージェント属性
seeds/
  └── bluesky_seeds.json      ← 初期投稿
```

> **注意**: フォルダ内の `.json` はすべて読み込まれるため、複数のデータセットを混在させないようにしてください（不要なファイルは `.bak` 等にリネームすると読み込まれません）。

---

## バージョン管理について

以下のファイル・フォルダは `.gitignore` により管理対象から除外されています。

* `config.json`（ローカルの IP アドレス等を含む）
* `raw_users.json` / `gemini_prompt.txt`（生成物）
* `result_data/`（実験記録）
* `*.db` / `*.sqlite3`（データベースファイル）
* `*.log` / `log/`（記録ファイル）
* `.venv/`（仮想環境）
* `wandb/`（実験追跡）
* `*.bak` / `*.backup`（バックアップファイル）

`profiles/` と `seeds/` は Git 管理対象です（`sim.json` / `seed_sim.json` 等をバージョン管理できます）。

## 権利 / 出典

* OASIS: [https://github.com/camel-ai/oasis](https://github.com/camel-ai/oasis)
* CAMEL-AI: [https://www.camel-ai.org/](https://www.camel-ai.org/)
