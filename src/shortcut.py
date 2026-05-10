"""
shortcut.py — DeckOps non-Steam shortcut creator

Creates non-Steam game shortcuts in Steam for CoD4 Multiplayer (CoD4x) and
World at War Multiplayer. These shortcuts point to the original game exes
in the Steam library and use the original compatdata prefixes.

Shortcuts include:
  - Proper artwork (icon, grid, wide, hero, logo) from SteamGridDB
  - Correct compatdata prefix via launch options
  - Controller template assignment based on gyro mode
  - GE-Proton compat tool assignment
  - Steam Input enabled (AllowDesktopConfig)

Called at the end of InstallScreen._run() after client installation completes.
Must be called while Steam is closed.
"""

import binascii
import os
import re
import shutil
import struct
import threading
import time
import urllib.request

from identity import INSTALL_DIR, VENV_PYTHON, asset_url
from log import get_logger

_log = get_logger(__name__)


# ── Paths ─────────────────────────────────────────────────────────────────────

STEAM_ROOT     = os.path.expanduser("~/.local/share/Steam")
USERDATA_DIR   = os.path.join(STEAM_ROOT, "userdata")
COMPAT_ROOT    = os.path.join(STEAM_ROOT, "steamapps", "compatdata")
STEAM_CONFIG   = os.path.join(STEAM_ROOT, "config", "config.vdf")

_HERE          = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT   = os.path.dirname(_HERE)
ASSETS_DIR     = os.path.join(PROJECT_ROOT, "assets", "controllers")

MIN_UID = 10000

_BROWSER_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
}


# ── Shortcut definitions ──────────────────────────────────────────────────────

SHORTCUTS = {
    "cod4mp": {
        "name":            "Call of Duty 4: Modern Warfare - Multiplayer",
        "exe_name":        "iw3mp.exe",
        "game_appid":      "7940",
        "template_type":   "other",
        "icon_url":        "https://cdn2.steamgriddb.com/icon/59b109c700b500daa9ef3a6769bc8c6f.png",
        "grid_url":        "https://cdn2.steamgriddb.com/thumb/7a22b900577a6edbffd53153cea2999c.jpg",
        "wide_url":        "https://cdn2.steamgriddb.com/thumb/69a24bf40cd265fb00ae685cdaa040c7.jpg",
        "hero_url":        "https://cdn2.steamgriddb.com/hero_thumb/95bc8e097e09212ec0160a7bc0b46fd6.jpg",
        "logo_url":        "https://cdn2.steamgriddb.com/logo_thumb/0440169a43de927753429dd69ca8c735.png",
        "icon_ext":        "png",
        "grid_ext":        "jpg",
        "wide_ext":        "jpg",
        "hero_ext":        "jpg",
        "logo_ext":        "png",
    },
    "t4mp": {
        "name":            "Call of Duty: World at War - Multiplayer",
        "exe_name":        "CoDWaWmp.exe",
        "game_appid":      "10090",
        "template_type":   "standard",
        "icon_url":        "https://cdn2.steamgriddb.com/icon/854d6fae5ee42911677c739ee1734486.png",
        "grid_url":        "https://cdn2.steamgriddb.com/grid/bb933c55afc6987ae406e48ff58786d6.png",
        "wide_url":        "https://cdn2.steamgriddb.com/thumb/a6a0076c7e1907a4555b17cc2a6ebc85.jpg",
        "hero_url":        "https://cdn2.steamgriddb.com/hero_thumb/e369853df766fa44e1ed0ff613f563bd.jpg",
        "logo_url":        "https://cdn2.steamgriddb.com/logo_thumb/0a32bfcf5c87aa42d2a0367c1f6bb17c.png",
        "icon_ext":        "png",
        "grid_ext":        "png",
        "wide_ext":        "jpg",
        "hero_ext":        "jpg",
        "logo_ext":        "png",
    },
    "t7x": {
        "name":            "Call of Duty: Black Ops 3 T7x",
        "exe_name":        "t7x.exe",
        "game_appid":      "311210",
        "template_type":   "standard",
        "icon_url":        "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/311210/bd3e3a9516b480164df25d16e49ae4ce4a063cb4.jpg",
        "grid_url":        "https://cdn2.steamgriddb.com/grid/18ad806798df1fdc114ced9115330fac.jpg",
        "wide_url":        "https://cdn2.steamgriddb.com/grid/445cef1a5008beb63c078f314d820e1f.jpg",
        "hero_url":        "https://cdn2.steamgriddb.com/hero/c938d97fb333d4b1fbf906b760afa29b.png",
        "logo_url":        "https://cdn2.steamgriddb.com/logo/d2b9d7150a1f6693817d82d4ca9b701d.png",
        "icon_ext":        "jpg",
        "grid_ext":        "jpg",
        "wide_ext":        "jpg",
        "hero_ext":        "png",
        "logo_ext":        "png",
    },
}


# ── Own game shortcut definitions ─────────────────────────────────────────────
#
# Used when the user selects "My Own" on the source screen. DeckOps creates
# non-Steam shortcuts for games installed outside of Steam (CD, GOG, etc.)
# with canonical names so the appid is deterministic and controllable.
#
# Artwork credits (SteamGridDB): see README.md

