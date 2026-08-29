import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GITHUB_TOKEN", "test_gh_token")
os.environ.setdefault("GITHUB_REPO", "test/repo")
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("ALLOWED_TELEGRAM_ID", "123456789")
os.environ.setdefault("OPENAI_API_KEY", "test_openai_key")


# ---- handler 測試用的假物件 ---------------------------------------------
# handler 層有 2000 多行完全沒有測試，而今天找到的三個 bug 全都住在那裡：
# 問題不在單一函式算錯，而在跨函式的「順序」——先寫基準還是先推播、
# 指令有沒有先清掉追問。這些假物件讓那種順序可以被斷言。

class FakeBot:
    """記下所有送出的訊息；可指定第 N 次呼叫要爆炸。"""

    def __init__(self, fail_on: set[int] | None = None):
        self.sent: list[dict] = []
        self.documents: list[dict] = []
        self._fail_on = fail_on or set()

    async def send_message(self, chat_id, text, **kwargs):
        index = len(self.sent)
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})
        if index in self._fail_on:
            raise RuntimeError("模擬傳送失敗")
        return FakeMessage(text)

    async def send_document(self, chat_id, document, **kwargs):
        self.documents.append({"chat_id": chat_id, **kwargs})
        return FakeMessage("")

    @property
    def texts(self) -> list[str]:
        return [m["text"] for m in self.sent]


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.chat_id = 123456789
        self.edits: list[str] = []
        self.deleted = False

    async def reply_text(self, text, **kwargs):
        return FakeMessage(text)

    async def edit_text(self, text, **kwargs):
        self.edits.append(text)
        return self

    async def delete(self):
        self.deleted = True


class FakeContext:
    """夠用來跑 job 與 handler 的 context 替身。"""

    def __init__(self, bot=None):
        self.bot = bot or FakeBot()
        self.user_data: dict = {}
        self.chat_data: dict = {}
        self.bot_data: dict = {}
        self.args: list[str] = []
        self.error = None
