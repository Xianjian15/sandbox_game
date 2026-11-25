# RimWorld-like 沙盒生存

Python + pygame-ce 的 2D 俯视角殖民地沙盒游戏，支持局域网 2~4 人联机（锁步同步，每位玩家控制自己的小人）。

## 玩家：怎么玩

不需要安装 Python。到仓库的 **Releases** 页面下载对应系统的 zip，解压后双击
`SandboxGame.exe`（macOS 是 `SandboxGame.app`）即可。详细说明见 `assets/玩家说明.txt`。

## 开发者：从源码运行

```
pip install -r requirements.txt
python main.py                       # 主菜单：单人 / 多人（局域网房间列表）
python main.py --host                # 命令行直接开房（可选）
python main.py --join 192.168.1.5    # 命令行直连（可选）
```

调试输出：运行前设置环境变量 `RW_DEBUG=1`。

## 开发者：打包成独立程序

```
pip install -r requirements-build.txt     # pygame-ce + pyinstaller
python build.py                            # 自检 → 打包 → 生成 dist/SandboxGame-v版本-系统.zip
```

| 命令 | 作用 |
|---|---|
| `python build.py` | 文件夹版 + zip（推荐：启动快、杀毒软件误报少） |
| `python build.py --onefile` | 单个文件（体积小，但每次启动都要解压，更慢、更易被误报） |
| `python build.py --console` | 保留控制台窗口，程序闪退/打不开时用来看报错 |
| `python build.py --check` | 只做打包前自检 |
| `python build.py --dry-run` | 只打印将要执行的 PyInstaller 命令 |

**PyInstaller 不能交叉编译**：要 Windows 的 `.exe` 必须在 Windows 上打包，要 mac 的 `.app` 必须在 mac 上打包。
没有对应系统的电脑，就把代码推到 GitHub，`.github/workflows/build.yml` 会在云端同时打出三个系统的版本
（手动：Actions → 打包游戏 → Run workflow；发布：`git tag v0.1.0 && git push origin v0.1.0`，自动生成 Release）。

### 发布新版本的步骤
1. 改 `core/version.py` 里的 `GAME_VERSION`（**只要改了游戏规则/数值，就必须升版本号**——
   不同版本的玩家无法联机，因为两端的模拟必须完全一致）。
2. `python -m tools.package_check && python -m tools.package_test`（`build.py` 也会自动跑自检）。
3. 打包并在**没装 Python 的电脑**上试一次。

### 相关文件
| 文件 | 说明 |
|---|---|
| `core/version.py` | 版本号、游戏名、程序名（唯一来源） |
| `core/app_paths.py` | 资源路径、用户数据目录、日志、崩溃报告 |
| `ui/fonts.py` | 字体选择（系统字体 → 内置后备字体） |
| `assets/` | 图标（`tools/make_icon.py` 生成，可替换成自己的）、后备字体及其许可 |
| `build.py` / `requirements-build.txt` | 打包脚本与依赖 |
| `tools/package_check.py` | 打包前自检 |
| `tools/package_test.py` | 打包相关代码的测试 |

### 玩家数据与日志
程序**不会**往自己所在的文件夹写任何东西。日志和崩溃报告在：
Windows `%APPDATA%\SandboxGame\`，macOS `~/Library/Application Support/SandboxGame/`，
Linux `~/.local/share/SandboxGame/`（`crash.log`、`game.log`、`desync_report.json`）。

### 字体
界面优先使用玩家系统里的中文字体；一个都没有时回退到内置的 `assets/fonts/GameUISans-Subset.otf`
（Noto Sans CJK 子集，SIL OFL 1.1 许可，见 `assets/fonts/OFL-NotoSansCJK.txt`）。
想换成自己的字体：丢一个 `.ttf/.otf/.ttc` 到 `assets/fonts/user/` 即可，它优先级最高。
重新生成后备字体：`python -m tools.make_font_subset`（需要 `pip install fonttools`）。

## 测试

| 命令 | 内容 |
|---|---|
| `python -m tools.determinism_test` | 两个世界同 seed 对拍，逐 tick 比对状态哈希 |
| `python -m tools.command_test` | 指令序列化 / 回放一致 / 双端锁步 |
| `python -m tools.net_test` | 真实 TCP 联机：卡顿、碎片化、分叉检测、掉线、非法数据 |
| `python -m tools.menu_test` | 主菜单、局域网房间发现、创建/加入房间 |
| `python -m tools.package_check` / `package_test` | 打包前自检 / 打包代码测试 |

## 玩家资料与自动回血

- 联机大厅左上角点自己的名字：设置用户名、上传头像（文件选择窗口，或拖图片进窗口）。资料保存在用户数据目录的 `profile.json`。
- 资料只用于显示，不参与模拟与状态哈希；联机时随握手发给主机，主机清洗后把名单发给所有人。
- 小人自动回血：规则在 `core/regen.py`，参数在 `settings.py`（REGEN_DELAY / REGEN_RATE）。
- 测试：`python -m tools.profile_test`（回血、资料、名单、资料页流程）。
