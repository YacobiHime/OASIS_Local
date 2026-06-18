"""二段階テキストパース方式の単体テスト（_parse_stage1 / _dispatch）。

SocialAgent.__new__ で __init__ を迂回し、最小のモックで検証する。
実行: .venv/bin/python test_text_action.py
"""
import asyncio
from types import SimpleNamespace

from oasis.social_agent.agent import SocialAgent
from oasis.social_agent.agent_action import SocialAction


class MockChannel:
    def __init__(self):
        self.last = None

    async def write_to_receive_queue(self, msg):
        self.last = msg
        return 1

    async def read_from_send_queue(self, mid):
        return (None, None, {"success": True})


# sumika.py の available_actions 21個相当
NAMES = {
    "like_post", "unlike_post", "dislike_post", "undo_dislike_post",
    "like_comment", "unlike_comment", "dislike_comment",
    "undo_dislike_comment",
    "create_post", "repost", "quote_post", "create_comment",
    "follow", "unfollow", "mute", "unmute",
    "search_posts", "search_user", "trend", "do_nothing",
}


def make_agent():
    inst = SocialAgent.__new__(SocialAgent)
    inst.social_agent_id = 1
    inst.available_action_names = set(NAMES)
    ch = MockChannel()
    inst.env = SimpleNamespace(action=SocialAction(1, ch))
    inst.user_info = SimpleNamespace(name="森本")
    return inst, ch


def test_parse_stage1():
    inst, _ = make_agent()
    cases = [
        # (入力テキスト, 期待 (action, target))
        ("like_post 6", ("like_post", 6)),
        ("create_comment 6", ("create_comment", 6)),
        ("create_post", ("create_post", None)),
        ("quote_post 12", ("quote_post", 12)),
        ("search_posts AI 倫理 規制", ("search_posts", "AI 倫理 規制")),
        ("do_nothing", ("do_nothing", None)),
        ("follow 5", ("follow", 5)),
        # 正規化
        ("likePost 6", ("like_post", 6)),            # camelCase
        ("LikePost 6", ("like_post", 6)),            # 先頭大文字
        ("default_api:like 6", ("like_post", 6)),    # プレフィックス剥離＋エイリアス
        ("comment 6", ("create_comment", 6)),        # エイリアス
        ("reply 6", ("create_comment", 6)),          # エイリアス
        ("post", ("create_post", None)),             # エイリアス
        # ラベル付き
        ("action: like_post 6", ("like_post", 6)),
        # 無効
        ("hoge 6", None),                            # 未定義アクション
        ("", None),                                  # 空
        ("   \n  \n", None),                         # 空白のみ
        ("like_post abc", None),                     # ID 数値化失敗
        ("like_post", None),                         # ID 必須だが省略
    ]
    for text, exp in cases:
        got = inst._parse_stage1(text)
        assert got == exp, f"parse {text!r}: expected {exp}, got {got}"
    print(f"OK _parse_stage1 ({len(cases)} cases)")


def test_extract_content():
    cases = [
        ("こんにちは", "こんにちは"),
        ("content: こんにちは", "こんにちは"),
        ("```\n本文です\n```", "本文です"),          # フェンス行は空なのでスキップ
        ("> これは引用", "これは引用"),               # > を剥がす
        ("- 箇条書き本文", "箇条書き本文"),           # - を剥がす
        ("", None),
        ("   \n", None),
    ]
    for text, exp in cases:
        got = SocialAgent._extract_content(text)
        assert got == exp, f"extract {text!r}: expected {exp!r}, got {got!r}"
    print(f"OK _extract_content ({len(cases)} cases)")


async def test_dispatch():
    def check(ch, message, type_str):
        # message（引数）が正しく platform まで届くことを検証。
        # type は ActionType.value（文字列）または enum の両方を許容。
        assert ch.last[0] == 1, ch.last
        assert ch.last[1] == message, ch.last
        t = ch.last[2]
        tval = t.value if hasattr(t, "value") else t
        assert tval == type_str, ch.last

    # create_post -> content（単 str）
    inst, ch = make_agent()
    await inst._dispatch("create_post", None, "こんにちは")
    check(ch, "こんにちは", "create_post")

    # create_comment -> (post_id, content) タプル
    inst, ch = make_agent()
    await inst._dispatch("create_comment", 6, "返信です")
    check(ch, (6, "返信です"), "create_comment")

    # quote_post -> (post_id, quote_content) タプル
    inst, ch = make_agent()
    await inst._dispatch("quote_post", 12, "引用")
    check(ch, (12, "引用"), "quote_post")

    # like_post -> post_id（単 int）
    inst, ch = make_agent()
    await inst._dispatch("like_post", 6, None)
    check(ch, 6, "like_post")

    # follow -> followee_id
    inst, ch = make_agent()
    await inst._dispatch("follow", 5, None)
    check(ch, 5, "follow")

    # search_posts -> query str
    inst, ch = make_agent()
    await inst._dispatch("search_posts", "AI倫理", None)
    check(ch, "AI倫理", "search_posts")

    # do_nothing -> None
    inst, ch = make_agent()
    await inst._dispatch("do_nothing", None, None)
    check(ch, None, "do_nothing")

    # 不正アクション名（getattr 無し）は {success:False}
    inst, ch = make_agent()
    res = await inst._dispatch("__notexist__", None, None)
    assert res == {"success": False, "error": "unknown action: __notexist__"}, res
    print("OK _dispatch (8 cases)")


def main():
    test_parse_stage1()
    test_extract_content()
    asyncio.run(test_dispatch())
    print("\nALL PASSED")


if __name__ == "__main__":
    main()