OWN_SHORTCUTS = {
    "cod4sp": {
        "name":           "Call of Duty 4: Modern Warfare - Singleplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/7940/b40c43b0b14b7e124553e0220581a1b9ef8e38bf.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/7940/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/7940/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/7940/library_hero_2x.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/7940/logo_2x.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "cod4mp": {
        "name":           "Call of Duty 4: Modern Warfare - Multiplayer",
        "template_type":  "other",
        "icon_url":       "https://cdn2.steamgriddb.com/icon/59b109c700b500daa9ef3a6769bc8c6f.png",
        "grid_url":       "https://cdn2.steamgriddb.com/thumb/7a22b900577a6edbffd53153cea2999c.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/thumb/69a24bf40cd265fb00ae685cdaa040c7.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/95bc8e097e09212ec0160a7bc0b46fd6.jpg",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/0440169a43de927753429dd69ca8c735.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "iw4sp": {
        "name":           "Call of Duty: Modern Warfare 2 (2009) - Singleplayer",
        "template_type":  "other",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/10180/ad502494f1658220f9166c7e17ac90422bf6a479.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10180/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10180/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10180/library_hero_2x.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10180/logo_2x.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "iw4mp": {
        "name":           "Call of Duty: Modern Warfare 2 (2009) - Multiplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/10190/7dd7c2d5bce2413131762d7cbee3f059614ed69d.jpg",
        "grid_url":       "https://cdn2.steamgriddb.com/thumb/4f4ecc161b18f07dcf2c8296fad55709.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10190/header.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/1fc214004c9481e4c8073e85323bfd4b.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/d79aac075930c83c2f1e369a511148fe.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    "iw5sp": {
        "name":           "Call of Duty: Modern Warfare 3 (2011) - Singleplayer",
        "template_type":  "other",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/42680/c3330a875925437d8216949b6571f6e941ba0679.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/42680/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/42680/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/42680/library_hero_2x.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/42680/logo_2x.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "iw5mp": {
        "name":           "Call of Duty: Modern Warfare 3 (2011) - Multiplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn2.steamgriddb.com/icon_thumb/67b48cc32ab9f04633bd50656a4a26fc.png",
        "grid_url":       "https://cdn2.steamgriddb.com/thumb/54726e7600c9c297610f6ed9d7d19ca7.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/thumb/ce65f40e3a20ad19fe352c52ce3bcf51.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/51770b1e6f66ba5d45e58a76e6a73dc2.jpg",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/4a64d913220fca4c33c140c6952688a8.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "t4sp": {
        "name":           "Call of Duty: World at War",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/10090/2bfb85222af4a01842baa5c3a16a080eb27ac6c3.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10090/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10090/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10090/library_hero_2x.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/10090/logo_2x.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "t4mp": {
        "name":           "Call of Duty: World at War - Multiplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn2.steamgriddb.com/icon/854d6fae5ee42911677c739ee1734486.png",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/bb933c55afc6987ae406e48ff58786d6.png",
        "wide_url":       "https://cdn2.steamgriddb.com/thumb/a6a0076c7e1907a4555b17cc2a6ebc85.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/e369853df766fa44e1ed0ff613f563bd.jpg",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/0a32bfcf5c87aa42d2a0367c1f6bb17c.png",
        "icon_ext": "png", "grid_ext": "png", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "t5sp": {
        "name":           "Call of Duty: Black Ops",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/42700/ea744d59efded3feaeebcafed224be9eadde90ac.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/42700/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/42700/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/42700/library_hero.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/42700/logo_2x.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "t5mp": {
        "name":           "Call of Duty: Black Ops - Multiplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/42710/d595fb4b01201cade09e1232f2c41c0866840628.jpg",
        "grid_url":       "https://cdn2.steamgriddb.com/thumb/978f9d25644371a4c4b8df8c994cd880.png",
        "wide_url":       "https://cdn2.steamgriddb.com/thumb/a6330e9317a50ccf2d79c295dd18046f.png",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/dc82d632c9fcecb0778afbc7924494a6.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/dfb84a11f431c62436cfb760e30a34fe.png",
        "icon_ext": "jpg", "grid_ext": "png", "wide_ext": "png", "hero_ext": "png", "logo_ext": "png",
    },
    "t6sp": {
        "name":           "Call of Duty: Black Ops II - Singleplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/202970/0a23d78ade8c8d7b4cfa15bf71c9dd535b2998ca.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/202970/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/202970/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/202970/library_hero.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/202970/logo_2x.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "t6zm": {
        "name":           "Call of Duty: Black Ops II - Zombies",
        "template_type":  "standard",
        "icon_url":       "https://cdn2.steamgriddb.com/icon_thumb/743c11a9f3cb65cda4994bbdfb66c398.png",
        "grid_url":       "https://cdn2.steamgriddb.com/thumb/3d9ffc992e48d2aeb4b06f05471f619d.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/thumb/b87c4d009662bc436961d8f753a8de78.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/e5e63da79fcd2bebbd7cb8bf1c1d0274.jpg",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/79514e888b8f2acacc68738d0cbb803e.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "t6mp": {
        "name":           "Call of Duty: Black Ops II - Multiplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn2.steamgriddb.com/icon_thumb/715eb56d3f3b71792e230102d1da496d.png",
        "grid_url":       "https://cdn2.steamgriddb.com/thumb/7d3695ac5fbf55fb65ea261dd3a8577c.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/thumb/d841ee63e07b28f94920b81d2e4c21c9.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/731c83db8d2ff01bdc000083fd3c3740.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/6271faadeedd7626d661856b7a004e27.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    "t7": {
        "name":           "Call of Duty: Black Ops III",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/311210/bd3e3a9516b480164df25d16e49ae4ce4a063cb4.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/311210/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/311210/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/311210/library_hero.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/311210/logo.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "t7x": {
        "name":           "Call of Duty: Black Ops 3 T7x",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/311210/bd3e3a9516b480164df25d16e49ae4ce4a063cb4.jpg",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/18ad806798df1fdc114ced9115330fac.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/grid/445cef1a5008beb63c078f314d820e1f.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero/c938d97fb333d4b1fbf906b760afa29b.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo/d2b9d7150a1f6693817d82d4ca9b701d.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    "iw6sp": {
        "name":           "Call of Duty: Ghosts - Singleplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/209160/634577eb0ac94ce620c328885961ed6756823474.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/209160/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/209160/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/209160/library_hero.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/209160/logo.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "iw6mp": {
        "name":           "Call of Duty: Ghosts - Multiplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/209170/634577eb0ac94ce620c328885961ed6756823474.jpg",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/66820f8c84215725cac52e00587988fd.png",
        "wide_url":       "https://cdn2.steamgriddb.com/grid/4f3244fc8b8787fe45c90c2a41c28478.png",
        "hero_url":       "https://cdn2.steamgriddb.com/hero/8c59fd6fbe0e9793ec2b27971221cace.jpg",
        "logo_url":       "https://cdn2.steamgriddb.com/logo/287e03db1d99e0ec2edb90d079e142f3.png",
        "icon_ext": "jpg", "grid_ext": "png", "wide_ext": "png", "hero_ext": "jpg", "logo_ext": "png",
    },
    "s1sp": {
        "name":           "Call of Duty: Advanced Warfare - Singleplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/209650/aab8b39ef63c54af5497b55aa104d5c7ec860fd9.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/209650/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/209650/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/209650/library_hero.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/209650/logo.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "s1mp": {
        "name":           "Call of Duty: Advanced Warfare - Multiplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/209660/aab8b39ef63c54af5497b55aa104d5c7ec860fd9.jpg",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/dfee5996d068e6bed170ff189ca2f193.png",
        "wide_url":       "https://cdn2.steamgriddb.com/grid/d790c9e6c0b5e02c87b375e782ac01bc.png",
        "hero_url":       "https://cdn2.steamgriddb.com/hero/7070f9088e456682f0f84f815ebda761.jpg",
        "logo_url":       "https://cdn2.steamgriddb.com/logo/e243aa93e6b6e031797f86d0858f5e40.png",
        "icon_ext": "jpg", "grid_ext": "png", "wide_ext": "png", "hero_ext": "jpg", "logo_ext": "png",
    },
}


# ── Steam game artwork ────────────────────────────────────────────────────────
#
# Custom artwork applied to Steam-owned MP and ZM titles that share a store
# page with their SP counterpart. Without this, all modes show the same
# generic header in the library.
#
# SP titles (7940, 10180, 42680, 42700, 202970) are left alone — Steam's
# default artwork is fine for those.

STEAM_ARTWORK = {
    "10190": {  # MW2 MP
        "icon_url":  "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/10190/7dd7c2d5bce2413131762d7cbee3f059614ed69d.jpg",
        "grid_url":  "https://cdn2.steamgriddb.com/thumb/4f4ecc161b18f07dcf2c8296fad55709.jpg",
        "wide_url":  "https://shared.steamstatic.com/store_item_assets/steam/apps/10190/header.jpg",
        "hero_url":  "https://cdn2.steamgriddb.com/hero_thumb/1fc214004c9481e4c8073e85323bfd4b.png",
        "logo_url":  "https://cdn2.steamgriddb.com/logo_thumb/d79aac075930c83c2f1e369a511148fe.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    "42690": {  # MW3 MP
        "icon_url":  "https://cdn2.steamgriddb.com/icon_thumb/67b48cc32ab9f04633bd50656a4a26fc.png",
        "grid_url":  "https://cdn2.steamgriddb.com/thumb/54726e7600c9c297610f6ed9d7d19ca7.jpg",
        "wide_url":  "https://cdn2.steamgriddb.com/thumb/ce65f40e3a20ad19fe352c52ce3bcf51.jpg",
        "hero_url":  "https://cdn2.steamgriddb.com/hero_thumb/51770b1e6f66ba5d45e58a76e6a73dc2.jpg",
        "logo_url":  "https://cdn2.steamgriddb.com/logo_thumb/4a64d913220fca4c33c140c6952688a8.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "42750": {  # MW3 Dedicated Server (same art as MW3 MP)
        "icon_url":  "https://cdn2.steamgriddb.com/icon_thumb/67b48cc32ab9f04633bd50656a4a26fc.png",
        "grid_url":  "https://cdn2.steamgriddb.com/thumb/54726e7600c9c297610f6ed9d7d19ca7.jpg",
        "wide_url":  "https://cdn2.steamgriddb.com/thumb/ce65f40e3a20ad19fe352c52ce3bcf51.jpg",
        "hero_url":  "https://cdn2.steamgriddb.com/hero_thumb/51770b1e6f66ba5d45e58a76e6a73dc2.jpg",
        "logo_url":  "https://cdn2.steamgriddb.com/logo_thumb/4a64d913220fca4c33c140c6952688a8.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "42710": {  # BO1 MP
        "icon_url":  "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/42710/d595fb4b01201cade09e1232f2c41c0866840628.jpg",
        "grid_url":  "https://cdn2.steamgriddb.com/thumb/978f9d25644371a4c4b8df8c994cd880.png",
        "wide_url":  "https://cdn2.steamgriddb.com/thumb/a6330e9317a50ccf2d79c295dd18046f.png",
        "hero_url":  "https://cdn2.steamgriddb.com/hero_thumb/dc82d632c9fcecb0778afbc7924494a6.png",
        "logo_url":  "https://cdn2.steamgriddb.com/logo_thumb/dfb84a11f431c62436cfb760e30a34fe.png",
        "icon_ext": "jpg", "grid_ext": "png", "wide_ext": "png", "hero_ext": "png", "logo_ext": "png",
    },
    "202990": {  # BO2 MP
        "icon_url":  "https://cdn2.steamgriddb.com/icon_thumb/715eb56d3f3b71792e230102d1da496d.png",
        "grid_url":  "https://cdn2.steamgriddb.com/thumb/7d3695ac5fbf55fb65ea261dd3a8577c.jpg",
        "wide_url":  "https://cdn2.steamgriddb.com/thumb/d841ee63e07b28f94920b81d2e4c21c9.jpg",
        "hero_url":  "https://cdn2.steamgriddb.com/hero_thumb/731c83db8d2ff01bdc000083fd3c3740.png",
        "logo_url":  "https://cdn2.steamgriddb.com/logo_thumb/6271faadeedd7626d661856b7a004e27.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    "212910": {  # BO2 ZM
        "icon_url":  "https://cdn2.steamgriddb.com/icon_thumb/743c11a9f3cb65cda4994bbdfb66c398.png",
        "grid_url":  "https://cdn2.steamgriddb.com/thumb/3d9ffc992e48d2aeb4b06f05471f619d.jpg",
        "wide_url":  "https://cdn2.steamgriddb.com/thumb/b87c4d009662bc436961d8f753a8de78.jpg",
        "hero_url":  "https://cdn2.steamgriddb.com/hero_thumb/e5e63da79fcd2bebbd7cb8bf1c1d0274.jpg",
        "logo_url":  "https://cdn2.steamgriddb.com/logo_thumb/79514e888b8f2acacc68738d0cbb803e.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "209170": {  # Ghosts MP
        "icon_url":  "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/209170/634577eb0ac94ce620c328885961ed6756823474.jpg",
        "grid_url":  "https://cdn2.steamgriddb.com/grid/66820f8c84215725cac52e00587988fd.png",
        "wide_url":  "https://cdn2.steamgriddb.com/grid/4f3244fc8b8787fe45c90c2a41c28478.png",
        "hero_url":  "https://cdn2.steamgriddb.com/hero/8c59fd6fbe0e9793ec2b27971221cace.jpg",
        "logo_url":  "https://cdn2.steamgriddb.com/logo/287e03db1d99e0ec2edb90d079e142f3.png",
        "icon_ext": "jpg", "grid_ext": "png", "wide_ext": "png", "hero_ext": "jpg", "logo_ext": "png",
    },
    "209660": {  # AW MP
        "icon_url":  "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/209660/aab8b39ef63c54af5497b55aa104d5c7ec860fd9.jpg",
        "grid_url":  "https://cdn2.steamgriddb.com/grid/dfee5996d068e6bed170ff189ca2f193.png",
        "wide_url":  "https://cdn2.steamgriddb.com/grid/d790c9e6c0b5e02c87b375e782ac01bc.png",
        "hero_url":  "https://cdn2.steamgriddb.com/hero/7070f9088e456682f0f84f815ebda761.jpg",
        "logo_url":  "https://cdn2.steamgriddb.com/logo/e243aa93e6b6e031797f86d0858f5e40.png",
        "icon_ext": "jpg", "grid_ext": "png", "wide_ext": "png", "hero_ext": "jpg", "logo_ext": "png",
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_all_steam_uids():
    """Return all valid Steam user ID folders from userdata/."""
    if not os.path.isdir(USERDATA_DIR):
        return []
    seen, uids = set(), []
    for entry in os.listdir(USERDATA_DIR):
        if not entry.isdigit() or int(entry) < MIN_UID:
            continue
        real = os.path.realpath(os.path.join(USERDATA_DIR, entry))
        if real in seen:
            continue
        seen.add(real)
        uids.append(entry)
    return uids


def _get_deck_serial() -> str | None:
    """Read the Steam Deck serial number from Steam's config.vdf."""
    if not os.path.exists(STEAM_CONFIG):
        return None
    try:
        with open(STEAM_CONFIG, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        match = re.search(r'"SteamDeckRegisteredSerialNumber"\s+"([^"]+)"', content)
        if match:
            return match.group(1)
    except Exception:
        _log.debug("serial number read failed", exc_info=True)
    return None


def _calc_shortcut_appid(exe_path: str, name: str) -> int:
    """
    Calculate the Steam shortcut appid from exe path and name.
    This must match Steam's internal algorithm exactly. If the CRC or
    bitmask changes, shortcuts will not resolve and artwork/controller
    configs will point to the wrong appid. Do not modify.
    """
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    return (crc | 0x80000000) & 0xFFFFFFFF


def _to_signed32(n):
    """Convert unsigned int32 appid to signed int32 for vdf binary format."""
    return n if n <= 2147483647 else n - 2**32


def _download(url: str, dest: str) -> bool:
    """Download a file from URL to dest path. Returns True on success."""
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        req = urllib.request.Request(url, headers=_BROWSER_UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            with open(dest, "wb") as f:
                f.write(r.read())
        return True
    except Exception:
        _log.debug("artwork download failed", exc_info=True)
        return False


# ── Binary VDF helpers ────────────────────────────────────────────────────────

def _vdf_string(key: str, val: str) -> bytes:
    """Encode a string field for binary VDF."""
    return b'\x01' + key.encode('utf-8') + b'\x00' + val.encode('utf-8') + b'\x00'


def _vdf_int32(key: str, val: int) -> bytes:
    """Encode an int32 field for binary VDF."""
    return b'\x02' + key.encode('utf-8') + b'\x00' + struct.pack('<i', val)


def _make_shortcut_entry(idx: int, fields: dict) -> bytes:
    """Build a single shortcut entry in binary VDF format."""
    data = b'\x00' + str(idx).encode('utf-8') + b'\x00'
    
    for key, value in fields.items():
        if key == "tags":
            # Tags is a sub-dict
            data += b'\x00' + b'tags' + b'\x00'
            for tk, tv in value.items():
                data += _vdf_string(tk, tv)
            data += b'\x08'
        elif isinstance(value, str):
            data += _vdf_string(key, value)
        elif isinstance(value, int):
            data += _vdf_int32(key, value)
    
    data += b'\x08'
    return data


def _read_existing_shortcuts(path: str) -> list:
    """Return list of existing shortcut names from shortcuts.vdf."""
    if not os.path.exists(path):
        return []
    
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except Exception:
        _log.debug("operation failed", exc_info=True)
        return []
    
    # Extract AppName values
    existing = []
    for match in re.finditer(b'\x01[Aa]pp[Nn]ame\x00([^\x00]+)\x00', data):
        existing.append(match.group(1).decode('utf-8', errors='replace'))
    
    return existing


def _read_shortcuts_raw(path: str) -> bytes:
    """Read the raw shortcuts.vdf content, stripping header/footer."""
    if not os.path.exists(path):
        return b''
    
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except Exception:
        _log.debug("shortcuts.vdf read failed", exc_info=True)
        return b''
    
    # Strip header (b'\x00shortcuts\x00') and footer (b'\x08\x08')
    header = b'\x00shortcuts\x00'
    if data.startswith(header):
        data = data[len(header):]
    if data.endswith(b'\x08\x08'):
        data = data[:-2]
    elif data.endswith(b'\x08'):
        data = data[:-1]
    
    return data


def _get_next_index(raw_data: bytes) -> int:
    """
    Find the next available shortcut index from raw shortcut entry data.

    Shortcut entries start with the byte sequence: 0x00 <index_str> 0x00
    immediately followed by 0x02 (the appid int field marker). This two-byte
    lookahead distinguishes real entry headers from the many other 0x00...0x00
    numeric sequences present in binary VDF data (string lengths, field values, etc.).
    """
    if not raw_data:
        return 0

    indices = []
    i = 0
    while i < len(raw_data) - 2:
        if raw_data[i] == 0x00:
            end = raw_data.find(b'\x00', i + 1)
            if end != -1 and end > i + 1:
                # Only treat as an entry index if immediately followed by
                # 0x02 (int32 field type byte for the 'appid' field header)
                if end + 1 < len(raw_data) and raw_data[end + 1] == 0x02:
                    try:
                        idx_str = raw_data[i + 1:end].decode('utf-8')
                        if idx_str.isdigit():
                            indices.append(int(idx_str))
                    except (UnicodeDecodeError, ValueError):
                        _log.debug("shortcut index parse failed", exc_info=True)
                i = end + 1
            else:
                i += 1
        else:
            i += 1

    return max(indices, default=-1) + 1


def _backup_file(path: str):
    """Write a .bak copy before modifying a Steam config file."""
    if os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
        except OSError:
            _log.debug("shortcuts.vdf backup failed", exc_info=True)


def _write_shortcuts_vdf(path: str, existing_raw: bytes, new_entries: list):
    """Write shortcuts.vdf with existing entries preserved and new ones appended."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _backup_file(path)
    
    data = b'\x00shortcuts\x00'
    
    if existing_raw:
        data += existing_raw
    
    for entry_bytes in new_entries:
        data += entry_bytes
    
    data += b'\x08\x08'
    
    with open(path, 'wb') as f:
        f.write(data)


# ── Artwork download ──────────────────────────────────────────────────────────

def _download_artwork(grid_dir: str, appid: int, shortcut_def: dict, prog,
                      force: bool = False, clean_stale: bool = False):
    """Download all artwork for a shortcut to the grid directory (concurrent).

    force       — if True, re-download even if the file already exists on disk.
    clean_stale — if True, delete all existing {appid}* files in grid_dir
                  before downloading. Handles extension changes between
                  versions (e.g. old .jpg → new .png) that would otherwise
                  leave orphans Steam might pick up instead of the new files.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    appid_str = str(appid)
    os.makedirs(grid_dir, exist_ok=True)

    if clean_stale:
        try:
            import glob as _glob
            for f in _glob.glob(os.path.join(grid_dir, f"{appid_str}*")):
                try:
                    os.remove(f)
                except OSError:
                    _log.debug("file removal failed", exc_info=True)
        except Exception:
            _log.debug("file removal failed", exc_info=True)
    
    artwork_map = [
        ("icon_url",  f"{appid_str}_icon.{shortcut_def['icon_ext']}",  "icon"),
        ("grid_url",  f"{appid_str}p.{shortcut_def['grid_ext']}",      "grid"),
        ("wide_url",  f"{appid_str}.{shortcut_def['wide_ext']}",       "wide"),
        ("hero_url",  f"{appid_str}_hero.{shortcut_def['hero_ext']}",  "hero"),
        ("logo_url",  f"{appid_str}_logo.{shortcut_def['logo_ext']}",  "logo"),
    ]

    # Collect items that actually need downloading
    to_download = []
    for url_key, filename, label in artwork_map:
        url = shortcut_def.get(url_key)
        if not url:
            continue
        dest = os.path.join(grid_dir, filename)
        if not force and os.path.exists(dest):
            prog(f"    ✓ {label} (cached)")
            continue
        to_download.append((url, dest, label))

    if not to_download:
        return

    # Download up to 5 images concurrently
    results_lock = threading.Lock()

    def _dl(url, dest, label):
        ok = _download(url, dest)
        with results_lock:
            if ok:
                prog(f"    ✓ {label}")
            else:
                prog(f"    ⚠ {label} failed")

    with ThreadPoolExecutor(max_workers=min(5, len(to_download))) as ex:
        futs = [ex.submit(_dl, url, dest, label) for url, dest, label in to_download]
        for fut in as_completed(futs):
            # Exceptions are logged inside _dl, but catch anything unexpected
            try:
                fut.result()
            except Exception:
                _log.debug("artwork download task failed", exc_info=True)


# ── Controller template assignment ────────────────────────────────────────────

def _get_template_filename(template_type: str, gyro_mode: str) -> str:
    """Return the controller template filename based on type and gyro mode."""
    suffix = "ads" if gyro_mode == "on" else "off"
    if template_type == "other":
        return f"controller_neptune_deckops_other_{suffix}.vdf"
    else:
        return f"controller_neptune_deckops_{suffix}.vdf"


def _assign_controller_config(uid: str, appid: int, shortcut_def: dict,
                               gyro_mode: str, prog):
    """
    Assign controller template for a non-Steam shortcut.

    We write to both configset_controller_neptune.vdf and the Deck's
    serial-specific configset. SteamOS in Game Mode reads from the serial
    file, so without it the profile only works in Desktop Mode.
    This mirrors what controller_profiles.py does for regular Steam games.
    """
    template_type = shortcut_def["template_type"]
    template_filename = _get_template_filename(template_type, gyro_mode)
    
    src_template = os.path.join(ASSETS_DIR, template_filename)
    if not os.path.exists(src_template):
        prog(f"    ⚠ Template not found: {template_filename}")
        return
    
    appid_str = str(appid)
    
    # Path: Steam Controller Configs/<uid>/config/<appid>/
    steam_cfg_root = os.path.join(
        STEAM_ROOT, "steamapps", "common",
        "Steam Controller Configs", uid, "config"
    )
    cfg_dir = os.path.join(steam_cfg_root, appid_str)
    os.makedirs(cfg_dir, exist_ok=True)
    shutil.copy2(src_template, os.path.join(cfg_dir, "controller_neptune.vdf"))
    
    # Patch configset_controller_neptune.vdf
    configset_path = os.path.join(steam_cfg_root, "configset_controller_neptune.vdf")
    _patch_configset(configset_path, appid_str, template_filename)
    
    # Patch configset_{serial}.vdf — SteamOS on Deck reads from this file
    serial = _get_deck_serial()
    if serial:
        configset_serial = os.path.join(steam_cfg_root, f"configset_{serial}.vdf")
        _patch_configset(configset_serial, appid_str, template_filename)
    
    prog(f"    ✓ Controller: {template_filename}")


def _record_configset_edit(configset_path: str, key: str, template_name: str):
    """Record a configset VDF edit in the wrapper ledger."""
    try:
        from wrapper import _record_configset
        filename = os.path.basename(configset_path)
        _record_configset(filename, key, template_name)
    except Exception:
        _log.debug("configset ledger record failed", exc_info=True)


def _patch_configset(configset_path: str, key: str, template_name: str):
    """
    Patch configset_controller_neptune.vdf to set our template as default.
    Duplicated from controller_profiles.py because shortcut.py runs
    standalone and should not import from the controller module.
    """
    entry = f'\t"{key}"\n\t{{\n\t\t"template"\t\t"{template_name}"\n\t}}\n'

    if not os.path.exists(configset_path):
        os.makedirs(os.path.dirname(configset_path), exist_ok=True)
        with open(configset_path, "w", encoding="utf-8") as f:
            f.write('"controller_config"\n{\n' + entry + '}\n')
        _record_configset_edit(configset_path, key, template_name)
        return

    with open(configset_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    pattern = rf'\t"{re.escape(key)}"\n\t\{{[^}}]*\}}\n?'
    if re.search(pattern, content, re.MULTILINE | re.DOTALL):
        content = re.sub(pattern, entry, content, flags=re.MULTILINE | re.DOTALL)
    else:
        content = content.rstrip()
        if content.endswith("}"):
            content = content[:-1].rstrip() + "\n" + entry + "}\n"

    with open(configset_path, "w", encoding="utf-8") as f:
        f.write(content)
    _record_configset_edit(configset_path, key, template_name)


def _clear_compat_tool(appid_str: str):
    """
    Remove any CompatToolMapping entry for the given appid from config.vdf.

    Used for shortcuts that must NOT have a Steam compat tool — e.g. HGL
    shortcuts where Steam's compat tool sandboxes flatpak away from the host.

    Delegates to wrapper.clear_compat_tool() so the write goes through
    _write_and_validate_vdf() with brace-balance checking and auto-restore.
    """
    from wrapper import clear_compat_tool
    clear_compat_tool([appid_str])


# ── Shortcut appid lookup ────────────────────────────────────────────────────

def get_shortcut_appid(name: str) -> int | None:
    """
    Look up the actual appid of a non-Steam shortcut by its display name.

    Reads shortcuts.vdf for all Steam user accounts and returns the unsigned
    appid if a matching entry is found. Returns None if the shortcut doesn't
    exist yet.

    This is more reliable than recalculating the CRC because the appid in
    shortcuts.vdf is the one Steam actually uses for the prefix, artwork,
    and controller config — even if the exe path has changed since creation.
    """
    uids = _find_all_steam_uids()
    name_bytes = name.encode("utf-8")

    for uid in uids:
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        if not os.path.exists(shortcuts_path):
            continue

        try:
            with open(shortcuts_path, "rb") as f:
                data = f.read()
        except Exception:
            _log.debug("shortcuts.vdf read failed", exc_info=True)
            continue

        idx = data.find(name_bytes)
        if idx == -1:
            continue

        # The appid int32 field is before the AppName field.
        # Search backward from the name for the appid marker.
        # Binary VDF: \x02appid\x00<4 bytes signed int32>
        search_start = max(0, idx - 80)
        chunk = data[search_start:idx]
        marker = b'\x02appid\x00'
        marker_pos = chunk.rfind(marker)
        if marker_pos == -1:
            continue

        appid_offset = marker_pos + len(marker)
        if appid_offset + 4 > len(chunk):
            continue

        signed = struct.unpack_from("<i", chunk, appid_offset)[0]
        unsigned = signed if signed >= 0 else signed + 2**32
        return unsigned

    return None


# ── Entry-stripping helper (rewrite-on-collision support) ────────────────────
#
# When a shortcut with a matching AppName already exists, we strip the stale
# entry from the raw VDF body and re-index the remaining entries so the new
# write can append a fresh entry with correct Exe / LaunchOptions / StartDir.
#
# Prior behavior (before this was added): name collisions caused a no-op and
# left whatever LaunchOptions the stale entry had. That meant reinstalls
# could not correct a broken LaunchOptions field. For LCD Own installs in
# particular this broke every reinstall after Steam touched shortcuts.vdf.
#
# This helper uses the same \x00\d+\x00 entry-boundary regex that
# remove_shortcut and cleanup_orphan_shortcuts already use for consistency.

def _strip_entries_by_name(raw_body: bytes, names_to_strip: set) -> tuple:
    """
    Remove entries from raw_body whose AppName matches any name in
    names_to_strip. raw_body is the shortcut body with header/footer
    already stripped (as returned by _read_shortcuts_raw).

    Returns (new_body, stripped_names) where stripped_names is a set of
    names that were actually found and removed. Re-indexes remaining
    entries to contiguous numeric indices starting at 0.

    If no matching entries are found, returns (raw_body, set()) unchanged.
    """
    if not raw_body or not names_to_strip:
        return raw_body, set()

    # Find entry boundaries. Same pattern as remove_shortcut/cleanup_orphan.
    entry_starts = [m.start() for m in re.finditer(rb'\x00\d+\x00', raw_body)]
    if not entry_starts:
        return raw_body, set()

    entries = []
    for i, start in enumerate(entry_starts):
        end = entry_starts[i + 1] if i + 1 < len(entry_starts) else len(raw_body)
        entries.append(raw_body[start:end])

    kept = []
    stripped = set()
    for entry in entries:
        # Check if this entry's AppName (or appname) matches anything we
        # want to strip. Match the full "\x01AppName\x00NAME\x00" sequence
        # so partial substring matches do not trigger a false strip.
        matched_name = None
        for name in names_to_strip:
            name_bytes = name.encode("utf-8")
            if (b'\x01AppName\x00' + name_bytes + b'\x00' in entry or
                b'\x01appname\x00' + name_bytes + b'\x00' in entry):
                matched_name = name
                break
        if matched_name is not None:
            stripped.add(matched_name)
            continue
        kept.append(entry)

    if not stripped:
        return raw_body, set()

    # Re-index remaining entries so Steam sees contiguous indices starting at 0
    reindexed = []
    for new_idx, entry in enumerate(kept):
        entry = re.sub(
            rb'^\x00\d+\x00',
            f'\x00{new_idx}\x00'.encode(),
            entry,
        )
        reindexed.append(entry)

    return b''.join(reindexed), stripped


# ── Generic shortcut API ─────────────────────────────────────────────────────
#
# add_shortcut / remove_shortcut are the single-shortcut building blocks.
# Higher-level functions like create_shortcuts and create_own_shortcuts batch
# multiple shortcuts per VDF write. These generic functions write one shortcut
# at a time, which is appropriate for callers that create shortcuts one by one
# (e.g. heroic.py's per-game HGL shortcut creation).

def add_shortcut(
    name: str,
    exe_path: str,
    start_dir: str,
    launch_options: str,
    artwork_def: dict,
    template_type: str,
    gyro_mode: str,
    on_progress=None,
    compat_tool: str = None,
    clear_compat_tool: bool = False,
    force_artwork: bool = False,
    appid_exe_path: str = None,
) -> int:
    """
    Create a single non-Steam shortcut across all Steam UIDs.

    Returns the unsigned shortcut appid.

    name             — display name (AppName in shortcuts.vdf)
    exe_path         — quoted exe path for the shortcut entry
    start_dir        — quoted StartDir for the shortcut entry
    launch_options   — LaunchOptions string
    artwork_def      — dict with icon_url, grid_url, wide_url, hero_url,
                        logo_url and corresponding *_ext keys
    template_type    — "standard" or "other" for controller config
    gyro_mode        — "on" or "off"
    on_progress      — optional callback(msg: str)
    compat_tool      — GE-Proton version to set, or None to skip
    clear_compat_tool— if True, remove any existing compat tool entry
                        (needed for HGL shortcuts where Steam's compat tool
                        sandboxes flatpak away from the host)
    force_artwork    — re-download even if cached
    appid_exe_path   — if provided, use this instead of exe_path for the
                        appid CRC calculation (for stable appids when the
                        actual exe differs from the original shortcut exe)
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    appid_key = appid_exe_path if appid_exe_path else exe_path
    shortcut_appid = _calc_shortcut_appid(appid_key, name)

    uids = _find_all_steam_uids()
    if not uids:
        prog("  No Steam user accounts found — shortcut skipped.")
        return shortcut_appid

    for uid in uids:
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")

        existing_names = _read_existing_shortcuts(shortcuts_path)
        existing_raw = _read_shortcuts_raw(shortcuts_path)

        # If a shortcut with this name already exists, strip its entry from
        # the raw body so we can write a fresh one with current Exe /
        # StartDir / LaunchOptions. Prior behavior was a no-op on name
        # match, which left stale LaunchOptions in place across reinstalls.
        replaced = False
        if name in existing_names:
            existing_raw, stripped = _strip_entries_by_name(
                existing_raw, {name}
            )
            if stripped:
                replaced = True

        next_idx = _get_next_index(existing_raw)

        icon_path = os.path.join(
            grid_dir,
            f"{shortcut_appid}_icon.{artwork_def.get('icon_ext', 'png')}",
        )

        entry = {
            "appid":               _to_signed32(shortcut_appid),
            "AppName":             name,
            "Exe":                 exe_path,
            "StartDir":            start_dir,
            "icon":                icon_path,
            "ShortcutPath":        "",
            "LaunchOptions":       launch_options,
            "IsHidden":            0,
            "AllowDesktopConfig":  1,
            "AllowOverlay":        1,
            "OpenVR":              0,
            "Devkit":              0,
            "DevkitGameID":        "",
            "DevkitOverrideAppID": 0,
            "LastPlayTime":        0,
            "FlatpakAppID":        "",
            "tags":                {"0": "DeckOps"},
        }

        entry_bytes = _make_shortcut_entry(next_idx, entry)
        try:
            _write_shortcuts_vdf(shortcuts_path, existing_raw, [entry_bytes])
            if replaced:
                prog(f"    ✓ Shortcut replaced: {name}")
            else:
                prog(f"    ✓ Shortcut created: {name}")
        except Exception as e:
            prog(f"    ⚠ Failed to write shortcut: {e}")

        # Artwork
        _download_artwork(grid_dir, shortcut_appid, artwork_def, prog,
                          force=force_artwork, clean_stale=force_artwork)

        # Controller config
        _assign_controller_config(uid, shortcut_appid,
                                  {"template_type": template_type},
                                  gyro_mode, prog)

    # Compat tool handling (config.vdf is global, outside UID loop)
    if clear_compat_tool:
        try:
            _clear_compat_tool(str(shortcut_appid))
            prog(f"    Cleared compat tool for shortcut")
        except Exception as ex:
            prog(f"    Could not clear compat tool: {ex}")
    elif compat_tool:
        try:
            from wrapper import set_compat_tool as _set_compat
            _set_compat([str(shortcut_appid)], compat_tool)
            prog(f"    ✓ GE-Proton {compat_tool} set")
        except Exception as ex:
            prog(f"    ⚠ Could not set compat tool: {ex}")

    prog(f"  Shortcut appid: {shortcut_appid}")
    return shortcut_appid


def remove_shortcut(name: str, exe_path: str, artwork_def: dict = None,
                    on_progress=None):
    """
    Remove a non-Steam shortcut by name from shortcuts.vdf for all UIDs.
    Also removes associated artwork from the grid directory.

    name        — AppName to match in shortcuts.vdf
    exe_path    — quoted exe path used for appid CRC (needed for artwork
                   file cleanup — artwork filenames are keyed on appid)
    artwork_def — dict with *_ext keys for artwork file removal;
                   if None, artwork files are left in place
    on_progress — optional callback(msg: str)
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    shortcut_appid = _calc_shortcut_appid(exe_path, name)

    uids = _find_all_steam_uids()
    if not uids:
        return

    for uid in uids:
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")

        if not os.path.exists(shortcuts_path):
            continue

        try:
            with open(shortcuts_path, "rb") as f:
                data = f.read()
        except OSError:
            _log.debug("shortcuts.vdf read failed", exc_info=True)
            continue

        header = b'\x00shortcuts\x00'
        footer = b'\x08\x08'

        body = data
        if body.startswith(header):
            body = body[len(header):]
        if body.endswith(footer):
            body = body[:-2]
        elif body.endswith(b'\x08'):
            body = body[:-1]

        entry_starts = [m.start() for m in re.finditer(rb'\x00\d+\x00', body)]
        if not entry_starts:
            continue

        entries = []
        for i, start in enumerate(entry_starts):
            end = entry_starts[i + 1] if i + 1 < len(entry_starts) else len(body)
            entries.append(body[start:end])

        title_bytes = name.encode("utf-8")
        filtered = [
            e for e in entries
            if b'\x01AppName\x00' + title_bytes + b'\x00' not in e
            and b'\x01appname\x00' + title_bytes + b'\x00' not in e
        ]

        if len(filtered) < len(entries):
            reindexed = []
            for new_idx, entry in enumerate(filtered):
                entry = re.sub(
                    rb'^\x00\d+\x00',
                    f'\x00{new_idx}\x00'.encode(),
                    entry,
                )
                reindexed.append(entry)
            new_data = header + b''.join(reindexed) + footer
            try:
                _backup_file(shortcuts_path)
                with open(shortcuts_path, "wb") as f:
                    f.write(new_data)
                prog(f"  Removed shortcut '{name}' for uid {uid}")
            except OSError as ex:
                prog(f"  Could not write shortcuts.vdf: {ex}")

        # Remove artwork
        if artwork_def:
            artwork_suffixes = [
                f"_icon.{artwork_def.get('icon_ext', 'png')}",
                f"p.{artwork_def.get('grid_ext', 'jpg')}",
                f".{artwork_def.get('wide_ext', 'jpg')}",
                f"_hero.{artwork_def.get('hero_ext', 'jpg')}",
                f"_logo.{artwork_def.get('logo_ext', 'png')}",
            ]
            for suffix in artwork_suffixes:
                art_path = os.path.join(grid_dir, f"{shortcut_appid}{suffix}")
                if os.path.exists(art_path):
                    try:
                        os.remove(art_path)
                    except OSError:
                        _log.debug("file removal failed", exc_info=True)


# ── Orphan shortcut cleanup ──────────────────────────────────────────────────
#
# When DeckOps changes the exe_path in a shortcut pattern, the CRC-based
# appid changes. The old shortcut entry, artwork, and shader cache become
# orphaned. This cleanup removes known orphan patterns automatically.
#
# To add a new orphan pattern: append (old_exe_path, title) to the list.
# The exe_path must include quotes if the original shortcut entry did.

# Known orphan patterns: old "flatpak" exe_path (before we switched to
# "/usr/bin/flatpak"). These are the 7 LCD Plutonium game titles.
_ORPHAN_PATTERNS = [
    ('"flatpak"', "Call of Duty: World at War"),
    ('"flatpak"', "Call of Duty: World at War - Multiplayer"),
    ('"flatpak"', "Call of Duty: Black Ops"),
    ('"flatpak"', "Call of Duty: Black Ops - Multiplayer"),
    ('"flatpak"', "Call of Duty: Black Ops II - Multiplayer"),
    ('"flatpak"', "Call of Duty: Black Ops II - Zombies"),
    ('"flatpak"', "Call of Duty: Modern Warfare 3 (2011) - Multiplayer"),
]


def cleanup_orphan_shortcuts(on_progress=None):
    """
    Remove orphaned DeckOps shortcuts left by older builds that used a
    different exe_path pattern. Also cleans associated artwork and shader
    caches. Safe to call multiple times -- no-ops if no orphans exist.

    Called automatically at the top of create_own_shortcuts() before new
    entries are written.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    # Build set of orphan appids from known stale (exe_path, name) pairs
    orphan_appids = set()
    orphan_names = {}  # appid -> name, for logging
    for exe_path, name in _ORPHAN_PATTERNS:
        appid = _calc_shortcut_appid(exe_path, name)
        orphan_appids.add(appid)
        orphan_names[appid] = name

    if not orphan_appids:
        return

    uids = _find_all_steam_uids()
    if not uids:
        return

    total_removed = 0

    for uid in uids:
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")

        if not os.path.exists(shortcuts_path):
            continue

        try:
            with open(shortcuts_path, "rb") as f:
                data = f.read()
        except OSError:
            _log.debug("shortcuts.vdf read failed", exc_info=True)
            continue

        header = b'\x00shortcuts\x00'
        footer = b'\x08\x08'

        body = data
        if body.startswith(header):
            body = body[len(header):]
        if body.endswith(footer):
            body = body[:-2]
        elif body.endswith(b'\x08'):
            body = body[:-1]

        # Split into entries
        entry_starts = [m.start() for m in re.finditer(rb'\x00\d+\x00', body)]
        if not entry_starts:
            continue

        entries = []
        for i, start in enumerate(entry_starts):
            end = entry_starts[i + 1] if i + 1 < len(entry_starts) else len(body)
            entries.append(body[start:end])

        # Filter out orphans by checking their stored appid against our set
        keep = []
        removed_here = 0
        for entry in entries:
            appid_match = re.search(rb'\x02appid\x00(.{4})', entry)
            if appid_match:
                stored_appid = struct.unpack('<I', appid_match.group(1))[0]
                if stored_appid in orphan_appids:
                    label = orphan_names.get(stored_appid, str(stored_appid))
                    prog(f"  Removed orphan shortcut: {label} (uid {uid})")
                    removed_here += 1
                    continue
            keep.append(entry)

        if removed_here > 0:
            # Reindex remaining entries
            reindexed = []
            for new_idx, entry in enumerate(keep):
                entry = re.sub(
                    rb'^\x00\d+\x00',
                    f'\x00{new_idx}\x00'.encode(),
                    entry,
                )
                reindexed.append(entry)
            new_data = header + b''.join(reindexed) + footer
            try:
                _backup_file(shortcuts_path)
                with open(shortcuts_path, "wb") as f:
                    f.write(new_data)
            except OSError as ex:
                prog(f"  Could not write shortcuts.vdf: {ex}")
            total_removed += removed_here

        # Remove artwork for orphan appids
        if os.path.isdir(grid_dir):
            for appid in orphan_appids:
                appid_str = str(appid)
                try:
                    for f in os.listdir(grid_dir):
                        if f.startswith(appid_str):
                            os.remove(os.path.join(grid_dir, f))
                except OSError:
                    _log.debug("file removal failed", exc_info=True)

    # Remove shader caches for orphan appids
    shadercache_dir = os.path.join(STEAM_ROOT, "steamapps", "shadercache")
    if os.path.isdir(shadercache_dir):
        for appid in orphan_appids:
            cache_dir = os.path.join(shadercache_dir, str(appid))
            if os.path.isdir(cache_dir):
                try:
                    shutil.rmtree(cache_dir)
                    prog(f"  Removed shader cache for orphan appid {appid}")
                except OSError:
                    _log.debug("directory removal failed", exc_info=True)

    if total_removed > 0:
        prog(f"Cleaned {total_removed} orphan shortcut(s)")
    else:
        prog("No orphan shortcuts found")


# ── Public API ────────────────────────────────────────────────────────────────

def create_shortcuts(installed_games: dict, selected_keys: list,
                     gyro_mode: str, on_progress=None, steam_root: str = None):
    """
    Create non-Steam shortcuts for CoD4 MP and WaW MP if they were selected
    and installed. Creates shortcuts for ALL Steam user accounts.

    steam_root -- path to Steam root, used to dynamically resolve the game's
                  compatdata prefix (internal or SD card). Falls back to
                  STEAM_ROOT if not provided.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)
    
    to_create = []
    for key, shortcut_def in SHORTCUTS.items():
        if key not in selected_keys:
            continue
        if key not in installed_games:
            continue
        game = installed_games[key]
        install_dir = game.get("install_dir") or game.get("path")
        if not install_dir:
            continue
        to_create.append((key, shortcut_def, install_dir))
    
    if not to_create:
        prog("No shortcuts to create.")
        return
    
    uids = _find_all_steam_uids()
    if not uids:
        prog("⚠ No Steam user accounts found — shortcuts skipped.")
        return
    
    for uid in uids:
        prog(f"Creating shortcuts for user {uid}...")
        
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")
        
        existing_raw = _read_shortcuts_raw(shortcuts_path)

        # Strip any existing entries whose AppName matches a shortcut we're
        # about to write. Without this, reinstalls leave stale Exe /
        # LaunchOptions / StartDir fields in place (e.g. T7X moving from
        # the stock BO3 dir to DeckOps-T7X sibling dir).
        names_to_write = {sd["name"] for _, sd, _ in to_create}
        existing_raw, stripped = _strip_entries_by_name(
            existing_raw, names_to_write
        )
        if stripped:
            prog(f"  Replacing {len(stripped)} stale shortcut(s)...")

        existing_names = [
            n for n in _read_existing_shortcuts(shortcuts_path)
            if n not in stripped
        ]
        next_idx = _get_next_index(existing_raw)
        
        new_entries = []
        
        for key, shortcut_def, install_dir in to_create:
            name = shortcut_def["name"]
            exe_path = os.path.join(install_dir, shortcut_def["exe_name"])
            game_appid = shortcut_def["game_appid"]

            # ── Resolve the game's actual compatdata prefix ───────────────
            # Dynamically find the prefix so it works whether the game is
            # on the internal NVME or an SD card. The shortcut reuses the
            # game's prefix (no separate prefix needed).
            from wrapper import find_compatdata
            _sr = steam_root or STEAM_ROOT
            game_data = installed_games.get(key, {})
            compatdata_path = find_compatdata(
                _sr, game_appid,
                game_install_dir=game_data.get("install_dir"),
            )
            if not compatdata_path:
                # Prefix doesn't exist yet - fall back to same library as game
                steamapps = os.path.dirname(os.path.dirname(install_dir))
                compatdata_path = os.path.join(steamapps, "compatdata", game_appid)

            # For t4mp (WaW Multiplayer), plutonium.py has replaced CoDWaWmp.exe
            # with a bash wrapper -- Proton cannot run it as a Windows binary.
            # OLED / Other: point at the launcher with a protocol URL for
            #               online play.
            # LCD: create a Heroic flatpak shortcut for online play. Uses the
            #      same LD_PRELOAD pattern as Steam library launch options to
            #      work around Steam's pinned libcurl conflict with flatpak.
            # exe_path (CoDWaWmp.exe) is still used for appid calculation so any
            # existing shortcut entry in Steam is not invalidated.
            if key == "t4mp":
                import config as _cfg
                if _cfg.uses_oled_path():
                    plut_dir = os.path.join(
                        compatdata_path,
                        "pfx", "drive_c", "users", "steamuser",
                        "AppData", "Local", "Plutonium",
                    )
                    plut_launcher  = os.path.join(plut_dir, "bin", "plutonium-launcher-win32.exe")
                    actual_exe     = plut_launcher
                    start_dir      = install_dir
                    launch_options = (
                        f'STEAM_COMPAT_DATA_PATH="{compatdata_path}" '
                        f'%command% "plutonium://play/t4mp"'
                    )
                else:
                    # LCD: non-Steam shortcut for online play via cache_cleanup.py.
                    # t4mp shares appid 10090 with t4sp so it can't use
                    # set_launch_options on the Steam library entry — it
                    # gets its own non-Steam shortcut instead.
                    # cache_cleanup.py cleans the Fossilize shader cache and
                    # then execs the Heroic flatpak launch.
                    _cleanup_script = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)), "cache_cleanup.py"
                    )
                    _venv_python = VENV_PYTHON
                    actual_exe     = _venv_python
                    start_dir      = os.path.dirname(_cleanup_script)
                    launch_options = f'"{_cleanup_script}" t4mp steam'
            elif key == "t7x":
                # T7X (AlterWare) -- standalone exe in the DeckOps-T7X
                # sibling dir. GE-Proton compat tool handles everything;
                # no launch options needed.
                actual_exe     = exe_path
                start_dir      = install_dir
                launch_options = ""
            else:
                actual_exe     = exe_path
                start_dir      = install_dir
                launch_options = f'STEAM_COMPAT_DATA_PATH="{compatdata_path}" %command%'

            shortcut_appid = _calc_shortcut_appid(exe_path, name)

            prog(f"  → {name}")
            prog(f"    appid: {shortcut_appid}")

            if name in existing_names:
                prog(f"    ✓ Shortcut exists")
            else:
                icon_path = os.path.join(grid_dir, f"{shortcut_appid}_icon.{shortcut_def['icon_ext']}")

                entry = {
                    "appid":               _to_signed32(shortcut_appid),
                    "AppName":             name,
                    "Exe":                 f'"{actual_exe}"',
                    "StartDir":            f'"{start_dir}"',
                    "icon":                icon_path,
                    "ShortcutPath":        "",
                    "LaunchOptions":       launch_options,
                    "IsHidden":            0,
                    "AllowDesktopConfig":  1,
                    "AllowOverlay":        1,
                    "OpenVR":              0,
                    "Devkit":              0,
                    "DevkitGameID":        "",
                    "DevkitOverrideAppID": 0,
                    "LastPlayTime":        int(time.time()),
                    "FlatpakAppID":        "",
                    "tags":                {"0": "DeckOps"},
                }

                entry_bytes = _make_shortcut_entry(next_idx, entry)
                new_entries.append(entry_bytes)
                next_idx += 1
                prog(f"    ✓ Shortcut created")

            # Set GE-Proton as the compat tool for this shortcut's appid,
            # the same way it is set for regular Steam games in ge_proton.py.
            # We use the shortcut_appid (not game_appid) because config.vdf
            # CompatToolMapping is keyed on the appid Steam actually launches.
            #
            # Exception: t4mp on LCD uses a Heroic flatpak shortcut — setting
            # a compat tool would sandbox flatpak inside SLR and break it.
            try:
                import config as cfg
                if key == "t4mp" and cfg.is_lcd():
                    _clear_compat_tool(str(shortcut_appid))
                    prog(f"    ✓ Cleared compat tool (LCD Heroic shortcut)")
                else:
                    from wrapper import set_compat_tool
                    ge_version = cfg.get_ge_proton_version()
                    if ge_version:
                        set_compat_tool([str(shortcut_appid)], ge_version)
                        prog(f"    ✓ GE-Proton {ge_version} set")
                    else:
                        prog(f"    ⚠ GE-Proton version unknown — compat tool not set")
            except Exception as ex:
                prog(f"    ⚠ Could not set compat tool for shortcut: {ex}")

            _download_artwork(grid_dir, shortcut_appid, shortcut_def, prog,
                              force=True, clean_stale=True)
            _assign_controller_config(uid, shortcut_appid, shortcut_def, gyro_mode, prog)
        
        if new_entries:
            try:
                _write_shortcuts_vdf(shortcuts_path, existing_raw, new_entries)
                prog(f"  ✓ shortcuts.vdf saved")
            except Exception as e:
                prog(f"  ⚠ Failed to write shortcuts.vdf: {e}")
        else:
            prog(f"  ✓ No new shortcuts needed")
    
    prog("✓ Non-Steam shortcuts created.")


def apply_steam_artwork(selected_keys: list, on_progress=None):
    """
    Download and apply custom artwork for Steam-owned MP/ZM games.

    Uses the Steam appid directly as the grid filename prefix, so files
    like 10190p.jpg, 10190_hero.png end up in the grid folder and Steam
    picks them up on next launch.

    selected_keys — list of game keys the user selected (e.g. ["iw4mp", "t6zm"])
    on_progress   — optional callback(msg: str)
    """
    from detect_games import GAMES

    def prog(msg):
        if on_progress:
            on_progress(msg)

    # Map game keys to Steam appids that have custom artwork
    KEY_TO_STEAM_APPID = {
        "iw4mp":     "10190",
        "iw5mp":     "42690",
        "iw5mp_ds":  "42750",
        "t5mp":      "42710",
        "t6mp":      "202990",
        "t6zm":      "212910",
        "iw6mp":     "209170",   # Ghosts MP
        "s1mp":      "209660",   # AW MP
    }

    to_apply = []
    for key in selected_keys:
        steam_appid = KEY_TO_STEAM_APPID.get(key)
        if not steam_appid:
            continue
        art_def = STEAM_ARTWORK.get(steam_appid)
        if not art_def:
            continue
        to_apply.append((key, steam_appid, art_def))

    if not to_apply:
        return

    uids = _find_all_steam_uids()
    if not uids:
        prog("⚠ No Steam user accounts found — artwork skipped.")
        return

    for uid in uids:
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")
        os.makedirs(grid_dir, exist_ok=True)

        for key, steam_appid, art_def in to_apply:
            prog(f"  Downloading artwork for {key} (appid {steam_appid})...")
            _download_artwork(grid_dir, int(steam_appid), art_def, prog,
                              force=True, clean_stale=True)

    prog(f"✓ Steam artwork applied for {len(to_apply)} game(s).")


def enrich_own_games(own_games: dict, selected_keys: list,
                     on_progress=None):
    """
    Compute shortcut appids, compatdata paths, resolved exe paths, and
    launch options for own games — WITHOUT writing any VDF entries,
    artwork, controller configs, or compat tool mappings.

    Must run early in the install flow so prefix creation can use the
    computed compatdata_path. The actual shortcut writing is deferred to
    write_own_shortcuts(), which should run AFTER all mod client installs
    so every target exe exists on disk.

    own_games     — dict {key: game_dict} from detect_games / OwnScanScreen
    selected_keys — list of game keys the user selected
    on_progress   — optional callback(msg: str)

    Returns own_games dict enriched with:
      shortcut_appid, compatdata_path, source, current_name,
      _own_actual_exe, _own_launch_options
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    _PLUT_KEYS = {"t4sp", "t4mp", "t5sp", "t5mp", "t6zm", "t6mp",
                  "iw5mp"}

    for key in selected_keys:
        if key not in OWN_SHORTCUTS:
            continue
        if key not in own_games:
            continue
        game = own_games[key]
        install_dir = game.get("install_dir")
        if not install_dir:
            continue

        shortcut_def = OWN_SHORTCUTS[key]
        name         = shortcut_def["name"]
        exe_path     = game["exe_path"]

        # Calculate appid from quoted exe + canonical name.
        quoted_exe     = f'"{exe_path}"'
        shortcut_appid = _calc_shortcut_appid(quoted_exe, name)

        # Own games always get their own CRC-based prefix keyed on the
        # shortcut appid.
        compatdata_path = os.path.join(COMPAT_ROOT, str(shortcut_appid))

        # Enrich the game dict so downstream code has the appid and paths
        game["shortcut_appid"]  = shortcut_appid
        game["compatdata_path"] = compatdata_path
        game["source"]          = "own"
        game["current_name"]    = name

        # ── Resolve the actual exe and launch options per client type ──
        if key in _PLUT_KEYS:
            import config as _cfg
            if _cfg.is_lcd():
                # LCD Plutonium: shortcut handled separately by heroic.py.
                # Still enrich the dict — install_plutonium needs the paths.
                game["_own_actual_exe"]      = None
                game["_own_launch_options"]  = None
                prog(f"  → {name}  (LCD path — shortcut handled separately)")
                continue

            plut_dir = os.path.join(
                compatdata_path,
                "pfx", "drive_c", "users", "steamuser",
                "AppData", "Local", "Plutonium",
            )
            actual_exe = os.path.join(plut_dir, "bin", "plutonium-launcher-win32.exe")
            launch_options = (
                f'STEAM_COMPAT_DATA_PATH="{compatdata_path}" '
                f'%command% "plutonium://play/{key}"'
            )

        elif key == "iw4mp":
            actual_exe = os.path.join(install_dir, "iw4x.exe")
            launch_options = ""

        elif key == "cod4sp":
            actual_exe = os.path.join(install_dir, "iw3sp_mod.exe")
            launch_options = ""

        elif key == "t7":
            actual_exe = exe_path
            launch_options = 'WINEDLLOVERRIDES="d3d11=n,b" %command%'

        elif key == "t7x":
            actual_exe = os.path.join(install_dir, "t7x.exe")
            launch_options = ""

        elif key in ("iw6mp", "iw6sp"):
            actual_exe = os.path.join(install_dir, "iw6-mod.exe")
            launch_options = "-multiplayer" if key == "iw6mp" else "-singleplayer"

        elif key in ("s1mp", "s1sp"):
            actual_exe = os.path.join(install_dir, "s1-mod.exe")
            launch_options = "-multiplayer" if key == "s1mp" else "-singleplayer"

        else:
            actual_exe = exe_path
            launch_options = ""

        # Recalculate appid from actual_exe (mod client exe may differ
        # from the original game exe used above).
        #
        # Skip for Plutonium keys — their actual_exe path is built from
        # compatdata_path which embeds the initial appid. Recalculating
        # produces a *different* appid (different exe path → different CRC),
        # causing the shortcut to point at a prefix that was never created.
        # The initial appid is correct for Plutonium because the prefix,
        # launch options, and exe path all reference it consistently.
        if key not in _PLUT_KEYS:
            quoted_actual = f'"{actual_exe}"'
            final_appid   = _calc_shortcut_appid(quoted_actual, name)
            if final_appid != shortcut_appid:
                shortcut_appid  = final_appid
                compatdata_path = os.path.join(COMPAT_ROOT, str(shortcut_appid))
                game["shortcut_appid"]  = shortcut_appid
                game["compatdata_path"] = compatdata_path

        # Store resolved values for write_own_shortcuts() to use later
        game["_own_actual_exe"]     = actual_exe
        game["_own_launch_options"] = launch_options

        prog(f"  → {name}  appid: {shortcut_appid}")

    return own_games


def write_own_shortcuts(own_games: dict, selected_keys: list,
                        gyro_mode: str, on_progress=None):
    """
    Write non-Steam shortcut VDF entries, download artwork, assign
    controller configs, and set GE-Proton compat tool for own games.

    Must run AFTER all mod client installs so every target exe exists
    on disk. Reads enrichment data (shortcut_appid, _own_actual_exe,
    _own_launch_options) previously set by enrich_own_games().

    own_games     — dict {key: game_dict} enriched by enrich_own_games()
    selected_keys — list of game keys the user selected
    gyro_mode     — "on" or "off"
    on_progress   — optional callback(msg: str)
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    # Clean up orphaned shortcuts from older DeckOps builds before
    # writing new entries. Safe to call every time -- no-ops if clean.
    cleanup_orphan_shortcuts(on_progress=on_progress)

    _PLUT_KEYS = {"t4sp", "t4mp", "t5sp", "t5mp", "t6zm", "t6mp",
                  "iw5mp"}

    to_create = {}
    for key in selected_keys:
        if key not in OWN_SHORTCUTS:
            continue
        if key not in own_games:
            continue
        game = own_games[key]
        if not game.get("install_dir"):
            continue
        # Skip LCD Plutonium keys — handled separately by heroic.py
        if game.get("_own_actual_exe") is None and key in _PLUT_KEYS:
            continue
        to_create[key] = (OWN_SHORTCUTS[key], game)

    if not to_create:
        prog("No non-Steam game shortcuts to write.")
        return

    uids = _find_all_steam_uids()
    if not uids:
        prog("⚠ No Steam user accounts found — own shortcuts skipped.")
        return

    for uid in uids:
        prog(f"Writing own game shortcuts for user {uid}...")

        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")

        existing_raw = _read_shortcuts_raw(shortcuts_path)

        # Strip any existing entries whose AppName matches a shortcut we're
        # about to write so reinstalls replace stale entries cleanly.
        names_to_write = {d["name"] for d, _ in to_create.values()}
        existing_raw, stripped = _strip_entries_by_name(
            existing_raw, names_to_write
        )
        if stripped:
            prog(f"  Replacing {len(stripped)} stale shortcut(s)...")

        existing_names = [
            n for n in _read_existing_shortcuts(shortcuts_path)
            if n not in stripped
        ]

        next_idx = _get_next_index(existing_raw)

        new_entries = []

        for key, (shortcut_def, game) in to_create.items():
            name          = shortcut_def["name"]
            install_dir   = game["install_dir"]
            actual_exe    = game["_own_actual_exe"]
            launch_options = game["_own_launch_options"]
            shortcut_appid = game["shortcut_appid"]

            icon_path = os.path.join(
                grid_dir, f"{shortcut_appid}_icon.{shortcut_def['icon_ext']}"
            )

            if not os.path.exists(actual_exe):
                prog(f"  → {name}")
                prog(f"    ⚠ {os.path.basename(actual_exe)} not found — shortcut will be created anyway")
            else:
                prog(f"  → {name}")
            prog(f"    appid: {shortcut_appid}")

            if name in existing_names:
                prog(f"    ⚠ Unexpected name collision after strip")

            entry = {
                "appid":               _to_signed32(shortcut_appid),
                "AppName":             name,
                "Exe":                 f'"{actual_exe}"',
                "StartDir":            f'"{install_dir}"',
                "icon":                icon_path,
                "ShortcutPath":        "",
                "LaunchOptions":       launch_options,
                "IsHidden":            0,
                "AllowDesktopConfig":  1,
                "AllowOverlay":        1,
                "OpenVR":              0,
                "Devkit":              0,
                "DevkitGameID":        "",
                "DevkitOverrideAppID": 0,
                "LastPlayTime":        0,
                "FlatpakAppID":        "",
                "tags":                {"0": "DeckOps"},
            }

            entry_bytes = _make_shortcut_entry(next_idx, entry)
            new_entries.append(entry_bytes)
            next_idx += 1
            prog(f"    ✓ Shortcut created")

            # Download artwork
            _download_artwork(grid_dir, shortcut_appid, shortcut_def, prog,
                              force=True, clean_stale=True)

            # Assign controller config
            _assign_controller_config(uid, shortcut_appid, shortcut_def, gyro_mode, prog)

            # Set GE-Proton compat tool
            try:
                import config as _cfg
                from wrapper import set_compat_tool
                ge_version = _cfg.get_ge_proton_version()
                if ge_version:
                    set_compat_tool([str(shortcut_appid)], ge_version)
                    prog(f"    ✓ GE-Proton {ge_version} set")
            except Exception as ex:
                prog(f"    ⚠ Could not set GE-Proton: {ex}")

        if new_entries:
            try:
                _write_shortcuts_vdf(shortcuts_path, existing_raw, new_entries)
                prog(f"  ✓ shortcuts.vdf saved")
            except Exception as e:
                prog(f"  ⚠ Failed to write shortcuts.vdf: {e}")
        else:
            prog(f"  ✓ No new shortcuts needed")

    prog("✓ Own game shortcuts written.")


def create_own_shortcuts(own_games: dict, selected_keys: list,
                        gyro_mode: str, on_progress=None, steam_root: str = None):
    """
    Legacy wrapper — enriches own game dicts AND writes shortcuts in one
    call. Kept for backward compatibility. New code should call
    enrich_own_games() early and write_own_shortcuts() after installs.

    Returns own_games dict enriched with shortcut_appid, compatdata_path,
    and source fields.
    """
    own_games = enrich_own_games(own_games, selected_keys,
                                 on_progress=on_progress)
    write_own_shortcuts(own_games, selected_keys, gyro_mode,
                        on_progress=on_progress)
    return own_games


# ── DeckOps Plutonium Offline Launcher shortcut ──────────────────────────────
# The launcher is a Windows exe (DeckOps_Offline.exe) built with PyInstaller
# that runs inside GE-Proton as a non-Steam shortcut. It shows installed
# Plutonium games and lets users pick a mode to launch. The bootstrapper
# runs as a direct Windows-to-Windows subprocess inside the same Wine/Proton
# session, so all games (including T4/T5) work in Game Mode.
#
# Both OLED and LCD Decks get this shortcut — it's the unified Plutonium
# offline entry point.

LAUNCHER_TITLE = "DeckOps: Plutonium Offline"

# Path to the Windows exe relative to the DeckOps install directory.
# install.sh pulls the repo to ~/DeckOps[-Nightly], so the exe lands at:
#   ~/DeckOps[-Nightly]/assets/LAN/DeckOps_Offline.exe
_LAUNCHER_EXE_REL = os.path.join("assets", "LAN", "DeckOps_Offline.exe")

# Custom DeckOps Plutonium launcher artwork. Hosted in the repo so updates
# ship with the source. _download_artwork below always re-downloads on
# install so URL/asset changes propagate to existing setups.
LAUNCHER_ART = {
    "icon_url":  asset_url("assets/images/icon.png"),
    "grid_url":  asset_url("assets/images/heroes/deckops_grid.png"),
    "wide_url":  asset_url("assets/images/heroes/deckops_launcher_banner.png"),
    "hero_url":  asset_url("assets/images/heroes/deckops_hero.png"),
    "logo_url":  asset_url("assets/images/heroes/deckops.png"),
    "icon_ext": "png", "grid_ext": "png", "wide_ext": "png", "hero_ext": "png", "logo_ext": "png",
}

# Old exe path used by the python3-based launcher. Needed so migration can
# calculate the old appid and strip stale artwork / compat tool entries.
_OLD_LAUNCHER_EXE = VENV_PYTHON


def get_launcher_appid() -> int:
    """
    Return the Steam shortcut appid for the offline launcher exe.

    Other modules (plutonium_oled, plutonium_lcd, game_config) use this
    to locate the launcher's compatdata prefix and copy configs into it
    so the offline launcher can see all installed games.
    """
    launcher_exe = os.path.join(INSTALL_DIR, _LAUNCHER_EXE_REL)
    exe_path = f'"{launcher_exe}"'
    return _calc_shortcut_appid(exe_path, LAUNCHER_TITLE)


def get_launcher_plut_dir() -> str:
    """
    Return the Plutonium directory inside the launcher's compatdata prefix.

    This is where Plutonium bins, storage/, config.json, and mods must be
    placed so the offline launcher exe (running inside this prefix via
    GE-Proton) can find them.

    Path: ~/.local/share/Steam/steamapps/compatdata/<appid>/pfx/drive_c/
          users/steamuser/AppData/Local/Plutonium
    """
    appid = get_launcher_appid()
    return os.path.join(
        COMPAT_ROOT, str(appid),
        "pfx", "drive_c", "users", "steamuser",
        "AppData", "Local", "Plutonium",
    )


def _launcher_launch_opts(shortcut_appid: int) -> str:
    """
    Return launch options for the offline launcher shortcut.

    Disables fsync and esync to prevent BO1/BO2 hangs on kernels
    without NTSync (pre-6.14 / SteamOS < 3.7.20).
    """
    return "PROTON_NO_FSYNC=1 PROTON_NO_ESYNC=1 %command%"


def create_launcher_shortcut(on_progress=None):
    """
    Create a non-Steam shortcut for the DeckOps Plutonium Offline Launcher.

    The launcher is a Windows exe (DeckOps_Offline.exe) that runs inside
    GE-Proton. Called once after Plutonium games are set up — both OLED
    and LCD.

    The shortcut runs:  GE-Proton → DeckOps_Offline.exe
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    launcher_exe = os.path.join(INSTALL_DIR, _LAUNCHER_EXE_REL)

    if not os.path.exists(launcher_exe):
        prog(f"  Launcher exe not found: {launcher_exe}")
        return

    exe_path  = f'"{launcher_exe}"'
    start_dir = f'"{os.path.dirname(launcher_exe)}"'

    shortcut_appid = _calc_shortcut_appid(exe_path, LAUNCHER_TITLE)

    uids = _find_all_steam_uids()
    if not uids:
        prog("  No Steam user accounts found - launcher shortcut skipped.")
        return

    for uid in uids:
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")

        existing_names = _read_existing_shortcuts(shortcuts_path)
        existing_raw = _read_shortcuts_raw(shortcuts_path)

        # ── Migration ────────────────────────────────────────────────────
        # Remove stale launcher shortcuts from prior versions so users
        # don't end up with duplicates.
        _stale_names = set()

        # 1) Very old name: "DeckOps: Plutonium Launcher"
        _OLD_LAUNCHER_TITLE = "DeckOps: Plutonium Launcher"
        if _OLD_LAUNCHER_TITLE in existing_names:
            _stale_names.add(_OLD_LAUNCHER_TITLE)

        # 2) Same name but old python3-based exe path — different appid
        #    because exe_path changed. Strip by name so the new entry
        #    (with the exe path) can be written fresh.
        _old_py_exe = f'"{_OLD_LAUNCHER_EXE}"'
        _old_py_appid = _calc_shortcut_appid(_old_py_exe, LAUNCHER_TITLE)
        if _old_py_appid != shortcut_appid and LAUNCHER_TITLE in existing_names:
            _stale_names.add(LAUNCHER_TITLE)

        if _stale_names:
            existing_raw, _stripped = _strip_entries_by_name(
                existing_raw, _stale_names
            )
            if _stripped:
                for _sn in _stripped:
                    prog(f"  Removed stale launcher shortcut: {_sn}")
            existing_names = [n for n in existing_names if n not in _stale_names]

            # Clean up artwork for the old python3-based appid
            if _old_py_appid != shortcut_appid:
                try:
                    import glob as _glob
                    for _f in _glob.glob(os.path.join(grid_dir, f"{_old_py_appid}*")):
                        try:
                            os.remove(_f)
                        except OSError:
                            _log.debug("file removal failed", exc_info=True)
                    prog(f"  Cleaned old launcher artwork (appid {_old_py_appid})")
                except Exception:
                    _log.debug("file removal failed", exc_info=True)

            # Clear stale compat tool entry for old appid
            try:
                _clear_compat_tool(str(_old_py_appid))
                prog(f"  Cleared old compat tool entry (appid {_old_py_appid})")
            except Exception:
                _log.debug("operation failed", exc_info=True)

        next_idx = _get_next_index(existing_raw)

        icon_path = os.path.join(
            grid_dir, f"{shortcut_appid}_icon.{LAUNCHER_ART['icon_ext']}"
        )

        if LAUNCHER_TITLE in existing_names:
            prog(f"  Launcher shortcut already exists")
        else:
            entry = {
                "appid":               _to_signed32(shortcut_appid),
                "AppName":             LAUNCHER_TITLE,
                "Exe":                 exe_path,
                "StartDir":            start_dir,
                "icon":                icon_path,
                "ShortcutPath":        "",
                "LaunchOptions":       _launcher_launch_opts(shortcut_appid),
                "IsHidden":            0,
                "AllowDesktopConfig":  1,
                "AllowOverlay":        1,
                "OpenVR":              0,
                "Devkit":              0,
                "DevkitGameID":        "",
                "DevkitOverrideAppID": 0,
                "LastPlayTime":        0,
                "FlatpakAppID":        "",
                "tags":                {"0": "DeckOps"},
            }

            entry_bytes = _make_shortcut_entry(next_idx, entry)
            try:
                _write_shortcuts_vdf(shortcuts_path, existing_raw, [entry_bytes])
                prog(f"  Launcher shortcut created: {LAUNCHER_TITLE}")
            except Exception as e:
                prog(f"  Failed to write launcher shortcut: {e}")

        # Always re-download launcher artwork (URLs may change between versions).
        _download_artwork(grid_dir, shortcut_appid, LAUNCHER_ART, prog,
                          force=True, clean_stale=True)

        # Assign the user's chosen controller template so games launched
        # from the launcher inherit the correct gamepad layout. The launcher
        # runs as a non-Steam shortcut and Steam applies its controller
        # config to all child processes — so the template here is what the
        # actual game will use. "standard" is correct for most Plutonium
        # games (the majority are Treyarch titles using standard layout).
        try:
            import config as _cfg
            _gyro = _cfg.get_gyro_mode() or "on"
        except Exception:
            _gyro = "on"
        _assign_controller_config(uid, shortcut_appid,
                                  {"template_type": "standard"},
                                  _gyro, prog)

        # Set GE-Proton as compat tool — the exe runs inside Proton.
        try:
            import config as _cfg
            from wrapper import set_compat_tool
            ge_version = _cfg.get_ge_proton_version()
            if ge_version:
                set_compat_tool([str(shortcut_appid)], ge_version)
                prog(f"    ✓ GE-Proton {ge_version} set for launcher")
            else:
                prog(f"    ⚠ No GE-Proton version found — compat tool not set")
        except Exception as ex:
            prog(f"    ⚠ Could not set GE-Proton: {ex}")

    prog(f"  Launcher shortcut appid: {shortcut_appid}")


def remove_launcher_shortcut(on_progress=None):
    """
    Remove the DeckOps Plutonium Offline Launcher shortcut from shortcuts.vdf
    for all discovered Steam UIDs. Also removes associated artwork.

    Handles both the current exe-based shortcut and the old python3-based
    shortcut (different appids due to different exe paths).
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    # Current exe-based appid
    launcher_exe = os.path.join(INSTALL_DIR, _LAUNCHER_EXE_REL)
    exe_path_new = f'"{launcher_exe}"'
    appid_new = _calc_shortcut_appid(exe_path_new, LAUNCHER_TITLE)

    # Old python3-based appid
    exe_path_old = f'"{_OLD_LAUNCHER_EXE}"'
    appid_old = _calc_shortcut_appid(exe_path_old, LAUNCHER_TITLE)

    appids_to_clean = {appid_new, appid_old}

    uids = _find_all_steam_uids()
    if not uids:
        return

    for uid in uids:
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")

        if not os.path.exists(shortcuts_path):
            continue

        try:
            with open(shortcuts_path, "rb") as f:
                data = f.read()
        except OSError:
            _log.debug("shortcuts.vdf read failed", exc_info=True)
            continue

        header = b'\x00shortcuts\x00'
        footer = b'\x08\x08'

        body = data
        if body.startswith(header):
            body = body[len(header):]
        if body.endswith(footer):
            body = body[:-2]
        elif body.endswith(b'\x08'):
            body = body[:-1]

        entry_starts = [m.start() for m in re.finditer(rb'\x00\d+\x00', body)]
        if not entry_starts:
            continue

        entries = []
        for i, start in enumerate(entry_starts):
            end = entry_starts[i + 1] if i + 1 < len(entry_starts) else len(body)
            entries.append(body[start:end])

        title_bytes = LAUNCHER_TITLE.encode("utf-8")
        filtered = [
            e for e in entries
            if b'\x01AppName\x00' + title_bytes + b'\x00' not in e
            and b'\x01appname\x00' + title_bytes + b'\x00' not in e
        ]

        if len(filtered) < len(entries):
            reindexed = []
            for new_idx, entry in enumerate(filtered):
                entry = re.sub(rb'^\x00\d+\x00', f'\x00{new_idx}\x00'.encode(), entry)
                reindexed.append(entry)
            new_data = header + b''.join(reindexed) + footer
            try:
                _backup_file(shortcuts_path)
                with open(shortcuts_path, "wb") as f:
                    f.write(new_data)
                prog(f"  Removed launcher shortcut for uid {uid}")
            except OSError as ex:
                prog(f"  Could not write shortcuts.vdf: {ex}")

        # Remove artwork for both old and new appids
        artwork_suffixes = [
            f"_icon.{LAUNCHER_ART['icon_ext']}",
            f"p.{LAUNCHER_ART['grid_ext']}",
            f".{LAUNCHER_ART['wide_ext']}",
            f"_hero.{LAUNCHER_ART['hero_ext']}",
            f"_logo.{LAUNCHER_ART['logo_ext']}",
        ]
        for appid in appids_to_clean:
            for suffix in artwork_suffixes:
                art_path = os.path.join(grid_dir, f"{appid}{suffix}")
                if os.path.exists(art_path):
                    try:
                        os.remove(art_path)
                    except OSError:
                        _log.debug("file removal failed", exc_info=True)


# ── CLI for testing ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    from detect_games import find_steam_root, parse_library_folders, find_installed_games
    
    print("Finding installed games...")
    steam_root = find_steam_root()
    if not steam_root:
        print("Steam not found.")
        sys.exit(1)
    
    libs = parse_library_folders(steam_root)
    installed = find_installed_games(libs)
    
    print(f"Found {len(installed)} games")
    for key in SHORTCUTS:
        if key in installed:
            print(f"  ✓ {key}: {installed[key].get('install_dir', installed[key].get('path'))}")
        else:
            print(f"  ✗ {key}: not installed")
    
    print("\nCreating shortcuts (test mode)...")
    create_shortcuts(
        installed_games=installed,
        selected_keys=list(SHORTCUTS.keys()),
        gyro_mode="on",
        on_progress=lambda msg: print(msg)
    )
