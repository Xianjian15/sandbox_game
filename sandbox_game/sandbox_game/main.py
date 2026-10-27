# main.py
import os
import pygame
import sys
import random
from settings import *
from core.camera import Camera
from core.time_system import GameTime
from world.world import World
from world.items import ItemManager, ITEM_DEFS, ItemStack
from world.stockpile import StockpileManager
from world.farm import FarmManager
from world.buildings import BuildingManager, BUILDING_DEFS, Building, Blueprint
from ui.selection import Selection
from ui.hud import HUD
from ui.building_hud import BuildingHUD
from ui.stockpile_hud import StockpileHUD
from ui.item_hud import ItemHUD
from ui.build_menu import BuildMenu
from ui.toolbar import Toolbar
from ui.research_menu import ResearchMenu
from entities.colonist import Colonist
from entities.enemy import Enemy
from entities.animal import Animal
from combat.effects import Shot, MeleeHit, CombatLog
from systems.research import ResearchManager

INIT_W, INIT_H = 1280, 720


def load_font(size=18):
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def main():
    pygame.init()
    screen = pygame.display.set_mode((INIT_W, INIT_H), pygame.RESIZABLE)
    pygame.display.set_caption("RimWorld-like - 手动搬运与烹饪")
    clock = pygame.time.Clock()

    font = load_font(16)
    font_big = load_font(20)
    font_small = load_font(14)
    font_warn = load_font(28)

    game_time = GameTime(day_length_sec=120.0, start_hour=7.0)
    research_mgr = ResearchManager()

    world = World(MAP_WIDTH, MAP_HEIGHT)
    items = ItemManager()
    stockpiles = StockpileManager()
    farms = FarmManager()
    buildings = BuildingManager(research_mgr)
    world.buildings = buildings

    camera = Camera(INIT_W, INIT_H, MAP_WIDTH * TILE_SIZE, MAP_HEIGHT * TILE_SIZE)
    camera.x = (MAP_WIDTH * TILE_SIZE - INIT_W) / 2
    camera.y = (MAP_HEIGHT * TILE_SIZE - INIT_H) / 2

    selection = Selection()
    hud = HUD(font)
    bhud = BuildingHUD(font)
    shud = StockpileHUD(font)
    ihud = ItemHUD(font)
    build_menu = BuildMenu(font)
    toolbar = Toolbar(font)
    research_menu = ResearchMenu(font)
    log = CombatLog()

    colonists = []
    base_x = MAP_WIDTH // 2
    base_y = MAP_HEIGHT // 2 - 5
    for i in range(3):
        found = None
        for dy in range(-2, 3):
            for dx in range(-3, 4):
                tx, ty = base_x + i * 2 + dx, base_y + dy
                if world.is_walkable(tx, ty):
                    found = (tx, ty);
                    break
            if found: break
        if not found: found = (base_x, base_y)
        colonists.append(Colonist(*found, weapon_key="fist"))

    Colonist._items_ref = items
    Colonist._buildings_ref = buildings

    enemies = []
    animals = []
    spawn_attempts = 0
    while len(animals) < 15 and spawn_attempts < 200:
        spawn_attempts += 1
        ax, ay = random.randint(5, MAP_WIDTH - 5), random.randint(5, MAP_HEIGHT - 5)
        if world.is_walkable(ax, ay):
            is_safe = True
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                if not world.is_walkable(ax + dx, ay + dy): is_safe = False; break
            if is_safe:
                animals.append(Animal(ax, ay, random.choice(["rabbit", "rabbit", "deer", "deer", "deer"])))

    animal_respawn_timer = 10.0
    MAX_ANIMALS = 20
    enemy_invasion_timer = game_time.day_length_sec * 3

    effects = []
    mode = None
    current_build_kind = None
    current_build_mat = None
    build_rotation = 0
    show_help = False

    farm_start = None
    farm_end = None
    pending_farm_rect = None

    selected_building = None
    selected_stockpile = None
    selected_item_stack = None

    drag_start = None
    drag_end = None
    dragging_cam_right = False
    right_down_pos = (0, 0)
    last_mouse = (0, 0)
    left_down_pos = None
    left_drag_moved = False
    auto_work = True
    game_speed = 1.0
    is_fullscreen = False
    warning_timer = 0.0
    warning_text = ""

    running = True
    while running:
        dt_raw = clock.tick(FPS) / 1000.0
        dt = dt_raw * game_speed
        if game_speed > 0:
            game_time.update(dt)
            farms.update(dt)

        screen_w, screen_h = screen.get_size()
        mouse_pos = pygame.mouse.get_pos()
        mods = pygame.key.get_mods()
        shift_held = bool(mods & pygame.KMOD_SHIFT)

        ui_bottom_height = toolbar.height
        if mode == "build":
            ui_bottom_height += build_menu.height
            if build_menu.active_kind:
                ui_bottom_height += build_menu.sub_height

        selected_colonists = [c for c in colonists if c.selected]
        mouse_in_colonist_hud = hud.panel_rect.collidepoint(mouse_pos) and bool(selected_colonists)
        mouse_in_building_hud = bhud.panel_rect.collidepoint(mouse_pos) and bool(selected_building)
        mouse_in_stockpile_hud = shud.panel_rect.collidepoint(mouse_pos) and bool(selected_stockpile)
        mouse_in_item_hud = ihud.panel_rect.collidepoint(mouse_pos) and bool(selected_item_stack)
        mouse_in_ui = mouse_in_colonist_hud or mouse_in_building_hud or mouse_in_stockpile_hud or mouse_in_item_hud

        global_items = {}
        for s in items.stacks.values():
            global_items[s.kind] = global_items.get(s.kind, 0) + s.amount
        for b in buildings.buildings.values():
            if b.kind in ("small_cabinet", "large_cabinet"):
                for k, amt in b.inventory.items():
                    global_items[k] = global_items.get(k, 0) + amt

        if warning_timer > 0:
            warning_timer -= dt_raw
        else:
            attacked = [c for c in colonists if c.hp > 0 and c.hit_flash > 0.1]
            if attacked:
                names = ", ".join([c.name for c in attacked[:3]])
                if len(attacked) > 3: names += "..."
                warning_text = f"警告: {names} 正在遭受攻击！"
                warning_timer = 2.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                camera.resize(event.w, event.h)

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    if game_speed == 0.0:
                        game_speed = 1.0
                    elif game_speed == 1.0:
                        game_speed = 2.0
                    elif game_speed == 2.0:
                        game_speed = 3.0
                    else:
                        game_speed = 0.0
                    continue
                elif event.key == pygame.K_F11:
                    is_fullscreen = not is_fullscreen
                    if is_fullscreen:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((INIT_W, INIT_H), pygame.RESIZABLE)
                    camera.resize(screen.get_width(), screen.get_height())
                elif event.key == pygame.K_ESCAPE:
                    if show_help:
                        show_help = False
                    elif mode is not None:
                        mode = None
                        current_build_kind = None
                        current_build_mat = None
                        build_menu.active_kind = None
                        pending_farm_rect = None
                    else:
                        for c in colonists: c.selected = False
                        selected_building = None
                        selected_stockpile = None
                        selected_item_stack = None
                        selection.clear()
                elif event.key == pygame.K_h:
                    show_help = not show_help
                elif event.key == pygame.K_b:
                    mode = "build" if mode != "build" else None
                    current_build_kind = None;
                    current_build_mat = None;
                    build_menu.active_kind = None
                elif event.key == pygame.K_s:
                    mode = "stockpile" if mode != "stockpile" else None
                elif event.key == pygame.K_f:
                    mode = "farm" if mode != "farm" else None
                    pending_farm_rect = None
                elif event.key == pygame.K_x:
                    mode = "deconstruct" if mode != "deconstruct" else None
                elif event.key == pygame.K_r:
                    if mode == "build" and current_build_kind:
                        data = BUILDING_DEFS[current_build_kind]
                        if data["w"] != data["h"]:
                            build_rotation = (build_rotation + 1) % 2
                    else:
                        mode = "research" if mode != "research" else None
                elif event.key == pygame.K_a:
                    auto_work = not auto_work
                elif event.key == pygame.K_g:
                    if selected_colonists:
                        ah_count = sum(1 for c in selected_colonists if c.auto_harvest)
                        new_state = not (ah_count == len(selected_colonists))
                        for c in selected_colonists: c.auto_harvest = new_state

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if not mouse_in_ui:
                    dragging_cam_right = True
                    right_down_pos = event.pos
                    last_mouse = event.pos
            elif event.type == pygame.MOUSEMOTION:
                if dragging_cam_right:
                    dx, dy = event.pos[0] - last_mouse[0], event.pos[1] - last_mouse[1]
                    camera.move_by(-dx, -dy)
                    last_mouse = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                if dragging_cam_right:
                    dragging_cam_right = False
                    dist = abs(event.pos[0] - right_down_pos[0]) + abs(event.pos[1] - right_down_pos[1])
                    if dist < 5 and mode is None and not show_help and not mouse_in_ui:
                        selected = [c for c in colonists if c.selected and c.hp > 0]
                        if selected:
                            wx, wy = camera.screen_to_world(*event.pos)
                            tx, ty = camera.screen_to_tile(*event.pos)

                            hit_enemy = None
                            for e in enemies:
                                if (e.x - wx) ** 2 + (e.y - wy) ** 2 <= (e.radius + 12) ** 2: hit_enemy = e; break
                            hit_animal = None
                            for a in animals:
                                if (a.x - wx) ** 2 + (a.y - wy) ** 2 <= (a.radius + 10) ** 2: hit_animal = a; break

                            hit_item = None
                            for s in items.get_at(tx, ty):
                                if (s.x - wx) ** 2 + (s.y - wy) ** 2 <= (TILE_SIZE // 2) ** 2:
                                    hit_item = s;
                                    break

                            if hit_enemy is not None:
                                cmd = {"type": "attack", "enemy": hit_enemy}
                                if not shift_held:
                                    for c in selected: c.queue.clear(); c.job = None; c.path = []; c.target_enemy = None; c.target_animal = None
                                    for c in selected: c.assign_attack(hit_enemy)
                                else:
                                    for c in selected: c.enqueue_command(cmd)
                            elif hit_animal is not None:
                                cmd = {"type": "hunt", "animal": hit_animal}
                                if not shift_held:
                                    for c in selected: c.queue.clear(); c.job = None; c.path = []; c.target_enemy = None; c.target_animal = None
                                    for c in selected: c.assign_hunt(hit_animal)
                                else:
                                    for c in selected: c.enqueue_command(cmd)
                            elif hit_item is not None:
                                # 指派搬运
                                cabinet = None
                                for b in buildings.buildings.values():
                                    if b.kind in ("small_cabinet",
                                                  "large_cabinet") and not b.marked_for_deconstruction and b.reserved_by is None:
                                        current_types = len(b.inventory.keys())
                                        if hit_item.kind not in b.inventory and current_types >= b.max_types:
                                            continue
                                        space = b.capacity - b.inventory.get(hit_item.kind, 0)
                                        if space > 0:
                                            cabinet = b
                                            break

                                target_pos = (0, 0)
                                if cabinet:
                                    target_pos = (cabinet.tx, cabinet.ty)
                                else:
                                    sp_dst = selected[0]._find_dst_slot(items, stockpiles)
                                    if sp_dst: target_pos = sp_dst

                                if cabinet or target_pos != (0, 0):
                                    cmd = {"type": "haul", "world": world, "items": items, "stockpiles": stockpiles,
                                           "src": (tx, ty), "dst": target_pos, "kind": hit_item.kind,
                                           "amount": hit_item.amount, "cabinet": cabinet}
                                    if not shift_held:
                                        for c in selected: c.queue.clear(); c.job = None; c.path = []
                                        selected[0].assign_haul(world, items, stockpiles, tx, ty, target_pos[0],
                                                                target_pos[1], hit_item.kind, hit_item.amount, cabinet)
                                    else:
                                        for c in selected: c.enqueue_command(cmd)

                            elif buildings.get_blueprints_at(tx, ty):
                                bp = buildings.get_blueprints_at(tx, ty)[0]
                                bp.reserved_by = None
                                cmd = {"type": "build", "world": world, "buildings": buildings, "items": items,
                                       "stockpiles": stockpiles, "bp": bp}
                                if not shift_held:
                                    for c in selected: c.queue.clear(); c.job = None; c.path = []; c.target_enemy = None; c.target_animal = None
                                    selected[0].assign_build(world, buildings, items, stockpiles, bp)
                                else:
                                    for c in selected: c.enqueue_command(cmd)
                            elif world.is_harvestable(tx, ty):
                                cmd = {"type": "harvest", "world": world, "tx": tx, "ty": ty}
                                if not shift_held:
                                    for c in selected: c.queue.clear(); c.job = None; c.path = []; c.target_enemy = None; c.target_animal = None
                                    selected[0].assign_harvest(world, tx, ty)
                                else:
                                    for c in selected: c.enqueue_command(cmd)
                            elif world.is_walkable(tx, ty):
                                offsets = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
                                for i, c in enumerate(selected):
                                    ox, oy = offsets[i % len(offsets)]
                                    gx, gy = tx + ox, ty + oy
                                    if not world.is_walkable(gx, gy): gx, gy = tx, ty
                                    cmd = {"type": "move", "world": world, "tx": gx, "ty": gy}
                                    if not shift_held:
                                        c.queue.clear();
                                        c.job = None;
                                        c.path = [];
                                        c.target_enemy = None;
                                        c.target_animal = None
                                        c.move_to(world, gx, gy)
                                    else:
                                        c.enqueue_command(cmd)

            if mode == "farm" and pending_farm_rect:
                popup_rect = pygame.Rect(screen_w // 2 - 200, screen_h // 2 - 100, 400, 200)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if pygame.Rect(screen_w // 2 - 180, screen_h // 2 - 30, 160, 50).collidepoint(event.pos):
                        if research_mgr.can_plant("berry"):
                            farms.add(pending_farm_rect, "berry")
                            pending_farm_rect = None;
                            mode = None
                    elif pygame.Rect(screen_w // 2 + 20, screen_h // 2 - 30, 160, 50).collidepoint(event.pos):
                        if research_mgr.can_plant("tree"):
                            farms.add(pending_farm_rect, "tree")
                            pending_farm_rect = None;
                            mode = None
                    elif pygame.Rect(screen_w // 2 - 50, screen_h // 2 + 60, 100, 30).collidepoint(event.pos):
                        pending_farm_rect = None
                    continue

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hud.handle_click(event.pos, selected_colonists):
                    left_down_pos = None;
                    continue

                consumed, action = bhud.handle_click(event.pos, selected_building, global_items)
                if consumed:
                    left_down_pos = None;
                    continue

                consumed_sp, delete_sp = shud.handle_click(event.pos)
                if consumed_sp:
                    if delete_sp:
                        if selected_stockpile in stockpiles.stockpiles:
                            stockpiles.stockpiles.remove(selected_stockpile)
                        selected_stockpile = None
                    left_down_pos = None;
                    continue

                if ihud.handle_click(event.pos):
                    left_down_pos = None;
                    continue

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if mouse_in_ui:
                    left_down_pos = None;
                    continue

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked_mode = toolbar.handle_click(event.pos)
                if clicked_mode != "NOT_CLICKED":
                    if clicked_mode == "close":
                        mode = None; current_build_kind = None; current_build_mat = None; build_menu.active_kind = None
                    elif mode == clicked_mode:
                        mode = None
                    else:
                        mode = clicked_mode; current_build_kind = None; current_build_mat = None
                    drag_start = None;
                    drag_end = None;
                    left_down_pos = None
                    continue

                if mode == "build" and event.pos[1] > screen_h - ui_bottom_height:
                    k, m, is_selected = build_menu.handle_click(event.pos, research_mgr)
                    if is_selected:
                        current_build_kind = k
                        current_build_mat = m
                        build_rotation = 0
                    left_down_pos = None;
                    continue

                if mode == "research":
                    panel_w, panel_h = 600, 400
                    rx, ry = screen_w // 2 - panel_w // 2, screen_h // 2 - panel_h // 2
                    if rx <= event.pos[0] <= rx + panel_w and ry <= event.pos[1] <= ry + panel_h:
                        research_menu.handle_click(event.pos, research_mgr)
                        left_down_pos = None;
                        continue

            if show_help:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1: show_help = False
                continue

            if mode in ("stockpile", "build", "deconstruct", "farm"):
                if pending_farm_rect: continue

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if mode == "build" and (current_build_kind is None or current_build_mat is None): continue
                    if event.pos[1] < screen_h - ui_bottom_height:
                        drag_start = camera.screen_to_tile(*event.pos)
                        drag_end = drag_start
                elif event.type == pygame.MOUSEMOTION and drag_start:
                    drag_end = camera.screen_to_tile(*event.pos)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if drag_start and drag_end:
                        x1, y1 = drag_start;
                        x2, y2 = drag_end
                        tx1, tx2 = min(x1, x2), max(x1, x2);
                        ty1, ty2 = min(y1, y2), max(y1, y2)
                        if mode == "stockpile":
                            stockpiles.add((tx1, ty1, tx2, ty2))
                            mode = None
                        elif mode == "farm":
                            pending_farm_rect = (tx1, ty1, tx2, ty2)
                        elif mode == "build" and current_build_kind and current_build_mat:
                            w, h = BUILDING_DEFS[current_build_kind]["w"], BUILDING_DEFS[current_build_kind]["h"]
                            if build_rotation % 2 == 1: w, h = h, w
                            for ty in range(ty1, ty2 + 1, h):
                                for tx in range(tx1, tx2 + 1, w):
                                    if buildings.can_place(world, tx, ty, current_build_kind, current_build_mat,
                                                           build_rotation):
                                        buildings.add_blueprint(current_build_kind, current_build_mat, tx, ty,
                                                                build_rotation)
                        elif mode == "deconstruct":
                            stockpiles.remove_tiles(tx1, ty1, tx2, ty2)
                            farms.remove_tiles(tx1, ty1, tx2, ty2)
                            buildings.remove_area(tx1, ty1, tx2, ty2)
                    drag_start = None;
                    drag_end = None
                continue

            if not dragging_cam_right:
                selection.handle_event(event, camera, mouse_pos)

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    left_down_pos = event.pos
                    left_drag_moved = False
                elif event.type == pygame.MOUSEMOTION and left_down_pos is not None:
                    if abs(event.pos[0] - left_down_pos[0]) > 8 or abs(event.pos[1] - left_down_pos[1]) > 8:
                        left_drag_moved = True
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if not left_drag_moved and left_down_pos is not None:
                        wx, wy = camera.screen_to_world(*event.pos)
                        tx, ty = camera.screen_to_tile(*event.pos)

                        hit_col = None
                        for c in colonists:
                            if c.hp <= 0: continue
                            if (c.x - wx) ** 2 + (c.y - wy) ** 2 <= (c.radius + 15) ** 2:
                                hit_col = c;
                                break

                        if hit_col:
                            if not shift_held:
                                for c in colonists: c.selected = False
                            hit_col.selected = True
                            selected_building = None;
                            selected_stockpile = None;
                            selected_item_stack = None
                            if not shift_held: selection.selected_tiles.clear()
                        else:
                            hit_item = None
                            for s in items.get_at(tx, ty):
                                if (s.x - wx) ** 2 + (s.y - wy) ** 2 <= (TILE_SIZE // 2) ** 2:
                                    hit_item = s;
                                    break

                            if hit_item:
                                selected_building = None;
                                selected_stockpile = None
                                selected_item_stack = hit_item
                                ihud.set_target(hit_item, tx, ty)
                                ihud.in_cabinet = False
                                selection.selected_tiles.clear()
                            else:
                                hit_building = buildings.get_building_at(tx, ty)
                                if not hit_building:
                                    bps = buildings.get_blueprints_at(tx, ty)
                                    if bps: hit_building = bps[0]

                                if hit_building and hit_building.kind == "floor":
                                    hit_building = None

                                if hit_building:
                                    for c in colonists: c.selected = False
                                    selected_building = hit_building
                                    selected_stockpile = None;
                                    selected_item_stack = None
                                    selection.selected_tiles.clear()
                                else:
                                    hit_sp = stockpiles.find_stockpile_for(tx, ty)
                                    if hit_sp:
                                        selected_building = None;
                                        selected_stockpile = hit_sp;
                                        selected_item_stack = None
                                        shud.set_target(hit_sp, event.pos, screen_w, screen_h)
                                    else:
                                        if not shift_held:
                                            for c in colonists: c.selected = False
                                            selected_building = None;
                                            selected_stockpile = None;
                                            selected_item_stack = None
                    else:
                        for c in colonists: c.selected = False
                        selected_building = None;
                        selected_stockpile = None;
                        selected_item_stack = None
                        for c in colonists:
                            if c.hp > 0 and c.current_tile() in selection.selected_tiles:
                                c.selected = True
                    left_down_pos = None;
                    left_drag_moved = False

        edge_margin = 20
        scroll_speed = 600 * dt_raw
        if not mouse_in_ui:
            if mouse_pos[0] < edge_margin:
                camera.move_by(-scroll_speed, 0)
            elif mouse_pos[0] > screen_w - edge_margin:
                camera.move_by(scroll_speed, 0)
            if mouse_pos[1] < edge_margin:
                camera.move_by(0, -scroll_speed)
            elif mouse_pos[1] > screen_h - edge_margin:
                camera.move_by(0, scroll_speed)

        if game_speed > 0:
            for c in colonists:
                c.update_needs(dt, game_time)
                c.check_urgent_needs(world, items, stockpiles, buildings)
                c.update(dt, world, items, stockpiles, buildings, enemies, game_time, research_mgr)

            for e in enemies:
                e.update(dt, world, colonists, buildings)
            for a in animals:
                a.update(dt, world, colonists)
            animals = [a for a in animals if a.hp > 0]

            animal_respawn_timer -= dt
            if animal_respawn_timer <= 0 and len(animals) < MAX_ANIMALS:
                animal_respawn_timer = 15.0
                for _ in range(20):
                    ax, ay = random.randint(5, MAP_WIDTH - 5), random.randint(5, MAP_HEIGHT - 5)
                    if world.is_walkable(ax, ay):
                        is_safe = True
                        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                            if not world.is_walkable(ax + dx, ay + dy): is_safe = False; break
                        if is_safe:
                            animals.append(Animal(ax, ay, random.choice(["rabbit", "rabbit", "deer", "deer", "deer"])))
                            break

            enemy_invasion_timer -= dt
            if enemy_invasion_timer <= 0:
                enemy_invasion_timer = game_time.day_length_sec * 3
                if random.random() < 0.5:
                    count = random.randint(1, 3)
                    for _ in range(count):
                        ex, ey = random.randint(5, MAP_WIDTH - 5), random.randint(5, MAP_HEIGHT - 5)
                        if world.is_walkable(ex, ey):
                            enemies.append(Enemy(ex, ey))
                    log.add(f"警告：发现 {count} 名敌人入侵！", (255, 50, 50))
                    warning_text = f"警告：发现 {count} 名敌人入侵！"
                    warning_timer = 3.0

            for c in colonists:
                if c.recent_shot is not None:
                    kind, x1, y1, x2, y2, color = c.recent_shot
                    if kind == "shot":
                        effects.append(Shot(x1, y1, x2, y2, color))
                    else:
                        effects.append(MeleeHit(x2, y2, color))
                    c.recent_shot = None
            for e in enemies:
                if e.recent_shot is not None:
                    kind, x1, y1, x2, y2, color = e.recent_shot
                    if kind == "shot":
                        effects.append(Shot(x1, y1, x2, y2, color))
                    else:
                        effects.append(MeleeHit(x2, y2, color))
                    e.recent_shot = None

            for c in colonists:
                if c.hp <= 0:
                    log.add(f"{c.name} 倒下了！", (255, 80, 80))
                    if c.bed_tile is not None:
                        b = buildings.get_building_at(c.bed_tile[0], c.bed_tile[1])
                        if b and b.occupied_by == c.id: b.occupied_by = None
            colonists = [c for c in colonists if c.hp > 0]

            for e in enemies:
                if e.hp <= 0: log.add(f"{e.name} 被击杀", (100, 255, 100))
            enemies = [e for e in enemies if e.hp > 0]

            if selected_building:
                if hasattr(selected_building, "work_done"):
                    if (selected_building.tx, selected_building.ty,
                        selected_building.layer) not in buildings.blueprints: selected_building = None
                else:
                    if (selected_building.tx, selected_building.ty,
                        selected_building.layer) not in buildings.buildings: selected_building = None

            if selected_item_stack:
                if selected_item_stack.amount <= 0 or selected_item_stack not in items.stacks.values():
                    selected_item_stack = None

            if auto_work:
                for c in colonists:
                    if c.is_idle():
                        c.try_find_job(world, items, stockpiles, buildings, research_mgr, animals, farms.farms)

            effects = [ef for ef in effects if ef.update(dt)]

        log.update(dt_raw)

        # ================= 渲染 =================
        screen.fill(BLACK)
        world.draw(screen, camera)
        stockpiles.draw(screen, camera)
        farms.draw(screen, camera)
        buildings.draw_layer(screen, camera, font_small, 0)
        items.draw(screen, camera, font)
        buildings.draw_layer(screen, camera, font_small, 1)

        for a in animals:
            a.draw(screen, camera, font)

        if selected_building:
            sx, sy = camera.world_to_screen(selected_building.tx * TILE_SIZE, selected_building.ty * TILE_SIZE)
            rect = pygame.Rect(sx, sy, TILE_SIZE * selected_building.w, TILE_SIZE * selected_building.h)
            pygame.draw.rect(screen, (255, 255, 255), rect, 2)

        if selected_item_stack:
            sx, sy = camera.world_to_screen(selected_item_stack.x, selected_item_stack.y)
            pygame.draw.circle(screen, (255, 255, 255), (int(sx), int(sy)), TILE_SIZE // 2, 2)

        if mode in ("stockpile", "build", "deconstruct", "farm") and drag_start and drag_end and not pending_farm_rect:
            x1, y1 = drag_start;
            x2, y2 = drag_end
            tx1, tx2 = min(x1, x2), max(x1, x2);
            ty1, ty2 = min(y1, y2), max(y1, y2)
            for ty in range(ty1, ty2 + 1):
                for tx in range(tx1, tx2 + 1):
                    sx, sy = camera.world_to_screen(tx * TILE_SIZE, ty * TILE_SIZE)
                    s = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                    if mode == "stockpile":
                        s.fill((80, 140, 220, 80))
                    elif mode == "build":
                        s.fill((100, 200, 100, 100))
                    elif mode == "farm":
                        s.fill((60, 180, 60, 100))
                    else:
                        s.fill((255, 50, 50, 80))
                    screen.blit(s, (sx, sy))
                    pygame.draw.rect(screen, (255, 255, 255), (sx, sy, TILE_SIZE, TILE_SIZE), 1)

        if mode == "build" and current_build_kind and current_build_mat and not drag_start:
            if mouse_pos[1] < screen_h - ui_bottom_height:
                tx, ty = camera.screen_to_tile(*mouse_pos)
                if buildings.can_place(world, tx, ty, current_build_kind, current_build_mat, build_rotation):
                    w, h = BUILDING_DEFS[current_build_kind]["w"], BUILDING_DEFS[current_build_kind]["h"]
                    if build_rotation % 2 == 1: w, h = h, w
                    sx, sy = camera.world_to_screen(tx * TILE_SIZE, ty * TILE_SIZE)
                    s = pygame.Surface((TILE_SIZE * w, TILE_SIZE * h), pygame.SRCALPHA)
                    s.fill((100, 200, 100, 100));
                    screen.blit(s, (sx, sy))
                    pygame.draw.rect(screen, (255, 255, 255), (sx, sy, TILE_SIZE * w, TILE_SIZE * h), 1)

        for c in colonists:
            if c.selected: c.draw_path(screen, camera, world)
        for c in colonists: c.draw(screen, camera, font)
        for e in enemies: e.draw(screen, camera, font)
        for ef in effects: ef.draw(screen, camera)
        selection.draw(screen, camera)

        light = game_time.get_light_level()
        if light < 1.0:
            shade = pygame.Surface((screen_w, screen_h))
            shade.fill((0, 0, 30))
            shade.set_alpha(int((1.0 - light) * 160))
            screen.blit(shade, (0, 0))

        speed_text = "暂停" if game_speed == 0 else f"{int(game_speed)}x"
        info = (f"{game_time.time_str()} | 速度 {speed_text} | "
                f"殖民者 {len(colonists)} | 敌人 {len(enemies)} | 动物 {len(animals)}")
        screen.blit(font_big.render(info, True, WHITE), (10, 10))

        totals = {}
        for s in items.stacks.values(): totals[s.kind] = totals.get(s.kind, 0) + s.amount
        for b in buildings.buildings.values():
            if b.kind in ("small_cabinet", "large_cabinet"):
                for k, amt in b.inventory.items(): totals[k] = totals.get(k, 0) + amt

        y0 = 10
        for kind, amt in totals.items():
            d = ITEM_DEFS.get(kind, {"name": kind})
            surf = font_big.render(f"{d['name']}: {amt}", True, (255, 240, 180))
            screen.blit(surf, (screen_w - surf.get_width() - 10, y0))
            y0 += 24

        log.draw(screen, font, screen_w, screen_h)

        if mode == "build":
            build_menu.draw(screen, screen_w, screen_h, screen_h - toolbar.height, current_build_kind,
                            current_build_mat, totals, research_mgr, build_rotation)
        elif mode == "research":
            research_menu.draw(screen, screen_w, screen_h, research_mgr)

        toolbar.draw(screen, screen_w, screen_h, mode)

        if selected_colonists:
            hud.draw(screen, colonists, selected_colonists, camera)
        elif selected_building:
            bhud.draw(screen, selected_building, totals)
        elif selected_stockpile:
            shud.draw(screen)
        elif selected_item_stack:
            ihud.draw(screen, buildings)

        if pending_farm_rect:
            popup_rect = pygame.Rect(screen_w // 2 - 200, screen_h // 2 - 100, 400, 200)
            pygame.draw.rect(screen, (20, 20, 25), popup_rect, border_radius=8)
            pygame.draw.rect(screen, (100, 200, 100), popup_rect, 2, border_radius=8)
            title = font_big.render("选择种植作物", True, (100, 200, 100))
            screen.blit(title, (popup_rect.centerx - title.get_width() // 2, popup_rect.y + 15))

            b_rect = pygame.Rect(screen_w // 2 - 180, screen_h // 2 - 30, 160, 50)
            b_ok = research_mgr.can_plant("berry")
            col = (80, 160, 80) if b_ok else (50, 50, 50)
            pygame.draw.rect(screen, col, b_rect, border_radius=6)
            txt = font.render("浆果 (已解锁)" if b_ok else "浆果 (需基础农业)", True, WHITE)
            screen.blit(txt, (b_rect.centerx - txt.get_width() // 2, b_rect.y + 15))

            t_rect = pygame.Rect(screen_w // 2 + 20, screen_h // 2 - 30, 160, 50)
            t_ok = research_mgr.can_plant("tree")
            col = (80, 160, 80) if t_ok else (50, 50, 50)
            pygame.draw.rect(screen, col, t_rect, border_radius=6)
            txt = font.render("树木 (已解锁)" if t_ok else "树木 (需速生树种)", True, WHITE)
            screen.blit(txt, (t_rect.centerx - txt.get_width() // 2, t_rect.y + 15))

            c_rect = pygame.Rect(screen_w // 2 - 50, screen_h // 2 + 60, 100, 30)
            pygame.draw.rect(screen, (180, 60, 60), c_rect, border_radius=4)
            txt = font.render("取消", True, WHITE)
            screen.blit(txt, (c_rect.centerx - txt.get_width() // 2, c_rect.y + 5))

        if warning_timer > 0:
            warn_surf = font_warn.render(warning_text, True, (255, 80, 80))
            bg_rect = pygame.Rect(0, 0, warn_surf.get_width() + 20, warn_surf.get_height() + 10)
            bg_rect.center = (screen_w // 2, 80)
            s = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
            s.fill((40, 0, 0, 200))
            screen.blit(s, bg_rect)
            screen.blit(warn_surf, (bg_rect.x + 10, bg_rect.y + 5))

        if show_help:
            help_surf = pygame.Surface((600, 480), pygame.SRCALPHA)
            help_surf.fill((20, 20, 25, 240))
            pygame.draw.rect(help_surf, (100, 160, 220), help_surf.get_rect(), 2)
            title = font_big.render("操作说明", True, (100, 160, 220))
            help_surf.blit(title, (20, 20))
            keys_text = [
                "边缘/右键拖拽 : 移动视角",
                "左键点击 / 框选 : 选中殖民者、建筑、库存区或物品",
                "右键单击 : 命令 (建造/采集/攻击/狩猎/移动/搬运)",
                "Shift + 右键 : 将命令加入队列 (依次执行)",
                "空格键 : 切换时间流速 (暂停/1x/2x/3x)",
                "B : 建造菜单   |   F : 划定农业区",
                "S : 划定库存   |   X : 拆除/删除模式",
                "R : 建造时旋转 / 开启科技树",
                "A : 自动工作   |   G : 自动采集",
                "H / Esc : 打开/关闭此帮助面板",
                "F11 : 切换全屏模式"
            ]
            for i, txt in enumerate(keys_text):
                line = font.render(txt, True, WHITE)
                help_surf.blit(line, (30, 60 + i * 26))
            screen.blit(help_surf, (screen_w // 2 - 300, screen_h // 2 - 240))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()