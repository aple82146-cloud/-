"""
当前时间插件
提供获取当前时间的便捷工具
"""
from datetime import datetime
from langchain.tools import tool


@tool
def get_current_time(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """获取当前时间。
    
    Args:
        format: 时间格式，默认为"%Y-%m-%d %H:%M:%S"
            常用格式：
            - "%Y-%m-%d" 返回如 "2025-06-20"
            - "%Y-%m-%d %H:%M:%S" 返回如 "2025-06-20 15:30:45"
            - "%Y年%m月%d日 %H时%M分" 返回如 "2025年06月20日 15时30分"
            - "%A, %B %d, %Y" 返回如 "Friday, June 20, 2025"
    
    Returns:
        格式化后的当前时间字符串
    """
    now = datetime.now()
    return now.strftime(format)


@tool
def get_today_date() -> str:
    """获取今天的日期。
    
    Returns:
        今天的日期，格式为 YYYY-MM-DD，如 "2025-06-20"
    """
    now = datetime.now()
    return now.strftime("%Y-%m-%d")


@tool
def get_weekday() -> str:
    """获取今天是星期几。
    
    Returns:
        今天是星期几，如 "星期一"、"星期二" 等
    """
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    now = datetime.now()
    return weekdays[now.weekday()]
