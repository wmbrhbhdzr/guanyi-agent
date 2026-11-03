# -*- coding: utf-8 -*-
"""工具协议层（实验6 §2.2）：工具 Schema、参数校验与白名单。

三条硬规则（都由程序执行，不写在提示词里）：

1. **白名单**：模型只能调用注册表里存在的工具名；未知名字直接拒绝，绝不按名字动态执行。
2. **参数校验**：每个参数声明类型/必填/取值范围/正则；校验不过就返回结构化错误，工具不执行。
3. **路径范围**：对局文件位于 `data/runs`；知识库只读 `knowledge`，运行记录写入 `data/agent`。
   `run_id` 先过正则，再由 `JsonlStore` 拼路径，拒绝 `../` 之类的穿越参数。

返回给模型的错误统一是 `{"ok": false, "error": {"code": ..., "message": ...}}`，
模型据此可以自行修正参数（有限次），而不是让程序崩掉。
"""

import re
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .runtime import wait_call

#: run_id 允许的写法（与 JsonlStore 生成的 id 保持一致，禁止路径分隔符）
RUN_ID_PATTERN = r"^run-[A-Za-z0-9_\-]{1,30}$"


class ToolError(Exception):
    """工具层错误（参数、权限、执行），由调用方转成结构化返回。"""

    def __init__(self, code: str, message: str, detail: Optional[Dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> Dict:
        return {"ok": False, "error": {"code": self.code, "message": self.message,
                                       "detail": self.detail}}


@dataclass
class ParamSpec:
    """一个工具参数的声明。"""

    name: str
    type: str                      # string / integer / boolean / number
    description: str = ""
    required: bool = False
    pattern: Optional[str] = None   # string 类型使用的正则
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    enum: Optional[List[str]] = None
    default: object = None

    def schema(self) -> Dict:
        spec: Dict = {"type": self.type, "description": self.description}
        if self.pattern:
            spec["pattern"] = self.pattern
        if self.minimum is not None:
            spec["minimum"] = self.minimum
        if self.maximum is not None:
            spec["maximum"] = self.maximum
        if self.enum:
            spec["enum"] = list(self.enum)
        if self.default is not None:
            spec["default"] = self.default
        return spec


@dataclass
class ToolSpec:
    """一个工具的完整声明。"""

    name: str
    description: str
    params: List[ParamSpec] = field(default_factory=list)
    read_only: bool = True            # 是否只读
    requires_confirm: bool = False    # 执行前是否需要人工确认
    timeout_s: float = 20.0           # 单次执行的最长等待（超时即放弃等待并报 timeout）
    repeated_call: str = "可重复调用，结果相同"   # 重复调用的语义说明（讲义 2.2 要求）
    side_effects: str = "无"

    def json_schema(self) -> Dict:
        """OpenAI tools 格式（供支持工具调用的模型接口使用）。"""
        props = {p.name: p.schema() for p in self.params}
        required = [p.name for p in self.params if p.required]
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": props, "required": required,
                               "additionalProperties": False},
            },
        }

    def validate(self, args: Dict) -> Dict:
        """校验并归一化参数；不合法抛 ToolError。"""
        if not isinstance(args, dict):
            raise ToolError("invalid_arguments", "参数必须是 JSON 对象")
        known = {p.name for p in self.params}
        unknown = [k for k in args if k not in known]
        if unknown:
            raise ToolError("unknown_argument",
                            "出现未声明的参数：%s；可用参数：%s"
                            % ("、".join(unknown), "、".join(sorted(known)) or "无"))
        clean: Dict = {}
        for param in self.params:
            if param.name not in args or args[param.name] is None:
                if param.required:
                    raise ToolError("missing_argument", "缺少必填参数：%s（%s）"
                                    % (param.name, param.description))
                if param.default is not None:
                    clean[param.name] = param.default
                continue
            value = args[param.name]
            if param.type == "integer":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ToolError("invalid_argument", "参数 %s 必须是整数" % param.name,
                                    {"value": value})
            elif param.type == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ToolError("invalid_argument", "参数 %s 必须是数字" % param.name)
            elif param.type == "boolean":
                if not isinstance(value, bool):
                    raise ToolError("invalid_argument", "参数 %s 必须是布尔值" % param.name)
            else:                                   # string
                if not isinstance(value, str):
                    raise ToolError("invalid_argument", "参数 %s 必须是字符串" % param.name)
                if param.pattern and not re.match(param.pattern, value):
                    raise ToolError("invalid_argument",
                                    "参数 %s 格式不合法（要求匹配 %s）" % (param.name, param.pattern),
                                    {"value": value})
                if not value.strip():
                    raise ToolError("invalid_argument", "参数 %s 不能为空" % param.name)
            if param.minimum is not None and value < param.minimum:
                raise ToolError("out_of_range", "参数 %s 不能小于 %s" % (param.name, param.minimum))
            if param.maximum is not None and value > param.maximum:
                raise ToolError("out_of_range", "参数 %s 不能大于 %s" % (param.name, param.maximum))
            if param.enum and value not in param.enum:
                raise ToolError("invalid_argument", "参数 %s 只能是 %s" % (param.name, param.enum))
            clean[param.name] = value
        return clean


