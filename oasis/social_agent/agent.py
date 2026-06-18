# =========== Copyright 2023 @ CAMEL-AI.org. All Rights Reserved. ===========
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =========== Copyright 2023 @ CAMEL-AI.org. All Rights Reserved. ===========
from __future__ import annotations

import asyncio
import inspect
import logging
import re
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Union

from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import BaseModelBackend, ModelManager
from camel.prompts import TextPrompt
from camel.toolkits import FunctionTool
from camel.types import OpenAIBackendRole

from oasis.social_agent.agent_action import SocialAction, _camel_to_snake
from oasis.social_agent.agent_environment import SocialEnvironment
from oasis.social_platform import Channel
from oasis.social_platform.config import UserInfo
from oasis.social_platform.typing import ActionType

if TYPE_CHECKING:
    from oasis.social_agent import AgentGraph

if "sphinx" not in sys.modules:
    agent_log = logging.getLogger(name="social.agent")
    agent_log.setLevel("DEBUG")

    if not agent_log.handlers:
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_handler = logging.FileHandler(
            f"./log/social.agent-{str(now)}.log")
        file_handler.setLevel("DEBUG")
        file_handler.setFormatter(
            logging.Formatter(
                "%(levelname)s - %(asctime)s - %(name)s - %(message)s"))
        agent_log.addHandler(file_handler)

ALL_SOCIAL_ACTIONS = [action.value for action in ActionType]

# A1: LLMがツールを呼ばなかった（テキストのみ返した）場合の再試行回数。
# camel の astep はツール不呼び出しで即終了するため、perform_action_by_llm
# 側で再催促メッセージを送りリトライする。実時間との兼ね合いで2回まで。
MAX_ACTION_RETRY = 2


def _looks_like_error(result: Any) -> bool:
    r"""ツール実行結果がエラー（引数ミス・未知関数・例外等）かを判定する。

    Function Calling の失敗をログで拾うため、result がエラーメッセージ
    や異常値のときだけ真を返す。正常完了（success:True の dict 等）は偽。
    """
    if result is None:
        return False
    if isinstance(result, str):
        return any(
            k in result
            for k in ("Error", "error", "Traceback", "Exception", "例外", "失敗")
        )
    if isinstance(result, dict):
        return result.get("success") is False
    return False


# ---- 二段階テキストパース方式の設定 -----------------------------------
# Function Calling を廃止し、LLM には「アクション名 ID」の1行テキストを出させて
# agent 側でパースする。第1段階で行動を選ばせ、本文が必要なアクションだけ
# 第2段階で本文のみを書かせる。
MAX_CONTENT_RETRY = 1  # 第2段階（本文生成）のリトライ上限

# 第2段階（本文生成）が必要なアクション
NEEDS_CONTENT = frozenset({"create_post", "create_comment", "quote_post"})

# target（第1段階の第2トークン）を int として解釈するアクション。
# create_comment / quote_post は第1引数(post_id)が int。
ID_ACTIONS = frozenset({
    "like_post", "unlike_post", "dislike_post", "undo_dislike_post",
    "like_comment", "unlike_comment", "dislike_comment",
    "undo_dislike_comment",
    "repost", "follow", "unfollow", "mute", "unmute",
    "create_comment", "quote_post",
})

# target を query 文字列として行末まで取るアクション
QUERY_ACTIONS = frozenset({"search_posts", "search_user"})

# target を取らないアクション
NO_ARG_ACTIONS = frozenset({"do_nothing", "trend"})

# よくある誤呼び出し・省略名を正規アクション名へ
ACTION_ALIASES = {
    "like": "like_post",
    "unlike": "unlike_post",
    "dislike": "dislike_post",
    "post": "create_post",
    "tweet": "create_post",
    "comment": "create_comment",
    "reply": "create_comment",
    "comment_on_post": "create_comment",
    "quote": "quote_post",
    "reshare": "repost",
    "retweet": "repost",
    "follow_user": "follow",
    "mute_user": "mute",
}


