from enum import Enum, auto
from typing import List, Dict, Any, Optional
import json
import time


# 定义记忆类型枚举
class MemoryType(Enum):
    PLAN = auto()  # 规划信息
    INSTRUCTION = auto()  # 用户指令
    RESPONSE = auto()  # API 响应结果


# ApiMemory 类实现
class ApiMemory:
    def __init__(self):
        self.instruction = ""  # 专门存储用户指令
        self.total_plans = []  # 专门存储规划信息  [{'step1': {'method': 'POST', 'url': '/system/role/checkRoleNameUnique'}}, {'step2': {'method': 'POST', 'url': '/system/role/checkRoleKeyUnique'}}]
        self.step = 0  # 记录当前第几步
        self.response_history = []
        self.api_complete_filter_result = []
        self.current_api = ""

    def set_api_complete_filter_result(self, api_complete_filter_result):
        self.api_complete_filter_result = api_complete_filter_result
    # 添加用户指令
    def set_instruction(self, instruction):
        self.instruction = instruction

    def set_total_plans(self, plans):
        # 将嵌套字典转换为有序列表（按步骤名排序）
        self.total_plans = plans

    # 获取所有用户指令
    def get_instruction(self):
        return self.instruction

    def get_step(self):
        return self.step

    def get_total_plans(self):
        # [{'step1': {'method': 'POST', 'url': '/system/role/checkRoleNameUnique'}}, {'step2': {'method': 'POST', 'url': '/system/role/checkRoleKeyUnique'}}]
        return self.total_plans

    def get_current_plan(self):
        # {'step1': {'method': 'POST', 'url': '/system/role/checkRoleNameUnique'}}
        # 获取当前步骤的嵌套字典
        current_step_dict = self.total_plans[self.step]
        # 提取步骤数据字典（忽略步骤名称）
        step_data = next(iter(current_step_dict.values()))
        # 直接返回 method 和 url 组成的元组
        return step_data['method'], step_data['url'], step_data['api_template']

    def step_continue(self):
        self.step += 1

    def store_api_response(self, method, api_template, response):
        """将API响应结果按指定结构存储到历史记录列表"""
        # 构建键名：{method}-{url}
        key = f"{method}-{api_template}"
        # 创建单元数据结构
        response_item = {key: response}
        # 添加到历史记录列表
        self.response_history.append(response_item)

    def store_current_api(self, current_api):
        self.current_api = current_api
