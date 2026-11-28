# tools/gen_textures.py —— 一键生成全部贴图到 assets/textures/*.png
"""用法： python -m tools.gen_textures
需要 Pillow（仅开发期用；玩家运行游戏不需要）。贴图有改动后重新运行即可。"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


HAND_KEYS = ("stone_pickaxe", "iron_pickaxe", "stone_axe", "axe", "stone_spear", "spear", "iron_spear", "stone_hammer",
             "war_hammer", "stone_knife", "dagger", "machete", "longsword", "club", "bow", "crossbow", "pistol", "rifle",
             "shotgun", "smg", "sniper", "gun")


def main():
    try:
        from tools import fake_pygame; fake_pygame.install()          # 只为导入建筑表，不需要真 pygame
    except Exception:
        pass
    from world.buildings import BUILDING_DEFS
    from tools import gen_terrain, gen_buildings, gen_items, gen_creatures
    out = {}
    out.update(gen_terrain.build()); out.update(gen_buildings.build(BUILDING_DEFS))
    out.update(gen_items.build()); out.update(gen_creatures.build())
    gen_items.SHADOW = False                                   # 手持武器：同样的图，不带投影，运行时按朝向旋转
    hold = gen_items.build("hold_")
    out.update({k: v for k, v in hold.items() if k[len("hold_"):] in HAND_KEYS})
    d = os.path.join(ROOT, "assets", "textures")
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        if f.endswith(".png"): os.remove(os.path.join(d, f))
    for name, im in out.items():
        im.save(os.path.join(d, name + ".png"), optimize=True)
    print(f"已生成 {len(out)} 张贴图 → {d}")


if __name__ == "__main__":
    main()
