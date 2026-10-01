#!/usr/bin/env python3
"""Download sprites from the community maplestory.io API and pack them into assets.js.

Run once: python3 build_assets.py
Output: assets.js, which defines window.ASSETS so index.html works when opened directly from disk,
plus scenery and wardrobe icon PNGs under assets/.
Outfit changes and non-default pets are fetched live from maplestory.io by the page itself.
"""
import base64
import io
import json
import os
import re
import urllib.parse
import urllib.request

from PIL import Image

REGION, VERSION = "GMS", "270"
API = "https://maplestory.io/api"
UA = {"User-Agent": "curl/8.7.1"}

PET_ID = 5000144  # Adriano, "a surly pirate otter of few words"
CHAIR_ID = 3015787  # Rabbit Lamp Chair
CHAIR_WZ = f"Item/Install/030157.img/0{CHAIR_ID}"

SKIN = 2000
OUTFIT = [
    12000,    # head
    21000,    # face
    31000,    # hair
    1002738,  # Bunny Earmuffs
    1052926,  # Cottontail Rabbit Dress
    1073062,  # Cottontail Rabbit Shoes
]
CHAR_ACTIONS = {"stand1": 700, "walk1": 180, "jump": 200, "sit": 1000}

# Wardrobe: Halloween-leaning picks, each checked to render on the character.
# Face accessories (101xxxx) and eye decorations (102xxxx) share the Face tab but are separate slots.
WARDROBE = {
    "hat": [
        (1002738, "Bunny Earmuffs"),
        (1001002, "Witch Hat"),
        (1004342, "Witch Hat"),
        (1002544, "Pumpkin Headgear"),
        (1002839, "Pumpkin Hat"),
        (1004385, "Pumpkin Cake Hat"),
        (1002525, "Mummy Hat"),
        (1003386, "Bat Costume Hood"),
        (1003682, "Jiangshi Hat"),
        (1004001, "Vampire Phantom Hat"),
        (1004343, "Skull Hat"),
        (1004738, "Baby Ghost Hat"),
        (1004841, "Ghost Hat"),
        (1003022, "Devil Horns"),
        (1000003, "Ghost Mask"),
    ],
    "outfit": [
        (1052926, "Cottontail Rabbit Dress"),
        (1051048, "Witch Clothes"),
        (1051700, "Nomad Witch"),
        (1050057, "Ghost Costume"),
        (1051076, "Ghost Suit"),
        (1050476, "Halloween Pumpkin Suit"),
        (1051543, "Halloween Pumpkin Suit"),
        (1050848, "Pumpkin Witch Tailcoat"),
        (1050849, "Haunted Punk Leather Fit"),
        (1051793, "Spooky Soul"),
        (1050724, "Ghost Groom Tuxedo"),
        (1050248, "Halloween Leopard Costume"),
        (1051376, "Halloweenroid Dress"),
        (1050012, "Grey Skull Overall"),
        (1051542, "Spooky Skirt"),
    ],
    "cape": [
        (1102769, "Witch Cape"),
        (1102066, "Dracula Cloak"),
        (1102150, "Count Dracula Cape"),
        (1102631, "Vampire Phantom Cape"),
        (1102098, "Coffin of Gloom"),
        (1102673, "Ghost Balloon"),
        (1102773, "Ghost Cape"),
        (1102868, "Triple Bat Cape"),
        (1102006, "Devil Wings"),
        (1103911, "Halloween Magic Cape"),
        (1103946, "Ghost Shadow"),
        (1103796, "Will's Spider Legs"),
        (1103649, "Chubby Ghost Kitty"),
    ],
    "shoes": [
        (1073062, "Cottontail Rabbit Shoes"),
        (1070094, "Spooky Shoes"),
        (1071111, "Spooky Heels"),
        (1070207, "Pumpkin Witch Sneakers"),
        (1071218, "Pumpkin Witch Pumps"),
        (1072878, "Vampire Phantom Boots"),
        (1073096, "Little Vampire Shoes"),
        (1073183, "Pumpkin Cookie"),
        (1073184, "Pumpkin Soup"),
        (1074267, "Skeleton Shoes"),
        (1073487, "Ruffled Ghost Shoes"),
        (1074227, "Halloween Magic Shoes"),
    ],
    "face": [
        (1012814, "Witch Cat Face Accessory"),
        (1012815, "Spooky Blush"),
        (1012556, "Vampire Eyes (Ruby)"),
        (1012555, "Vampire Eyes (Sapphire)"),
        (1012044, "Mummy Mask"),
        (1012495, "Skull Mask"),
        (1012645, "Skeleton Surgeon Mask"),
        (1022258, "Bat Wing Monocle"),
        (1022024, "Skull Patch"),
    ],
    "weapon": [
        (1702036, "Witch's Broomstick"),
        (1702092, "Glowing Pumpkin Basket"),
        (1702714, "Witch's Staff"),
        (1702726, "Pumpkin Star"),
        (1702203, "Halloween Teddy"),
        (1702146, "Skull Staff"),
        (1702472, "Vampire Phantom's Fate"),
        (1702785, "Cursed Bat Weapon"),
        (1702962, "Magical Bat"),
        (1702861, "One-Eyed Grim Reaper Weapon"),
        (1702246, "Ghost Weapon"),
    ],
    # Mounts render with the character riding them (the sitting pose dismounts, like on chairs).
    "mount": [
        (1902012, "Yeti"),
        (1902000, "Hog"),
        (1902032, "Nightmare"),
        (1932142, "The Decapatruck"),
        (1902059, "Giant Bunny"),
        (1902060, "Tiny Bunny"),
        (1902008, "Frog"),
        (1902011, "Turtle"),
        (1902013, "Buffalo"),
        (1902046, "Chicken"),
        (1902051, "Owl"),
        (1902009, "Ostrich"),
        (1902045, "Tiger"),
        (1902024, "Pegasus"),
        (1902025, "Dragon"),
        (1902038, "Pink Scooter"),
        (1902021, "Robot"),
    ],
}
PETS = [5000144, 5000036, 5000256, 5000257, 5000258, 5000502, 5000697, 5000296, 5002531,
        5000903, 5000904, 5000905, 5002519, 5002076, 5002327, 5002328, 5002329, 5002502, 5000476]

