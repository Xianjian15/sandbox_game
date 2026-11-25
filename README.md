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

## 界面自动缩放

- 界面画在“逻辑尺寸”画布（窗口尺寸 ÷ 缩放比例）上，再整体平滑缩放到窗口；鼠标坐标反向换算。地图仍按真实分辨率绘制。
- 缩放比例 = min(窗口宽/1280, 窗口高/720) × 玩家偏好（Ctrl +/-/0，存 `ui.json`），范围 0.6~3.0。比例恰为 1.0（1280×720）时直接画在屏幕上。
- 实现在 `core/ui_scale.py`，游戏内接入见 `GameWorld._draw_ui / _L / handle_event`，菜单见 `run_menu`。新写的界面代码照旧按 1280×720 的像素值写即可，不用关心缩放；
  但“点击判定”必须用换算后的逻辑坐标（`self._L(event.pos)`），地图相关仍用窗口坐标。
- 测试：`python -m tools.ui_scale_test`（没装 pygame 时自动用 `tools/fake_pygame.py`，游戏本体照常运行）。

## 敌人入侵规则（v0.5.0）
- 警报数字 = 实际生成的敌人数（出生点不可走时会重试；一个都没生成则不报警、四分之一天后重试）。
- 单波数量上限：联机 = 玩家总数；单人 = 3。
- 威胁等级 = (天数-1)//2 + 已来袭波数（单人再 -1，武器更弱）。等级越高，数量上限越接近玩家数，武器依次：拳头/木棒 → 矛/斧 → 斧/手枪 → 手枪/长剑 → 长剑/步枪。
- 规则变更，GAME_VERSION 升到 0.5.0，联机双方须使用同一版本。

## 中文用户名 / 面板位置
- 用户名、房间名可直接用中文输入法输入：输入法正在组合的拼音以黄色下划线显示在输入框里，选字确认后才写入；候选框会出现在输入框旁边；名字过长时只显示末尾。用户名最多 12 个字，房间名 20 个字。
- 选中小人后，小人面板显示在左下角，紧贴底部工具栏/建造菜单上方，不再遮挡它们。

## 界面大小
- 默认界面大小 85%，窗口变大时按钮/字体大小不变（地图显示范围变大）；窗口小于 1280×720 时才自动缩小。
- Ctrl + / Ctrl - 调整，Ctrl 0 恢复默认。
- 建造栏按钮放不下时自动变窄，保证全部可见。

## 新手教程
- 首次启动自动弹出；主菜单「新手教程」；游戏中按 F1 随时打开（联机时不会暂停游戏）。
- 共 10 页：目标与流程 / 视角与选择 / 右键指挥 / 工具栏与快捷键 / 建造 / 食物与农业 / 研究与工作站 / 战斗 / 时间与界面快捷键 / 联机。
- 内容是纯数据（ui/tutorial.py 的 PAGES），改文字不需要动别处。看过的标记文件为用户数据目录下的 tutorial_seen，删掉它会再次自动弹出。
