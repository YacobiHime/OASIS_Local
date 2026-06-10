"""
sumika_event.py
----------------
イベント・情報ドリブンなOASISシミュレーションのエントリポイント。

元の sumika.py と同じ設定ファイル (config.json) を読み込むが、
以下が追加される:
  - EventBus によるイベント伝播
  - SearXNG からの外部情報自動注入
  - 通知ベースのエージェント選択的起動 (全員ターン制 → 必要な人だけ起動)

config.json 追加フィールド:
    "event_driven": {
        "enabled": true,
        "baseline_wakeup_rate": 0.1,
        "inject_interval_steps": 5,
        "topics": ["AI倫理", "SNS誤情報", "生成AI規制"],
        "num_results_per_topic": 3,
        "searxng_url": "http://192.168.15.146:8080",
        "news_bot_agent_id": 0
    }
"""

import argparse
import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime

import wandb

from camel.models import ModelFactory, ModelManager
from camel.types import ModelPlatformType

import oasis
from oasis import (
    ActionType, LLMAction, ManualAction,
    AgentGraph, SocialAgent, UserInfo,
)
from oasis.clock.clock import Clock

# ─── イベントドリブン拡張 ───
from oasis.events.event_bus import EventBus
from oasis.social_platform.platform_events import EventDrivenPlatform
from oasis.environment.env_event_driven import EventDrivenEnv
from oasis.information.injector import InformationInjector
from oasis.social_agent.agent_environment_event import EventAwareSocialEnvironment
from oasis.social_agent.agent_action import SocialAction

# ─────────────────────────────────────────
# ロガー設定
# ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sumika_event")

# ─────────────────────────────────────────
# 設定ファイル読み込み
# ─────────────────────────────────────────
with open("config.json", "r", encoding="utf-8") as _f:
    CONFIG = json.load(_f)

if os.environ.get("OLLAMA_URL"):
    CONFIG["ollama_url"] = os.environ["OLLAMA_URL"]

# イベントドリブン設定 (デフォルト付き)
EV_CFG = CONFIG.get("event_driven", {})
EV_ENABLED          = EV_CFG.get("enabled", True)
BASELINE_RATE       = float(EV_CFG.get("baseline_wakeup_rate", 0.1))
INJECT_INTERVAL     = int(EV_CFG.get("inject_interval_steps", 5))
TOPICS              = EV_CFG.get("topics", ["AI倫理", "SNS誤情報", "生成AI規制"])
NUM_RESULTS         = int(EV_CFG.get("num_results_per_topic", 3))
SEARXNG_URL         = EV_CFG.get("searxng_url", "http://192.168.15.146:8080")
NEWS_BOT_AGENT_ID   = int(EV_CFG.get("news_bot_agent_id", 0))
NUM_STEPS           = int(CONFIG.get("num_steps", 20))
DB_PATH             = CONFIG.get("db_path", "simulation_event.db")
SEED_PATH           = CONFIG.get("seed_path", "seeds/seed_test.json")
PROFILE_PATH        = CONFIG.get("profile_path", "profiles/test.json")


# ─────────────────────────────────────────
# モデル構築 (sumika.py と同じロジック)
# ─────────────────────────────────────────

def build_model():
    ollama_url = CONFIG.get("ollama_url", "http://localhost:11434/v1")
    model_type = CONFIG.get("ollama_model_sim", "llama3")
    return ModelFactory.create(
        model_platform=ModelPlatformType.OLLAMA,
        model_type=model_type,
        url=ollama_url,
        model_config_dict={"temperature": 0.7},
    )


# ─────────────────────────────────────────
# シードポスト投入ヘルパ
# ─────────────────────────────────────────