# Halloween scenery from the game's map files: name -> WZ path (a canvas or a folder of frames).
BG_SPRITES = {
    "sky": "Map/Back/HalloweenBack.img/back/0",
    "moon": "Map/Back/HalloweenBack.img/back/11",
    "stars": "Map/Back/HalloweenBack.img/back/12",
    "cloud0": "Map/Back/HalloweenBack.img/back/5",
    "cloud1": "Map/Back/HalloweenBack.img/back/8",
    "cloud2": "Map/Back/HalloweenBack.img/back/9",
    "cloud3": "Map/Back/HalloweenBack.img/back/10",
    "treeline0": "Map/Back/HalloweenBack.img/back/13",
    "treeline1": "Map/Back/HalloweenBack.img/back/14",
    "stone": "Map/Back/HalloweenBack.img/back/15",
    "witch": "Map/Back/HalloweenBack.img/ani/3",
    "zombie": "Map/Back/HalloweenBack.img/ani/4",
    "jester": "Map/Back/HalloweenBack.img/ani/2",
    "mansion": "Map/Obj/halloween.img/2019halloween/etc/0",
    "faceTree0": "Map/Obj/halloween.img/field/wood/0",
    "faceTree1": "Map/Obj/halloween.img/field/wood/2",
    "faceTree2": "Map/Obj/halloween.img/field/wood/3",
    "deadTree0": "Map/Obj/halloween.img/field/2011halloween/0",
    "deadTree1": "Map/Obj/halloween.img/field/2011halloween/2",
    "deadTree2": "Map/Obj/halloween.img/field/2011halloween/3",
    "wallEnd": "Map/Obj/halloween.img/field/2011halloween/4",
    "wall0": "Map/Obj/halloween.img/field/2011halloween/5",
    "wall1": "Map/Obj/halloween.img/field/2011halloween/6",
    "wallStart": "Map/Obj/halloween.img/field/2011halloween/8",
    "pumpkinPillarL": "Map/Obj/halloween.img/2020halloween/outside/4",
    "pumpkinPillarR": "Map/Obj/halloween.img/2020halloween/outside/5",
    "signpost": "Map/Obj/halloween.img/field/2011halloween/13",
    "pumpkinTree": "Map/Obj/halloween.img/field/2011halloween/15",
    "floatingPumpkins": "Map/Obj/halloween.img/field/2011halloween/16",
    "grave0": "Map/Obj/halloween.img/field/acc/0",
    "grave1": "Map/Obj/halloween.img/field/acc/1",
    "grave2": "Map/Obj/halloween.img/field/acc/2",
    "grave3": "Map/Obj/halloween.img/field/acc/3",
    "weeds0": "Map/Obj/halloween.img/field/acc/4",
    "weeds1": "Map/Obj/halloween.img/field/acc/5",
    "woodSign": "Map/Obj/halloween.img/field/acc/7",
    "vines0": "Map/Obj/halloween.img/field/amber/5",
    "vines1": "Map/Obj/halloween.img/field/amber/6",
    "wardrobe": "Map/Obj/halloween.img/inside/room7/3",
    # Off-theme guests from Aqua Road. GMS v270's API doesn't serve this monster, so use v250.
    "bubbleFish": ("Mob/2230109.img/move", "250"),
    "candles0": "Map/Obj/halloween.img/2019halloween/ani/4",
    "candles1": "Map/Obj/halloween.img/2019halloween/ani/6",
    "candles2": "Map/Obj/halloween.img/2019halloween/ani/7",
}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read(), r.headers.get("Content-Type", "")


