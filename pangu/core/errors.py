"""盘古统一错误码 — 标准化错误响应"""

from dataclasses import dataclass
from typing import Any


@dataclass
class PanguError:
    """盘古错误"""

    code: int
    message: str
    details: Any = None

    def to_dict(self) -> dict:
        result = {"error": {"code": self.code, "message": self.message}}
        if self.details:
            result["error"]["details"] = self.details
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


import json


class ErrorCode:
    """错误码定义"""

    # 成功
    OK = 0

    # 通用错误 (1000-1099)
    UNKNOWN = 1000
    INVALID_PARAMS = 1001
    NOT_FOUND = 1002
    ALREADY_EXISTS = 1003
    PERMISSION_DENIED = 1004
    RATE_LIMITED = 1005
    INTERNAL_ERROR = 1099

    # 记忆操作 (2000-2099)
    MEMORY_NOT_FOUND = 2001
    MEMORY_CREATE_FAILED = 2002
    MEMORY_UPDATE_FAILED = 2003
    MEMORY_DELETE_FAILED = 2004
    MEMORY_DUPLICATE = 2005
    MEMORY_SEARCH_FAILED = 2006
    MEMORY_Embed_FAILED = 2007
    MEMORY_INDEX_FAILED = 2008

    # 向量/嵌入 (3000-3099)
    EMBED_MODEL_NOT_LOADED = 3001
    EMBED_FAILED = 3002
    VECTOR_INDEX_NOT_BUILT = 3003
    VECTOR_DIMENSION_MISMATCH = 3004

    # 知识图谱 (4000-4099)
    KG_ENTITY_NOT_FOUND = 4001
    KG_RELATION_NOT_FOUND = 4002
    KG_CYCLE_DETECTED = 4003

    # 插件 (5000-5099)
    PLUGIN_NOT_FOUND = 5001
    PLUGIN_LOAD_FAILED = 5002
    PLUGIN_HOOK_FAILED = 5003

    # 外部服务 (6000-6099)
    LLM_API_FAILED = 6001
    LLM_TIMEOUT = 6002
    LLM_RATE_LIMITED = 6003

    # 存储 (7000-7099)
    STORAGE_READ_FAILED = 7001
    STORAGE_WRITE_FAILED = 7002
    STORAGE_CORRUPTED = 7003


def make_error(code: int, message: str, details: Any = None) -> str:
    """创建标准化错误响应"""
    return json.dumps(
        {
            "code": code,
            "error": message,
            "details": details,
        },
        ensure_ascii=False,
        indent=2,
    )


def error_memory_not_found(memory_id: str) -> str:
    return make_error(ErrorCode.MEMORY_NOT_FOUND, f"记忆不存在: {memory_id}")


def error_invalid_params(param: str) -> str:
    return make_error(ErrorCode.INVALID_PARAMS, f"无效参数: {param}")


def error_not_found(resource: str) -> str:
    return make_error(ErrorCode.NOT_FOUND, f"资源不存在: {resource}")


def error_already_exists(name: str) -> str:
    return make_error(ErrorCode.ALREADY_EXISTS, f"已存在: {name}")


def error_internal(message: str) -> str:
    return make_error(ErrorCode.INTERNAL_ERROR, message)
