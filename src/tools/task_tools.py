"""
飞书多维表格工具封装
用于操作期末任务跟踪助手的数据
"""
import json
from typing import Any, Optional
from datetime import datetime
from langchain.tools import tool
from coze_workload_identity import Client
from cozeloop.decorator import observe

# 飞书多维表格配置
APP_TOKEN = "IQ1Bb3swGa6hcfs23wocKzW3nfb"
TASKS_TABLE_ID = "tblYSoijlxdXjVeJ"  # 任务总览表
DAILY_PLAN_TABLE_ID = "tblj59FZrlCq3gfB"  # 每日计划表


def get_access_token() -> str:
    """获取飞书访问令牌"""
    client = Client()
    access_token = client.get_integration_credential("integration-feishu-base")
    return access_token


class FeishuBitableClient:
    """飞书多维表格HTTP客户端"""
    
    BASE_URL = "https://open.larkoffice.com/open-apis"
    TIMEOUT = 30
    
    def __init__(self):
        self.access_token = get_access_token()
    
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
    
    @observe
    def _request(self, method: str, path: str, params: dict | None = None, json: dict | None = None) -> dict:
        """发送HTTP请求"""
        import requests
        try:
            url = f"{self.BASE_URL}{path}"
            resp = requests.request(method, url, headers=self._headers(), params=params, json=json, timeout=self.TIMEOUT)
            resp_data = resp.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"飞书API请求错误: {e}")
        
        if resp_data.get("code") != 0:
            raise Exception(f"飞书API错误: code={resp_data.get('code')}, msg={resp_data.get('msg')}")
        
        return resp_data
    
    @observe
    def list_records(self, table_id: str, page_size: int = 100) -> list[dict]:
        """获取表的所有记录"""
        all_records = []
        page_token = None
        
        while True:
            body = {"page_size": page_size}
            if page_token:
                body["page_token"] = page_token
            
            resp = self._request("POST", f"/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/search", json=body)
            items = resp.get("data", {}).get("items", [])
            all_records.extend(items)
            
            has_more = resp.get("data", {}).get("has_more", False)
            if not has_more:
                break
            page_token = resp.get("data", {}).get("page_token")
        
        return all_records
    
    @observe
    def add_records(self, table_id: str, records: list) -> list:
        """批量新增记录"""
        resp = self._request(
            "POST", 
            f"/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/batch_create",
            json={"records": records}
        )
        return resp.get("data", {}).get("records", [])
    
    @observe
    def update_records(self, table_id: str, records: list) -> list:
        """批量更新记录"""
        resp = self._request(
            "POST",
            f"/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/batch_update",
            json={"records": records}
        )
        return resp.get("data", {}).get("records", [])
    
    @observe
    def delete_records(self, table_id: str, record_ids: list) -> dict:
        """批量删除记录"""
        resp = self._request(
            "POST",
            f"/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/batch_delete",
            json={"record_ids": record_ids}
        )
        return resp
    
    @observe
    def list_fields(self, table_id: str) -> list:
        """获取表的所有字段"""
        resp = self._request("GET", f"/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/fields")
        return resp.get("data", {}).get("items", [])


# 全局客户端实例
_client: Optional[FeishuBitableClient] = None


def get_client() -> FeishuBitableClient:
    """获取飞书客户端单例"""
    global _client
    if _client is None:
        _client = FeishuBitableClient()
    return _client


