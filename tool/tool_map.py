#「schema 名字 → 执行函数」的唯一映射表
# tool/tool_map.py 工具名→执行函数映射
# LLM 只知道 "name": "get_order_status"
# Python 必须知道 这个名字对应哪个函数
# 而你不希望在 start.py 里 if-else 100 个工具,tool_map = 解耦神器

from tool.schemas import (
    GET_ORDER_STATUS_SCHEMA,
    CHECK_REFUND_POLICY_SCHEMA,
    ESCALATE_TO_HUMAN_SCHEMA
)

from tool.executors import (
    get_order_status,
    check_refund_policy,
    escalate_to_human
)

# 所有可以暴露给 LLM 的工具 schema
TOOL_SCHEMAS = [
    GET_ORDER_STATUS_SCHEMA,
    CHECK_REFUND_POLICY_SCHEMA,
    ESCALATE_TO_HUMAN_SCHEMA
]

# schema.name → 实际执行函数
TOOL_EXECUTORS = {
    "get_order_status": get_order_status,
    "check_refund_policy": check_refund_policy,
    "escalate_to_human": escalate_to_human
}