# ---- LLM 同時実行数の制限（VRAM 枯渇対策）---------------------------
# env.step は asyncio.gather で全エージェントを同時並列実行する。26B など
# 大規模モデルを多数エージェントで並列推論すると VRAM に載りきらず、Ollama が
# 「全レイヤーをGPUに載せる（num_gpu=99）」を要求して 500/OOM になる。
# これを防ぐため astep（LLM リクエスト）の同時実行数をセマフォで絞る。
# llm_concurrency は sumika.py / config.json から configure_llm_concurrency()
# で設定する。未設定（0）なら制限なし（従来挙動）。セマフォは asyncio イベント
# ループ上で生成する必要があるため、生成は初回の astep 呼び出し時まで遅延させる。
_LLM_CONCURRENCY = 0
_LLM_SEMAPHORE: Optional[asyncio.Semaphore] = None


def configure_llm_concurrency(limit: int) -> None:
    r"""LLM への同時リクエスト数を制限するセマフォを（再）設定する。

    0 以下なら制限なし（従来挙動）。1 以上ならその数まで同時実行を許可する。
    値を変えるたびに既存セマフォを破棄し、次回 astep 時に新しい値で再生成する。
    """
    global _LLM_CONCURRENCY, _LLM_SEMAPHORE
    _LLM_CONCURRENCY = max(0, int(limit))
    _LLM_SEMAPHORE = None


def _get_llm_semaphore() -> Optional[asyncio.Semaphore]:
    r"""設定されていれば、イベントループ上でセマフォを遅延生成して返す。"""
    global _LLM_SEMAPHORE
    if _LLM_CONCURRENCY > 0 and _LLM_SEMAPHORE is None:
        _LLM_SEMAPHORE = asyncio.Semaphore(_LLM_CONCURRENCY)
    return _LLM_SEMAPHORE


# ---- チャットテンプレート制御トークンの除去（パーサ堅牢化）-----------
# Ollama が適用するチャットテンプレートとモデルの学習テンプレートが不一致の
# 場合、<|channel>thought / <channel|> / end_of_turn / </thought> のような
# 制御トークンがモデル出力に生で混入する。これらを行から除去し、純粋な
# アクション行/本文だけを取り出すことで、テンプレート不一致のモデルでも
# アクションを救済する。
_TEMPLATE_TAG_RE = re.compile(
    r'<\|?/?(?:channel|thought|start_of_turn|end_of_turn|im_start|im_end|'
    r'system|user|model|assistant)\|?>',
    re.IGNORECASE,
)
# タグ除去後にこれらの予約語だけが残る行は無視する（アクション/本文ではない）
_TEMPLATE_NOISE_WORDS = frozenset({
    "thought", "end_of_turn", "start_of_turn", "channel",
    "system", "user", "model", "assistant",
})


def _strip_template_tokens(line: str) -> str:
    r"""チャットテンプレートの制御トークンを行から除去する。"""
    return _TEMPLATE_TAG_RE.sub("", line).strip()


