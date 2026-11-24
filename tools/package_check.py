# tools/package_check.py
"""打包前自检：在花几分钟打包、再发给朋友发现"缺文件/少模块"之前，先把能提前发现的问题查出来。

检查项：
  1 导入图      从 main.py 出发，顺着所有 import 找到游戏用到的每个模块，确认文件都存在、
                包都有 __init__.py、游戏代码没有依赖 tools/（测试脚本不会被打进程序）
  2 第三方依赖  游戏运行时用到的第三方库只有 pygame；出现别的会警告（PyInstaller 需要知道它们）
  3 动态导入    __import__ / importlib 打包工具看不见，出现会警告
  4 资源文件    图标、后备字体及其许可文本是否齐全
  5 版本号      格式是否为 x.y.z
  6 打包后路径  模拟"打包后运行"（sys.frozen + sys._MEIPASS），资源路径是否还能找到
  7 字体兜底    模拟"系统里一个中文字体都没有"，是否能回退到随游戏打包的字体
用法：  python -m tools.package_check
"""
import ast
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

LOCAL_TOPS = {"core", "entities", "world", "ui", "net", "systems", "combat", "settings", "main", "tools"}
STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}


def module_file(name):
    """项目内的模块名 -> 文件路径（模块或包），找不到返回 None。"""
    parts = name.split(".")
    base = os.path.join(ROOT, *parts)
    if os.path.isfile(base + ".py"):
        return base + ".py"
    if os.path.isfile(os.path.join(base, "__init__.py")):
        return os.path.join(base, "__init__.py")
    return None


def scan_imports(path):
    """返回 (导入的模块名集合, 是否含动态导入)。包含函数内部的 import。"""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    mods, dynamic = set(), False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:                                   # 相对导入：项目里没有用，出现就当问题
                mods.add("." * node.level + (node.module or ""))
            elif node.module:
                mods.add(node.module)
                for a in node.names:                          # from pkg import submodule
                    mods.add(f"{node.module}.{a.name}")
        elif isinstance(node, ast.Call):
            fn = node.func
            if (isinstance(fn, ast.Name) and fn.id == "__import__") or \
               (isinstance(fn, ast.Attribute) and fn.attr in ("import_module",) ):
                dynamic = True
    return mods, dynamic


def import_graph(entry="main"):
    seen, queue = {}, [entry]
    third, missing, relative, dynamic_files, uses_tools = set(), [], [], [], []
    while queue:
        m = queue.pop()
        if m in seen:
            continue
        path = module_file(m)
        if path is None:
            continue
        seen[m] = path
        # 包的 __init__ 也属于依赖
        parts = m.split(".")
        for i in range(1, len(parts)):
            queue.append(".".join(parts[:i]))
        mods, dyn = scan_imports(path)
        if dyn:
            dynamic_files.append(os.path.relpath(path, ROOT))
        for imp in mods:
            if imp.startswith("."):
                relative.append((os.path.relpath(path, ROOT), imp)); continue
            top = imp.split(".")[0]
            if top in LOCAL_TOPS:
                if module_file(imp):
                    queue.append(imp)
                    if top == "tools" and m.split(".")[0] != "tools":
                        uses_tools.append((os.path.relpath(path, ROOT), imp))
                elif "." not in imp or module_file(imp.rsplit(".", 1)[0]) is None:
                    missing.append((os.path.relpath(path, ROOT), imp))
            elif top not in STDLIB:
                third.add(top)
    return seen, third, missing, relative, dynamic_files, uses_tools


# ---------------- 各项检查：返回 (ok, 说明, 警告列表) ----------------
def check_graph():
    seen, third, missing, relative, dyn, uses_tools = import_graph("main")
    bad = []
    if missing:
        bad.append("找不到模块: " + "; ".join(f"{f} 导入 {m}" for f, m in missing))
    if relative:
        bad.append("使用了相对导入（打包不友好）: " + "; ".join(f"{f}:{m}" for f, m in relative))
    if uses_tools:
        bad.append("游戏代码依赖了 tools/（测试脚本不应被游戏引用）: " + "; ".join(f"{f}→{m}" for f, m in uses_tools))
    pkgs = {m.split(".")[0] for m in seen if "." in m} | {m for m in seen if module_file(m) and module_file(m).endswith("__init__.py")}
    for p in sorted(pkgs):
        if p in LOCAL_TOPS and os.path.isdir(os.path.join(ROOT, p)) and not os.path.isfile(os.path.join(ROOT, p, "__init__.py")):
            bad.append(f"包 {p}/ 缺少 __init__.py")
    return (not bad), f"从 main.py 可达 {len(seen)} 个项目模块", bad, third, dyn


