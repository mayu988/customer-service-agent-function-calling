

import os
import json
import random
from collections import defaultdict
import socketio

#如果我是在云服务器运行后端，就需要把云服务器的地址写在我的前端笔记本的环境变量ENTRY_URL中
URL = os.environ["ENTRY_URL"]

#创建一个 SocketIO 客户端实例，用于连接后端 SocketIO 服务器
sio = socketio.Client()

#使用 @sio.on("事件名") 装饰器注册事件回调函数，当客户端连接成功时自动执行该函数
@sio.on("connect")
def on_connect():
    print("connected to server")

#与服务器断开时调用
@sio.on("disconnect")
def on_disconnect():
    print("disconnected to server")

#接收普通消息
@sio.on("message")
def on_message(data):  
    print('Received message:', data)  

#捕获错误
@sio.on("error")
def on_error(e):
    print('Error:', e)  

TRACE_BUF = defaultdict(lambda: {
    "begin_printed": False,
    "stream_answer": []
})


def _pretty_print_end(d: dict):
    trace_id = d.get("trace_id", "")
    intent = d.get("intent", "")
    intent_id = d.get("intent_id", "")
    func = d.get("function", d.get("func", ""))
    slots = d.get("slots", {}) or {}
    answer = d.get("answer", "")
    cost = d.get("cost", 0)
    try:
        cost = f"{float(cost):.4f}s"
    except Exception:
        pass

    print("\n" + "=" * 70)
    print(f"TraceID : {trace_id}")
    print(f"Intent  : {intent} ({intent_id})")
    print(f"Func    : {func}")
    if slots:
        print("Slots   : " + json.dumps(slots, ensure_ascii=False))
    else:
        print("Slots   : -")
    print(f"Cost    : {cost}")
    print("-" * 70)
    print("Answer:")
    print(answer.strip() if isinstance(answer, str) else str(answer))
    print("=" * 70 + "\n")


#接收后端返回的 NLU 解析结果
@sio.on("request_nlu")
def on_response(raw):
    #反序列化：接收数据时用 json.loads() 转为 Python 字典
    try:
        data = json.loads(raw)
    except Exception:
        print("Response (raw):", raw)
        return

    trace_id = data.get("trace_id", "no-trace")
    frame = data.get("frame", "")
    status = data.get("status", None)

    buf = TRACE_BUF[trace_id]

    # BEGIN：只提示一行，减少噪音
    if frame == "BEGIN" or status == 0:
        if not buf["begin_printed"]:
            q = data.get("query", "")
            print(f"\n>>> [{trace_id}] {q}")
            buf["begin_printed"] = True
        return

    # 中间流式帧：拼接 answer
    if status == 1:
        chunk = data.get("answer") or data.get("frame") or ""
        if chunk:
            buf["stream_answer"].append(chunk)
        return

    # END：合并流式内容后打印
    if frame == "END" or status == 2:
        if buf["stream_answer"]:
            merged = "".join(buf["stream_answer"]).strip()
            if merged:
                data["answer"] = merged
        _pretty_print_end(data)
        TRACE_BUF.pop(trace_id, None)
        return

    # 兜底：打印一行
    print(f"[{trace_id}] {frame} status={status} -> {data}")


def rand_str(size=6):
    return "".join(random.sample("1234567890zyxwvutsrqponmlkjihgfedcba", size))


if __name__ == "__main__":

    data = {
        "sender_id": rand_str(9)
    }

    sio.connect(URL)

    while True:
        data["trace_id"] = rand_str(9)
        print("enter query: ")
        query = input().strip()
        data["query"] = query
        # 如果关闭：
        # 系统不会做多轮历史关联
        # 变成纯 NLU（单轮）模式
        data["enable_dm"] = True
        #通过 sio.emit("事件名", 数据) 向服务端发送事件
        #json.dumps序列化：将 Python 字典 data 转换成 JSON 字符串
        sio.emit("request_nlu", json.dumps(data, ensure_ascii=False))

    print("done")
