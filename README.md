# Customer Service Agent Function Calling

一个基于 Python 的多轮客服 Agent 示例项目，演示如何把大模型的 Function Calling 能力接入真实业务工具，实现订单查询、退货政策查询、情绪分流和人工客服转接。

## 项目简介

本项目的核心目标是展示一个 Agent 工程的基本分层：

- `tool/schemas.py`：定义暴露给大模型的工具协议。
- `tool/tool_map.py`：维护工具名称到真实执行函数的映射。
- `tool/executors.py`：封装真实业务函数，目前使用 mock 数据。
- `tool/runner.py`：执行 Function Calling 编排，解析模型返回的 `tool_calls`，调用工具，并把工具结果返回给模型。
- `start.py`：SocketIO 服务入口，负责接收用户请求、维护多轮状态、分流到聊天或任务执行。

适合用于学习：

- Function Calling / Tool Calling 的工程落地方式
- Agent 工具调用链路
- 多轮对话中的参数追问与 pending 状态管理
- 客服场景中的高风险情绪识别与人工转接

## 功能特性

- 支持订单状态查询，例如 `ORD-1234`
- 支持退货政策查询
- 支持缺少订单号时自动追问
- 支持 Redis 保存多轮上下文和 pending 状态
- 支持高风险关键词触发人工客服转接
- 支持大模型自动选择工具并进行多步调用

## 项目结构

```text
.
├── client/
│   ├── arbitration.py      # 情绪分流/仲裁
│   ├── correlation.py      # 多轮相关性判断
│   ├── nlg.py              # 自然语言生成封装
│   ├── rewrite.py          # 多轮 query 改写
│   └── stream_chat.py      # 流式聊天接口
├── tool/
│   ├── executors.py        # 真实工具执行函数
│   ├── runner.py           # Function Calling 执行器
│   ├── schemas.py          # 工具 schema 定义
│   └── tool_map.py         # 工具映射表
├── utils/
│   ├── logger.py           # 日志封装
│   └── redis_tool.py       # Redis 客户端封装
├── dialog.py               # 命令行 SocketIO 测试客户端
├── prompts.py              # Prompt 模板
├── start.py                # 服务入口
├── requirements.txt        # Python 依赖
└── server.sh               # 原始启动脚本
```

## 核心流程

1. 用户通过 SocketIO 发送请求到 `start.py`。
2. 系统读取 Redis 中的上一轮对话状态。
3. `rewrite.py` 根据历史对话改写用户 query。
4. `arbitration.py` 判断是否需要转人工。
5. 如果命中订单/退货规则，直接调用业务工具。
6. 如果规则无法覆盖，则进入 `tool/runner.py` 的 Function Calling 编排流程。
7. Runner 将工具执行结果作为 `role=tool` 消息返回给大模型。
8. 大模型结合工具结果生成最终回复。

## Function Calling 分层说明

### 1. 工具协议：`tool/schemas.py`

这里定义模型可以看到的工具名称、描述和参数结构。例如：

- `get_order_status`
- `check_refund_policy`
- `escalate_to_human`

### 2. 工具映射：`tool/tool_map.py`

模型只会返回工具名称，Python 需要知道这个名称对应哪个函数：

```python
TOOL_EXECUTORS = {
    "get_order_status": get_order_status,
    "check_refund_policy": check_refund_policy,
    "escalate_to_human": escalate_to_human
}
```

### 3. 工具执行：`tool/executors.py`

这里是真正执行业务逻辑的地方。目前是 mock 实现，后续可以替换成数据库、RPC 或 HTTP 服务。

### 4. 编排执行：`tool/runner.py`

Runner 负责：

- 请求大模型
- 解析 `tool_calls`
- 校验工具名称
- 归一化参数
- 执行业务工具
- 把工具结果喂回大模型
- 循环直到模型输出最终答案

## 环境变量

项目依赖以下环境变量：

```bash
API_KEY=你的模型 API Key
BASE_URL=模型接口地址
BOT_URL=聊天 Bot 接口地址
ENTRY_URL=SocketIO 服务地址
FLASK_SERVER_PORT=8081
```

其中 `FLASK_SERVER_PORT` 可选，默认端口为 `8081`。

## 运行方式

安装依赖：

```bash
pip install -r requirements.txt
```

启动 Redis：

```bash
redis-server
```

启动服务：

```bash
python start.py
```

启动命令行测试客户端：

```bash
set ENTRY_URL=http://127.0.0.1:8081
python dialog.py
```

Linux/macOS 下设置环境变量可使用：

```bash
export ENTRY_URL=http://127.0.0.1:8081
```

## 示例对话

订单号完整时：

```text
用户：帮我查一下订单 ORD-1234 的状态
系统：已查询到订单 ORD-1234 当前状态：已发货。
```

缺少订单号时：

```text
用户：帮我查一下快递
系统：请提供您的订单号，例如 ORD-9999。
用户：ORD-1234
系统：已查询到订单 ORD-1234 当前状态：已发货。
```

退货咨询：

```text
用户：我的蓝牙耳机 ORD-1234 有质量问题，能退货吗？
系统：订单 ORD-1234 当前状态：已发货。商品品类：电子产品，退货政策：7 天内支持无理由退货。
```

## 当前状态

这个仓库更偏向 Agent 工程学习 Demo，部分模块仍保留原始项目中的外部依赖。

当前需要注意：

- `config/config.py` 未包含在仓库中，需要自行补充模型配置。
- `client/reject.py` 和 `client/nlu.py` 在当前目录中不存在，但 `start.py` 中仍有历史导入。
- `requirements.txt` 来自完整环境，包含较多与当前 Demo 无关的依赖，实际部署时建议精简。
- `server.sh` 引用了当前目录不存在的 `train`、`function_call` 目录，不能直接作为完整部署脚本使用。

## 后续优化方向

- 补齐配置模板，例如 `.env.example`
- 精简依赖文件
- 拆分旧 NLU 逻辑和当前客服 Agent 逻辑
- 为 `tool/runner.py` 增加单元测试
- 将 mock executor 替换为真实业务 API
- 增加 README 中的架构图和调用时序图

