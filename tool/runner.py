# tool/runner.py  执行编排（解析 tool_calls、校验参数、循环多轮、回灌 tool result）
# -------------------------------------------------
# 通用 Function-Calling 执行器（Agent 执行层）
# 作用：
#   - 接收 LLM 的工具调用请求
#   - 做参数兜底 / 归一化（安全边界）
#   - 调用真实业务 executor
#   - 支持多步工具链
# -------------------------------------------------

import json
import requests

from tool.tool_map import TOOL_SCHEMAS, TOOL_EXECUTORS
from tool.executors import PRODUCT_CATEGORY_MAP


def run_function_calling(
    llm_url: str,
    api_key: str,
    model: str,
    user_query: str,
    system_prompt: str,
    max_rounds: int = 5
):
    """
    通用的 function-calling Agent 执行器

    特点：
    - 支持多轮、多工具调用
    - LLM 只“提议”，runner 负责校验与兜底
    - 不 hardcode 具体业务逻辑
    """

    # 初始化对话
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query}
    ]

    headers = {
        "Content-Type": "application/json",
        "Authorization": api_key
    }
    """"
    "tool_choice": "auto",#你可以自己决定：是直接回答（content），还是返回 tool_calls（调用工具）
    "tool_choice": {
                        "type": "function",
                        "function": { "name": "check_refund_policy" }
                        }
                    强制模型必须调用这个工具
    """
    for _ in range(max_rounds):
        body = {
            "model": model,
            "messages": messages,
            "tools": TOOL_SCHEMAS,

            "tool_choice": "auto",
            "temperature": 0
        }

        # 调用 LLM
        resp = requests.post(
            llm_url,
            headers=headers,
            json=body,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        msg = data["choices"][0]["message"]

        # ===== 1️⃣ LLM 不再请求工具，直接给最终答案 =====
        if "tool_calls" not in msg:
            messages.append(msg)
            return msg.get("content", "")

        # ===== 2️⃣ LLM 请求调用工具 =====
        messages.append(msg)

        for call in msg["tool_calls"]:
            tool_name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"])

            if tool_name not in TOOL_EXECUTORS:
                raise RuntimeError(f"未知工具: {tool_name}")

            # ==================================================
            # ✅ 参数兜底 / 归一化（Agent 工程关键点）
            # ==================================================
            if tool_name == "check_refund_policy":
                raw_category = args.get("category", "")
                if raw_category in PRODUCT_CATEGORY_MAP:
                    args["category"] = PRODUCT_CATEGORY_MAP[raw_category]

            # ===== 执行真实业务函数 =====
            result = TOOL_EXECUTORS[tool_name](**args)

            # ===== 把工具结果喂回给 LLM =====
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "name": tool_name,
                "content": json.dumps(result, ensure_ascii=False)
            })

    # 超过最大轮次仍未结束
    raise RuntimeError("function calling 超过最大轮次，可能进入死循环")
