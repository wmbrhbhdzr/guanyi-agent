# 观弈（GuanYi）

基于视觉语言模型的离散决策游戏智能体。

## 项目背景

本项目为《软件应用开发实践》课程个人项目，同时作为毕业设计的前期预研。

目标是让视觉语言模型（VLM）在**只观察屏幕像素**的条件下完成游戏决策，
并通过结构化记忆机制在多次对局中持续改进表现。

## 核心设计约束

- **像素优先**：决策层的输入只有屏幕截图，不读取任何游戏内部数据
  （如内存、存档、日志、Mod 接口），以保证方案的通用性，而非只适配某一款游戏。
- **真值隔离**：游戏内部状态仅用于**离线评测、日志标注与动作合法性校验**，
  绝不进入模型上下文，也绝不作为动作执行通道。
- **决策点采样**：不逐帧分析画面，仅在需要决策时采集截图，
  以控制延迟与调用成本。

## 核心流程

```
截取屏幕 → VLM 视觉理解 → 结构化动作 → 执行 → 记录 → 评测 → 记忆更新 → 循环
```

## 目录结构

```
.
├── README.md              项目说明
├── LICENSE                开源许可（MIT）
├── .gitignore             版本忽略规则
├── .env.example           环境变量模板（不含真实密钥）
├── docs/
│   ├── 视觉识别-运行说明.md
│   └── 视觉识别-开发记录.md
├── guanyi/
│   ├── vision/             截图预处理、提取协议与局面校验
│   ├── agent/              复盘 Agent 与运行时 Harness
│   ├── app/                应用服务
│   └── ui/                 六页桌面界面
├── scripts/                演示与验证入口
├── tests/                  离线自动化测试
└── 实验1—6报告              各阶段的要求与操作记录
```

> 随开发进度持续更新。

## 环境要求

- 操作系统：Windows 11
- Python：3.13
- GPU：NVIDIA GeForce RTX 4060 Laptop（8 GB 显存）
- 依赖清单：见 `requirements.txt`

## 快速开始

```powershell
# 1. 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量（复制模板后填入真实密钥）
Copy-Item .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
```

> `.env` 已被 `.gitignore` 忽略，不会进入版本库。

### 游戏窗口采集与识别

```powershell
# 打开“游戏画面识别”页，自动连接游戏或手动选择窗口
.\.venv\Scripts\python.exe -m guanyi.ui

# 命令行也可以识别指定图片（实际请求模型）
.\.venv\Scripts\python.exe -m guanyi.cli vision --image "C:\截图\战斗.png"

# 生成可核对的合成图；默认不调用模型
.\.venv\Scripts\python.exe scripts\vision_demo.py
```

首版提取玩家血量、能量、格挡、手牌、敌人血量与意图。看不清的值保留未知，结果需对照图片核对。
支持自动检测游戏窗口、手动选择、单次采集与1—300秒间隔连续识别，相同画面跳过请求。
导入图片用于固定局面复测；当前未接视觉动作决策，识别不会自动操作游戏，最小化窗口会停止采集。
用法与验证记录见 [运行说明](docs/视觉识别-运行说明.md) 和 [开发记录](docs/视觉识别-开发记录.md)。

## 模型说明

运行时决策模型调用名为 `deepseek-flash`。旧名称
`deepseek-v4-flash` / `deepseek-v4-flash-vision-exp` 为别名，
实际由 DeepSeek-V4.1-Flash 提供服务，按 Flash 价格计费。

## 项目状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| 实验1—6 | 环境、需求、设计、基础功能、RAG、复盘Agent与Harness | 已完成阶段实现与报告 |
| 视觉识别 | 连接窗口→采集→模型提取→校验→展示与记录 | 窗口采集已接入；固定十例对比完成，继续检验实际游戏渲染兼容性 |

## 已初步调研的现有方案

- **Cradle**：以截图作为输入、键鼠作为输出的通用计算机控制框架
- **ScreenAgent / UI-TARS**：规划—执行—反思式的 GUI 智能体
- **CommunicationMod**：杀戮尖塔的外部进程控制协议
  （仅用于离线评测与合法性校验，**不进入模型上下文**，以保持方案通用性）

## 许可

本项目采用 MIT License，详见 [LICENSE](LICENSE)。
