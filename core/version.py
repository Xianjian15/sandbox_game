# core/version.py
"""版本与名称：全项目唯一的来源。发布新版本时只改这里。

GAME_VERSION 会参与联机握手：两端版本不同的玩家无法联机（模拟逻辑不同必然分叉），
并且在房间列表里显示为"版本不符"。所以每次改动了游戏规则/数值/存档格式都应该升版本号。
"""
GAME_VERSION = "0.15.1"
DISPLAY_NAME = "RimWorld-like 沙盒生存"      # 窗口标题、主菜单大标题
EXE_NAME = "SandboxGame"                      # 打包出的程序文件名（建议纯英文，避免部分系统路径问题）
DATA_DIR_NAME = "SandboxGame"                 # 日志/崩溃报告所在的用户数据目录名
