"""
prelaunch.py: silent mod client update that prelaunch.sh runs before a game

    prelaunch.py <game key> <original launch command...>

Never blocks the launch on failure: prelaunch.sh starts the game no matter
how this exits. Output goes only to install.log and never opens a window.
"""

import json
import os
import sys
import time

from log import setup_logging, get_logger

_log = get_logger("prelaunch")


def _cod4mp(key, cmd):
    exe = next((a for a in cmd if a.lower().endswith("iw3mp.exe")), None)
    if not exe:
        return  # SP launch on the shared 7940 appid
    install_dir = os.path.dirname(exe)
    meta = os.path.join(install_dir, "deckops_cod4r.json")
    if not os.path.isfile(meta):
        return  # CoD4x or vanilla MP
    with open(meta) as f:
        compat = json.load(f)["compatdata_path"]
    from cod4r import sync_files
    # One quick try at the manifest so being offline costs a few seconds.
    sync_files(install_dir, compat, log=lambda m: _log.info(m.strip()), fetch_timeout=5, tries=1)


def _plutonium(key, cmd):
    # OLED only: the online wrapper and own shortcuts export the game's
    # prefix. Offline/LAN launches don't come through here.
    from plutonium import DEDICATED_PREFIX, _plut_dir_in_prefix
    import plutonium_update as pu
    master = _plut_dir_in_prefix(DEDICATED_PREFIX)
    compat = os.environ.get("STEAM_COMPAT_DATA_PATH", "")
    if not os.path.isdir(master) or not compat:
        return
    log = lambda m: _log.info(m)
    info = pu.update(master, log)
    prefix = _plut_dir_in_prefix(compat)
    if os.path.isdir(prefix) and os.path.realpath(prefix) != os.path.realpath(master):
        pu.link_prefix(master, prefix, info, log)


def _iwpad(key, cmd):
    from sp_mod import sp_exe
    exe = sp_exe(key).lower()
    path = next((a for a in cmd if a.lower().endswith(exe)), None)
    if path:
        from sp_mod import update_iw_pad
        update_iw_pad(key, os.path.dirname(path), log=_log.info)


def _cod3(key, cmd):
    exe = next((a for a in cmd if a.lower().endswith("cod3sp_s.exe")), None)
    if exe:
        from cod3recomp import update_cod3
        update_cod3(os.path.dirname(exe), log=_log.info)


def _bro(key, cmd):
    exe = next((a for a in cmd if os.path.basename(a) == "cod_bro"), None)
    if exe:
        from bro import update_bro
        update_bro(os.path.dirname(exe), log=_log.info)


def _cod1x(key, cmd):
    # CoD1x's CoDMP.exe, in the 1.1 copy or a 1.1 disc copy's own folder
    exe = next((a for a in cmd if a.replace("\\", "/").lower().endswith("/codmp.exe")
                and os.path.isfile(os.path.join(os.path.dirname(a), "cod1x.dll"))), None)
    if exe:
        from cod1x import update_cod1x
        update_cod1x(os.path.dirname(exe), log=_log.info)


def _cod2x(key, cmd):
    exe = next((a for a in cmd if a.replace("\\", "/").lower().endswith("/cod2mp_s.exe")), None)
    if exe:
        from cod2x import update_cod2x
        update_cod2x(os.path.dirname(exe), log=_log.info)


def _coduox(key, cmd):
    exe = next((a for a in cmd if a.replace("\\", "/").lower().endswith("/coduomp.exe")), None)
    pfx = os.environ.get("STEAM_COMPAT_DATA_PATH")
    # CoDUOx (cod1x.dll beside the exe): the UO key into the prefix. A stock exe needs nothing
    if exe and pfx and os.path.isfile(os.path.join(os.path.dirname(exe), "cod1x.dll")):
        from coduox import set_key
        set_key(os.path.join(pfx, "pfx"), os.path.dirname(exe),
                os.environ.get("STEAM_COMPAT_CLIENT_INSTALL_PATH"))


def _lan(key, args):
    # Offline launch from lan_server.sh: relink the offline copies, then print the
    # Steam Linux Runtime and the library mounts to stdout for lan_server.sh.
    from plutonium import refresh_lan, lan_runtime
    try:
        refresh_lan(args[0])
    finally:
        print(*lan_runtime(), sep="\t")


_HANDLERS = {"cod4mp": _cod4mp, "lan": _lan, "iw4sp": _iwpad, "iw5sp": _iwpad,
             "cod1sp": _iwpad, "coduosp": _iwpad, "cod2sp": _iwpad, "cod3": _cod3, "bro": _bro,
             "cod1mp": _cod1x, "cod2mp": _cod2x, "coduomp": _coduox}
_HANDLERS.update(dict.fromkeys(
    ("t4sp", "t4mp", "t5sp", "t5mp", "t6mp", "t6zm", "iw5mp", "iw5mp_ds"), _plutonium))


def main(argv):
    if not argv or argv[0] not in _HANDLERS:
        return
    t0 = time.monotonic()
    try:
        _HANDLERS[argv[0]](argv[0], argv[1:])
    except Exception as ex:
        _log.warning("prelaunch %s: update skipped: %s", argv[0], ex)
    _log.info("prelaunch %s: %.1fs", argv[0], time.monotonic() - t0)


if __name__ == "__main__":
    setup_logging()
    main(sys.argv[1:])
