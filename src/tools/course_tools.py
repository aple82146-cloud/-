"""
课程表和代办事项工具封装
用于管理课程表和日常代办事项
"""
import json
from typing import Any, Optional
from datetime import datetime, timedelta
from langchain.tools import tool
from coze_workload_identity import Client
from cozeloop.decorator import observe

# 飞书多维表格配置
APP_TOKEN = "IQ1Bb3swGa6hcfs23wocKzW3nfb"
COURSE_TABLE_ID = "tblCourseSchedule"  # 课程表（需要创建）
TODO_TABLE_ID = "tblTodoItems"  # 代办事项（需要创建）


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
    def list_tables(self) -> list:
        """获取Base下所有表"""
        resp = self._request("GET", f"/bitable/v1/apps/{APP_TOKEN}/tables")
        return resp.get("data", {}).get("items", [])
    
    @observe
    def create_table(self, table_name: str, fields: list) -> dict:
        """创建新表"""
        resp = self._request(
            "POST",
            f"/bitable/v1/apps/{APP_TOKEN}/tables",
            json={"table_name": table_name, "fields": fields}
        )
        return resp.get("data", {})
    
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


# ============ 课程表工具 ============

@tool
def get_course_schedule(weekday: str = None) -> str:
    """获取课程表。
    
    Args:
        weekday: 星期几（如"星期一"、"周二"），为空则返回整周课程
    
    Returns:
        课程表JSON列表
    """
    client = get_client()
    try:
        records = client.list_records(COURSE_TABLE_ID)
        courses = []
        
        for record in records:
            fields = record.get("fields", {})
            course_weekday = fields.get("星期", "")
            
            # 星期匹配
            if weekday:
                weekday_clean = weekday.replace("周", "").replace("星期", "")
                if weekday_clean not in course_weekday and course_weekday not in weekday:
                    continue
            
            course = {
                "record_id": record.get("record_id"),
                "课程名称": fields.get("课程名称", ""),
                "星期": course_weekday,
                "开始时间": fields.get("开始时间", ""),
                "结束时间": fields.get("结束时间", ""),
                "上课地点": fields.get("上课地点", ""),
                "授课老师": fields.get("授课老师", ""),
                "周次": fields.get("周次", ""),
            }
            courses.append(course)
        
        return json.dumps({"课程数": len(courses), "课程列表": courses}, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取课程表失败: {str(e)}"


@tool
def add_course(
    course_name: str,
    weekday: str,
    start_time: str,
    end_time: str,
    location: str = "",
    teacher: str = "",
    week_range: str = ""
) -> str:
    """添加课程到课表。
    
    Args:
        course_name: 课程名称
        weekday: 星期几（如"周一"、"星期三"）
        start_time: 开始时间（如"09:00"）
        end_time: 结束时间（如"10:30"）
        location: 上课地点（可选）
        teacher: 授课老师（可选）
        week_range: 周次范围（如"1-16周"、"单周"）（可选）
    
    Returns:
        添加结果
    """
    client = get_client()
    try:
        records = [{
            "fields": {
                "课程名称": course_name,
                "星期": weekday,
                "开始时间": start_time,
                "结束时间": end_time,
                "上课地点": location,
                "授课老师": teacher,
                "周次": week_range,
            }
        }]
        
        result = client.add_records(COURSE_TABLE_ID, records)
        if result:
            return f"✅ 课程添加成功！\n📚 {course_name}\n📅 {weekday} {start_time}-{end_time}\n📍 {location or '未指定'}"
        return "课程添加失败"
    except Exception as e:
        return f"添加课程失败: {str(e)}"


@tool
def delete_course(course_id: str) -> str:
    """删除课程。
    
    Args:
        course_id: 课程ID（record_id）
    
    Returns:
        删除结果
    """
    client = get_client()
    try:
        client.delete_records(COURSE_TABLE_ID, [course_id])
        return "🗑️ 课程删除成功！"
    except Exception as e:
        return f"删除课程失败: {str(e)}"


# ============ 代办事项工具 ============

@tool
def get_todo_list(category: str = None) -> str:
    """获取代办事项列表。
    
    Args:
        category: 分类（可选），如"生活"、"学习"、"工作"等
    
    Returns:
        代办事项JSON列表
    """
    client = get_client()
    try:
        records = client.list_records(TODO_TABLE_ID)
        todos = []
        
        for record in records:
            fields = record.get("fields", {})
            todo_category = fields.get("分类", "")
            
            if category and category not in todo_category:
                continue
            
            todo = {
                "record_id": record.get("record_id"),
                "事项内容": fields.get("事项内容", ""),
                "分类": todo_category,
                "优先级": fields.get("优先级", "🟡中"),
                "截止时间": _parse_timestamp(fields.get("截止时间", "")),
                "状态": fields.get("状态", "待办"),
                "关联任务ID": fields.get("关联任务", ""),
            }
            todos.append(todo)
        
        return json.dumps({"事项数": len(todos), "代办列表": todos}, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取代办事项失败: {str(e)}"


@tool
def add_todo(
    content: str,
    category: str = "其他",
    priority: str = "🟡中",
    deadline: str = None,
    task_id: str = None
) -> str:
    """添加代办事项。
    
    Args:
        content: 事项内容
        category: 分类（可选），如"生活"、"学习"、"工作"、"购物"等
        priority: 优先级（可选），如"🔴高"、"🟡中"、"🟢低"
        deadline: 截止时间（可选），格式为YYYY-MM-DD
        task_id: 关联的任务ID（可选）
    
    Returns:
        添加结果
    """
    valid_priorities = ["🔴高", "🟡中", "🟢低"]
    
    if priority not in valid_priorities:
        return f"优先级错误，有效值: {', '.join(valid_priorities)}"
    
    client = get_client()
    try:
        fields = {
            "事项内容": content,
            "分类": category,
            "优先级": priority,
            "状态": "待办",
        }
        
        if deadline:
            fields["截止时间"] = _convert_date_to_timestamp(deadline)
        
        if task_id:
            fields["关联任务"] = task_id
        
        records = [{"fields": fields}]
        
        result = client.add_records(TODO_TABLE_ID, records)
        if result:
            return f"✅ 代办事项添加成功！\n📝 {content}\n🏷️ 分类: {category} | 🎯 优先级: {priority}"
        return "代办事项添加失败"
    except Exception as e:
        return f"添加代办事项失败: {str(e)}"


@tool
def update_todo(
    todo_id: str,
    content: str = None,
    category: str = None,
    priority: str = None,
    deadline: str = None,
    status: str = None
) -> str:
    """更新代办事项。
    
    Args:
        todo_id: 代办事项ID（record_id）
        content: 事项内容（可选）
        category: 分类（可选）
        priority: 优先级（可选）
        deadline: 截止时间（可选）
        status: 状态（可选），如"待办"、"进行中"、"已完成"
    
    Returns:
        更新结果
    """
    if status:
        valid_statuses = ["待办", "进行中", "已完成"]
        if status not in valid_statuses:
            return f"状态错误，有效值: {', '.join(valid_statuses)}"
    
    client = get_client()
    try:
        fields = {}
        if content is not None:
            fields["事项内容"] = content
        if category is not None:
            fields["分类"] = category
        if priority is not None:
            fields["优先级"] = priority
        if deadline is not None:
            fields["截止时间"] = _convert_date_to_timestamp(deadline)
        if status is not None:
            fields["状态"] = status
        
        if not fields:
            return "没有需要更新的字段"
        
        records = [{"record_id": todo_id, "fields": fields}]
        
        client.update_records(TODO_TABLE_ID, records)
        return f"✅ 代办事项更新成功！\n📊 状态: {status or '不变'}"
    except Exception as e:
        return f"更新代办事项失败: {str(e)}"


@tool
def delete_todo(todo_id: str) -> str:
    """删除代办事项。
    
    Args:
        todo_id: 代办事项ID（record_id）
    
    Returns:
        删除结果
    """
    client = get_client()
    try:
        client.delete_records(TODO_TABLE_ID, [todo_id])
        return "🗑️ 代办事项删除成功！"
    except Exception as e:
        return f"删除代办事项失败: {str(e)}"


@tool
def get_today_schedule() -> str:
    """获取今日课程和待办事项综合视图。
    整合课程表和代办事项，生成一日安排。
    
    Returns:
        今日综合安排JSON
    """
    client = get_client()
    today = datetime.now()
    weekday_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
    today_weekday = weekday_map[today.weekday()]
    today_str = today.strftime("%Y-%m-%d")
    
    result = {
        "日期": today_str,
        "星期": today_weekday,
        "课程": [],
        "待办事项": [],
        "期末任务": [],
    }
    
    try:
        # 获取今日课程
        course_records = client.list_records(COURSE_TABLE_ID)
        for record in course_records:
            fields = record.get("fields", {})
            if today_weekday in fields.get("星期", ""):
                result["课程"].append({
                    "record_id": record.get("record_id"),
                    "课程名称": fields.get("课程名称", ""),
                    "时间": f"{fields.get('开始时间', '')}-{fields.get('结束时间', '')}",
                    "地点": fields.get("上课地点", ""),
                })
        
        # 获取今日待办
        todo_records = client.list_records(TODO_TABLE_ID)
        for record in todo_records:
            fields = record.get("fields", {})
            deadline = _parse_timestamp(fields.get("截止时间", ""))
            if not deadline or deadline == today_str:
                result["待办事项"].append({
                    "record_id": record.get("record_id"),
                    "内容": fields.get("事项内容", ""),
                    "分类": fields.get("分类", ""),
                    "优先级": fields.get("优先级", "🟡中"),
                    "状态": fields.get("状态", "待办"),
                })
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取今日安排失败: {str(e)}"


@tool
def initialize_tables() -> str:
    """初始化课程表和代办事项表。
    如果表不存在，自动创建所需字段。
    
    Returns:
        初始化结果
    """
    client = get_client()
    try:
        # 检查现有表
        existing_tables = client.list_tables()
        existing_table_ids = {t.get("name", ""): t.get("table_id", "") for t in existing_tables}
        
        result_messages = []
        
        # 创建课程表（如果不存在）
        if "课程表" not in existing_table_ids:
            course_fields = [
                {"field_name": "课程名称", "type": 1},
                {"field_name": "星期", "type": 3},
                {"field_name": "开始时间", "type": 1},
                {"field_name": "结束时间", "type": 1},
                {"field_name": "上课地点", "type": 1},
                {"field_name": "授课老师", "type": 1},
                {"field_name": "周次", "type": 1},
            ]
            new_table = client.create_table("课程表", course_fields)
            result_messages.append(f"✅ 课程表创建成功，ID: {new_table.get('table_id', '')}")
        else:
            result_messages.append("📋 课程表已存在")
        
        # 创建代办事项表（如果不存在）
        if "代办事项" not in existing_table_ids:
            todo_fields = [
                {"field_name": "事项内容", "type": 1},
                {"field_name": "分类", "type": 3},
                {"field_name": "优先级", "type": 3},
                {"field_name": "截止时间", "type": 5},
                {"field_name": "状态", "type": 3},
                {"field_name": "关联任务", "type": 1},
            ]
            new_table = client.create_table("代办事项", todo_fields)
            result_messages.append(f"✅ 代办事项表创建成功，ID: {new_table.get('table_id', '')}")
        else:
            result_messages.append("📋 代办事项表已存在")
        
        return "\n".join(result_messages)
    except Exception as e:
        return f"初始化表失败: {str(e)}"
