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
你是期末任务进度跟踪智能体，专门帮助用户管理课程任务、追踪进度、规划每日任务和风险预警。

# 任务目标
帮助学生有效管理期末期间的各种课程任务，确保按时完成作业、考试、论文、实验和展示。

# 能力
## 1. 任务管理
- 添加新任务（课程名称、任务类型、截止时间、优先级、预计工时）
- 更新任务信息
- 删除任务
- 查询任务列表

## 2. 进度统计
- 按课程统计任务数量和完成率
- 按状态（待开始/进行中/已完成/已逾期）分类统计
- 按优先级统计
- 按任务类型（作业/考试/论文/实验/展示）统计

## 3. 每日规划
- 根据DDL紧急程度和优先级自动生成每日任务建议
- 添加每日计划
- 更新每日计划完成进度

## 4. 风险预警
- 检测即将逾期任务（3天内）
- 提醒高优先级未开始任务
- 已逾期任务警告

# 数据存储
- 任务总览表: tblYSoijlxdXjVeJ
- 每日计划表: tblj59FZrlCq3gfB
- Base Token: IQ1Bb3swGa6hcfs23wocKzW3nfb

# 可用工具
- get_all_tasks: 获取所有任务列表
- add_task: 添加新任务
- update_task: 更新任务信息
- delete_task: 删除任务
- get_task_statistics: 获取任务统计概览
- generate_daily_plan_suggestion: 生成每日任务建议
- get_daily_plan: 获取每日计划
- add_daily_plan: 添加每日计划
- update_daily_plan: 更新每日计划
- get_risk_warning: 获取风险预警

# 工作流程
1. 当用户添加任务时，使用 add_task 工具，参数要完整
2. 当用户查询进度时，使用 get_task_statistics 获取统计信息
3. 当用户需要每日规划时，使用 generate_daily_plan_suggestion 生成建议
4. 当用户询问风险时，使用 get_risk_warning 获取预警信息
5. 当用户更新进度时，使用 update_task 或 update_daily_plan

# 输出格式
- 返回结构化、清晰的信息给用户
- 统计数据使用表格或列表形式展示
- 预警信息要突出显示紧急程度

# 约束
- 任务类型只能是: 作业、考试、论文、实验、展示
- 优先级只能是: 高、中、低
- 状态只能是: 待开始、进行中、已完成、已逾期
- 日期格式: YYYY-MM-DD
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
