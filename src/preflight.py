"""
preflight.py - checks to run before a long install starts

The depot downgrade checks disk space itself, but only after Steam has
been killed and the install is underway. These checks run first, while
backing out still costs nothing.

Only sizes DeckOps already knows are checked: the depot downgrade
headroom, the IW4x DLC pack and the Zombies Declassified pack. The
clients themselves get no estimate on purpose. Refusing an install over
a guessed number is worse than not checking.
"""

import os
import socket
from collections import namedtuple

from log import get_logger

_log = get_logger(__name__)

Check = namedtuple("Check", "level title detail")
OK, WARN, BLOCK = "ok", "warn", "block"

# Copy of _DG_KEY_MAP in ui_install._run_inner, kept here so preflight
# stays a leaf module. Update both if the depot game list changes.
DOWNGRADE_KEYS = {"iw5mp", "iw5mp_ds", "iw5sp", "iw6mp", "iw6sp", "s1mp", "s1sp"}


def free_gb(path: str) -> float:
    try:
        st = os.statvfs(path)
        return (st.f_bavail * st.f_frsize) / (1024 ** 3)
    except OSError:
        return 0.0


def _probe(path: str):
    """Filesystem id and a usable path, walking up to the nearest one that exists."""
    p = os.path.abspath(path)
    while p and not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    try:
        return os.stat(p).st_dev, p
    except OSError:
        return None, p


def _on_ac() -> bool:
    """True when any mains or USB supply reports online. If sysfs lists none, assume plugged in."""
    base = "/sys/class/power_supply"
    seen = False
    try:
        names = os.listdir(base)
    except OSError:
        return True
    for n in names:
        d = os.path.join(base, n)
        try:
            with open(os.path.join(d, "type")) as f:
                if f.read().strip() not in ("Mains", "USB"):
                    continue
            with open(os.path.join(d, "online")) as f:
                seen = True
                if f.read().strip() == "1":
                    return True
        except OSError:
            continue
    return not seen


def _online() -> bool:
    try:
        socket.create_connection(("api.github.com", 443), timeout=5).close()
        return True
    except OSError:
        return False


def check(selected, iw4x_dlc=False, zd=False, downgrade_keys=()):
    """
    Run the pre-install checks.

    selected:       list of (key, client, install_dir)
    downgrade_keys: selected keys that will need a depot downgrade
    Returns a list of Check(level, title, detail). Empty means nothing to say.
    """
    from depot_downgrade import REQUIRED_FREE_SPACE_GB
    from iw4x import DLC_SIZE_GB
    from zombies_declassified import PACK_SIZE_GB

    need = {}   # device -> [gb wanted, representative path]

    def add(path, gb):
        if not path:
            return
        dev, probe = _probe(path)
        entry = need.setdefault(dev, [0.0, probe])
        entry[0] += gb

    dg = {k for k in downgrade_keys if k in DOWNGRADE_KEYS}
    dg_devs = set()
    for key, client, install_dir in selected:
        # The downgrade stages a second copy beside the game it belongs to.
        if key in dg and install_dir:
            dev = _probe(install_dir)[0]
            if dev not in dg_devs:
                dg_devs.add(dev)
                add(install_dir, REQUIRED_FREE_SPACE_GB)
        if client == "iw4x" and iw4x_dlc:
            add(install_dir, DLC_SIZE_GB)
    if zd:
        add(os.path.expanduser("~"), PACK_SIZE_GB)

    out = []
    for want, path in sorted(need.values(), key=lambda e: e[1]):
        have = free_gb(path)
        detail = f"{path}: {have:.1f} GB free, {want:.0f} GB needed"
        if have < want:
            out.append(Check(BLOCK, "Not enough disk space", detail))
        else:
            out.append(Check(OK, "Disk space", detail))

    if dg:
        out.append(Check(WARN, "This will take a long time",
                         "Downgrading game files can run for hours. Keep the "
                         "device plugged in and somewhere it can stay cool."))

    if not _on_ac():
        out.append(Check(WARN, "On battery",
                         "Plug the device in. Installs can run for hours."))
    if not _online():
        out.append(Check(WARN, "No internet connection",
                         "Downloads will fail. Connect to Wi-Fi first."))
    return out


def worst(checks):
    for level in (BLOCK, WARN):
        if any(c.level == level for c in checks):
            return level
    return OK
