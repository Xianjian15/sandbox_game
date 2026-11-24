# core/app_paths.py
"""打包相关的路径与日志。

开发时直接 python main.py 运行；发布时用 PyInstaller 打成独立程序（不需要玩家安装 Python）。
两种环境下"资源在哪里""日志写哪里"不一样，这里统一处理：

  resource_path(rel)   随程序打包的只读资源（图标、字体）。
                       开发时 = 项目根目录；打包后 = PyInstaller 解压目录（sys._MEIPASS）。
  user_data_dir()      可写目录（日志、崩溃报告、失去同步报告）。绝不写到程序所在目录——
                       装在 Program Files 里时没有写权限，U 盘上运行也不应留下文件。
                       Windows: %APPDATA%/SandboxGame   macOS: ~/Library/Application Support/SandboxGame
                       Linux: ~/.local/share/SandboxGame   （可用环境变量 RW_DATA_DIR 覆盖）
  setup_logging()      打包成无控制台窗口（windowed）后 sys.stdout/stderr 是 None，print 和未捕获的
                       异常都会"消失"。这里把它们接到日志文件，并开启 faulthandler 记录底层崩溃。
  report_crash()       程序崩溃时把完整错误写进 crash.log，并在 Windows 上弹窗告诉玩家日志在哪。
"""
import faulthandler
import os
import platform
import sys
import time
import traceback

from core.version import DATA_DIR_NAME, GAME_VERSION

_log_file = None


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def base_dir():
    """随程序打包的资源的根目录。"""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts):
    return os.path.join(base_dir(), *parts)


def user_data_dir(create=True):
    override = os.environ.get("RW_DATA_DIR")
    if override:
        path = override
    elif sys.platform.startswith("win"):
        path = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), DATA_DIR_NAME)
    elif sys.platform == "darwin":
        path = os.path.join(os.path.expanduser("~"), "Library", "Application Support", DATA_DIR_NAME)
    else:
        path = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), DATA_DIR_NAME)
    if create:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return path


def data_file(name):
    return os.path.join(user_data_dir(), name)


def setup_logging(max_bytes=1_000_000):
    """把 stdout/stderr 接到日志文件（仅在它们不可用，即打包成无控制台程序时）。返回日志路径或 None。"""
    global _log_file
    if sys.stdout is not None and sys.stderr is not None and not is_frozen():
        return None                               # 开发时保持普通控制台输出
    path = data_file("game.log")
    try:
        if os.path.exists(path) and os.path.getsize(path) > max_bytes:
            os.replace(path, path + ".old")       # 简单轮转，防止日志无限增长
        _log_file = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    _log_file.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')}  v{GAME_VERSION}  "
                    f"{platform.platform()}  Python {platform.python_version()} =====\n")
    if sys.stdout is None:
        sys.stdout = _log_file
    if sys.stderr is None:
        sys.stderr = _log_file
    try:
        faulthandler.enable(file=_log_file)       # 底层崩溃（如 SDL 出错）也能留下痕迹
    except (RuntimeError, ValueError, OSError):
        pass
    return path


def _message_box(title, text):
    """弹一个原生消息框（只在 Windows；其他系统只写日志）。不依赖 tkinter，打包体积更小。
    设环境变量 RW_NO_DIALOG=1 可关闭弹窗（自动化测试/CI 里弹窗会一直卡住等人点）。"""
    if sys.platform.startswith("win") and not os.environ.get("RW_NO_DIALOG"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)     # MB_ICONERROR
        except Exception:                                                  # noqa: BLE001
            pass


def report_crash(exc_info=None):
    """记录崩溃并告诉玩家日志位置。返回崩溃报告路径。"""
    exc_info = exc_info or sys.exc_info()
    text = "".join(traceback.format_exception(*exc_info))
    path = data_file("crash.log")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')}  v{GAME_VERSION}  "
                    f"{platform.platform()}  Python {platform.python_version()} =====\n{text}")
    except OSError:
        path = None
    try:
        sys.stderr and sys.stderr.write(text)
    except Exception:                                                      # noqa: BLE001
        pass
    where = path or "（无法写入日志）"
    _message_box("游戏遇到了错误", f"抱歉，游戏意外退出了。\n\n错误信息已保存到：\n{where}\n\n"
                                  f"反馈问题时请附上这个文件。")
    return path
