# ui/fonts.py
"""字体选择：保证任何电脑上中文界面都不会变成方块。

优先级（找到第一个存在的就用）：
  1. 环境变量 RW_FONT 指定的字体文件（调试用）
  2. assets/fonts/user/ 里玩家/开发者自己放的字体（想换字体就丢一个 .ttf/.otf/.ttc 进去）
  3. 系统自带的中文字体（Windows 微软雅黑/黑体、macOS 苹方/黑体、Linux 的 Noto CJK/文泉驿等）
  4. 随游戏打包的后备字体 assets/fonts/GameUISans-Subset.otf（Noto Sans CJK 子集，保证兜底）
  5. pygame 默认字体（只能显示英文，中文会是方块）
系统字体放在后备字体前面：它覆盖全部汉字（玩家给房间起的名字里可能有生僻字），
后备字体只含约 3900 个常用字。
"""
import glob
import os

from core.app_paths import resource_path

SYSTEM_FILES = [
    # Windows
    "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyh.ttf", "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc", "C:/Windows/Fonts/Deng.ttf",
    # macOS
    "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc", "/Library/Fonts/Arial Unicode.ttf",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc", "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]
SYSTEM_NAMES = ["microsoftyahei", "simhei", "pingfangsc", "stheitimedium", "hiraginosansgb",
                "notosanscjksc", "notosanssc", "wenquanyimicrohei", "droidsansfallback"]
BUNDLED = ("assets", "fonts", "GameUISans-Subset.otf")

_cache = {}


def find_font_path(exists=os.path.exists, match=None, env=None):
    """返回 (路径, 来源说明) 或 (None, "default")。参数可注入，方便测试。"""
    env = os.environ if env is None else env
    p = env.get("RW_FONT")
    if p and exists(p):
        return p, "环境变量 RW_FONT"
    user_dir = resource_path("assets", "fonts", "user")
    for ext in ("ttf", "otf", "ttc"):
        for p in sorted(glob.glob(os.path.join(user_dir, f"*.{ext}"))):
            return p, "用户字体"
    for p in SYSTEM_FILES:
        if exists(p):
            return p, "系统字体"
    if match is None:
        try:
            import pygame
            match = pygame.font.match_font
        except Exception:                                              # noqa: BLE001
            match = None
    if match is not None:
        for name in SYSTEM_NAMES:
            try:
                p = match(name)
            except Exception:                                          # noqa: BLE001
                p = None
            if p and exists(p):
                return p, "系统字体(按名称)"
    bundled = resource_path(*BUNDLED)
    if exists(bundled):
        return bundled, "随游戏打包的后备字体"
    return None, "default"


def load_font(size=18):
    import pygame
    if "path" not in _cache:
        _cache["path"] = find_font_path()
    path, _ = _cache["path"]
    if path:
        try:
            return pygame.font.Font(path, size)
        except Exception:                                              # noqa: BLE001
            pass
    return pygame.font.Font(None, size)


def font_source():
    """调试/日志用：当前使用的字体及来源。"""
    if "path" not in _cache:
        _cache["path"] = find_font_path()
    return _cache["path"]
