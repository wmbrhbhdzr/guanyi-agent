实验6 的截图与示意图（编号与报告《实验6-工具调用、Agent与Harness实现.md》一致）

- 图1-工具参数校验.png          scripts/test_tools.py 的输出（正确参数 + 错误参数）
- 图2-工具白名单-1.png          agent --tools 输出前半（compute_stats / get_decisions / list_runs）
- 图2-工具白名单-2.png          agent --tools 输出后半（query_knowledge / write_report）
- 图3-Agent循环图.png           由 scripts/draw_exp6_agent_loop.py 生成（讲义 2.3 要求）
- 图4-运行记录.png              data/agent/<任务号>.log 与 .jsonl
- 图5-人工确认弹窗.png          写操作前的确认弹窗（30 秒倒计时，拒绝/超时都不执行）
- 图6-真实运行输出.png          scripts/run_agent_demo.py：真实模型 + 真实工具的完整运行
- 图7-停止与失败场景.png        达到步数上限 / 参数错误等边界
- 图8-Agent页运行完成.png       界面「复盘 Agent」页运行结束后的日志与结论
- 图9-单元测试全绿-1.png        scripts/run_tests.py：用例列表（前半）
- 图9-单元测试全绿-2.png        scripts/run_tests.py：用例列表（后半）与 37 个用例全部通过