class ToolRegistry:
    """工具注册表 = 允许调用的工具白名单。"""

    _blocked_write_scopes = set()
    _write_lock = threading.Lock()

    def __init__(self, write_scope=None):
        self._specs: Dict[str, ToolSpec] = {}
        self._impls: Dict[str, callable] = {}
        self._write_scope = write_scope if write_scope is not None else object()

    def register(self, spec: ToolSpec, impl):
        if spec.name in self._specs:
            raise ValueError("工具重复注册：%s" % spec.name)
        self._specs[spec.name] = spec
        self._impls[spec.name] = impl
        return spec

    def names(self) -> List[str]:
        return sorted(self._specs)

    def spec(self, name: str) -> ToolSpec:
        if name not in self._specs:
            raise ToolError("unknown_tool",
                            "工具 %r 不在允许调用的白名单内；可用工具：%s"
                            % (name, "、".join(self.names())))
        return self._specs[name]

    def schemas(self) -> List[Dict]:
        """供模型接口使用的 tools 列表。"""
        return [self._specs[n].json_schema() for n in self.names()]

    def describe(self) -> List[Dict]:
        """人类可读的工具说明（写进报告与界面）。"""
        out = []
        for name in self.names():
            spec = self._specs[name]
            out.append({
                "name": spec.name, "description": spec.description,
                "read_only": spec.read_only, "requires_confirm": spec.requires_confirm,
                "timeout_s": spec.timeout_s, "repeated_call": spec.repeated_call,
                "side_effects": spec.side_effects,
                "params": [{"name": p.name, "type": p.type, "required": p.required,
                            "pattern": p.pattern, "minimum": p.minimum, "maximum": p.maximum,
                            "description": p.description} for p in spec.params],
            })
        return out

    def call(self, name: str, args: Dict, timeout_s=None) -> Dict:
        """校验并执行一个工具（不含人工确认；确认由 Harness 在调用前完成）。"""
        spec = self.spec(name)                    # 白名单检查
        clean = spec.validate({} if args is None else args)  # 参数检查
        budget = spec.timeout_s if timeout_s is None else min(spec.timeout_s, timeout_s)
        if budget <= 0:
            raise ToolError("timeout", "工具尚未执行：运行预算已耗尽")
        if not spec.read_only:
            with self._write_lock:
                if self._write_scope in self._blocked_write_scopes:
                    raise ToolError("write_state_unknown", "写入仍在进行或结果不明；停止任务，关闭进程后核对目标文件，再决定是否重试",
                                    {"state_unknown": True, "requires_reconciliation": True})
                # 同时阻止超时后再次调用，以及并发写入。
                self._blocked_write_scopes.add(self._write_scope)
        try:
            result = wait_call(lambda: self._impls[name](**clean), budget)
            if not isinstance(result, dict) or not result.get("ok"):
                error = result.get("error", {}) if isinstance(result, dict) else {}
                raise ToolError(error.get("code", "tool_failed"),
                                error.get("message", "工具返回格式不正确或未成功"))
        except TimeoutError:
            raise ToolError("timeout", "工具等待超时，后台操作可能仍在运行", {
                "state_unknown": not spec.read_only,
                "requires_reconciliation": not spec.read_only,
            }) from None
        except ToolError as exc:
            if not spec.read_only:
                if exc.code in ("not_found", "invalid_argument", "missing_argument", "out_of_range"):
                    # 内置写工具的这些错误发生在写入之前，可反馈模型修正。
                    with self._write_lock:
                        self._blocked_write_scopes.discard(self._write_scope)
                else:
                    exc.detail.update(state_unknown=True, requires_reconciliation=True)
            raise
        except Exception as exc:                  # noqa: BLE001 —— 工具内部异常统一转成结构化错误
            raise ToolError("tool_failed", "%s 执行失败：%s: %s"
                            % (name, type(exc).__name__, exc),
                            {"state_unknown": not spec.read_only,
                             "requires_reconciliation": not spec.read_only})
        else:
            if not spec.read_only:
                with self._write_lock:
                    self._blocked_write_scopes.discard(self._write_scope)
            return result
