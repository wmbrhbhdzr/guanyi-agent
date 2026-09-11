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
│   └── AI协作记录.md       AI 工具使用过程记录
└── 实验1-AI软件开发环境安装与配置.md
    实验2-个人软件选题与需求分析.md
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

## 模型说明

运行时决策模型调用名为 `deepseek-flash`。旧名称
`deepseek-v4-flash` / `deepseek-v4-flash-vision-exp` 为别名，
实际由 DeepSeek-V4.1-Flash 提供服务，按 Flash 价格计费。

## 许可

本项目采用 MIT License，详见 [LICENSE](LICENSE)。
