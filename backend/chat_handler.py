"""
网页聊天 - Hermes 双向桥接模块

流程：
1. 网页发消息 → POST /api/chat/send → 存储 + 调用 hermes -z 获取回复
2. 回复存储到 DB → SSE 推送到网页
"""

import threading
import subprocess
import os
from models import get_db

HERMES_BIN = "/home/ubuntu/.hermes/hermes-agent/venv/bin/hermes"

_sse_listeners = []
_poll_thread = None


def _call_hermes(message: str, conversation_history: list = None) -> str:
    """调用 Hermes CLI 获取回复"""
    prompt = message
    if conversation_history and len(conversation_history) > 1:
        # 最近 8 条历史拼为简洁上下文
        ctx_parts = []
        for m in conversation_history[-8:]:
            role = "用户" if m['role'] == 'user' else "小欢欢"
            content = m['content'][:200]
            ctx_parts.append(f"{role}: {content}")
        prompt = "以下是之前的对话：\n" + "\n".join(ctx_parts) + f"\n\n用户最新消息：{message}"

    try:
        result = subprocess.run(
            [HERMES_BIN, "-z", prompt, "--yolo", "--accept-hooks"],
            capture_output=True, text=True, timeout=300,
            env={**os.environ, "HERMES_HOME": "/home/ubuntu/.hermes"}
        )
        output = result.stdout.strip()
        # 清理可能的 spinner/ANSI 字符
        import re
        output = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', output)
        output = re.sub(r'[⠙⠹⠸⠼⠴⠦⠧⠇⠏⠋]', '', output)
        if result.returncode != 0 and not output:
            output = f"(错误: {result.stderr[:200]})"
        return output or "(空回复)"
    except subprocess.TimeoutExpired:
        return "(回复超时，请稍后重试)"
    except Exception as e:
        return f"(调用失败: {str(e)[:100]})"


def store_message(contract_id: int, role: str, content: str) -> dict:
    """存储消息到数据库，返回消息 dict"""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO chat_messages (contract_id, role, content) VALUES (?,?,?)",
        (contract_id, role, content)
    )
    msg_id = c.lastrowid
    conn.commit()
    msg = dict(c.execute("SELECT * FROM chat_messages WHERE id = ?", (msg_id,)).fetchone())
    conn.close()
    return msg


def get_messages(contract_id: int, since_id: int = 0) -> list:
    """获取消息历史"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE contract_id = ? AND id > ? ORDER BY id",
        (contract_id, since_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def notify_sse(msg: dict):
    """通知所有 SSE 监听器有新消息"""
    for q in _sse_listeners:
        try:
            q.append(msg)
        except:
            pass


def register_sse_listener(q: list):
    _sse_listeners.append(q)


def unregister_sse_listener(q: list):
    if q in _sse_listeners:
        _sse_listeners.remove(q)


def handle_user_message(contract_id: int, text: str) -> dict:
    """处理用户消息：存储 → 调用 Hermes → 存储回复 → SSE 推送"""
    # 1. 存储用户消息
    user_msg = store_message(contract_id, "user", text)
    notify_sse(user_msg)

    # 2. 获取对话历史
    history = get_messages(contract_id)

    # 3. 调用 Hermes（在后台线程中，避免阻塞 HTTP 响应）
    def _process():
        try:
            reply = _call_hermes(text, history[:-1])  # 排除刚存的那条
            assistant_msg = store_message(contract_id, "assistant", reply)
            notify_sse(assistant_msg)
        except Exception as e:
            err_msg = store_message(contract_id, "assistant", f"(处理出错: {e})")
            notify_sse(err_msg)

    threading.Thread(target=_process, daemon=True).start()

    return user_msg
