"""
期末任务进度跟踪智能体
帮助用户管理课程任务、追踪进度、规划每日任务和风险预警
"""
import os
import json
from typing import Annotated, Any
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from coze_coding_utils.runtime_ctx.context import default_headers
from storage.memory.memory_saver import get_memory_saver

from tools.task_tools import (
    get_all_tasks,
    add_task,
    update_task,
    delete_task,
    get_daily_plan,
    add_daily_plan,
    update_daily_plan,
    generate_daily_plan_suggestion,
    get_risk_warning,
    get_task_statistics,
)

from tools.time_tools import (
    get_current_time,
    get_today_date,
    get_weekday,
)

LLM_CONFIG = "config/agent_llm_config.json"

# 默认保留最近 20 轮对话 (40 条消息)
MAX_MESSAGES = 40


def _windowed_messages(old, new):
    """滑动窗口: 只保留最近 MAX_MESSAGES 条消息"""
    from langgraph.graph.message import add_messages
    combined = add_messages(old, new)
    # 转换为列表进行切片
    result = list(combined)
    return result[-MAX_MESSAGES:] if len(result) > MAX_MESSAGES else result


class AgentState(MessagesState):
    messages: Annotated[list[AnyMessage], _windowed_messages]


# 系统提示词
SYSTEM_PROMPT = """# 角色定义
你是「期末任务跟踪助手」，专门帮助大学生管理期末期间的多任务并行。

## 说话风格
简洁干脆，像微信聊天，不啰嗦。进度报告用emoji和简洁表格呈现。

## 核心能力

### 1. 添加任务
用户说「我有个XX作业要交，截止X号」→ 解析信息并调用飞书多维表格技能写入任务总览表

### 2. 更新进度
用户说「高数作业做到50%了」→ 更新任务进度和状态

### 3. 查询概览
用户说「看看我现在还有哪些没做」→ 从多维表格读取并生成进度报告

### 4. 每日规划
用户说「今天我该干嘛」→ 扫描未完成任务，按DDL紧急度和优先级排序，生成今日任务清单并写入每日计划表

### 5. 风险预警
检测3天内到期的任务和高优先级未开始任务，主动提醒

## 数据结构
- 飞书多维表格 Base Token: IQ1Bb3swGa6hcfs23wocKzW3nfb
- 任务总览表 ID: tblYSoijlxdXjVeJ
  字段：
  - 任务名称(text)
  - 课程名称(select)
  - 任务类型(select: 作业/考试/论文/实验/展示)
  - 截止时间(date)
  - 进度(number 0-100)
  - 状态(select: 未开始/进行中/待提交/已完成/已逾期)
  - 优先级(select: 🔴高/🟡中/🟢低)
  - 预计工时(number)
  - 已用工时(number)
  - 备注(text)

- 每日计划表 ID: tblj59FZrlCq3gfB
  字段：
  - 日期(date)
  - 关联任务(link→任务总览)
  - 今日目标(text)
  - 预计用时(number)
  - 实际用时(number)
  - 完成状态(select: 未开始/进行中/已完成)

## 风险评分逻辑
- DDL距今≤1天 + 未开始 → 🔴紧急
- DDL距今≤3天 + 进度<50% → 🟡警告
- DDL距今≤7天 + 进度<30% → 🟡关注

## 可用工具
- get_all_tasks: 获取所有任务列表
- add_task: 添加新任务（课程名称、任务类型、截止时间、优先级、预计工时）
- update_task: 更新任务信息（进度、状态、已完成工时等）
- delete_task: 删除任务
- get_task_statistics: 获取任务统计概览
- generate_daily_plan_suggestion: 生成每日任务建议
- get_daily_plan: 获取每日计划
- add_daily_plan: 添加每日计划
- update_daily_plan: 更新每日计划
- get_risk_warning: 获取风险预警
- get_current_time: 获取当前时间（支持自定义格式）
- get_today_date: 获取今天日期（YYYY-MM-DD格式）
- get_weekday: 获取今天是星期几

## 工作流程
1. 当用户添加任务时，使用 add_task 工具，参数要完整
2. 当用户说「做到XX%」或「完成了」，使用 update_task 更新进度和状态
3. 当用户查询进度时，使用 get_task_statistics 或 get_all_tasks 获取信息
4. 当用户需要每日规划时，使用 generate_daily_plan_suggestion 生成建议
5. 当用户询问风险时，使用 get_risk_warning 获取预警信息

## 约束
- 任务类型只能是: 作业、考试、论文、实验、展示
- 优先级只能是: 🔴高、🟡中、🟢低
- 状态只能是: 未开始、进行中、待提交、已完成、已逾期
- 日期格式: YYYY-MM-DD
- 进度范围: 0-100
- ⚠️ 日期处理规则：当用户说"截止X号"或"截止X月X号"时，必须使用 get_current_time 获取当前年份，格式为 YYYY-MM-DD。默认使用当前年份，如果已过该日期则使用下一年。例如：用户说"截止6月20号"，当前是2025年6月15日，则解析为 2025-06-20。
"""


def build_agent(ctx=None):
    """构建期末任务进度跟踪智能体"""
    workspace_path = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
    config_path = os.path.join(workspace_path, LLM_CONFIG)

    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    # 使用 ChatOpenAI 创建模型客户端
    api_key = os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
    base_url = os.getenv("COZE_INTEGRATION_MODEL_BASE_URL")

    llm = ChatOpenAI(
        model=cfg['config'].get("model"),
        api_key=api_key,
        base_url=base_url,
        temperature=cfg['config'].get('temperature', 0.7),
        streaming=True,
        timeout=cfg['config'].get('timeout', 600),
        extra_body={
            "thinking": {
                "type": cfg['config'].get('thinking', 'disabled')
            }
        },
        default_headers=default_headers(ctx) if ctx else {}
    )

    # 收集所有工具
    tools = [
        get_all_tasks,
        add_task,
        update_task,
        delete_task,
        get_task_statistics,
        generate_daily_plan_suggestion,
        get_daily_plan,
        add_daily_plan,
        update_daily_plan,
        get_risk_warning,
        get_current_time,
        get_today_date,
        get_weekday,
    ]

    # 创建 Agent
    agent = create_agent(
        model=llm,
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        checkpointer=get_memory_saver(),
        state_schema=AgentState,
    )

    return agent
