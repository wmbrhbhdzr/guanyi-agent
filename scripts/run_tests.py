# -*- coding: utf-8 -*-
"""跑全部单元测试并把结果输出到标准输出（便于截图，避免 PowerShell 把进度当错误显示）。

    python scripts/run_tests.py

等价于 `python -m unittest discover -s tests -v`，但输出不会出现红色“错误”字样。
"""

import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                     # noqa: BLE001
    pass


def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 回到项目根目录
    suite = unittest.TestLoader().discover("tests")
    buffer = io.StringIO()
    result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(suite)
    print(buffer.getvalue())
    print("=" * 64)
    print("用例数：%d　失败：%d　错误：%d" % (result.testsRun, len(result.failures), len(result.errors)))
    print("结论：%s" % ("全部通过 ✓" if result.wasSuccessful() else "存在失败 ✗"))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
