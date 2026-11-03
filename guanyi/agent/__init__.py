# -*- coding: utf-8 -*-
"""Agent 包（实验6）：工具调用、单 Agent 循环与运行时 Harness。

与实验3 设计的关系：这是**新增能力**，不属于原有 7 个包中的某一块——
- `agent/tools.py` 把数据层（`data`）与知识层（`knowledge`）暴露成**受控工具**；
- `agent/harness.py` 是运行时外壳，负责循环、限制、确认与校验；
- `agent/protocol.py` 是工具 Schema 与白名单（程序侧的权限边界）；
- `agent/trace.py` 负责运行记录（可观测性）。
"""

from .confirm import AutoApprove, AutoReject, CliConfirm, GuiConfirm
from .harness import AgentConfig, AgentHarness, AgentResult, SYSTEM_PROMPT
from .protocol import ParamSpec, ToolError, ToolRegistry, ToolSpec
from .tools import build_registry, describe_tools
from .trace import Trace

__all__ = [
    "AgentConfig", "AgentHarness", "AgentResult", "SYSTEM_PROMPT",
    "ParamSpec", "ToolError", "ToolRegistry", "ToolSpec",
    "build_registry", "describe_tools",
    "Trace", "AutoApprove", "AutoReject", "CliConfirm", "GuiConfirm",
]
