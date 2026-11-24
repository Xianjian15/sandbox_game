# tools/make_font_subset.py
"""生成随游戏打包的"后备中文字体"（Noto Sans CJK SC 的子集）。开发者工具，玩家不需要运行。

为什么需要：打包后的游戏会优先使用玩家系统自带的中文字体（Windows 微软雅黑等）；
但在没有中文字体的系统上（精简版 Linux、某些容器），界面文字会变成方块。带一个小字体做后备就不会了。

子集内容：游戏源码里出现的所有字符 + 常用 ASCII/全角标点 + GB2312 一级汉字（约 3755 个常用字，
够玩家给房间起名）。体积约 1~2MB，完整字体有近 20MB。

用法：  python -m tools.make_font_subset [原字体.ttc]
          默认在常见位置自动寻找 NotoSansCJK-Regular.ttc
需要：  pip install fonttools
许可：  Noto Sans CJK 使用 SIL Open Font License 1.1，允许打包再分发（含修改/子集版本），
        条件是附带版权声明和许可文本——本脚本会一并生成 assets/fonts/OFL-NotoSansCJK.txt。
        子集字体改了家族名，不使用保留字体名。
"""
import ast
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "assets", "fonts")
OUT_FONT = os.path.join(OUT_DIR, "GameUISans-Subset.otf")
OUT_LICENSE = os.path.join(OUT_DIR, "OFL-NotoSansCJK.txt")

CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/Supplemental/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/NotoSansCJK-Regular.ttc",
]

OFL_TEXT = """-----------------------------------------------------------
SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
-----------------------------------------------------------

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font
creation efforts of academic and linguistic communities, and to provide
a free and open framework in which fonts may be shared and improved in
partnership with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded,
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply to
any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components
as distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to,
deleting, or substituting -- in part or in whole -- any of the
components of the Original Version, by changing formats or by porting
the Font Software to a new environment.

"Author" refers to any designer, engineer, programmer, technical writer
or other person who contributed to the Font Software.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining a
copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components, in
Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the
corresponding Copyright Holder. This restriction only applies to the
primary font name as presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole, must
be distributed entirely under this license, and must not be distributed
under any other license. The requirement for fonts to remain under this
license does not apply to any document created using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.
"""


def source_characters():
    """游戏源码里出现过的所有字符（字符串字面量 + 注释之外的文本都算，宁多勿少）。"""
    chars = set()
    for path in glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True):
        if os.sep + "tools" + os.sep in path:
            continue
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                chars.update(node.value)
    return chars


def gb2312_level1():
    """GB2312 一级汉字（3755 个最常用字）。"""
    out = set()
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            try:
                out.add(bytes([hi, lo]).decode("gb2312"))
            except UnicodeDecodeError:
                pass
    return out


def find_font(arg=None):
    for p in ([arg] if arg else []) + CANDIDATES:
        if p and os.path.exists(p):
            return p
    sys.exit("找不到 NotoSansCJK-Regular.ttc。请把路径作为参数传入： python -m tools.make_font_subset <字体文件>")


def main(argv=None):
    from fontTools import subset
    from fontTools.ttLib import TTFont
    src = find_font((argv or sys.argv[1:] or [None])[0])
    # 在 ttc 集合里找"简体中文"那一款
    n = 0
    index = None
    while True:
        try:
            f = TTFont(src, fontNumber=n, lazy=True)
        except Exception:                                              # noqa: BLE001
            break
        fam = f["name"].getDebugName(1) or ""
        if "SC" in fam.split():
            index = n
            break
        n += 1
    if index is None:
        sys.exit("字体集合里没有找到 SC（简体中文）款")
    text = set(chr(c) for c in range(0x20, 0x7F))                       # ASCII
    text |= source_characters()
    text |= gb2312_level1()
    text |= set("，。！？、；：“”‘’（）【】《》…—·￥％＋－＝＜＞～　℃×÷①②③④⑤⑥⑦⑧⑨⑩←↑→↓▲▼●○■□★☆✓✗·")
    unicodes = sorted(ord(c) for c in text if not c.isspace() or c == " ")
    opts = subset.Options()
    opts.layout_features = ["kern", "liga", "ccmp", "locl", "mark", "mkmk"]
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]                       # 保留版权/许可相关 name 记录
    opts.notdef_outline = True
    opts.hinting = False
    opts.desubroutinize = True
    font = TTFont(src, fontNumber=index)
    copyright_line = font["name"].getDebugName(0) or ""
    license_line = font["name"].getDebugName(13) or ""
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=unicodes)
    sub.subset(font)
    # 改家族名：这是修改版，不沿用原名（OFL 条款 3）。版权声明保留在 nameID 0。
    for rec in font["name"].names:
        if rec.nameID in (1, 16):
            rec.string = "Game UI Sans"
        elif rec.nameID in (4, 18):
            rec.string = "Game UI Sans Regular"
        elif rec.nameID == 6:
            rec.string = "GameUISans-Regular"
        elif rec.nameID == 3:
            rec.string = "GameUISans-Subset;derived-from-Noto-Sans-CJK-SC"
    os.makedirs(OUT_DIR, exist_ok=True)
    font.save(OUT_FONT)
    with open(OUT_LICENSE, "w", encoding="utf-8") as f:
        f.write("本目录下的 GameUISans-Subset.otf 是 Noto Sans CJK SC 字体的子集（只保留游戏界面用到的字符，\n"
                "并改了家族名），按 SIL Open Font License 1.1 再分发。\n\n"
                f"原字体版权声明：\n  {copyright_line}\n  {license_line}\n\n"
                "原字体项目： https://github.com/notofonts/noto-cjk\n\n" + OFL_TEXT)
    size = os.path.getsize(OUT_FONT)
    cmap = font.getBestCmap()
    missing = [c for c in sorted(source_characters()) if not c.isspace() and ord(c) not in cmap and ord(c) >= 0x2E80]
    print(f"已生成 {OUT_FONT}  ({size / 1024:.0f} KB)，收录 {len(cmap)} 个字符；游戏源码里字体缺字: {missing or '无'}")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
