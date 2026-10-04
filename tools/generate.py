#!/usr/bin/env python3
"""Turns Fabric's official example-mod template (one branch per Minecraft version)
into a small custom-item mod. Run by the GitHub Action before building."""
import argparse, json, os, re, shutil, struct, zlib, glob


def vt(v):
    return tuple(int(p) for p in v.split("."))


def ge(v, other):
    return vt(v) >= vt(other)


def png(path, w, h, px):
    raw = b"".join(b"\x00" + b"".join(bytes(px[y * w + x]) for x in range(w)) for y in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(data)


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def fang_pixels(accent):
    rows = {2: (9, 13), 3: (8, 13), 4: (8, 12), 5: (7, 12), 6: (7, 11), 7: (6, 11), 8: (6, 10), 9: (5, 10), 10: (5, 9), 11: (4, 8), 12: (4, 7), 13: (3, 6), 14: (3, 5)}
    a = hexrgb(accent)
    a2 = tuple(min(255, int(c * 0.8 + 40)) for c in a)
    mask = {(x, y) for y, (x0, x1) in rows.items() for x in range(x0, x1 + 1)}
    img = [(0, 0, 0, 0)] * 256
    for (x, y) in mask:
        col = (185, 216, 176) if x >= rows[y][1] - 1 else (238, 247, 230)
        if y >= 12:
            col = a if (y == 14 or x % 2) else a2
        if y == 11 and x <= 5:
            col = a2
        img[y * 16 + x] = col + (255,)
    for (x, y) in mask:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) not in mask and 0 <= nx < 16 and 0 <= ny < 16:
                img[ny * 16 + nx] = (22, 48, 29, 255)
    return img


