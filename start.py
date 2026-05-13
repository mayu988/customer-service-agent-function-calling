
from tool.runner import run_function_calling
from config.config import (
    API_KEY,
    BASE_URL,
    DEFAULT_MODEL,
    AGENT_SYSTEM_PROMPT
)

import re

from tool.executors import (
    get_order_status,
    check_refund_policy,
    escalate_to_human as tool_escalate_to_human,
    PRODUCT_CATEGORY_MAP,
)



import json
import os
import copy
import traceback
import time
import redis
import requests
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, jsonify, make_response
from flask_socketio import SocketIO, emit

import prompts
from utils import logger
from utils.redis_tool import RedisClient
from client.arbitration import request_arbitration
from client.stream_chat import request_chat, process_chat
from client.reject import request_reject
from client.nlu import request_nlu
from client.rewrite import request_rewrite
from client.correlation import request_correlation


socketio = SocketIO(cors_allowed_origins='*', async_mode='threading')
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
socketio.init_app(app)


TTL = 40
REDIS_KEY = "voice:last_service:{}"
redis_client = RedisClient()
thread_pool = ThreadPoolExecutor(max_workers=10)


@app.route("/health", methods=["GET"])
def check():
    response = make_response(
        jsonify(health="healthy"),
        200,
        {'content-type': 'application/json'}
    )
    return response


@socketio.on('connect')
def connected_msg():
    manager = socketio.server.manager
    connections_count = len(manager.rooms['/']) - 1
    logger.info(f'当前连接数: {connections_count}')
    logger.info('client connected.')


@socketio.on('disconnect')
def disconnect_msg():
    logger.info('client disconnected.')

ORDER_ID_RE = re.compile(r"\bORD-\d+\b", re.IGNORECASE)
PENDING_KEY = "voice:pending:{}"   # 单独一条 key，避免破坏你现有 last_service 结构

ORDER_QUERY_KEYWORDS = ["快递", "物流", "到哪", "订单状态", "查订单", "查一下订单", "帮我查", "订单号"]
REFUND_KEYWORDS = [
    "退货",
    "退款",
    "退",
    "退掉",
    "退回",
    "退换",
    "换货",
    "符合政策",
    "能退吗",
    "想退",
    "申请退",
    "杂音",
    "坏了",
    "质量",
    "不想要",
    "有问题",
    "故障"
]

def send_msg(nlu_result, func, frame, seq, cost, status):
    if func == "CHAT":
        intent, intent_id = "闲聊百科", "439"
    elif func == "ASK":
        intent, intent_id = "追问补参", "441"
    elif func == "ESCALATE":
        intent, intent_id = "转人工", "442"
    elif func == "TASK":
        intent, intent_id = "任务执行", "443"
    else:
        intent, intent_id = "拒识", "440"

    nlu_result["intent"] = intent
    nlu_result["intent_id"] = intent_id
    nlu_result["func"] = func
    nlu_result["function"] = func
    nlu_result["frame"] = frame
    nlu_result["seq"] = seq
    nlu_result["cost"] = cost
    nlu_result["status"] = status

    emit(
        "request_nlu",
        json.dumps(nlu_result, ensure_ascii=False),
        broadcast=False
    )


def handle_chat(handler_bot, nlu_result, query, sender_id, begin):

    # 开始帧
    seq = 1
    nlu_result_begin = copy.deepcopy(nlu_result)
    send_msg(nlu_result_begin, "CHAT", "", seq, time.time() - begin, status=0)

    # 中间帧
    full_answer = ""
    for value in process_chat(handler_bot.result(), query, sender_id):
        nlu_result_chat = copy.deepcopy(nlu_result)
        send_msg(nlu_result_chat, "CHAT", value, seq, time.time() - begin, status=1)
        seq += 1
        full_answer += value
        logger.info(f"Chat Frame:{seq},content:{value}")

    # 结束帧
    if seq > 1:
        nlu_result_end = copy.deepcopy(nlu_result)
        send_msg(nlu_result_end, "CHAT", "", seq, time.time() - begin, status=2)
        logger.info(f"Chat cost time: {time.time() - begin}")
        return True, full_answer
    else:
        logger.info(f"Chat cost time: {time.time() - begin}")
        return False, full_answer