def _convert_date_to_timestamp(date_str: str) -> int:
    """将日期字符串转换为毫秒时间戳"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp() * 1000)
    except ValueError:
        return 0


def _parse_timestamp(value: Any) -> str:
    """解析时间戳或日期值"""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000).strftime("%Y-%m-%d")
    return str(value) if value else ""


@tool
def get_all_tasks() -> str:
    """获取所有任务列表。用于查看任务总览，了解当前所有任务情况。
    Returns:
        所有任务的JSON列表，包含任务ID、任务名称、课程名称、任务类型、截止时间、进度、状态、优先级、预计工时、已用工时、备注等信息
    """
    client = get_client()
    try:
        records = client.list_records(TASKS_TABLE_ID)
        tasks = []
        for record in records:
            fields = record.get("fields", {})
            task = {
                "record_id": record.get("record_id"),
                "任务名称": fields.get("任务名称", ""),
                "课程名称": fields.get("课程名称", ""),
                "任务类型": fields.get("任务类型", ""),
                "截止时间": _parse_timestamp(fields.get("截止时间", "")),
                "进度": fields.get("进度", 0),
                "状态": fields.get("状态", "未开始"),
                "优先级": fields.get("优先级", "🟡中"),
                "预计工时": fields.get("预计工时", 0),
                "已用工时": fields.get("已用工时", 0),
                "备注": fields.get("备注", ""),
            }
            tasks.append(task)
        return json.dumps(tasks, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取任务列表失败: {str(e)}"


@tool
def add_task(
    course_name: str,
    task_name: str,
    task_type: str,
    deadline: str,
    priority: str,
    estimated_hours: float,
    description: str = ""
) -> str:
    """添加新任务。
    
    Args:
        course_name: 课程名称，如"高等数学"、"数据结构"
        task_name: 任务名称/标题
        task_type: 任务类型，只能是"作业"、"考试"、"论文"、"实验"、"展示"中的一个
        deadline: 截止时间，格式为YYYY-MM-DD
        priority: 优先级，只能是"🔴高"、"🟡中"、"🟢低"中的一个
        estimated_hours: 预计工时（小时）
        description: 备注描述（可选）
    
    Returns:
        添加结果，成功返回任务ID，失败返回错误信息
    """
    valid_types = ["作业", "考试", "论文", "实验", "展示"]
    valid_priorities = ["🔴高", "🟡中", "🟢低"]
    
    if task_type not in valid_types:
        return f"任务类型错误，有效值: {', '.join(valid_types)}"
    
    if priority not in valid_priorities:
        return f"优先级错误，有效值: {', '.join(valid_priorities)}"
    
    client = get_client()
    try:
        deadline_timestamp = _convert_date_to_timestamp(deadline)
        
        records = [{
            "fields": {
                "任务名称": task_name,
                "课程名称": course_name,
                "任务类型": task_type,
                "截止时间": deadline_timestamp,
                "进度": 0,
                "状态": "未开始",
                "优先级": priority,
                "预计工时": estimated_hours,
                "已用工时": 0,
                "备注": description,
            }
        }]
        
        result = client.add_records(TASKS_TABLE_ID, records)
        if result:
            record_id = result[0].get("record_id")
            return f"✅ 任务添加成功！\n📝 {task_name}\n📚 {course_name} | ⏰ {deadline}\n🎯 优先级: {priority}"
        return "任务添加失败"
    except Exception as e:
        return f"添加任务失败: {str(e)}"


@tool
def update_task(
    task_id: str,
    task_name: str = None,
    task_type: str = None,
    deadline: str = None,
    priority: str = None,
    estimated_hours: float = None,
    progress: int = None,
    status: str = None,
    used_hours: float = None,
    description: str = None
) -> str:
    """更新任务信息。
    
    Args:
        task_id: 任务ID（record_id）
        task_name: 新任务名称（可选）
        task_type: 新任务类型（可选）
        deadline: 新截止时间，格式为YYYY-MM-DD（可选）
        priority: 新优先级（可选）
        estimated_hours: 新预计工时（可选）
        progress: 新进度 0-100（可选）
        status: 新状态，如"未开始"、"进行中"、"待提交"、"已完成"、"已逾期"（可选）
        used_hours: 已用工时（可选）
        description: 新备注（可选）
    
    Returns:
        更新结果
    """
    if task_type:
        valid_types = ["作业", "考试", "论文", "实验", "展示"]
        if task_type not in valid_types:
            return f"任务类型错误，有效值: {', '.join(valid_types)}"
    
    if priority:
        valid_priorities = ["🔴高", "🟡中", "🟢低"]
        if priority not in valid_priorities:
            return f"优先级错误，有效值: {', '.join(valid_priorities)}"
    
    if status:
        valid_statuses = ["未开始", "进行中", "待提交", "已完成", "已逾期"]
        if status not in valid_statuses:
            return f"状态错误，有效值: {', '.join(valid_statuses)}"
    
    if progress is not None:
        if progress < 0 or progress > 100:
            return "进度必须在 0-100 之间"
    
    client = get_client()
    try:
        fields = {}
        if task_name is not None:
            fields["任务名称"] = task_name
        if task_type is not None:
            fields["任务类型"] = task_type
        if deadline is not None:
            fields["截止时间"] = _convert_date_to_timestamp(deadline)
        if priority is not None:
            fields["优先级"] = priority
        if estimated_hours is not None:
            fields["预计工时"] = estimated_hours
        if progress is not None:
            fields["进度"] = progress
        if status is not None:
            fields["状态"] = status
        if used_hours is not None:
            fields["已用工时"] = used_hours
        if description is not None:
            fields["备注"] = description
        
        if not fields:
            return "没有需要更新的字段"
        
        records = [{
            "record_id": task_id,
            "fields": fields
        }]
        
        client.update_records(TASKS_TABLE_ID, records)
        return f"✅ 任务更新成功！\n📊 进度: {progress}% | 状态: {status or '不变'}"
    except Exception as e:
        return f"更新任务失败: {str(e)}"


@tool
def delete_task(task_id: str) -> str:
    """删除任务。
    
    Args:
        task_id: 任务ID（record_id）
    
    Returns:
        删除结果
    """
    client = get_client()
    try:
        client.delete_records(TASKS_TABLE_ID, [task_id])
        return "🗑️ 任务删除成功！"
    except Exception as e:
        return f"删除任务失败: {str(e)}"


@tool
def get_daily_plan(date: str = None) -> str:
    """获取每日计划列表。
    
    Args:
        date: 日期，格式为YYYY-MM-DD，默认为今天
    
    Returns:
        每日计划的JSON列表
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    client = get_client()
    try:
        records = client.list_records(DAILY_PLAN_TABLE_ID)
        plans = []
        for record in records:
            fields = record.get("fields", {})
            plan_date = _parse_timestamp(fields.get("日期", ""))
            
            if date and plan_date != date:
                continue
                
            plan = {
                "record_id": record.get("record_id"),
                "日期": plan_date,
                "关联任务ID": fields.get("关联任务", ""),
                "今日目标": fields.get("今日目标", ""),
                "预计用时": fields.get("预计用时", 0),
                "实际用时": fields.get("实际用时", 0),
                "完成状态": fields.get("完成状态", "未开始"),
            }
            plans.append(plan)
        return json.dumps(plans, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取每日计划失败: {str(e)}"


@tool
def add_daily_plan(
    date: str,
    task_id: str,
    today_goal: str,
    planned_hours: float
) -> str:
    """添加每日计划。
    
    Args:
        date: 日期，格式为YYYY-MM-DD
        task_id: 关联的任务ID
        today_goal: 今日目标描述
        planned_hours: 预计用时（小时）
    
    Returns:
        添加结果
    """
    client = get_client()
    try:
        date_timestamp = _convert_date_to_timestamp(date)
        
        records = [{
            "fields": {
                "日期": date_timestamp,
                "关联任务": task_id,
                "今日目标": today_goal,
                "预计用时": planned_hours,
                "实际用时": 0,
                "完成状态": "未开始",
            }
        }]
        
        result = client.add_records(DAILY_PLAN_TABLE_ID, records)
        if result:
            record_id = result[0].get("record_id")
            return f"✅ 每日计划添加成功！\n🎯 {today_goal}\n⏰ 预计 {planned_hours} 小时"
        return "每日计划添加失败"
    except Exception as e:
        return f"添加每日计划失败: {str(e)}"


@tool
def update_daily_plan(
    plan_id: str,
    actual_hours: float = None,
    status: str = None,
    today_goal: str = None
) -> str:
    """更新每日计划进度。
    
    Args:
        plan_id: 计划ID（record_id）
        actual_hours: 实际用时（可选）
        status: 完成状态，如"未开始"、"进行中"、"已完成"（可选）
        today_goal: 今日目标（可选）
    
    Returns:
        更新结果
    """
    if status:
        valid_statuses = ["未开始", "进行中", "已完成"]
        if status not in valid_statuses:
            return f"状态错误，有效值: {', '.join(valid_statuses)}"
    
    client = get_client()
    try:
        fields = {}
        if actual_hours is not None:
            fields["实际用时"] = actual_hours
        if status is not None:
            fields["完成状态"] = status
        if today_goal is not None:
            fields["今日目标"] = today_goal
        
        if not fields:
            return "没有需要更新的字段"
        
        records = [{
            "record_id": plan_id,
            "fields": fields
        }]
        
        client.update_records(DAILY_PLAN_TABLE_ID, records)
        return f"✅ 每日计划更新成功！\n📊 状态: {status or '不变'}"
    except Exception as e:
        return f"更新每日计划失败: {str(e)}"


@tool
def generate_daily_plan_suggestion(date: str = None) -> str:
    """根据任务紧急度和优先级生成每日任务建议。
    该工具会分析所有未完成任务，按DDL紧急程度和优先级排序，生成每日任务建议。
    
    Args:
        date: 日期，格式为YYYY-MM-DD，默认为今天
    
    Returns:
        每日任务建议列表（JSON格式）
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    client = get_client()
    try:
        records = client.list_records(TASKS_TABLE_ID)
        
        pending_tasks = []
        today = datetime.now()
        
        for record in records:
            fields = record.get("fields", {})
            status = fields.get("状态", "未开始")
            
            if status in ["已完成", "已逾期"]:
                continue
            
            deadline = fields.get("截止时间", "")
            deadline_str = _parse_timestamp(deadline)
            
            try:
                deadline_dt = datetime.strptime(deadline_str, "%Y-%m-%d")
            except:
                deadline_dt = today
            
            days_until_deadline = (deadline_dt - today).days
            progress = fields.get("进度", 0)
            
            # 风险评分
            risk_level = ""
            if days_until_deadline <= 1 and status == "未开始":
                risk_level = "🔴紧急"
            elif days_until_deadline <= 3 and progress < 50:
                risk_level = "🟡警告"
            elif days_until_deadline <= 7 and progress < 30:
                risk_level = "🟡关注"
            
            # 优先级权重
            priority = fields.get("优先级", "🟡中")
            priority_weight = {"🔴高": 1.5, "🟡中": 1.0, "🟢低": 0.5}.get(priority, 1.0)
            
            # 紧急度评分
            if days_until_deadline < 0:
                urgency_score = 100 + abs(days_until_deadline)
            elif days_until_deadline == 0:
                urgency_score = 95
            elif days_until_deadline == 1:
                urgency_score = 85
            elif days_until_deadline <= 3:
                urgency_score = 70
            elif days_until_deadline <= 7:
                urgency_score = 50
            else:
                urgency_score = 30
            
            total_score = urgency_score * priority_weight
            
            task = {
                "record_id": record.get("record_id"),
                "任务名称": fields.get("任务名称", ""),
                "课程名称": fields.get("课程名称", ""),
                "任务类型": fields.get("任务类型", ""),
                "截止时间": deadline_str,
                "优先级": priority,
                "进度": progress,
                "状态": status,
                "距截止天数": days_until_deadline,
                "预计工时": fields.get("预计工时", 0),
                "紧急度评分": round(total_score, 2),
                "风险等级": risk_level,
            }
            pending_tasks.append(task)
        
        # 按综合评分排序
        pending_tasks.sort(key=lambda x: x["紧急度评分"], reverse=True)
        
        # 生成建议
        suggestions = []
        max_daily_hours = 8
        total_planned_hours = 0
        
        for task in pending_tasks[:5]:
            estimated = task["预计工时"]
            if total_planned_hours + estimated <= max_daily_hours:
                task["建议优先级"] = len(suggestions) + 1
                task["建议用时"] = estimated
                suggestions.append(task)
                total_planned_hours += estimated
        
        return json.dumps({
            "日期": date,
            "建议任务数": len(suggestions),
            "建议总工时": total_planned_hours,
            "任务建议": suggestions
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"生成每日计划建议失败: {str(e)}"


@tool
def get_risk_warning() -> str:
    """获取风险预警信息。
    检测即将逾期和高优先级任务，按照风险评分逻辑：
    - DDL距今≤1天 + 未开始 → 🔴紧急
    - DDL距今≤3天 + 进度<50% → 🟡警告
    - DDL距今≤7天 + 进度<30% → 🟡关注
    
    Returns:
        风险预警列表（JSON格式）
    """
    client = get_client()
    try:
        records = client.list_records(TASKS_TABLE_ID)
        
        warnings = []
        today = datetime.now()
        
        for record in records:
            fields = record.get("fields", {})
            status = fields.get("状态", "未开始")
            
            if status in ["已完成", "已逾期"]:
                continue
            
            deadline = fields.get("截止时间", "")
            deadline_str = _parse_timestamp(deadline)
            priority = fields.get("优先级", "🟡中")
            progress = fields.get("进度", 0)
            
            try:
                deadline_dt = datetime.strptime(deadline_str, "%Y-%m-%d")
            except:
                continue
            
            days_until = (deadline_dt - today).days
            
            warning_level = ""
            warning_msg = ""
            
            # 风险评分逻辑
            if days_until <= 1 and status == "未开始":
                warning_level = "🔴紧急"
                warning_msg = "明天截止！还没开始！"
            elif days_until <= 3 and progress < 50:
                warning_level = "🟡警告"
                warning_msg = f"还有{days_until}天截止，进度{progress}%太慢"
            elif days_until <= 7 and progress < 30:
                warning_level = "🟡关注"
                warning_msg = f"一周内截止，进度{progress}%"
            elif days_until < 0:
                warning_level = "🔴逾期"
                warning_msg = f"已逾期{abs(days_until)}天！"
            
            # 高优先级未开始
            if priority == "🔴高" and status == "未开始":
                if not warning_level:
                    warning_level = "⚠️注意"
                    warning_msg = "高优先级任务还没开始"
                else:
                    warning_msg += " | 高优先级"
            
            if warning_level:
                warning = {
                    "record_id": record.get("record_id"),
                    "任务名称": fields.get("任务名称", ""),
                    "课程名称": fields.get("课程名称", ""),
                    "任务类型": fields.get("任务类型", ""),
                    "截止时间": deadline_str,
                    "优先级": priority,
                    "进度": progress,
                    "状态": status,
                    "距截止天数": days_until,
                    "预警级别": warning_level,
                    "预警原因": warning_msg,
                }
                warnings.append(warning)
        
        # 按紧急程度排序
        warnings.sort(key=lambda x: x["距截止天数"])
        
        return json.dumps({
            "预警任务数": len(warnings),
            "预警列表": warnings
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取风险预警失败: {str(e)}"


@tool
def get_task_statistics() -> str:
    """获取任务统计概览。
    按课程、状态、优先级分类统计任务数量和完成进度。
    
    Returns:
        任务统计信息（JSON格式）
    """
    client = get_client()
    try:
        records = client.list_records(TASKS_TABLE_ID)
        
        stats = {
            "总数": 0,
            "已完成": 0,
            "进行中": 0,
            "未开始": 0,
            "待提交": 0,
            "已逾期": 0,
            "按课程": {},
            "按任务类型": {},
            "按优先级": {},
        }
        
        for record in records:
            fields = record.get("fields", {})
            status = fields.get("状态", "未开始")
            course = fields.get("课程名称", "未分类")
            task_type = fields.get("任务类型", "未分类")
            priority = fields.get("优先级", "🟡中")
            
            stats["总数"] += 1
            
            # 按状态统计
            if status == "已完成":
                stats["已完成"] += 1
            elif status == "进行中":
                stats["进行中"] += 1
            elif status == "未开始":
                stats["未开始"] += 1
            elif status == "待提交":
                stats["待提交"] += 1
            elif status == "已逾期":
                stats["已逾期"] += 1
            
            # 按课程统计
            if course not in stats["按课程"]:
                stats["按课程"][course] = {"总数": 0, "已完成": 0, "进行中": 0, "未开始": 0}
            stats["按课程"][course]["总数"] += 1
            if status == "已完成":
                stats["按课程"][course]["已完成"] += 1
            elif status == "进行中":
                stats["按课程"][course]["进行中"] += 1
            else:
                stats["按课程"][course]["未开始"] += 1
            
            # 按任务类型统计
            if task_type not in stats["按任务类型"]:
                stats["按任务类型"][task_type] = {"总数": 0, "已完成": 0}
            stats["按任务类型"][task_type]["总数"] += 1
            if status == "已完成":
                stats["按任务类型"][task_type]["已完成"] += 1
            
            # 按优先级统计
            if priority not in stats["按优先级"]:
                stats["按优先级"][priority] = {"总数": 0, "已完成": 0, "待处理": 0}
            stats["按优先级"][priority]["总数"] += 1
            if status == "已完成":
                stats["按优先级"][priority]["已完成"] += 1
            else:
                stats["按优先级"][priority]["待处理"] += 1
        
        # 计算完成率
        if stats["总数"] > 0:
            stats["总完成率"] = f"{stats['已完成'] / stats['总数'] * 100:.1f}%"
        else:
            stats["总完成率"] = "0%"
        
        # 计算各课程的完成率
        for course, data in stats["按课程"].items():
            if data["总数"] > 0:
                data["完成率"] = f"{data['已完成'] / data['总数'] * 100:.1f}%"
            else:
                data["完成率"] = "0%"
        
        return json.dumps(stats, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取任务统计失败: {str(e)}"
