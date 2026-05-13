#「真正执行业务逻辑」的地方（安全边界）
# LLM 永远不能直接碰数据库 / 服务,它只能“提议”，这里才是真执行
# tool/executors.py  真正业务执行（查库/RPC/HTTP/权限/风控/日志）
# 因为未来你可以在这里：(可拓展)
# 加权限校验
# 加日志
# 加风控
# Mock 单测
# 换真实接口
PRODUCT_CATEGORY_MAP = {
    "蓝牙耳机": "电子产品",
    "耳机": "电子产品",
    "手机": "电子产品"
}

def get_order_status(order_id: str):
    """
    查询订单状态（示例实现）
    """
    # TODO：以后可以接数据库 / RPC / HTTP
    return {
        "order_id": order_id,
        "status": "已发货"
    }


def check_refund_policy(category: str):
    """
    查询退货政策（示例实现）
    """
    if category == "电子产品":
        policy = "7 天内支持无理由退货"
    else:
        policy = "不支持无理由退货"

    return {
        "category": category,
        "policy": policy
    }


def escalate_to_human(reason: str):
    return {
        "action": "escalate_to_human",
        "reason": reason,
        "message": "已为您转接人工客服，请稍候。"
    }
