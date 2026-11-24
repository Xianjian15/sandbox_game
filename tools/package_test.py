# tools/package_test.py
"""打包相关代码的测试（不需要 PyInstaller 也不需要窗口）。

没法在一台电脑上真的打出三个系统的包，所以这里把"能验证的部分"都验证掉：
  1 用户数据目录   三个系统的路径规则、环境变量覆盖、绝不写进程序目录
  2 日志重定向     无控制台程序（stdout=None）里 print 和未捕获异常不会消失，会进 game.log
  3 崩溃报告       main.py 里出现未捕获异常 → 写 crash.log（含版本和完整堆栈）→ 退出码 1
  4 字体优先级     环境变量 > 用户字体 > 系统字体 > 后备字体 > 默认
  5 打包命令       Windows/macOS/Linux 各自的图标、分隔符、版本资源、窗口模式参数
  6 压缩包结构     zip 里是否有统一的顶层目录、程序文件和玩家说明
用法： python -m tools.package_test
"""
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import types
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RW_NO_DIALOG", "1")          # 崩溃测试不要真的弹 Windows 消息框

from core.version import GAME_VERSION, EXE_NAME      # noqa: E402


def t_user_dir():
    from core import app_paths
    saved = (sys.platform, dict(os.environ))
    results = []
    try:
        os.environ.pop("RW_DATA_DIR", None)
        for plat, env, expect_part in [
            ("win32", {"APPDATA": r"C:\Users\x\AppData\Roaming"}, "SandboxGame"),
            ("darwin", {}, os.path.join("Library", "Application Support", "SandboxGame")),
            ("linux", {"XDG_DATA_HOME": "/home/x/.local/share"}, os.path.join(".local", "share", "SandboxGame")),
        ]:
            sys.platform = plat
            os.environ.update(env)
            p = app_paths.user_data_dir(create=False)
            results.append((plat, expect_part in p))
        sys.platform = saved[0]
        os.environ["RW_DATA_DIR"] = "/tmp/rw_override"
        results.append(("环境变量覆盖", app_paths.user_data_dir(create=False) == "/tmp/rw_override"))
    finally:
        sys.platform = saved[0]
        os.environ.clear(); os.environ.update(saved[1])
    ok = all(r for _, r in results)
    return ok, "；".join(f"{n}={'✓' if r else '✗'}" for n, r in results)


def run_py(code, env_extra=None, timeout=60):
    env = dict(os.environ)
    env["PYTHONPATH"] = ROOT
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=timeout, env=env, encoding="utf-8")


def t_logging():
    tmp = tempfile.mkdtemp()
    code = f"""
import sys
sys.stdout = None; sys.stderr = None            # 模拟 PyInstaller --windowed 的无控制台环境
from core import app_paths
path = app_paths.setup_logging()
print("这行 print 不该消失")
sys.stderr.write("这行 stderr 也不该消失\\n")
"""
    r = run_py(code, {"RW_DATA_DIR": tmp})
    log = os.path.join(tmp, "game.log")
    txt = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
    ok = r.returncode == 0 and "这行 print 不该消失" in txt and "stderr 也不该消失" in txt and f"v{GAME_VERSION}" in txt
    shutil.rmtree(tmp, ignore_errors=True)
    return ok, f"print/stderr 进入 game.log={ok}（退出码 {r.returncode}）"


def t_crash():
    tmp = tempfile.mkdtemp()
    code = '''
import sys, types, runpy
fake = types.ModuleType("pygame")
def boom(*a, **k): raise RuntimeError("模拟的游戏内部错误 xyz123")
fake.init = boom
for n in ("QUIT","KEYDOWN","VIDEORESIZE","K_F11","K_F10","K_ESCAPE","K_y","K_n","K_RETURN","K_KP_ENTER","RESIZABLE","FULLSCREEN","SRCALPHA"):
    setattr(fake, n, 1)
sys.modules["pygame"] = fake
sys.argv = ["main.py"]
runpy.run_path("main.py", run_name="__main__")
'''
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, encoding="utf-8",
                       env=dict(os.environ, RW_DATA_DIR=tmp, PYTHONPATH=ROOT), timeout=60)
    crash = os.path.join(tmp, "crash.log")
    txt = open(crash, encoding="utf-8").read() if os.path.exists(crash) else ""
    ok = r.returncode == 1 and "RuntimeError" in txt and "xyz123" in txt and f"v{GAME_VERSION}" in txt and "Traceback" in txt
    shutil.rmtree(tmp, ignore_errors=True)
    return ok, f"未捕获异常→退出码 {r.returncode}，crash.log 含版本与堆栈={ok}"


