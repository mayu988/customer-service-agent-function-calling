# tool/schemas.py 工具“合同”（给 LLM 看）
# 这一层只做一件事:不执行业务,不查数据库,不写逻辑
# 只告诉 LLM：工具叫什么,需要什么参数,参数结构是什么

GET_ORDER_STATUS_SCHEMA = {
    "name": "get_order_status",
    "description": "查询订单的当前状态",
    "parameters": {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "订单号，例如 ORD-2024"
            }
        },
        "required": ["order_id"]
    }
}

CHECK_REFUND_POLICY_SCHEMA = {
    "name": "check_refund_policy",
    "description": "查询某个商品品类是否支持退货",
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "商品品类，例如 电子产品"
            }
        },
        "required": ["category"]
    }
}

ESCALATE_TO_HUMAN_SCHEMA = {
    "name": "escalate_to_human",
    "description": "\u8f6c\u63a5\u4eba\u5de5\u5ba2\u670d\uff0c\u9002\u7528\u4e8e\u9ad8\u4e0d\u6ee1/\u6295\u8bc9/\u8fb1\u9a82\u7b49\u98ce\u9669\u573a\u666f",
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "\u8f6c\u4eba\u5de5\u7684\u539f\u56e0\uff0c\u4f8b\u5982\uff1a\u9ad8\u6124\u6012\u6295\u8bc9"
            }
        },
        "required": ["reason"]
    }
}