def check_assets():
    need = {"assets/icon.png": "窗口图标", "assets/icon.ico": "Windows 程序图标",
            "assets/fonts/GameUISans-Subset.otf": "后备中文字体", "assets/fonts/OFL-NotoSansCJK.txt": "字体许可文本"}
    warn_only = {"assets/icon.icns": "macOS 程序图标（只影响 mac 打包的图标）"}
    bad = [f"缺少 {p}（{d}）" for p, d in need.items() if not os.path.isfile(os.path.join(ROOT, p))]
    warns = [f"缺少 {p}：{d}" for p, d in warn_only.items() if not os.path.isfile(os.path.join(ROOT, p))]
    return (not bad), "图标/字体/许可文本", bad + [], warns


def check_version():
    from core.version import GAME_VERSION, EXE_NAME
    ok = bool(re.fullmatch(r"\d+\.\d+\.\d+", GAME_VERSION)) and bool(re.fullmatch(r"[A-Za-z0-9_\-]+", EXE_NAME))
    return ok, f"版本 {GAME_VERSION}，程序名 {EXE_NAME}", ([] if ok else ["版本号须为 x.y.z；程序名只能含字母数字下划线连字符"])


def check_frozen_paths():
    from core import app_paths
    tmp = tempfile.mkdtemp()
    old = (getattr(sys, "frozen", None), getattr(sys, "_MEIPASS", None))
    try:
        shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(tmp, "assets"))
        sys.frozen, sys._MEIPASS = True, tmp
        p_icon = app_paths.resource_path("assets", "icon.png")
        p_font = app_paths.resource_path("assets", "fonts", "GameUISans-Subset.otf")
        ok = (app_paths.is_frozen() and app_paths.base_dir() == tmp and os.path.isfile(p_icon) and os.path.isfile(p_font)
              and not app_paths.user_data_dir(create=False).startswith(tmp))
        return ok, "模拟打包环境下资源路径可解析，用户数据目录不在程序目录里", ([] if ok else ["资源路径解析失败"])
    finally:
        sys.frozen, sys._MEIPASS = old
        if old[0] is None: del sys.frozen
        if old[1] is None: del sys._MEIPASS
        shutil.rmtree(tmp, ignore_errors=True)


def check_font_fallback():
    from ui import fonts
    bundled = fonts.resource_path(*fonts.BUNDLED)
    path, src = fonts.find_font_path(exists=lambda p: p == bundled, match=lambda n: None, env={})
    ok = path == bundled and "后备" in src
    return ok, f"没有任何系统中文字体时回退到：{src}", ([] if ok else [f"期望回退到 {bundled}，实际 {path} ({src})"])


def main():
    allok = True
    ok, msg, bad, third, dyn = check_graph()
    print(f"{'✓' if ok else '✗'} 1 导入图：{msg}")
    for b in bad: print("    ✗", b)
    allok &= ok
    extra = sorted(t for t in third if t != "pygame")
    print(f"{'✓' if not extra else '⚠'} 2 第三方依赖：{sorted(third)}")
    if extra: print("    ⚠ 除 pygame 外还用到了:", extra, "→ 请确认它们在 requirements.txt 里，并考虑加进 build.py 的 HIDDEN_IMPORTS")
    print(f"{'✓' if not dyn else '⚠'} 3 动态导入：{'无' if not dyn else dyn}")
    if dyn: print("    ⚠ 这些文件用了 __import__/importlib，打包工具看不见被导入的模块，需要手动加 --hidden-import")
    for n, (fn, label) in enumerate([(check_assets, "4 资源文件"), (check_version, "5 版本号"),
                                      (check_frozen_paths, "6 打包后路径"), (check_font_fallback, "7 字体兜底")], start=4):
        res = fn()
        ok, msg, bad = res[0], res[1], res[2]
        warns = res[3] if len(res) > 3 else []
        print(f"{'✓' if ok else '✗'} {label}：{msg}")
        for b in bad: print("    ✗", b)
        for w in warns: print("    ⚠", w)
        allok &= ok
    print("\n打包前检查通过 ✓" if allok else "\n打包前检查未通过 ✗（请先修复上面的问题）")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