def fetch_json(url):
    return json.loads(fetch(url)[0])


def data_uri(png_bytes):
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode()


def pixels(png_bytes):
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    return img.size, img.tobytes()


def wz(path, version=VERSION):
    return fetch_json(f"{API}/wz/{REGION}/{version}/{urllib.parse.quote(path)}")


def build_pet():
    d = fetch_json(f"{API}/{REGION}/{VERSION}/pet/{PET_ID}")
    anims = {}
    for name, books in d["frameBooks"].items():
        book = books[0] if isinstance(books, list) and books else books
        frames = [f for f in ((book or {}).get("frames") or []) if f.get("image") and f.get("origin")]
        if not frames:
            continue
        anims[name] = [
            {
                "src": "data:image/png;base64," + f["image"],
                "ox": f["origin"]["x"],
                "oy": f["origin"]["y"],
                "delay": f.get("delay") or 180,
            }
            for f in frames
        ]
    print(f"pet: {len(anims)} animations")
    return {"id": PET_ID, "name": d["description"]["name"],
            "desc": d["description"]["description"], "anims": anims}


def build_chair():
    info = wz(f"{CHAIR_WZ}/info/bodyRelMove")["value"]
    root = f"{CHAIR_WZ}/info/customChair/randomChairInfo"
    variants = []
    for v in sorted(wz(root)["children"], key=int):
        eff = f"{root}/{v}/effect"
        frame_ids = sorted((c for c in wz(eff)["children"] if c.isdigit()), key=int)
        frames = []
        for fid in frame_ids:
            node = wz(f"{eff}/{fid}")
            kids = node.get("children") or []
            origin = wz(f"{eff}/{fid}/origin")["value"]
            delay = wz(f"{eff}/{fid}/delay")["value"] if "delay" in kids else 100
            img_path = wz(f"{eff}/{fid}/_outlink")["value"] if "_outlink" in kids else f"{eff}/{fid}"
            png, _ = fetch(f"{API}/wz/img/{REGION}/{VERSION}/{urllib.parse.quote(img_path)}")
            frames.append({"src": data_uri(png), "ox": origin["x"], "oy": origin["y"], "delay": delay})
        variants.append(frames)
        print(f"chair variant {v}: {len(frames)} frames")
    name = fetch_json(f"{API}/{REGION}/{VERSION}/item/{CHAIR_ID}")["description"]
    return {"id": CHAIR_ID, "name": name["name"], "desc": re.sub(r"#c?", "", name["description"]),
            "seat": {"x": info["x"], "y": info["y"]}, "variants": variants}


