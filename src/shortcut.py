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

import os
import re
import shutil
import struct
import threading
import time

from identity import INSTALL_DIR, VENV_PYTHON, asset_url
from log import get_logger
from net import download

_log = get_logger(__name__)


# ── Paths ─────────────────────────────────────────────────────────────────────

from steam_common import (
    PROJECT_ROOT, STEAM_ROOT, USERDATA_DIR,
    backup_file as _backup_file,
    calc_shortcut_appid as _calc_shortcut_appid,
    find_all_steam_uids as _find_all_steam_uids,
    get_deck_serial as _get_deck_serial,
    patch_configset as _patch_configset,
    shortcut_title_key as _shortcut_title_key,
)

COMPAT_ROOT    = os.path.join(STEAM_ROOT, "steamapps", "compatdata")
ASSETS_DIR     = os.path.join(PROJECT_ROOT, "assets", "controllers")




# ── Shortcut definitions ──────────────────────────────────────────────────────

SHORTCUTS = {
    # Stock MP with no client yet, so they get the KB+M template
    "cod1mp": {
        "name":            "Call of Duty - Multiplayer",
        "exe_name":        "CoDMP.exe",
        "game_appid":      "2620",
        "template_type":   "other",
        "icon_url":        "https://cdn2.steamgriddb.com/icon/5bb098377521372ff3fe2d5fdc965fa8/32/256x256.png",
        "grid_url":        "https://cdn2.steamgriddb.com/grid/49f6685e68490297d3b8e8b655c791cd.jpg",
        "wide_url":        "https://cdn2.steamgriddb.com/grid/ba11de6d3ef01bb8a2df64a347b63c5b.jpg",
        "hero_url":        "https://cdn2.steamgriddb.com/hero/a04a0656dfdbce5dbe00bfd0e401436e.png",
        "logo_url":        "https://cdn2.steamgriddb.com/logo/00570c78f3d7277184b5f86dc919fce5.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    "coduomp": {
        "name":            "Call of Duty: United Offensive - Multiplayer",
        "exe_name":        "CoDUOMP.exe",
        "game_appid":      "2640",
        "template_type":   "other",
        "icon_url":        "https://cdn2.steamgriddb.com/icon/fa46d72636d271b3974b6be01333c50e.ico",
        "grid_url":        "https://cdn2.steamgriddb.com/grid/ed6704089026138e6a3282339ee4374b.jpg",
        "wide_url":        "https://cdn2.steamgriddb.com/grid/f887105f1315f23a2740632b788b32f5.jpg",
        "hero_url":        "https://cdn2.steamgriddb.com/hero/74c040829e4620eb5628df19071ec670.png",
        "logo_url":        "https://cdn2.steamgriddb.com/logo/17186fe67f63a028d07a5821ad54dd0f.png",
        "icon_ext": "ico", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    "cod2mp": {
        "name":            "Call of Duty 2 - Multiplayer",
        "exe_name":        "CoD2MP_s.exe",
        "game_appid":      "2630",
        "template_type":   "other",
        "icon_url":        "https://cdn2.steamgriddb.com/icon/e7b9e0b39ba3af2f8aa0e8aaa630cd0d.png",
        "grid_url":        "https://cdn2.steamgriddb.com/grid/4ad72e8d113a1ff0abc77718f29f0f18.jpg",
        "wide_url":        "https://cdn2.steamgriddb.com/grid/7d98395d16a103b1f8042f7890343d5c.jpg",
        "hero_url":        "https://cdn2.steamgriddb.com/hero/6fad28dc918c302ede5ee2f2368228e5.png",
        "logo_url":        "https://cdn2.steamgriddb.com/logo/c01c46e45de108f23c7ddb2bc3bb4103.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    "cod4mp": {
        "name":            "Call of Duty 4: Modern Warfare - Multiplayer",
        "exe_name":        "iw3mp.exe",
        "game_appid":      "7940",
        "template_type":   "other",
        "icon_url":        "https://cdn2.steamgriddb.com/icon/59b109c700b500daa9ef3a6769bc8c6f.png",
        "grid_url":        "https://cdn2.steamgriddb.com/grid/ef334e3d937c406e95623fa641627a63.jpg",
        "wide_url":        "https://cdn2.steamgriddb.com/grid/b66c2356afe332554516c4ddc4708452.png",
        "hero_url":        "https://cdn2.steamgriddb.com/hero_thumb/95bc8e097e09212ec0160a7bc0b46fd6.jpg",
        "logo_url":        "https://cdn2.steamgriddb.com/logo_thumb/0440169a43de927753429dd69ca8c735.png",
        "icon_ext":        "png",
        "grid_ext":        "jpg",
        "wide_ext":        "png",
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
    "cod1sp": {
        "name":           "Call of Duty - Singleplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/2620/b4ce47894dee6ec21b0ad96cfb2b8c0036098e39.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/2620/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/2620/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/2620/library_hero_2x.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/2620/logo_2x.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "cod1mp": {
        "name":           "Call of Duty - Multiplayer",
        "template_type":  "other",
        "icon_url":       "https://cdn2.steamgriddb.com/icon/5bb098377521372ff3fe2d5fdc965fa8/32/256x256.png",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/49f6685e68490297d3b8e8b655c791cd.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/grid/ba11de6d3ef01bb8a2df64a347b63c5b.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero/a04a0656dfdbce5dbe00bfd0e401436e.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo/00570c78f3d7277184b5f86dc919fce5.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    "coduosp": {
        "name":           "Call of Duty: United Offensive - Singleplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/2640/e5fbc61fce98c303a9c49dc988163499b183f037.jpg",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/3ead4e722d6df4d4d7e1c61fbdd66968.png",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/2640/header.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero/52c103dad7014b76e67cd1307b4a4bf0.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo/5ff1ed03c4a4267f97fd841827b79e00.png",
        "icon_ext": "jpg", "grid_ext": "png", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    "coduomp": {
        "name":           "Call of Duty: United Offensive - Multiplayer",
        "template_type":  "other",
        "icon_url":       "https://cdn2.steamgriddb.com/icon/fa46d72636d271b3974b6be01333c50e.ico",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/ed6704089026138e6a3282339ee4374b.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/grid/f887105f1315f23a2740632b788b32f5.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero/74c040829e4620eb5628df19071ec670.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo/17186fe67f63a028d07a5821ad54dd0f.png",
        "icon_ext": "ico", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    "cod2sp": {
        "name":           "Call of Duty 2 - Singleplayer",
        "template_type":  "standard",
        "icon_url":       "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/2630/2e455daa8702a3cb9da8733232ec330a06936df3.jpg",
        "grid_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/2630/library_600x900_2x.jpg",
        "wide_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/2630/header.jpg",
        "hero_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/2630/library_hero_2x.jpg",
        "logo_url":       "https://shared.steamstatic.com/store_item_assets/steam/apps/2630/logo_2x.png",
        "icon_ext": "jpg", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "jpg", "logo_ext": "png",
    },
    "cod2mp": {
        "name":           "Call of Duty 2 - Multiplayer",
        "template_type":  "other",
        "icon_url":       "https://cdn2.steamgriddb.com/icon/e7b9e0b39ba3af2f8aa0e8aaa630cd0d.png",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/4ad72e8d113a1ff0abc77718f29f0f18.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/grid/7d98395d16a103b1f8042f7890343d5c.jpg",
        "hero_url":       "https://cdn2.steamgriddb.com/hero/6fad28dc918c302ede5ee2f2368228e5.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo/c01c46e45de108f23c7ddb2bc3bb4103.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "jpg", "hero_ext": "png", "logo_ext": "png",
    },
    # CoD3Recomp runs the console game, which already has pad support and aim assist
    "cod3": {
        "name":           "Call of Duty 3",
        "template_type":  "standard",
        "icon_url":       "https://cdn2.steamgriddb.com/icon/2f05776d37d873642af484255572600d.ico",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/ebb4cd828b62543f83b337e48b333eb8.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/grid/60b1bbf7401dd9361d241c7dc178b7e9.png",
        "hero_url":       "https://cdn2.steamgriddb.com/hero/e54002424031588e6248ffa5c5eaa36a.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo/16bc552457d2e473c07026303a5de747.png",
        "icon_ext": "ico", "grid_ext": "jpg", "wide_ext": "png", "hero_ext": "png", "logo_ext": "png",
    },
    # Finest Hour Remastered reads the pad itself
    "codfh": {
        "name":           "Call of Duty: Finest Hour",
        "template_type":  "standard",
        "icon_url":       "https://cdn2.steamgriddb.com/icon/5701f2db3b3e449c953c129fac75f358.ico",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/f0dda1e19cb7596fcb7430e4b3f4f0b5.png",
        "wide_url":       "https://cdn2.steamgriddb.com/grid/a39fdc350f2dccbd44187ec2b28b0052.png",
        "hero_url":       "https://cdn2.steamgriddb.com/hero/fee6e6bfe55024e4ae92983d776ecd56.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo/ec4e854146d020e2bae1e0d14bf709ad.png",
        "icon_ext": "ico", "grid_ext": "png", "wide_ext": "png", "hero_ext": "png", "logo_ext": "png",
    },
    # The BRO engine reads the pad in its Xbox layout
    "bro": {
        "name":           "Call of Duty 2: Big Red One",
        "template_type":  "standard",
        "icon_url":       "https://cdn2.steamgriddb.com/icon/613594054b1f1c7911d9f9fc9c795477.png",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/3e5589b2df55552e7716818b29ba2a2d.png",
        "wide_url":       "https://cdn2.steamgriddb.com/grid/ba7d4edf877300c40f66184e6cf56c73.png",
        "hero_url":       "https://cdn2.steamgriddb.com/hero/eb1009b8772fd76316bac8a1519b8a03.jpg",
        "logo_url":       "https://cdn2.steamgriddb.com/logo/713162451b118e993404ff1c7a759183.png",
        "icon_ext": "png", "grid_ext": "png", "wide_ext": "png", "hero_ext": "jpg", "logo_ext": "png",
    },
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
        "grid_url":       "https://cdn2.steamgriddb.com/grid/ef334e3d937c406e95623fa641627a63.jpg",
        "wide_url":       "https://cdn2.steamgriddb.com/grid/b66c2356afe332554516c4ddc4708452.png",
        "hero_url":       "https://cdn2.steamgriddb.com/hero_thumb/95bc8e097e09212ec0160a7bc0b46fd6.jpg",
        "logo_url":       "https://cdn2.steamgriddb.com/logo_thumb/0440169a43de927753429dd69ca8c735.png",
        "icon_ext": "png", "grid_ext": "jpg", "wide_ext": "png", "hero_ext": "jpg", "logo_ext": "png",
    },
    "iw4sp": {
        "name":           "Call of Duty: Modern Warfare 2 (2009) - Singleplayer",
        "template_type":  "standard",
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
        "template_type":  "standard",
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

def _to_signed32(n):
    """Convert unsigned int32 appid to signed int32 for vdf binary format."""
    return n if n <= 2147483647 else n - 2**32


def _download(url: str, dest: str) -> bool:
    """Download a file from URL to dest path. Returns True on success."""
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        download(url, dest, timeout=30)
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


def _split_entries(body: bytes) -> list:
    """Split a header-stripped shortcuts body into raw entries."""
    starts = [m.start() for m in re.finditer(rb'\x00\d+\x00', body)]
    return [body[s:e] for s, e in zip(starts, starts[1:] + [len(body)])]


def _reindex(entries: list) -> bytes:
    """Join entries with contiguous indices starting at 0 so Steam sees them all."""
    return b''.join(re.sub(rb'^\x00\d+\x00', f'\x00{i}\x00'.encode(), e)
                    for i, e in enumerate(entries))


def _shortcut_entry(appid: int, name: str, exe: str, start_dir: str, icon: str,
                    launch_options: str, last_play: int = 0) -> dict:
    """Field dict for _make_shortcut_entry. Exe/StartDir are passed already quoted."""
    return {
        "appid":               _to_signed32(appid),
        "AppName":             name,
        "Exe":                 exe,
        "StartDir":            start_dir,
        "icon":                icon,
        "ShortcutPath":        "",
        "LaunchOptions":       launch_options,
        "IsHidden":            0,
        "AllowDesktopConfig":  1,
        "AllowOverlay":        1,
        "OpenVR":              0,
        "Devkit":              0,
        "DevkitGameID":        "",
        "DevkitOverrideAppID": 0,
        "LastPlayTime":        last_play,
        "FlatpakAppID":        "",
        "tags":                {"0": "DeckOps"},
    }


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
    """Return the primary controller template filename for a profile type
    and gyro mode.

    Delegates to controller_profiles._profile_filename so shortcut
    creation and profile re-application always resolve the same file,
    including device variants (Legion Go, Legion Go 2, 2btn, Steam
    Machine triton) and all four gyro modes. The import is lazy to keep
    this module importable standalone, mirroring controller_profiles'
    own lazy imports of shortcut.py; there is no module-level cycle.

    Falls back to the standard Neptune mapping if delegation fails.
    """
    try:
        from controller_profiles import _profile_filename
        filenames = _profile_filename(template_type, gyro_mode)
        if filenames:
            return filenames[0]
    except Exception:
        _log.debug("profile filename delegation failed", exc_info=True)
    _SUFFIX_MAP = {"on": "ads", "hold": "hold", "toggle": "toggle"}
    suffix = _SUFFIX_MAP.get(gyro_mode, "off")
    if template_type == "other":
        return f"controller_neptune_deckops_other_{suffix}.vdf"
    else:
        return f"controller_neptune_deckops_{suffix}.vdf"


def _assign_controller_config(uid: str, appid: int, shortcut_def: dict,
                               gyro_mode: str, prog, title: str = None):
    """
    Assign controller template for a non-Steam shortcut.

    Writes the device's primary configset (configset_controller_neptune.vdf
    on Deck, verified on hardware as the file Game Mode resolves templates
    from; triton on Steam Machine, steamos_handheld on Legion Go 2) and,
    on a Deck, the serial configset. Game Mode reads the serial file first
    and keeps the user's own picks there; another device on the same
    account never rewrites it, while it can sync its own neptune file over
    ours through Steam Cloud. This mirrors controller_profiles.py for
    regular Steam games.
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
    try:
        from controller_profiles import _primary_configset_name
        canonical_vdf, configset_name = _primary_configset_name()
    except Exception:
        _log.debug("primary configset lookup failed", exc_info=True)
        canonical_vdf, configset_name = ("controller_neptune.vdf",
                                         "configset_controller_neptune.vdf")

    cfg_dir = os.path.join(steam_cfg_root, appid_str)
    os.makedirs(cfg_dir, exist_ok=True)
    shutil.copy2(src_template, os.path.join(cfg_dir, canonical_vdf))
    
    # Patch the primary configset
    configset_path = os.path.join(steam_cfg_root, configset_name)
    _patch_configset(configset_path, appid_str, template_filename)
    # Game Mode resolves shortcuts by their title key, not the appid
    if title:
        _patch_configset(configset_path, _shortcut_title_key(title), template_filename)
    
    # Serial configset survives a Cloud sync from another device
    serial = _get_deck_serial()
    if serial:
        configset_serial = os.path.join(steam_cfg_root, f"configset_{serial}.vdf")
        _patch_configset(configset_serial, appid_str, template_filename)
        if title:
            _patch_configset(configset_serial, _shortcut_title_key(title), template_filename)
    
    prog(f"    ✓ Controller: {template_filename}")

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
# Entry splitting goes through _split_entries (\x00\d+\x00 boundaries), shared
# with remove_shortcut and cleanup_orphan_shortcuts.

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

    entries = _split_entries(raw_body)
    if not entries:
        return raw_body, set()

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

    return _reindex(kept), stripped


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
    prog = on_progress or (lambda *a: None)

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

        entry = _shortcut_entry(shortcut_appid, name, exe_path, start_dir, icon_path, launch_options)

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
                                  gyro_mode, prog, name)

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
    prog = on_progress or (lambda *a: None)

    shortcut_appid = _calc_shortcut_appid(exe_path, name)

    uids = _find_all_steam_uids()
    if not uids:
        return

    for uid in uids:
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")

        body = _read_shortcuts_raw(shortcuts_path)
        if not _split_entries(body):
            continue

        new_body, stripped = _strip_entries_by_name(body, {name})
        if stripped:
            try:
                _write_shortcuts_vdf(shortcuts_path, new_body, [])
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
    prog = on_progress or (lambda *a: None)

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

        entries = _split_entries(_read_shortcuts_raw(shortcuts_path))
        if not entries:
            continue

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
            try:
                _write_shortcuts_vdf(shortcuts_path, _reindex(keep), [])
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
    Create non-Steam shortcuts for the Steam games in SHORTCUTS (CoD1, UO,
    CoD2, CoD4 and WaW MP) that are selected and installed, in every Steam
    user account.

    steam_root -- path to Steam root, used to dynamically resolve the game's
                  compatdata prefix (internal or SD card). Falls back to
                  STEAM_ROOT if not provided.
    """
    prog = on_progress or (lambda *a: None)
    
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
                    from steam_common import prelaunch_prefix
                    launch_options = (
                        f'STEAM_COMPAT_DATA_PATH="{compatdata_path}" '
                        f'{prelaunch_prefix("t4mp")}%command% "plutonium://play/t4mp"'
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
            elif key == "cod1mp":
                # CoD1x runs from its 1.1 copy, which must be the working folder
                # (the game loads its paks from there). exe_path stays the stock
                # CoDMP.exe for the appid, so prefix, art and controller keep theirs.
                from cod1x import COPY
                from steam_common import GL_FIX, prelaunch_prefix
                start_dir      = os.path.join(install_dir, COPY)
                actual_exe     = os.path.join(start_dir, "CoDMP.exe")
                launch_options = (f'STEAM_COMPAT_DATA_PATH="{compatdata_path}" '
                                  f'{GL_FIX}{prelaunch_prefix("cod1mp")}%command%')
            elif key == "coduomp" and os.path.isfile(os.path.join(install_dir, "deckops_coduox", "cod1x.dll")):
                # CoDUOx runs from its copy (the Steam folder stays stock), same as CoD1x
                from coduox import COPY
                from steam_common import GL_FIX, prelaunch_prefix
                start_dir      = os.path.join(install_dir, COPY)
                actual_exe     = os.path.join(start_dir, "CoDUOMP.exe")
                launch_options = (f'STEAM_COMPAT_DATA_PATH="{compatdata_path}" '
                                  f'{GL_FIX}{prelaunch_prefix("coduomp")}%command%')
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
                # Steam CoD4 MP is played through this shortcut, not appid
                # 7940, so CoD4R's pre-launch update has to hook in here.
                pre = ""
                if key == "cod4mp":
                    import config as _cfg
                    if _cfg.get_setup_games().get("cod4mp", {}).get("client") == "cod4r":
                        from steam_common import prelaunch_prefix
                        pre = prelaunch_prefix("cod4mp")
                elif key == "cod2mp":
                    # CoD2x update + the Steam CD key into the prefix, before Wine starts
                    from steam_common import prelaunch_prefix
                    pre = prelaunch_prefix("cod2mp")
                from steam_common import GL_FIX, GL_FIX_KEYS
                if key in GL_FIX_KEYS:
                    pre = GL_FIX + pre
                launch_options = f'STEAM_COMPAT_DATA_PATH="{compatdata_path}" {pre}%command%'

            shortcut_appid = _calc_shortcut_appid(exe_path, name)

            prog(f"  → {name}")
            prog(f"    appid: {shortcut_appid}")

            if name in existing_names:
                prog(f"    ✓ Shortcut exists")
            else:
                icon_path = os.path.join(grid_dir, f"{shortcut_appid}_icon.{shortcut_def['icon_ext']}")

                entry = _shortcut_entry(shortcut_appid, name, f'"{actual_exe}"', f'"{start_dir}"',
                                        icon_path, launch_options, last_play=int(time.time()))

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
                    prog(f"    ✓ Cleared compat tool (LCD HGL shortcut)")
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
            # CoD4R has native controller support -- use standard gamepad layout
            _ctrl_def = shortcut_def
            if key == "cod4mp":
                import config as _cfg_ctrl
                _ctrl_def = dict(shortcut_def)
                _ctrl_def["template_type"] = _cfg_ctrl.get_cod4mp_profile_type(
                    shortcut_def["template_type"])
            _assign_controller_config(uid, shortcut_appid, _ctrl_def, gyro_mode, prog, name)
        
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

    prog = on_progress or (lambda *a: None)

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


# Mod clients whose exe replaces the game's in own shortcuts; the appid CRC hashes this exe.
_OWN_MOD_EXES = {"iw4mp": "iw4x.exe", "cod4sp": "iw3sp_mod.exe", "t7x": "t7x.exe",
                 "iw6mp": "iw6-mod.exe", "iw6sp": "iw6-mod.exe", "s1mp": "s1-mod.exe", "s1sp": "s1-mod.exe"}


def own_shortcut_exe(key: str, game: dict) -> str:
    mod, d = _OWN_MOD_EXES.get(key), game.get("install_dir")
    if key == "cod1mp" and d:
        # CoD1x: in the game folder (1.1 disc copy) or in the 1.1 copy (1.5)
        from cod1x import client_dir
        return os.path.join(client_dir(d), "CoDMP.exe")
    return os.path.join(d, mod) if mod and d else game.get("exe_path", "")


def own_plut_prefix(key: str, game: dict) -> str:
    """Prefix for an own-copy Plutonium game. WaW is one game, so t4mp uses
    the t4sp prefix, same as Steam WaW sharing 10090: one Plutonium copy,
    one storage/t4 (stats, mods) for SP, ZM and MP. The MP shortcut keeps
    its own appid and points here through STEAM_COMPAT_DATA_PATH."""
    if key == "t4mp":
        from detect_games import GAMES
        key = "t4sp"
        exe = os.path.join(game["install_dir"], GAMES["t4sp"]["exe"])
    else:
        exe = game["exe_path"]
    appid = _calc_shortcut_appid(f'"{exe}"', OWN_SHORTCUTS[key]["name"])
    return os.path.join(COMPAT_ROOT, str(appid))


def _migrate_waw_mp_prefix(old_compat: str, new_compat: str, prog):
    """Copy WaW MP stats and mods from the old separate MP prefix into the
    shared WaW prefix. Copy only, newer file wins; the old prefix is left
    untouched so nothing can be lost."""
    rel = os.path.join("pfx", "drive_c", "users", "steamuser", "AppData",
                       "Local", "Plutonium", "storage", "t4")
    copied = 0
    for part in ("players", "mods"):
        src_root = os.path.join(old_compat, rel, part)
        for dirpath, _, files in os.walk(src_root):
            for f in files:
                src = os.path.join(dirpath, f)
                dst = os.path.join(new_compat, rel, part, os.path.relpath(src, src_root))
                try:
                    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
                        continue
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    copied += 1
                except OSError as ex:
                    _log.warning("WaW MP migrate: %s: %s", src, ex)
                    prog(f"  ⚠ Could not copy {src}: {ex}")
    if copied:
        prog(f"  WaW MP now shares the WaW prefix: copied {copied} stats/mod file(s).")
        prog(f"  Old MP prefix kept at {old_compat}; delete it to free space.")


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
    prog = on_progress or (lambda *a: None)

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

        # Own games get a CRC-based prefix keyed on the shortcut appid,
        # except WaW MP which shares the WaW SP prefix (see own_plut_prefix).
        compatdata_path = os.path.join(COMPAT_ROOT, str(shortcut_appid))
        if key == "t4mp":
            import config as _cfg
            compatdata_path = own_plut_prefix(key, game)
            if not _cfg.is_lcd():
                _migrate_waw_mp_prefix(
                    os.path.join(COMPAT_ROOT, str(shortcut_appid)), compatdata_path, prog)

        # Enrich the game dict so downstream code has the appid and paths
        game["shortcut_appid"]  = shortcut_appid
        game["compatdata_path"] = compatdata_path
        game["source"]          = "own"
        game["current_name"]    = name

        # ── Resolve the actual exe and launch options per client type ──
        actual_exe = own_shortcut_exe(key, game)
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
            from steam_common import prelaunch_prefix
            launch_options = (
                f'STEAM_COMPAT_DATA_PATH="{compatdata_path}" '
                f'{prelaunch_prefix(key)}%command% "plutonium://play/{key}"'
            )

        elif key == "iw4mp":
            # Run the launcher first so own installs self-update like Steam
            # copies; --arch x86 skips its x86/x64 picker.
            launch_options = "bash -c 'exec \"${@/iw4x.exe/iw4x-launcher.exe}\" --arch x86' -- %command%"

        elif key in ("iw4sp", "iw5sp", "cod1sp", "coduosp", "cod2sp"):
            # Same exe keeps the appid stable; IW-Pad's launcher picks the AlterWare client.
            from sp_mod import build_sp_launch_option
            launch_options = build_sp_launch_option(key)

        elif key == "cod1mp":
            from steam_common import GL_FIX, prelaunch_prefix
            launch_options = GL_FIX + prelaunch_prefix("cod1mp") + "%command%"

        elif key == "coduomp":
            # Pre-launch writes the UO key for CoDUOx (no-op on a stock exe)
            from steam_common import GL_FIX, prelaunch_prefix
            launch_options = GL_FIX + prelaunch_prefix("coduomp") + "%command%"

        elif key == "cod2mp":
            from steam_common import prelaunch_prefix
            launch_options = prelaunch_prefix("cod2mp") + "%command%"

        elif key == "cod3":
            # Prelaunch updates the exe with a verified download. The exe's own
            # updater would replace it unverified at every start.
            from steam_common import prelaunch_prefix
            launch_options = f"COD3_NOUPDATE=1 {prelaunch_prefix(key)}%command%"

        elif key == "bro":
            # Prelaunch updates the engine from its newest release
            from steam_common import prelaunch_prefix
            launch_options = f"{prelaunch_prefix(key)}%command% --fullscreen"

        elif key == "t6sp":
            # Same swap as the Steam copy: stock t6sp.exe keeps the appid stable
            from t6sp_mod import LAUNCH_OPTS
            launch_options = LAUNCH_OPTS

        elif key == "t7":
            launch_options = 'WINEDLLOVERRIDES="d3d11=n,b" %command%'

        elif key in ("iw6mp", "s1mp"):
            launch_options = "-multiplayer"

        elif key in ("iw6sp", "s1sp"):
            launch_options = "-singleplayer"

        else:
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
    prog = on_progress or (lambda *a: None)

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

    if "t6sp" in to_create:
        _drop_old_t6sp_appid(to_create["t6sp"][1], prog)

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

            # CoD1x loads its paks from its working folder, the 1.1 copy
            start = os.path.dirname(actual_exe) if key == "cod1mp" else install_dir
            entry = _shortcut_entry(shortcut_appid, name, f'"{actual_exe}"', f'"{start}"', icon_path, launch_options)

            entry_bytes = _make_shortcut_entry(next_idx, entry)
            new_entries.append(entry_bytes)
            next_idx += 1
            prog(f"    ✓ Shortcut created")

            # Download artwork
            _download_artwork(grid_dir, shortcut_appid, shortcut_def, prog,
                              force=True, clean_stale=True)

            # Assign controller config
            # CoD4R has native controller support -- use standard gamepad layout
            _ctrl_def = shortcut_def
            if key == "cod4mp":
                import config as _cfg_ctrl
                _ctrl_def = dict(shortcut_def)
                _ctrl_def["template_type"] = _cfg_ctrl.get_cod4mp_profile_type(
                    shortcut_def["template_type"])
            _assign_controller_config(uid, shortcut_appid, _ctrl_def, gyro_mode, prog, name)

            # Set GE-Proton compat tool. The BRO engine is a Linux program, so it gets none.
            try:
                import config as _cfg
                from wrapper import set_compat_tool
                ge_version = _cfg.get_ge_proton_version()
                if key == "bro":
                    _clear_compat_tool(str(shortcut_appid))
                elif ge_version:
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

# Path to the wrapper shell script relative to the DeckOps install directory.
# launcher_offline.sh manages its own Proton prefix, runs DeckOps_Offline.exe,
# reads the intent file, and exec's the per-game LAN wrapper.
_LAUNCHER_SH_REL = os.path.join("assets", "LAN", "launcher_offline.sh")

# Path to the Windows exe — kept for appid migration (old shortcut pointed
# at the exe directly; new shortcut points at the shell script).
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

# Old exe paths used by previous launcher versions. Needed so migration can
# calculate old appids and strip stale artwork / compat tool entries.
_OLD_LAUNCHER_EXE = VENV_PYTHON
_OLD_LAUNCHER_EXE_DIRECT = os.path.join(INSTALL_DIR, _LAUNCHER_EXE_REL)


def launcher_run_url() -> str:
    """Steam URL that starts the Offline launcher shortcut (same appid as create_launcher_shortcut)."""
    appid = _calc_shortcut_appid(f'"{os.path.join(INSTALL_DIR, _LAUNCHER_SH_REL)}"', LAUNCHER_TITLE)
    return f"steam://rungameid/{(appid << 32) | 0x02000000}"


def get_launcher_plut_dir() -> str:
    """
    Return the Plutonium directory inside the launcher's Wine prefix.

    launcher_offline.sh uses a fixed prefix at ~/.local/share/deckops/
    launcher_prefix/ (not the Steam shortcut compatdata). Inside Wine,
    LOCALAPPDATA resolves to this prefix's AppData/Local, so Plutonium
    lives here.
    """
    return os.path.join(
        os.path.expanduser("~/.local/share/deckops/launcher_prefix"),
        "pfx", "drive_c", "users", "steamuser",
        "AppData", "Local", "Plutonium",
    )


def _launcher_launch_opts(shortcut_appid: int) -> str:
    """
    Return launch options for the offline launcher shortcut.

    The shell script handles PROTON_NO_FSYNC/ESYNC internally,
    so no env vars needed in Steam launch options.
    """
    return ""


def repair_launcher_files(prog=lambda m: None):
    """Re-download the Offline launcher's files that differ from the user's DeckOps
    version on GitHub. An update only fetches files changed since the last one, so a
    copy cut off by a dropped download stays broken until a reinstall."""
    import json, urllib.request
    from identity import GITHUB_USER, GITHUB_REPO
    from steam_common import git_blob_sha
    try:
        with open(os.path.join(INSTALL_DIR, "VERSION")) as f:
            ref = f.read().strip() or "main"
    except OSError:
        ref = "main"
    api = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/assets/LAN?ref={ref}"
    try:
        with urllib.request.urlopen(urllib.request.Request(api, headers={"User-Agent": "DeckOps"}), timeout=15) as r:
            want = {e["name"]: e["sha"] for e in json.load(r) if e.get("type") == "file"}
    except Exception as ex:
        prog(f"  ⚠ Could not check the launcher files: {ex}")
        return
    for name in ("DeckOps_Offline.exe", "launcher_offline.sh", "lan_server.sh"):
        path = os.path.join(INSTALL_DIR, "assets", "LAN", name)
        if name not in want or (os.path.isfile(path) and git_blob_sha(path) == want[name]):
            continue
        prog(f"  Downloading {name}...")
        new = path + ".new"
        download(f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{ref}/assets/LAN/{name}",
                 new, headers={"User-Agent": "DeckOps"})
        if git_blob_sha(new) != want[name]:
            os.remove(new)
            raise IOError(f"{name} download does not match GitHub")
        if name.endswith(".sh"):
            os.chmod(new, 0o755)
        os.replace(new, path)
        prog(f"  ✓ {name} replaced")


def create_launcher_shortcut(on_progress=None):
    """
    Create a non-Steam shortcut for the DeckOps Plutonium Offline Launcher.

    The shortcut runs launcher_offline.sh, which manages its own Proton
    prefix, launches DeckOps_Offline.exe for the game picker UI, reads the
    intent file when the exe exits, and exec's the per-game LAN wrapper
    in the correct per-game Proton prefix.

    No compat tool is set — the shell script invokes Proton directly.
    Called once after Plutonium games are set up — both OLED and LCD.
    """
    prog = on_progress or (lambda *a: None)

    launcher_sh = os.path.join(INSTALL_DIR, _LAUNCHER_SH_REL)
    launcher_exe = os.path.join(INSTALL_DIR, _LAUNCHER_EXE_REL)

    if not os.path.exists(launcher_sh):
        prog(f"  Launcher script not found: {launcher_sh}")
        return

    if not os.path.exists(launcher_exe):
        prog(f"  Launcher exe not found: {launcher_exe}")
        return

    exe_path  = f'"{launcher_sh}"'
    start_dir = f'"{os.path.dirname(launcher_sh)}"'

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
        _stale_appids = set()

        # 1) Very old name: "DeckOps: Plutonium Launcher"
        _OLD_LAUNCHER_TITLE = "DeckOps: Plutonium Launcher"
        if _OLD_LAUNCHER_TITLE in existing_names:
            _stale_names.add(_OLD_LAUNCHER_TITLE)

        # 2) Old python3-based exe path
        _old_py_exe = f'"{_OLD_LAUNCHER_EXE}"'
        _old_py_appid = _calc_shortcut_appid(_old_py_exe, LAUNCHER_TITLE)
        if _old_py_appid != shortcut_appid:
            _stale_appids.add(_old_py_appid)

        # 3) Old exe-direct path (DeckOps_Offline.exe without wrapper script)
        _old_exe_direct = f'"{_OLD_LAUNCHER_EXE_DIRECT}"'
        _old_exe_appid = _calc_shortcut_appid(_old_exe_direct, LAUNCHER_TITLE)
        if _old_exe_appid != shortcut_appid:
            _stale_appids.add(_old_exe_appid)

        # If the current title exists but under an old appid, strip it
        # so the new entry (with the shell script path) can be written fresh.
        if _stale_appids and LAUNCHER_TITLE in existing_names:
            _stale_names.add(LAUNCHER_TITLE)

        if _stale_names:
            existing_raw, _stripped = _strip_entries_by_name(
                existing_raw, _stale_names
            )
            if _stripped:
                for _sn in _stripped:
                    prog(f"  Removed stale launcher shortcut: {_sn}")
            existing_names = [n for n in existing_names if n not in _stale_names]

            # Clean up artwork and compat tool entries for old appids
            for _old_appid in _stale_appids:
                try:
                    import glob as _glob
                    for _f in _glob.glob(os.path.join(grid_dir, f"{_old_appid}*")):
                        try:
                            os.remove(_f)
                        except OSError:
                            _log.debug("file removal failed", exc_info=True)
                    prog(f"  Cleaned old launcher artwork (appid {_old_appid})")
                except Exception:
                    _log.debug("file removal failed", exc_info=True)

                try:
                    _clear_compat_tool(str(_old_appid))
                    prog(f"  Cleared old compat tool entry (appid {_old_appid})")
                except Exception:
                    _log.debug("operation failed", exc_info=True)

        next_idx = _get_next_index(existing_raw)

        icon_path = os.path.join(
            grid_dir, f"{shortcut_appid}_icon.{LAUNCHER_ART['icon_ext']}"
        )

        if LAUNCHER_TITLE in existing_names:
            prog(f"  Launcher shortcut already exists")
        else:
            entry = _shortcut_entry(shortcut_appid, LAUNCHER_TITLE, exe_path, start_dir, icon_path, _launcher_launch_opts(shortcut_appid))

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
                                  _gyro, prog, LAUNCHER_TITLE)

        # No compat tool needed — launcher_offline.sh invokes Proton directly.
        # Clear any stale compat tool entry from previous exe-based shortcut
        # that may have been set for the new appid by a partial migration.
        try:
            from wrapper import clear_compat_tool
            clear_compat_tool([str(shortcut_appid)])
        except Exception:
            _log.debug("operation failed", exc_info=True)

    prog(f"  Launcher shortcut appid: {shortcut_appid}")


def remove_launcher_shortcut(on_progress=None):
    """Offline Mode removed: take the offline launcher shortcut and its artwork out."""
    exe_path = f'"{os.path.join(INSTALL_DIR, _LAUNCHER_SH_REL)}"'
    remove_shortcut(LAUNCHER_TITLE, exe_path, LAUNCHER_ART, on_progress=on_progress)


# --- Repair: re-add any DeckOps shortcut missing from shortcuts.vdf
# Steam must already be closed; it rewrites shortcuts.vdf on exit.

def _old_t6sp_appid(game: dict) -> int:
    # Own BO2 SP shortcuts used to target T6SP-Mod.exe directly
    return _calc_shortcut_appid(f'"{os.path.join(game["install_dir"], "T6SP-Mod.exe")}"',
                                OWN_SHORTCUTS["t6sp"]["name"])


def _drop_old_t6sp_appid(game: dict, prog):
    """Before the BO2 SP shortcut is rewritten: if it is still on the old
    T6SP-Mod.exe appid, remove that appid's artwork and compat tool entry.
    The old prefix stays (it may hold saves)."""
    import glob
    old = _old_t6sp_appid(game)
    if get_shortcut_appid(OWN_SHORTCUTS["t6sp"]["name"]) != old:
        return
    for uid in _find_all_steam_uids():
        for f in glob.glob(os.path.join(USERDATA_DIR, uid, "config", "grid", f"{old}*")):
            try:
                os.remove(f)
            except OSError:
                _log.debug("file removal failed", exc_info=True)
    try:
        _clear_compat_tool(str(old))
    except Exception:
        _log.debug("compat tool clear failed", exc_info=True)
    prog(f"  Old BO2 Singleplayer shortcut (appid {old}) cleaned up; its prefix is kept at "
         f"{os.path.join(COMPAT_ROOT, str(old))}")


def migrate_own_t6sp(game: dict, on_progress=None) -> bool:
    """Move an own BO2 SP shortcut that still targets T6SP-Mod.exe to t6sp.exe +
    the swap launch option (write_own_shortcuts cleans up the old appid).
    Steam must be closed."""
    import config as cfg
    if get_shortcut_appid(OWN_SHORTCUTS["t6sp"]["name"]) != _old_t6sp_appid(game):
        return False
    (on_progress or (lambda *a: None))("Moving the BO2 Singleplayer shortcut to t6sp.exe...")
    own = enrich_own_games({"t6sp": game}, ["t6sp"], on_progress)
    write_own_shortcuts(own, ["t6sp"], cfg.get_gyro_mode() or "on", on_progress)
    return True


def repair_shortcuts(steam_root: str = None, on_progress=None) -> list:
    """Re-add shortcuts for set-up games that are missing for any Steam
    user, and move an old own BO2 SP shortcut to t6sp.exe. Returns the
    names that were re-added or moved."""
    import config as cfg
    from detect_games import parse_library_folders, find_installed_games, find_own_installed

    prog = on_progress or (lambda *a: None)

    sr = steam_root or STEAM_ROOT
    setup = cfg.get_setup_games()
    lcd = cfg.is_lcd()
    from plutonium_lcd import HEROIC_PLUT_GAMES

    # key -> (kind, name). kind picks the writer below.
    expected = {}
    for key, entry in setup.items():
        src = entry.get("source", "steam")
        if src == "steam" and key in SHORTCUTS and key != "t7x":
            expected[key] = ("steam", SHORTCUTS[key]["name"])
        elif src == "own" and lcd and key in HEROIC_PLUT_GAMES:
            expected[key] = ("heroic", HEROIC_PLUT_GAMES[key]["title"])
        elif src == "own" and key in OWN_SHORTCUTS:
            expected[key] = ("own", OWN_SHORTCUTS[key]["name"])
    # The offline launcher exists only with Offline Mode added
    has_plut = cfg.get_offline_mode() and any(e.get("client") == "plutonium" for e in setup.values())

    uids = _find_all_steam_uids()
    if not uids:
        prog("⚠ No Steam user accounts found.")
        return []

    readded = []
    if setup.get("t6sp", {}).get("source") == "own":
        g = find_own_installed().get("t6sp")
        if g and migrate_own_t6sp(g, on_progress):
            readded.append(OWN_SHORTCUTS["t6sp"]["name"])

    present = None
    for uid in uids:
        names = set(_read_existing_shortcuts(
            os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")))
        present = names if present is None else present & names

    missing = {k: v for k, v in expected.items() if v[1] not in present}
    launcher_missing = has_plut and LAUNCHER_TITLE not in present
    total = len(expected) + (1 if has_plut else 0)

    if not missing and not launcher_missing:
        prog(f"All DeckOps shortcuts present ({total}).")
        return readded

    gyro = cfg.get_gyro_mode() or "on"
    by_kind = lambda kind: [k for k, (kd, _) in missing.items() if kd == kind]

    steam_keys = by_kind("steam")
    if steam_keys:
        steam_games = find_installed_games(parse_library_folders(sr), sr)
        found = [k for k in steam_keys if k in steam_games]
        for k in set(steam_keys) - set(found):
            prog(f"  ⚠ {missing[k][1]}: game not found in Steam, skipped")
        if found:
            create_shortcuts(steam_games, found, gyro, on_progress, steam_root=sr)
            readded += [missing[k][1] for k in found]

    own_keys = by_kind("own")
    if own_keys:
        own_games = find_own_installed()
        found = [k for k in own_keys if k in own_games]
        for k in set(own_keys) - set(found):
            prog(f"  ⚠ {missing[k][1]}: game folder not found, skipped")
        if found:
            own_games = enrich_own_games(own_games, found, on_progress)
            write_own_shortcuts(own_games, found, gyro, on_progress)
            readded += [missing[k][1] for k in found]

    heroic_keys = by_kind("heroic")
    if heroic_keys:
        from plutonium_lcd import _create_heroic_steam_shortcut
        for k in heroic_keys:
            _create_heroic_steam_shortcut(k, on_progress=on_progress, source="own")
            readded.append(missing[k][1])

    if launcher_missing:
        create_launcher_shortcut(on_progress=on_progress)
        readded.append(LAUNCHER_TITLE)

    return readded


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
