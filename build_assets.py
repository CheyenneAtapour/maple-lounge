#!/usr/bin/env python3
"""Download sprites from the community maplestory.io API and pack them into assets.js.

Run once: python3 build_assets.py
Output: assets.js, which defines window.ASSETS so index.html works when opened directly from disk,
plus shared scenery and mount icon PNGs under assets/. Each month's map is built by build_theme.py.
Outfit changes and non-default pets are fetched live from maplestory.io by the page itself.
"""
import base64
import io
import json
import os
import re
import time
import urllib.error
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

# Shared wardrobe tabs. Seasonal tabs (hats, outfits, ...) and pets live in each theme spec (themes/*.json).
WARDROBE = {
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

# Scenery shared by every map: the wardrobe and the Bubble Fish. Seasonal scenery is in themes/*.json.
# Favorite pets offered on every map, right after Adriano (seasonal pets come from each theme).
SHARED_PETS = [
    5000041,  # Snowman
    5000025,  # Golden Pig (the yellow flying pig)
    5000014,  # Rudolph
    5000058,  # White Duck
    5000466,  # Ducky
    5000135,  # Gingerbready
    5002399,  # Lil Cactus
    5000768,  # Microslime
    5002085,  # Cookie Bear
]

# Pets made from other game art. Penni is one of Lynn's Spirit Guides; it only exists as a skill
# summon, so it's built from those frames and flies alongside you.
CUSTOM_PETS = {
    "penni": {
        "name": "Penni",
        "desc": "Penni, the Sky Guardian, one of Lynn's Spirit Guides.",
        "fly": True,
        "anims": {
            "stand0": "Skill/_Canvas/17210.img/skill/172101003/summon/stand",
            "move": "Skill/_Canvas/17210.img/skill/172101003/summon/move/LayerSlots/Slots/loop",
        },
    },
}
BG_SPRITES = {
    "wardrobe": "Map/Obj/halloween.img/inside/room7/3",
    # Off-theme guests from Aqua Road. GMS v270's API doesn't serve this monster, so use v250.
    "bubbleFish": ("Mob/2230109.img/move", "250"),
}


def fetch(url, tries=6):
    """GET with retries: maplestory.io is a free service that returns 5xx errors under load."""
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read(), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == tries:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries:
                raise
        time.sleep(1.0 * attempt)


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
    for pet_id in SHARED_PETS:
        d = fetch_json(f"{API}/{REGION}/{VERSION}/pet/{pet_id}")
        icon = save_png(fetch(f"{API}/{REGION}/{VERSION}/item/{pet_id}/iconRaw")[0], f"assets/icons/{pet_id}.png")
        pets.append({"id": pet_id, "name": d["description"]["name"],
                     "desc": d["description"].get("description", ""), "icon": icon})
    print(f"shared pets: {len(pets)}")
    custom = {}
    for key, spec in CUSTOM_PETS.items():
        anims = {}
        for anim, path in spec["anims"].items():
            frames = wz_sprite(path, f"assets/pets/{key}_{anim}")
            for f in frames:
                if f["ox"] == 0 and f["oy"] == 0:  # skill frames carry no anchor; center them
                    f["ox"], f["oy"] = f["w"] // 2, f["h"] // 2
            anims[anim] = frames
        custom[key] = {"id": key, "name": spec["name"], "desc": spec["desc"], "fly": spec.get("fly", False), "anims": anims}
        pets.append({"id": key, "name": spec["name"], "desc": spec["desc"], "icon": anims["stand0"][0]["src"], "custom": True})
    print(f"custom pets: {len(custom)}")
    return {"items": wardrobe, "pets": pets, "customPets": custom}


HAIR_FACES = "hair_faces.json"  # classic hairstyles and faces, with the colors each comes in


def head_icon(items):
    """Render just the character's head (hair + face) as a small wardrobe icon."""
    png, _ = fetch(f"{API}/{REGION}/{VERSION}/Character/feetCenter/{SKIN}/{','.join(map(str, items))}/stand1/0")
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    left, top, right, bottom = img.getbbox()
    # The head is the top part of the character; keep about 44px of it, centered.
    crop = img.crop((left, top, right, min(bottom, top + 44)))
    out = io.BytesIO()
    crop.save(out, "PNG")
    return out.getvalue()


def build_hair_faces():
    import concurrent.futures as cf
    data = json.load(open(HAIR_FACES))
    def hair(entry):
        base, name, colors = entry
        icon = save_png(head_icon([12000, 21000, base]), f"assets/icons/hair_{base}.png")
        return {"id": base, "name": name, "colors": colors, "icon": icon}
    def face(entry):
        base, name, colors = entry
        icon = save_png(head_icon([12000, base, 31000]), f"assets/icons/face_{base}.png")
        return {"id": base, "name": name, "colors": colors, "icon": icon}
    with cf.ThreadPoolExecutor(3) as ex:
        hairs = list(ex.map(hair, data["hair"]))
        faces = list(ex.map(face, data["faces"]))
    print(f"hairstyles: {len(hairs)}, faces: {len(faces)}")
    return hairs, faces


def main():
    assets = {"pet": build_pet(), "chair": build_chair(), "character": build_character(),
              "wardrobe": build_wardrobe(), "bg": build_background()}
    assets["wardrobe"]["hair"], assets["wardrobe"]["faces"] = build_hair_faces()
    with open("assets.js", "w") as f:
        f.write("// Generated by build_assets.py from maplestory.io (GMS v%s). Do not edit.\n" % VERSION)
        f.write("window.ASSETS = ")
        json.dump(assets, f, separators=(",", ":"))
        f.write(";\n")
    print("wrote assets.js")


if __name__ == "__main__":
    main()