def build_character():
    items = ",".join(str(i) for i in OUTFIT)
    anims = {}
    for action, delay in CHAR_ACTIONS.items():
        frames = []
        for frame in range(12):
            url = f"{API}/{REGION}/{VERSION}/Character/feetCenter/{SKIN}/{items}/{action}/{frame}"
            try:
                png, ctype = fetch(url)
            except Exception:
                break
            if "image" not in ctype:
                break
            frames.append({"_raw": png, "src": data_uri(png), "delay": delay})
        # The API wraps frame indexes past the end, so keep the shortest repeating cycle.
        # PNG metadata differs per request, so compare decoded pixels.
        raws = [pixels(f["_raw"]) for f in frames]
        period = next(p for p in range(1, len(raws) + 1)
                      if all(raws[i] == raws[i % p] for i in range(len(raws))))
        frames = frames[:period]
        for f in frames:
            del f["_raw"]
        anims[action] = frames
        print(f"character {action}: {len(frames)} frames")
    return {"skin": SKIN, "items": OUTFIT, "anims": anims}


def save_png(png, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return path


def wz_canvas_png(path, kids, version=VERSION):
    """Canvases can be links to image data stored elsewhere in the file."""
    if "_outlink" in kids:
        path = wz(f"{path}/_outlink", version)["value"]
    elif "_inlink" in kids:
        path = path.split(".img/")[0] + ".img/" + wz(f"{path}/_inlink", version)["value"]
    return fetch(f"{API}/wz/img/{REGION}/{version}/{urllib.parse.quote(path)}")[0]


def wz_sprite(path, out_prefix, version=VERSION):
    node = wz(path, version)
    if node.get("type") == 12:
        frame_paths = [path]
    else:
        frame_paths = [f"{path}/{k}" for k in sorted((c for c in node["children"] if c.isdigit()), key=int)]
    frames = []
    for i, fp in enumerate(frame_paths):
        kids = wz(fp, version).get("children") or []
        origin = wz(f"{fp}/origin", version)["value"] if "origin" in kids else {"x": 0, "y": 0}
        delay = wz(f"{fp}/delay", version)["value"] if "delay" in kids else 150
        png = wz_canvas_png(fp, kids, version)
        w, h = Image.open(io.BytesIO(png)).size
        src = save_png(png, f"{out_prefix}_{i}.png")
        frames.append({"src": src, "w": w, "h": h, "ox": origin["x"], "oy": origin["y"], "delay": delay})
    return frames


def build_background():
    bg = {}
    for name, path in BG_SPRITES.items():
        path, version = path if isinstance(path, tuple) else (path, VERSION)
        bg[name] = wz_sprite(path, f"assets/bg/{name}", version)
        print(f"bg {name}: {len(bg[name])} frames")
    return bg


def build_wardrobe():
    wardrobe = {}
    for tab, entries in WARDROBE.items():
        wardrobe[tab] = []
        for item_id, name in entries:
            icon = save_png(fetch(f"{API}/{REGION}/{VERSION}/item/{item_id}/iconRaw")[0], f"assets/icons/{item_id}.png")
            slot = {"face": "faceAcc" if item_id // 10000 == 101 else "eyeAcc"}.get(tab, tab)
            wardrobe[tab].append({"id": item_id, "name": name, "slot": slot, "icon": icon})
        print(f"wardrobe {tab}: {len(entries)} items")
    pets = []
    for pet_id in PETS:
        d = fetch_json(f"{API}/{REGION}/{VERSION}/pet/{pet_id}")
        icon = save_png(fetch(f"{API}/{REGION}/{VERSION}/item/{pet_id}/iconRaw")[0], f"assets/icons/{pet_id}.png")
        pets.append({"id": pet_id, "name": d["description"]["name"],
                     "desc": d["description"].get("description", ""), "icon": icon})
    print(f"wardrobe pets: {len(pets)}")
    return {"items": wardrobe, "pets": pets}


def main():
    assets = {"pet": build_pet(), "chair": build_chair(), "character": build_character(),
              "wardrobe": build_wardrobe(), "bg": build_background()}
    with open("assets.js", "w") as f:
        f.write("// Generated by build_assets.py from maplestory.io (GMS v%s). Do not edit.\n" % VERSION)
        f.write("window.ASSETS = ")
        json.dump(assets, f, separators=(",", ":"))
        f.write(";\n")
    print("wrote assets.js")


if __name__ == "__main__":
    main()
