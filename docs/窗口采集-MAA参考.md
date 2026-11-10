# MAA PC连接方案参考

本次只读取`C:/MAA-v6.11.1-win-x64`文件，没有启动、注入或修改MAA。
该路径是已安装发行包，核心逻辑在DLL中，不是完整源码仓库。配置、DLL中的模块标识与公开源码交叉参考，
不能仅凭目录名称确定里面所有组件的源码版本。

## 本地看到的配置

`config/gui.new.json`中的PC连接配置为：

| 项目 | 配置 |
| --- | --- |
| ScreencapMethod | PrintWindow |
| MouseMethod | AnchoredTouch |
| KeyboardMethod | SendMessage |

`MaaWin32ControlUnit.dll`中包含PrintWindow、FramePool、PseudoMinimizeHelper、AnchoredTouchInput与MessageInput模块标识。
公开实现位于[MaaFramework](https://github.com/MaaXYZ/MaaFramework)。

## 可以借鉴的部分

1. **客户区采集与资源回收**：通过窗口句柄取得客户区，PrintWindow输出到独立位图；只读目标窗口像素，释放DC和位图。
   观弈采用同类Windows系统接口，自行实现了有界等待、句柄/PID核验和错误处理。
2. **DPI感知放在采集线程**：MaaFramework管理器用Per-Monitor DPI Aware V2避免尺寸虚拟化。
   观弈也在采集工作线程临时切换，并在结束时恢复，不改变Tk界面线程的缩放设置。
3. **截图与输入分别配置**：MAA鼠标和键盘可以使用不同方法；后台采集可用不等于后台输入对所有游戏也可用。
   观弈目前只接采集，不在此阶段开启键鼠注入。

## “最小化也可用”的实现

公开的`PseudoMinimizeHelper`检测窗口最小化后，保存扩展样式和透明度，
增加分层/点击穿透并设为透明，再用不激活方式恢复窗口，让它继续绘制。
用户重新激活时恢复外观，结束时恢复样式并重新最小化。这是一种伪最小化机制。

`AnchoredTouchInput`本身仍检查原生最小化状态；截图辅助层先把窗口转为伪最小化，才能继续后续工作。
`SendMessage`将键盘消息送往目标窗口，与全局SendInput不同；是否接受仍取决于游戏处理消息的方式。
因此该设计值得参考，但不能据此保证任意游戏在普通最小化状态下都能持续更新画面或接收输入。

观弈本轮没有直接复制该辅助层，也没有加载MAA的DLL。当前最小化会停止采集并提示恢复；
后续可增加可选的后台隐藏模式，重点验证样式/透明度恢复、失焦停帧、权限和不同渲染器兼容性。

## 来源

- [PrintWindowScreencap.cpp](https://github.com/MaaXYZ/MaaFramework/blob/main/source/MaaWin32ControlUnit/Screencap/PrintWindowScreencap.cpp)
- [PseudoMinimizeHelper.cpp](https://github.com/MaaXYZ/MaaFramework/blob/main/source/MaaWin32ControlUnit/Screencap/PseudoMinimizeHelper.cpp)
- [Win32ControlUnitMgr.cpp](https://github.com/MaaXYZ/MaaFramework/blob/main/source/MaaWin32ControlUnit/Manager/Win32ControlUnitMgr.cpp)
- [AnchoredTouchInput.cpp](https://github.com/MaaXYZ/MaaFramework/blob/main/source/MaaWin32ControlUnit/Input/AnchoredTouchInput.cpp)
- [MessageInput.cpp](https://github.com/MaaXYZ/MaaFramework/blob/main/source/MaaWin32ControlUnit/Input/MessageInput.cpp)
- [Microsoft PrintWindow接口说明](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-printwindow)