def load_seeds(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def inject_seeds(platform: EventDrivenPlatform, seeds: list) -> None:
    for seed in seeds:
        author_id = seed.get("author_id", NEWS_BOT_AGENT_ID)
        content = seed.get("content", "")
        if content:
            await platform.create_post(author_id, content)
            logger.info("Seed post injected by agent %d", author_id)


# ─────────────────────────────────────────
# エージェントに EventAwareSocialEnvironment を設定
# ─────────────────────────────────────────

def patch_agents_with_event_env(
    agent_graph: AgentGraph, event_bus: EventBus
) -> None:
    """
    全エージェントの env を EventAwareSocialEnvironment に差し替え、
    EventBus の通知キューを紐付ける。
    """
    for agent_id, agent in agent_graph.agent_mappings.items():
        queue = event_bus.get_agent_queue(agent_id)
        # SocialAction は既存のチャネルを再利用
        agent.env = EventAwareSocialEnvironment(
            action=SocialAction(agent_id, agent.channel),
            notification_queue=queue,
        )
    logger.info("Patched %d agents with EventAwareSocialEnvironment",
                len(agent_graph.agent_mappings))


# ─────────────────────────────────────────
# メインシミュレーション
# ─────────────────────────────────────────

async def run_simulation(num_steps: int):
    logger.info("=== OASIS Event-Driven Simulation START ===")
    logger.info("DB: %s | Steps: %d | SearXNG: %s", DB_PATH, num_steps, SEARXNG_URL)

    # --- 既存DBの削除 (二重起動防止) ---
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        logger.info("Removed existing DB: %s", DB_PATH)

    # --- W&B 初期化 ---
    run = wandb.init(
        project=CONFIG.get("wandb_project", "oasis-event-driven"),
        config={
            **CONFIG,
            "event_driven": EV_CFG,
        },
        mode=CONFIG.get("wandb_mode", "online"),
    )

    # --- EventBus 作成 ---
    event_bus = EventBus()

    # --- Platform 作成 ---
    from oasis.social_platform.channel import Channel
    channel = Channel()
    platform = EventDrivenPlatform(
        db_path=DB_PATH,
        channel=channel,
        event_bus=event_bus,
        recsys_type=CONFIG.get("recsys_type", "twitter"),
        refresh_rec_post_count=int(CONFIG.get("refresh_rec_post_count", 2)),
        max_rec_post_len=int(CONFIG.get("max_rec_post_len", 2)),
        following_post_count=int(CONFIG.get("following_post_count", 3)),
        sandbox_clock=Clock(60),
    )

    # --- AgentGraph 作成 ---
    with open(PROFILE_PATH, encoding="utf-8") as f:
        profiles = json.load(f)

    model = build_model()
    agent_graph = AgentGraph()
    for prof in profiles:
        user_info = UserInfo(
            user_name=prof.get("name", "user").lower(),
            name=prof.get("name", "User"),
            description=prof.get("bio", ""),
            profile={"other_info": prof.get("other_info", {})},
            recsys_type="twitter",
        )
        agent = SocialAgent(
            agent_id=int(prof["id"]),
            user_info=user_info,
            channel=channel,
            model=model,
            available_actions=ActionType.get_default_twitter_actions(),
        )
        agent_graph.add_agent(agent)

    # --- InformationInjector 作成 ---
    injector = InformationInjector(
        event_bus=event_bus,
        searxng_url=SEARXNG_URL,
        topics=TOPICS,
        inject_interval_steps=INJECT_INTERVAL,
        num_results_per_topic=NUM_RESULTS,
        platform=platform,
        news_bot_agent_id=NEWS_BOT_AGENT_ID,
        categories=EV_CFG.get("categories", "general"),
    )

    # --- EventDrivenEnv 作成 ---
    env = EventDrivenEnv(
        agent_graph=agent_graph,
        platform=platform,
        event_bus=event_bus,
        baseline_wakeup_rate=BASELINE_RATE,
        information_injector=injector,
    )

    # --- 環境リセット (プラットフォーム起動 + エージェント signup) ---
    await env.reset()

    # --- エージェントに通知環境をパッチ ---
    patch_agents_with_event_env(agent_graph, event_bus)

    # --- シードポスト投入 ---
    seeds = load_seeds(SEED_PATH)
    if seeds:
        await inject_seeds(platform, seeds)

    # ─────────────────────────────────────
    # シミュレーションループ
    # ─────────────────────────────────────
    for step in range(1, num_steps + 1):
        t_start = datetime.now()
        logger.info("── Step %d / %d ──", step, num_steps)

        await env.step_event_driven()

        elapsed = (datetime.now() - t_start).total_seconds()
        notif_counts = event_bus.get_all_queue_sizes()
        woken = len([c for c in notif_counts.values() if c > 0])

        wandb.log({
            "step": step,
            "elapsed_sec": elapsed,
            "agents_with_notifications": woken,
        })
        logger.info(
            "Step %d done in %.1fs | %d agents had notifications",
            step, elapsed, woken,
        )

    # ─────────────────────────────────────
    # クローズ
    # ─────────────────────────────────────
    await injector.close()
    await env.close()
    wandb.finish()
    logger.info("=== OASIS Event-Driven Simulation END ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OASIS Event-Driven Simulation")
    parser.add_argument("--turns", type=int, default=None,
                        help="Number of simulation steps (overrides config)")
    args = parser.parse_args()

    steps = args.turns if args.turns is not None else NUM_STEPS
    asyncio.run(run_simulation(steps))