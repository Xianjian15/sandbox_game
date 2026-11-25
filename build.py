#!/usr/bin/env python3
# build.py
"""一键打包：把游戏打成"双击就能玩、不需要安装 Python"的程序，并压成 zip 方便发给别人。

开发者（打包的人）一次性准备：
    pip install -r requirements-build.txt        # pygame-ce + pyinstaller

打包：
    python build.py                 # 自检 → 打包成文件夹版 → 压缩成 zip（推荐）
    python build.py --onefile       # 打成单个文件（体积小但启动慢，更容易被杀毒软件误报）
    python build.py --console       # 保留黑色控制台窗口（程序打不开/闪退时用来看报错）
    python build.py --check         # 只做打包前自检，不打包
    python build.py --dry-run       # 只打印将要执行的打包命令

重要：PyInstaller 不能交叉编译——想要 Windows 的 .exe 就必须在 Windows 上运行本脚本，
想要 mac 的 .app 就要在 mac 上运行。没有对应系统的电脑？用 .github/workflows/build.yml，
推送到 GitHub 后由云端同时打出三个系统的版本。

产物在 dist/ 目录：
    dist/SandboxGame/              程序文件夹（Windows 里面有 SandboxGame.exe）
    dist/SandboxGame-v0.1.0-windows-x64.zip   发给玩家的压缩包
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core.version import DISPLAY_NAME, EXE_NAME, GAME_VERSION          # noqa: E402

# 只在函数内部或被间接导入的模块，显式告诉 PyInstaller（自检里也会提醒新增的动态导入）
HIDDEN_IMPORTS = ["core.state_hash", "core.commands", "world.command_exec"]
EXCLUDES = []                            # 注意：不能排除 tkinter——选择头像的文件窗口要用它
PLAYER_README = os.path.join(ROOT, "assets", "玩家说明.txt")


def system_tag():
    sysname = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system().lower())
    arch = {"AMD64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine(), platform.machine().lower())
    return f"{sysname}-{arch}"


def windows_version_file(path):
    """Windows 文件属性里显示的版本信息（右键 → 属性 → 详细信息）。"""
    parts = [int(x) for x in GAME_VERSION.split(".")] + [0]
    tup = ", ".join(str(x) for x in parts[:4])
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('080404B0', [
      StringStruct('CompanyName', ''),
      StringStruct('FileDescription', '{DISPLAY_NAME}'),
      StringStruct('FileVersion', '{GAME_VERSION}'),
      StringStruct('InternalName', '{EXE_NAME}'),
      StringStruct('OriginalFilename', '{EXE_NAME}.exe'),
      StringStruct('ProductName', '{DISPLAY_NAME}'),
      StringStruct('ProductVersion', '{GAME_VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def build_command(args):
    sep = os.pathsep                                           # Windows 是 ';'，其他系统是 ':'
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--name", EXE_NAME,
           "--distpath", os.path.join(ROOT, "dist"),
           "--workpath", os.path.join(ROOT, "build"),
           "--specpath", os.path.join(ROOT, "build"),
           "--paths", ROOT,
           "--add-data", f"{os.path.join(ROOT, 'assets')}{sep}assets"]
    cmd.append("--onefile" if args.onefile else "--onedir")
    if not args.console:
        cmd.append("--windowed")                               # 不弹黑色控制台窗口（mac 上同时生成 .app）
    icon = {"Windows": "icon.ico", "Darwin": "icon.icns"}.get(platform.system())
    if icon and os.path.isfile(os.path.join(ROOT, "assets", icon)):
        cmd += ["--icon", os.path.join(ROOT, "assets", icon)]
    if platform.system() == "Windows":
        vf = os.path.join(ROOT, "build", "version_info.txt")
        cmd += ["--version-file", vf]
    for m in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", m]
    for m in EXCLUDES:
        cmd += ["--exclude-module", m]
    cmd.append(os.path.join(ROOT, "main.py"))
    return cmd


def collect_output(args):
    """返回要打进 zip 的 (磁盘路径, 压缩包内路径) 列表，以及 zip 文件名。"""
    dist = os.path.join(ROOT, "dist")
    if platform.system() == "Darwin" and not args.onefile:
        app = os.path.join(dist, f"{EXE_NAME}.app")
        root_item = app if os.path.isdir(app) else os.path.join(dist, EXE_NAME)
    elif args.onefile:
        root_item = os.path.join(dist, EXE_NAME + (".exe" if platform.system() == "Windows" else ""))
    else:
        root_item = os.path.join(dist, EXE_NAME)
    return root_item, f"{EXE_NAME}-v{GAME_VERSION}-{system_tag()}{'-onefile' if args.onefile else ''}.zip"


def make_zip(root_item, zip_name):
    zip_path = os.path.join(ROOT, "dist", zip_name)
    top = f"{EXE_NAME}-v{GAME_VERSION}"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        if os.path.isdir(root_item):
            for folder, _, files in os.walk(root_item):
                for fn in files:
                    full = os.path.join(folder, fn)
                    z.write(full, os.path.join(top, os.path.relpath(full, os.path.dirname(root_item))))
        else:
            z.write(root_item, os.path.join(top, os.path.basename(root_item)))
        if os.path.isfile(PLAYER_README):
            z.write(PLAYER_README, os.path.join(top, "玩家说明.txt"))
    return zip_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="一键打包游戏")
    ap.add_argument("--onefile", action="store_true", help="打成单个文件（启动慢、更易被杀毒误报）")
    ap.add_argument("--console", action="store_true", help="保留控制台窗口（排错用）")
    ap.add_argument("--check", action="store_true", help="只做打包前自检")
    ap.add_argument("--dry-run", action="store_true", help="只打印打包命令，不执行")
    ap.add_argument("--no-zip", action="store_true", help="不生成 zip")
    args = ap.parse_args(argv)

    print(f"== {DISPLAY_NAME}  v{GAME_VERSION}  →  {system_tag()} ==\n")
    from tools import package_check
    print("[1/4] 打包前自检")
    if package_check.main() != 0:
        return 1
    if args.check:
        return 0

    cmd = build_command(args)
    print("\n[2/4] 打包命令")
    print("  " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    if args.dry_run:
        root_item, zip_name = collect_output(args)
        print(f"\n（--dry-run）将生成: {root_item}\n（--dry-run）压缩包: dist/{zip_name}")
        return 0

    try:
        import PyInstaller                                       # noqa: F401
    except ImportError:
        print("\n✗ 没有安装 PyInstaller。请先运行：  pip install -r requirements-build.txt")
        return 2

    print("\n[3/4] 开始打包（第一次可能要几分钟）…")
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    if platform.system() == "Windows":
        windows_version_file(os.path.join(ROOT, "build", "version_info.txt"))
    if subprocess.call(cmd, cwd=ROOT) != 0:
        print("\n✗ 打包失败，请看上面 PyInstaller 的报错。")
        return 3

    root_item, zip_name = collect_output(args)
    if not os.path.exists(root_item):
        print(f"\n✗ 打包似乎成功了，但找不到预期的产物：{root_item}")
        return 4
    print(f"\n✓ 打包完成：{root_item}")
    if not args.no_zip:
        print("[4/4] 压缩")
        zp = make_zip(root_item, zip_name)
        print(f"✓ 发给玩家的压缩包：{zp}  ({os.path.getsize(zp) / 1024 / 1024:.1f} MB)")
    print("\n建议先自己解压、双击运行一次，并在没装 Python 的电脑上试一次再发给别人。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