class SocialAgent(ChatAgent):
    r"""Social Agent."""

    def __init__(self,
                 agent_id: int,
                 user_info: UserInfo,
                 user_info_template: TextPrompt | None = None,
                 channel: Channel | None = None,
                 model: Optional[Union[BaseModelBackend,
                                       List[BaseModelBackend],
                                       ModelManager]] = None,
                 agent_graph: "AgentGraph" = None,
                 available_actions: list[ActionType] = None,
                 tools: Optional[List[Union[FunctionTool, Callable]]] = None,
                 max_iteration: int = 1,
                 interview_record: bool = False):
        self.social_agent_id = agent_id
        self.user_info = user_info
        self.channel = channel or Channel()
        self.env = SocialEnvironment(SocialAction(agent_id, self.channel))
        if user_info_template is None:
            system_message_content = self.user_info.to_system_message()
        else:
            system_message_content = self.user_info.to_custom_system_message(
                user_info_template)
        system_message = BaseMessage.make_assistant_message(
            role_name="system",
            content=system_message_content,
        )

        # 第1段階パーサ用: 許可アクション名のホワイトリスト。
        # Function Calling は廃止してテキストパース方式にしたため、tools は
        # 構築しない。available_actions はパーサが許可するアクション名として使う。
        if not available_actions:
            self.available_action_names = set(a.value for a in ActionType)
        else:
            self.available_action_names = set(
                a.value if isinstance(a, ActionType) else a
                for a in available_actions
            )
            for name in sorted(self.available_action_names):
                if not hasattr(self.env.action, name):
                    agent_log.warning(
                        f"Action '{name}' has no SocialAction method; "
                        f"it will be rejected by the parser.")
        # astep でテキスト応答を取るため、ChatAgent には tools を渡さない
        # （外部 tools は互換のため残せるが本プロジェクトでは未使用）。
        super().__init__(
            system_message=system_message,
            model=model,
            scheduling_strategy='random_model',
            tools=tools or [],
        )
        self.max_iteration = max_iteration
        self.interview_record = interview_record
        self.agent_graph = agent_graph
        self.test_prompt = (
            "\n"
            "Helen is a successful writer who usually writes popular western "
            "novels. Now, she has an idea for a new novel that could really "
            "make a big impact. If it works out, it could greatly "
            "improve her career. But if it fails, she will have spent "
            "a lot of time and effort for nothing.\n"
            "\n"
            "What do you think Helen should do?")

    async def _astep_throttled(self, msg):
        r"""LLM 同時実行数をセマフォで制限しつつ astep を呼ぶ（VRAM 枯渇対策）。

        llm_concurrency が未設定（0）ならセマフォ無しでそのまま astep する。
        """
        sem = _get_llm_semaphore()
        if sem is None:
            return await self.astep(msg)
        async with sem:
            return await self.astep(msg)

    async def perform_action_by_llm(self):
        r"""二段階テキストパース方式でアクションを1つ実行する。

        第1段階: astep で「アクション名 ID」の1行テキストを取得してパース。
        第2段階: 本文が必要なアクション（create_post/create_comment/quote_post）
                 のみ、astep で本文のみを取得。
        最後に SocialAction の対応メソッドを直接呼ぶ（Function Casting 不使用）。
        Function Calling は廃止しており、astep は常にテキスト応答を返す。
        """
        try:
            env_prompt = await self.env.to_text_prompt()
            agent_log.info(
                f"Agent {self.social_agent_id} observing environment: "
                f"{env_prompt}"
            )

            # --- 第1段階: 行動選択 ---
            parsed = None
            for attempt in range(MAX_ACTION_RETRY + 1):
                msg = (
                    self._stage1_message(env_prompt)
                    if attempt == 0
                    else self._stage1_retry_message(env_prompt)
                )
                response = await self._astep_throttled(msg)
                raw = self._response_text(response)
                parsed = self._parse_stage1(raw)
                self._log_text_out("STAGE1", raw, parsed)
                if parsed is not None:
                    break
                agent_log.info(
                    f"Agent {self.social_agent_id} STAGE1 parse failed; "
                    f"retrying ({attempt + 1}/{MAX_ACTION_RETRY})"
                )

            if parsed is None:
                agent_log.warning(
                    f"Agent {self.social_agent_id} STAGE1 exhausted; "
                    f"falling back to do_nothing"
                )
                action, target = ("do_nothing", None)
            else:
                action, target = parsed

            # --- 第2段階: 本文生成（本文が必要なアクションのみ）---
            content = None
            if action in NEEDS_CONTENT:
                for attempt in range(MAX_CONTENT_RETRY + 1):
                    msg = (
                        self._stage2_message(action, target)
                        if attempt == 0
                        else self._stage2_retry_message(action, target)
                    )
                    response = await self._astep_throttled(msg)
                    raw = self._response_text(response)
                    content = self._extract_content(raw)
                    self._log_text_out("STAGE2", raw, content)
                    if content:
                        break
                if not content:
                    agent_log.warning(
                        f"Agent {self.social_agent_id} STAGE2 empty content; "
                        f"falling back to do_nothing"
                    )
                    action, target = ("do_nothing", None)

            # --- 実行 ---
            return await self._dispatch(action, target, content)
        except Exception as e:
            agent_log.error(f"Agent {self.social_agent_id} error: {e}")
            return e

    # ---- 二段階テキストパース方式のヘルパ群 ----

    @staticmethod
    def _response_text(response):
        r"""ChatAgentResponse からテキスト本文を安全に取り出す。"""
        try:
            if response is not None and response.msg is not None:
                return response.msg.content or ""
        except Exception:
            pass
        return ""

    def _stage1_message(self, env_prompt):
        return BaseMessage.make_user_message(
            role_name="User",
            content=(
                "上記は今のあなたのSNS環境（タイムライン含む）です。"
                "キャラクター設定に沿って、とる行動を1つだけ選び、"
                "下記の形式で1行で出力してください（本文はまだ書かない）。\n"
                "形式: <アクション名> <対象ID または query>\n"
                "例:\n"
                "  like_post 6        （投稿6にいいね）\n"
                "  create_comment 6   （投稿6にコメント。本文は次で聞きます）\n"
                "  create_post        （新規投稿。本文は次で聞きます）\n"
                "  quote_post 12      （投稿12を引用。本文は次で聞きます）\n"
                "  repost 12          （投稿12をリポスト）\n"
                "  follow 5           （ユーザー5をフォロー）\n"
                "  search_posts キーワード\n"
                "  do_nothing\n"
                "【優先行動】タイムラインに投稿があれば、まずその中から1件を選んで"
                "リアクション（like_post / create_comment / repost / quote_post）を。"
                "自分の発信(create_post)より他者へのリアクションを優先。\n"
                "注意: 1行だけ。余計な説明・記号・マークダウンは書かない。"
                "do_nothing は本当に迷ったときだけ。\n"
                f"現在の環境: {env_prompt}"
            ),
        )

    def _stage1_retry_message(self, env_prompt):
        return BaseMessage.make_user_message(
            role_name="User",
            content=(
                "形式が読み取れませんでした。行動を1つ選び、"
                "「<アクション名> <ID>」の1行だけを出力してください。"
                "（例: like_post 6 / create_comment 6 / create_post / follow 5）\n"
                "余計な説明は書かないこと。\n"
                f"現在の環境: {env_prompt}"
            ),
        )

    def _stage2_message(self, action, target):
        what = {
            "create_post": "新しい投稿",
            "create_comment": f"投稿{target}へのコメント",
            "quote_post": f"投稿{target}の引用",
        }.get(action, "本文")
        return BaseMessage.make_user_message(
            role_name="User",
            content=(
                f"選んだ行動: {action}（{what}）。\n"
                f"その{what}の本文を、{self.user_info.name}の口調・性格で書いてください。\n"
                "140字以内。アクション名・ID・記号・マークダウンは一切書かず、"
                "本文のテキストだけを出力すること。"
            ),
        )

    def _stage2_retry_message(self, action, target):
        return BaseMessage.make_user_message(
            role_name="User",
            content=(
                "本文が空でした。投稿内容のテキストだけを書いてください。"
                "（アクション名や記号は書かない）"
            ),
        )

    def _parse_stage1(self, text):
        r"""第1段階の出力「アクション名 [ID|query]」をパースする。

        戻り値: (action_name, target) または None（パース失敗・無効アクション）。
        target は ID アクションなら int、query アクションなら str、それ以外は None。
        """
        if not text:
            return None
        # 先頭の意味ある1行を取得。チャットテンプレートの制御トークン
        # (<|channel>thought / <channel|> / end_of_turn 等) が混入するモデル
        # にも耐えるため、各行情況トークンを除去してから評価する。
        line = None
        for cand in text.splitlines():
            s = _strip_template_tokens(cand)
            s = s.strip().strip("`").strip(">*#-").strip()
            if not s or s.lower() in _TEMPLATE_NOISE_WORDS:
                continue
            # "action: like_post 6" のようなラベル付きも許容
            if s.lower().startswith("action:"):
                s = s.split(":", 1)[1].strip()
            if s:
                line = s
                break
        if not line:
            return None

        parts = line.split(None, 1)
        action_raw = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ""

        # アクション名の正規化: プレフィックス剥離 → snake_case（大小保持）→
        # 小文字化 → エイリアス。先に lower すると camelCase 情報が消えるので注意。
        action = action_raw
        for sep in (":", "."):
            if sep in action:
                action = action.rsplit(sep, 1)[-1]
        action = _camel_to_snake(action).lower()
        action = ACTION_ALIASES.get(action, action)

        if action not in self.available_action_names:
            return None

        # target 解決
        if action in QUERY_ACTIONS:
            return (action, rest or None)
        if action in ID_ACTIONS:
            if not rest:
                return None  # ID 必須だが省略
            try:
                return (action, int(rest))
            except (ValueError, TypeError):
                return None  # 数値化失敗
        # NO_ARG_ACTIONS / create_post は target 不要
        return (action, None)

    @staticmethod
    def _extract_content(text):
        r"""第2段階の出力から本文を抽出する。先頭の意味ある行を返す。"""
        if not text:
            return None
        labels = ("content", "text", "message", "body", "本文", "投稿")
        for cand in text.splitlines():
            s = _strip_template_tokens(cand)
            s = s.strip().strip("`").strip(">*#-").strip()
            if not s or s.lower() in _TEMPLATE_NOISE_WORDS:
                continue
            if ":" in s:
                head = s.split(":", 1)[0].strip().lower()
                if head in labels:
                    s = s.split(":", 1)[1].strip()
            if s:
                return s
        return None

    async def _dispatch(self, action, target, content):
        r"""パース結果を SocialAction の対応メソッドへ渡して実行する。"""
        method = getattr(self.env.action, action, None)
        if method is None:
            agent_log.warning(
                f"Agent {self.social_agent_id} [LLM-OUT] EXEC_NO_METHOD "
                f"action={action}"
            )
            return {"success": False, "error": f"unknown action: {action}"}
        try:
            if action == "create_post":
                result = await method(content)
            elif action in ("create_comment", "quote_post"):
                result = await method(target, content)
            elif action in QUERY_ACTIONS:
                result = await method(target if target is not None else "")
            elif action in NO_ARG_ACTIONS:
                result = await method()
            else:
                # ID 型単引数アクション（like_post/follow/...）
                result = await method(target)
            self._log_text_out("EXEC", None, (action, target, result))
            return result
        except Exception as e:
            agent_log.warning(
                f"Agent {self.social_agent_id} [LLM-OUT] EXEC_ERROR "
                f"action={action} target={target} content={content!r} "
                f"error={e!r}"
            )
            return {"success": False, "error": str(e)}

    def _log_text_out(self, stage, raw, parsed):
        r"""二段階方式の各ステップの生テキストとパース結果をログ出力する。

        ``grep '[LLM-OUT]'`` で一覧可能。STAGE1/STAGE2/EXEC の各ステップと
        エラー（PARSE_FAIL / EMPTY / EXEC_ERROR）を記録し、LLM の失敗例を追跡できる。
        """
        aid = self.social_agent_id
        if raw:
            agent_log.info(f"Agent {aid} [LLM-OUT] {stage} raw: {raw!r}")
        if stage == "STAGE1":
            if parsed is None:
                agent_log.warning(f"Agent {aid} [LLM-OUT] {stage} PARSE_FAIL")
            else:
                agent_log.info(
                    f"Agent {aid} [LLM-OUT] {stage} parsed: {parsed}"
                )
        elif stage == "STAGE2":
            if not parsed:
                agent_log.warning(f"Agent {aid} [LLM-OUT] {stage} EMPTY")
            else:
                agent_log.info(
                    f"Agent {aid} [LLM-OUT] {stage} content: {parsed!r}"
                )
        elif stage == "EXEC":
            action, target, result = parsed
            if _looks_like_error(result):
                agent_log.warning(
                    f"Agent {aid} [LLM-OUT] EXEC_ERROR action={action} "
                    f"target={target} result={result!r}"
                )
            else:
                agent_log.info(
                    f"Agent {aid} [LLM-OUT] EXEC action={action} "
                    f"target={target}"
                )

    async def perform_test(self):
        """
        doing group polarization test for all agents.
        """
        openai_messages, num_tokens = self.memory.get_context()

        openai_messages = ([{
            "role":
            self.system_message.role_name,
            "content":
            self.system_message.content.split("# RESPONSE METHOD")[0],
        }] + openai_messages + [{
            "role": "user",
            "content": self.test_prompt
        }])

        agent_log.info(f"Agent {self.social_agent_id}: {openai_messages}")
        response = await self._aget_model_response(
            openai_messages=openai_messages, num_tokens=num_tokens)
        content = response.output_messages[0].content
        agent_log.info(
            f"Agent {self.social_agent_id} receive response: {content}")
        return {
            "user_id": self.social_agent_id,
            "prompt": openai_messages,
            "content": content
        }

    async def perform_interview(self, interview_prompt: str):
        """
        Perform an interview with the agent.
        """
        user_msg = BaseMessage.make_user_message(
            role_name="User", content=("You are a twitter user."))

        if self.interview_record:
            self.update_memory(message=user_msg, role=OpenAIBackendRole.SYSTEM)

        openai_messages, num_tokens = self.memory.get_context()

        openai_messages = ([{
            "role":
            self.system_message.role_name,
            "content":
            self.system_message.content.split("# RESPONSE METHOD")[0],
        }] + openai_messages + [{
            "role": "user",
            "content": interview_prompt
        }])

        agent_log.info(f"Agent {self.social_agent_id}: {openai_messages}")
        response = await self._aget_model_response(
            openai_messages=openai_messages, num_tokens=num_tokens)

        content = response.output_messages[0].content

        if self.interview_record:
            self.update_memory(message=response.output_messages[0],
                               role=OpenAIBackendRole.USER)
        agent_log.info(
            f"Agent {self.social_agent_id} receive response: {content}")

        interview_data = {"prompt": interview_prompt, "response": content}
        result = await self.env.action.perform_action(
            interview_data, ActionType.INTERVIEW.value)

        return {
            "user_id": self.social_agent_id,
            "prompt": openai_messages,
            "content": content,
            "success": result.get("success", False)
        }

    async def perform_action_by_hci(self) -> Any:
        print("Please choose one function to perform:")
        function_list = self.env.action.get_openai_function_list()
        for i in range(len(function_list)):
            agent_log.info(f"Agent {self.social_agent_id} function: "
                           f"{function_list[i].func.__name__}")

        selection = int(input("Enter your choice: "))
        if not 0 <= selection < len(function_list):
            agent_log.error(f"Agent {self.social_agent_id} invalid input.")
            return
        func = function_list[selection].func

        params = inspect.signature(func).parameters
        args = []
        for param in params.values():
            while True:
                try:
                    value = input(f"Enter value for {param.name}: ")
                    args.append(value)
                    break
                except ValueError:
                    agent_log.error("Invalid input, please enter an integer.")

        result = await func(*args)
        return result

    async def perform_action_by_data(self, func_name, *args, **kwargs) -> Any:
        func_name = func_name.value if isinstance(func_name,
                                                  ActionType) else func_name
        function_list = self.env.action.get_openai_function_list()
        for i in range(len(function_list)):
            if function_list[i].func.__name__ == func_name:
                func = function_list[i].func
                result = await func(*args, **kwargs)
                self.update_memory(message=BaseMessage.make_user_message(
                    role_name=OpenAIBackendRole.SYSTEM,
                    content=f"Agent {self.social_agent_id} performed "
                    f"{func_name} with args: {args} and kwargs: {kwargs}"
                    f"and the result is {result}"),
                                   role=OpenAIBackendRole.SYSTEM)
                agent_log.info(f"Agent {self.social_agent_id}: {result}")
                return result
        raise ValueError(f"Function {func_name} not found in the list.")

    def perform_agent_graph_action(
        self,
        action_name: str,
        arguments: dict[str, Any],
    ):
        r"""Remove edge if action is unfollow or add edge
        if action is follow to the agent graph.
        """
        if "unfollow" in action_name:
            followee_id: int | None = arguments.get("followee_id", None)
            if followee_id is None:
                return
            self.agent_graph.remove_edge(self.social_agent_id, followee_id)
            agent_log.info(
                f"Agent {self.social_agent_id} unfollowed Agent {followee_id}")
        elif "follow" in action_name:
            followee_id: int | None = arguments.get("followee_id", None)
            if followee_id is None:
                return
            self.agent_graph.add_edge(self.social_agent_id, followee_id)
            agent_log.info(
                f"Agent {self.social_agent_id} followed Agent {followee_id}")

    def __str__(self) -> str:
        return (f"{self.__class__.__name__}(agent_id={self.social_agent_id}, "
                f"model_type={self.model_type.value})")