def scale(img, s):
    return [img[(y // s) * 16 + (x // s)] for y in range(16 * s) for x in range(16 * s)]


def pascal(s):
    return "".join(w.capitalize() for w in re.split(r"[^A-Za-z0-9]+", s) if w) or "My"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--mc", required=True)
    ap.add_argument("--mod-name", default="Dragon Fang")
    ap.add_argument("--mod-id", default="dragonfang")
    ap.add_argument("--author", default="You")
    ap.add_argument("--item-name", default="Dragon Fang")
    ap.add_argument("--item-id", default="dragon_fang")
    ap.add_argument("--ingredients", default="blaze_rod, diamond, diamond")
    ap.add_argument("--count", default="1")
    ap.add_argument("--accent", default="#39ff14")
    a = ap.parse_args()

    v, T, MID = a.mc, a.template, a.mod_id
    assert re.fullmatch(r"[a-z][a-z0-9_]{1,40}", MID), "mod id must be lowercase letters, digits, underscores"
    assert re.fullmatch(r"[a-z][a-z0-9_]{1,40}", a.item_id), "item id must be lowercase letters, digits, underscores"
    assert re.fullmatch(r"#?[0-9a-fA-F]{6}", a.accent), "accent must be a hex colour like #39ff14"
    count = max(1, min(64, int(a.count)))
    ings = [i.strip().replace("minecraft:", "") for i in a.ingredients.split(",") if i.strip()][:9]
    assert ings and all(re.fullmatch(r"[a-z0-9_]+", i) for i in ings), "ingredients must be item ids like diamond"

    has_client = os.path.isdir(os.path.join(T, "src", "client"))
    # ---- clean template ----
    for d in ("src/main/java", "src/client/java"):
        shutil.rmtree(os.path.join(T, d), ignore_errors=True)
    for f in glob.glob(os.path.join(T, "src", "*", "resources", "*.mixins.json")):
        os.remove(f)
    old_icon = os.path.join(T, "src/main/resources/assets/modid")
    shutil.rmtree(old_icon, ignore_errors=True)

    # ---- era switches ----
    new_id = ge(v, "1.21.11")                       # ResourceLocation -> Identifier
    from_ns = ge(v, "1.21")                         # fromNamespaceAndPath
    builtin = ge(v, "1.19.3")                       # BuiltInRegistries
    set_id = ge(v, "1.21.2")                        # Item.Properties().setId(key)
    tab_new = ge(v, "26.0")                         # CreativeModeTabEvents
    tab_old = ge(v, "1.19.3") and not tab_new       # ItemGroupEvents
    items_def = ge(v, "1.21.4")                     # assets/<id>/items/<item>.json
    rec_folder = "recipe" if ge(v, "1.21") else "recipes"
    ing_str = ge(v, "1.21.2")
    res_id = ge(v, "1.20.5")

    RL = "Identifier" if new_id else "ResourceLocation"
    RLI = "net.minecraft.resources." + RL
    rl_expr = f"{RL}.fromNamespaceAndPath(MOD_ID, path)" if from_ns else f"new {RL}(MOD_ID, path)"
    reg = "BuiltInRegistries.ITEM" if builtin else "Registry.ITEM"
    pkg = f"com.dragonmodz.{MID}"
    P = pascal(a.mod_name)
    const = a.item_id.upper()

    main_java = f"""package {pkg};

import net.fabricmc.api.ModInitializer;
import {RLI};

public class {P}Mod implements ModInitializer {{
	public static final String MOD_ID = "{MID}";

	@Override
	public void onInitialize() {{
		ModItems.initialize();
	}}

	public static {RL} id(String path) {{
		return {rl_expr};
	}}
}}
"""
    imp = ["net.minecraft.core.Registry", "net.minecraft.world.item.Item"]
    if builtin:
        imp.append("net.minecraft.core.registries.BuiltInRegistries")
    if set_id:
        imp += ["net.minecraft.core.registries.Registries", "net.minecraft.resources.ResourceKey"]
    if not builtin:
        imp.append("net.minecraft.world.item.CreativeModeTab")
    if tab_old or tab_new:
        imp.append("net.minecraft.world.item.CreativeModeTabs")
    if tab_old:
        imp.append("net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents")
    if tab_new:
        imp.append("net.fabricmc.fabric.api.creativetab.v1.CreativeModeTabEvents")
    imports = "\n".join(f"import {i};" for i in sorted(imp))
    if set_id:
        reg_body = f"""		ResourceKey<Item> key = ResourceKey.create(Registries.ITEM, {P}Mod.id(name));
		Item item = new Item(new Item.Properties().setId(key));
		return Registry.register({reg}, key, item);"""
    elif builtin:
        reg_body = f"""		return Registry.register({reg}, {P}Mod.id(name), new Item(new Item.Properties()));"""
    else:
        reg_body = f"""		return Registry.register({reg}, {P}Mod.id(name), new Item(new Item.Properties().tab(CreativeModeTab.TAB_MISC)));"""
    if tab_new:
        init_body = f"		CreativeModeTabEvents.modifyOutputEvent(CreativeModeTabs.INGREDIENTS).register(tab -> tab.accept({const}));"
    elif tab_old:
        init_body = f"		ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.INGREDIENTS).register(entries -> entries.accept({const}));"
    else:
        init_body = "		// Item shows up in the Misc creative tab automatically."
    items_java = f"""package {pkg};

{imports}

public class ModItems {{
	// To add another item: copy the next line, change the name, then add a texture,
	// a model file and a lang entry with the same name.
	public static final Item {const} = register("{a.item_id}");

	private static Item register(String name) {{
{reg_body}
	}}

	public static void initialize() {{
{init_body}
	}}
}}
"""
    jdir = os.path.join(T, "src/main/java", *pkg.split("."))
    os.makedirs(jdir, exist_ok=True)
    open(os.path.join(jdir, f"{P}Mod.java"), "w").write(main_java)
    open(os.path.join(jdir, "ModItems.java"), "w").write(items_java)
    if has_client:
        cdir = os.path.join(T, "src/client/java", *pkg.split("."), "client")
        os.makedirs(cdir, exist_ok=True)
        open(os.path.join(cdir, f"{P}Client.java"), "w").write(f"""package {pkg}.client;

import net.fabricmc.api.ClientModInitializer;

public class {P}Client implements ClientModInitializer {{
	@Override
	public void onInitializeClient() {{
	}}
}}
""")

    # ---- fabric.mod.json ----
    fj = os.path.join(T, "src/main/resources/fabric.mod.json")
    m = json.load(open(fj))
    m["id"] = MID
    m["name"] = a.mod_name
    m["description"] = f"Adds the {a.item_name} item."
    m["authors"] = [a.author]
    m["license"] = "CC0-1.0"
    m["icon"] = f"assets/{MID}/icon.png"
    m.pop("contact", None)
    m.pop("mixins", None)
    m["entrypoints"] = {"main": [f"{pkg}.{P}Mod"]}
    if has_client:
        m["entrypoints"]["client"] = [f"{pkg}.client.{P}Client"]
    json.dump(m, open(fj, "w"), indent="\t")

    # ---- assets + data ----
    R = os.path.join(T, "src/main/resources")
    A = os.path.join(R, "assets", MID)
    os.makedirs(os.path.join(A, "lang"), exist_ok=True)
    os.makedirs(os.path.join(A, "models/item"), exist_ok=True)
    json.dump({f"item.{MID}.{a.item_id}": a.item_name}, open(os.path.join(A, "lang/en_us.json"), "w"), indent="\t")
    json.dump({"parent": "minecraft:item/generated", "textures": {"layer0": f"{MID}:item/{a.item_id}"}}, open(os.path.join(A, f"models/item/{a.item_id}.json"), "w"), indent="\t")
    if items_def:
        os.makedirs(os.path.join(A, "items"), exist_ok=True)
        json.dump({"model": {"type": "minecraft:model", "model": f"{MID}:item/{a.item_id}"}}, open(os.path.join(A, f"items/{a.item_id}.json"), "w"), indent="\t")
    img = fang_pixels(a.accent if a.accent.startswith("#") else "#" + a.accent)
    png(os.path.join(A, f"textures/item/{a.item_id}.png"), 16, 16, img)
    png(os.path.join(A, "icon.png"), 128, 128, scale(img, 8))
    ingr = [f"minecraft:{x}" for x in ings] if ing_str else [{"item": f"minecraft:{x}"} for x in ings]
    result = {"id": f"{MID}:{a.item_id}", "count": count} if res_id else {"item": f"{MID}:{a.item_id}", "count": count}
    rd = os.path.join(R, "data", MID, rec_folder)
    os.makedirs(rd, exist_ok=True)
    json.dump({"type": "minecraft:crafting_shapeless", "ingredients": ingr, "result": result}, open(os.path.join(rd, f"{a.item_id}.json"), "w"), indent="\t")

    # ---- gradle files ----
    for f in ("build.gradle", "settings.gradle", "gradle.properties"):
        p = os.path.join(T, f)
        s = open(p).read().replace("modid", MID).replace("com.example", pkg)
        open(p, "w").write(s)
    shutil.rmtree(os.path.join(T, ".git"), ignore_errors=True)
    print(f"generated {a.mod_name} ({MID}) for Minecraft {v}")


if __name__ == "__main__":
    main()