def t_fonts():
    from ui import fonts
    from core import app_paths
    bundled = app_paths.resource_path(*fonts.BUNDLED)
    user_dir = app_paths.resource_path("assets", "fonts", "user")
    names = {}

    def exists_only(*paths):
        return lambda p: p in paths

    sysfont = fonts.SYSTEM_FILES[0]
    res = []
    p, s = fonts.find_font_path(exists=exists_only(bundled), match=lambda n: None, env={"RW_FONT": "/x/custom.ttf"})
    res.append(("无任何系统字体→后备", p == bundled))
    p, s = fonts.find_font_path(exists=exists_only(bundled, sysfont), match=lambda n: None, env={})
    res.append(("有系统字体→系统字体优先", p == sysfont))
    p, s = fonts.find_font_path(exists=exists_only(bundled, sysfont, "/x/custom.ttf"), match=lambda n: None, env={"RW_FONT": "/x/custom.ttf"})
    res.append(("环境变量最优先", p == "/x/custom.ttf"))
    os.makedirs(user_dir, exist_ok=True)
    fake = os.path.join(user_dir, "zz_test_font.ttf")
    open(fake, "wb").write(b"x")
    try:
        p, s = fonts.find_font_path(exists=exists_only(bundled, sysfont), match=lambda n: None, env={})
        res.append(("用户字体目录优先于系统字体", p == fake))
    finally:
        os.remove(fake)
        try: os.rmdir(user_dir)
        except OSError: pass
    p, s = fonts.find_font_path(exists=lambda x: False, match=lambda n: None, env={})
    res.append(("什么都没有→默认字体", p is None and s == "default"))
    p, s = fonts.find_font_path(exists=exists_only(bundled, "/m/yahei.ttf"), match=lambda n: "/m/yahei.ttf" if n == "microsoftyahei" else None, env={})
    res.append(("按名称匹配系统字体", p == "/m/yahei.ttf"))
    return all(r for _, r in res), "；".join(f"{n}={'✓' if r else '✗'}" for n, r in res)


def t_commands():
    import build
    saved = (platform.system, os.pathsep)
    out = []
    try:
        class A: onefile = False; console = False
        for sysname, sep, want_icon, want_ver in [("Windows", ";", "icon.ico", True), ("Darwin", ":", "icon.icns", False), ("Linux", ":", None, False)]:
            platform.system = lambda s=sysname: s
            os.pathsep = sep
            cmd = build.build_command(A)
            j = " ".join(cmd)
            ok = ("--windowed" in cmd and "--onedir" in cmd and f"assets{sep}assets" in j
                  and (want_icon in j if want_icon else "--icon" not in cmd)
                  and (("--version-file" in cmd) == want_ver) and cmd[-1].endswith("main.py")
                  and "--hidden-import" in cmd and "--name" in cmd and EXE_NAME in cmd)
            out.append((sysname, ok))
        A.onefile, A.console = True, True
        platform.system = lambda: "Windows"; os.pathsep = ";"
        cmd = build.build_command(A)
        out.append(("onefile+console", "--onefile" in cmd and "--windowed" not in cmd and "--onedir" not in cmd))
    finally:
        platform.system, os.pathsep = saved
    return all(r for _, r in out), "；".join(f"{n}={'✓' if r else '✗'}" for n, r in out)


def t_zip():
    import build
    dist = os.path.join(ROOT, "dist")
    existed = os.path.exists(dist)
    app = os.path.join(dist, EXE_NAME)
    os.makedirs(os.path.join(app, "_internal"), exist_ok=True)
    open(os.path.join(app, EXE_NAME + ".exe"), "wb").write(b"MZ")
    open(os.path.join(app, "_internal", "x.dll"), "wb").write(b"x")
    zp = None
    try:
        zp = build.make_zip(app, "test.zip")
        names = zipfile.ZipFile(zp).namelist()
        top = {n.split("/")[0] for n in names}
        root = f"{EXE_NAME}-v{GAME_VERSION}"
        ok = top == {root} and f"{root}/{EXE_NAME}/{EXE_NAME}.exe" in names \
            and f"{root}/玩家说明.txt" in names and any(n.endswith("_internal/x.dll") for n in names)
        return ok, f"顶层目录={sorted(top)}，含程序、依赖、玩家说明={ok}"
    finally:
        shutil.rmtree(app, ignore_errors=True)
        if zp and os.path.exists(zp): os.remove(zp)
        if not existed:
            shutil.rmtree(dist, ignore_errors=True)


def main():
    plan = [("1 用户数据目录", t_user_dir), ("2 日志重定向", t_logging), ("3 崩溃报告", t_crash),
            ("4 字体优先级", t_fonts), ("5 各系统的打包命令", t_commands), ("6 压缩包结构", t_zip)]
    allok = True
    for name, fn in plan:
        try:
            ok, info = fn()
        except Exception as e:                                       # noqa: BLE001
            import traceback
            ok, info = False, f"异常 {type(e).__name__}: {e}\n" + traceback.format_exc()[-500:]
        allok &= bool(ok)
        print(f"{'✓' if ok else '✗'} {name}\n    {info}")
    print("\n全部通过 ✓" if allok else "\n存在失败 ✗")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