def send_escalate_msg(nlu_template, msg, begin):
    send_msg(nlu_template, "ESCALATE", msg, 1, time.time() - begin, status=0)

def extract_order_id(text: str) -> str:
    if not text:
        return ""
    m = ORDER_ID_RE.search(text)
    return m.group(0).upper() if m else ""

def extract_product_category(text: str) -> str:
    """
    从用户文本中找商品词，并映射到品类（复用 PRODUCT_CATEGORY_MAP）
    """
    if not text:
        return ""
    for k, v in PRODUCT_CATEGORY_MAP.items():
        if k in text:
            return v
    return ""


#dialog.py 发出的消息的接收端
#数据最终被 start.py 的 inference() 函数接收。
@socketio.on('request_nlu')
def inference(req):
    begin = time.time()
    json_info = json.loads(req)
    query = json_info.get("query")
    enable_dm = json_info.get("enable_dm")
    sender_id = json_info.get("sender_id", "test")
    trace_id = json_info.get("trace_id", "123")

    nlu_template = {
        "query": query,
        "trace_id": trace_id,
        "intent": "",
        "intent_id": "",
        "function": "",
        "slots": {},
        "cost": time.time() - begin
    }
    try:
        ori_query = query
        logger.session.trace_id = trace_id
        logger.info("Request Params: {}".format(json_info))

        last_info = redis_client.get(REDIS_KEY.format(sender_id))
        last_domain, last_query, last_reject, last_answer = "", "", "", ""
        if last_info:
            parts = last_info.split("#")
            if len(parts) >= 4:
                last_domain, last_query, last_reject, last_answer = parts[0], parts[1], parts[2], parts[3]
            else:
                last_domain, last_query, last_reject, last_answer = "", "", "", ""

        # Query改写
        query = request_rewrite(query, last_answer, sender_id)

        # 调用仲裁
        handler_arbitration = thread_pool.submit(request_arbitration, ori_query, sender_id)

        # 获取仲裁结果
        arbitration_result = handler_arbitration.result()

        logger.info(
            f"TraceID:{trace_id}, query:{query}, arbitration result: {arbitration_result}, cost time: {time.time() - begin}")

        HIGH_RISK_KEYWORDS = [
            "投诉", "举报", "垃圾", "气死", "你们不行", "人工", "客服"
        ]

        # ===== 情绪兜底规则（关键词强制转人工）=====
        if any(k in ori_query for k in HIGH_RISK_KEYWORDS):
            logger.info(
                f"TraceID:{trace_id}, hit high risk keyword, force escalate"
            )
            arbitration_result = "G"

    
        # ===== 情绪分拣仲裁逻辑 =====

        if arbitration_result == "G":
            tool_res = tool_escalate_to_human(reason="高愤怒/投诉，触发风控转人工")
            msg = tool_res.get("message", "已为您转接人工客服，请稍候。")
            send_escalate_msg(nlu_template, msg, begin)

            redis_client.set(
                REDIS_KEY.format(sender_id),
                f"ESCALATE#{ori_query}#1#{msg}",
                ex=TTL
            )
            return

        else:
            # =========================
            # 方案②：两条路由 + 场景A直编排 + 场景B缺参追问
            # =========================

            # 0) 取 pending（如果存在）
            pending_raw = redis_client.get(PENDING_KEY.format(sender_id))
            pending = json.loads(pending_raw) if pending_raw else None

            # 1) 抽取关键信息（不用依赖 NLU/LLM，稳定）
            order_id = extract_order_id(ori_query)
            category = extract_product_category(ori_query)

            is_order_query = any(k in ori_query for k in ORDER_QUERY_KEYWORDS)
            is_refund = any(k in ori_query for k in REFUND_KEYWORDS)

            # -----------------------------------------
            # 路由1：pending 续接（场景B第二轮）
            # 用户只补了 ORD-xxxx，且 pending 存在 -> 继续上次未完成任务
            # -----------------------------------------
            if pending and pending.get("state") == "WAIT_ORDER_ID" and order_id:
                # 继续执行“查订单状态”
                status_res = get_order_status(order_id=order_id)

                final_answer = f"已查到订单 {status_res['order_id']} 当前状态：{status_res['status']}。"
                send_msg(nlu_template, "TASK", final_answer, 1, time.time() - begin, status=0)

                # 清掉 pending
                redis_client.set(PENDING_KEY.format(sender_id), "", ex=1)

                # 记录 last_service（可选）
                redis_client.set(
                    REDIS_KEY.format(sender_id),
                    f"TASK#{ori_query}#1#{final_answer}",
                    ex=TTL
                )
                return

            # -----------------------------------------
            # 路由2：缺参追问（场景B第一轮）
            # 命中“查快递/查订单状态”但缺 order_id -> 追问并写 pending
            # -----------------------------------------
            if is_order_query and not order_id:
                ask = "请提供您的订单号（例如：ORD-9999）。"
                send_msg(nlu_template, "ASK", ask, 1, time.time() - begin, status=0)

                # 写 pending（只需要记住：我们在等订单号）
                pending_obj = {
                    "state": "WAIT_ORDER_ID",
                    "intent": "ORDER_STATUS",
                    "raw_query": ori_query,
                    "ts": int(time.time())
                }
                redis_client.set(
                    PENDING_KEY.format(sender_id),
                    json.dumps(pending_obj, ensure_ascii=False),
                    ex=TTL
                )

                # 记录 last_service（可选）
                redis_client.set(
                    REDIS_KEY.format(sender_id),
                    f"ASK#{ori_query}#1#{ask}",
                    ex=TTL
                )
                return

            # -----------------------------------------
            # 路由3：完整信息直编排（场景A）
            # 有 order_id + 有商品词(->品类) + 退货/杂音等 -> 固定调用两工具并综合答复
            # -----------------------------------------
            if order_id and category and is_refund:
                status_res = get_order_status(order_id=order_id)
                policy_res = check_refund_policy(category=category)

                final_answer = (
                    f"我帮您查到订单 {status_res['order_id']} 当前状态：{status_res['status']}。\n"
                    f"商品品类：{policy_res['category']}，退货政策：{policy_res['policy']}。\n"
                    f"如果您确认要退货，我可以继续引导您发起退货申请。"
                )

                send_msg(nlu_template, "TASK", final_answer, 1, time.time() - begin, status=0)

                redis_client.set(
                    REDIS_KEY.format(sender_id),
                    f"TASK#{ori_query}#1#{final_answer}",
                    ex=TTL
                )
                return

            # -----------------------------------------
            # 路由4：长尾兜底 -> 走你原来的通用 Agent
            # -----------------------------------------
            final_answer = run_function_calling(
                llm_url=BASE_URL,
                api_key=API_KEY,
                model=DEFAULT_MODEL,
                user_query=ori_query,
                system_prompt=AGENT_SYSTEM_PROMPT
            )

            send_msg(
                nlu_template,
                "TASK",
                final_answer,
                1,
                time.time() - begin,
                status=0
            )

            redis_client.set(
                REDIS_KEY.format(sender_id),
                f"TASK#{ori_query}#1#{final_answer}",
                ex=TTL
            )




        
    except Exception as e:
        logger.error(
            'TraceID:{}, Internal Server Error!'.format(trace_id))
        logger.error('{}'.format(e))
        traceback.print_exc()
        send_msg(nlu_template, "REJECT", "", 1, time.time() - begin, status=-1)

if __name__ == "__main__":
    socketio.run(
        app,
        allow_unsafe_werkzeug=True,
        host='0.0.0.0',
        port=os.getenv("FLASK_SERVER_PORT", 8081)
    )
