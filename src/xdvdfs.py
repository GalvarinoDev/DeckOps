"""
xdvdfs.py: read-only reader for Xbox and Xbox 360 disc images (XDVDFS)

It reads only the file table (a few sectors), so a scan can tell which game
an image holds without unpacking it. It works on stripped images (XISO) and on
full dumps, whose game partition starts at a fixed offset for each disc type.
"""

import struct

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"
# XISO, then full dumps: XGD1 (Xbox), XGD2 and XGD3 (Xbox 360)
BASES = (0, 0x18300000, 0xFD90000, 0x2080000)


def _base(f):
    for b in BASES:
        f.seek(b + 32 * SECTOR)
        if f.read(len(MAGIC)) == MAGIC:
            return b
    return None


def _entries(f, base, sector, size):
    """(name, start sector, size, is_dir) of one folder's table."""
    if not 0 < size <= 1 << 24:
        return
    f.seek(base + sector * SECTOR)
    table = f.read(size)
    stack, seen = [0], set()
    # Entries form a binary tree: left and right offsets in 4-byte units
    while stack:
        off = stack.pop()
        if off in seen or off + 14 > len(table):
            continue
        seen.add(off)
        left, right, start, fsize, attr, nlen = struct.unpack_from("<HHIIBB", table, off)
        if left == 0xFFFF or off + 14 + nlen > len(table):
            continue
        if left: stack.append(left * 4)
        if right: stack.append(right * 4)
        yield table[off + 14:off + 14 + nlen].decode("latin-1"), start, fsize, bool(attr & 0x10)


def walk(path: str, recursive: bool = True):
    """[(path inside the image with "/", byte offset, size)] of every file.
    Empty if the file is not an Xbox disc image or cannot be read."""
    out = []
    try:
        with open(path, "rb") as f:
            base = _base(f)
            if base is None:
                return out
            f.seek(base + 32 * SECTOR + 20)
            root = struct.unpack("<II", f.read(8))
            todo, seen = [("", *root)], set()
            while todo:
                prefix, sector, size = todo.pop()
                if sector in seen:
                    continue
                seen.add(sector)
                for name, start, fsize, is_dir in _entries(f, base, sector, size):
                    if is_dir:
                        if recursive:
                            todo.append((prefix + name + "/", start, fsize))
                    else:
                        out.append((prefix + name, base + start * SECTOR, fsize))
    except (OSError, struct.error):
        return []
    return out


def root_files(path: str) -> dict:
    """{lower-case name: (offset, size)} of the files in the image's root folder."""
    return {n.lower(): (o, s) for n, o, s in walk(path, recursive=False)}


if __name__ == "__main__":
    import os, tempfile

    def image(files, base=0):
        # Root table: each entry links right to the next one
        names = list(files)
        ents, data_sector = b"", 40
        offs = []
        for i, n in enumerate(names):
            offs.append(len(ents))
            e = struct.pack("<HHIIBB", 0, 0, data_sector + i, len(files[n]), 0, len(n)) + n.encode()
            ents += e + b"\0" * (-len(e) % 4)
        ents = bytearray(ents)
        for i in range(len(names) - 1):
            struct.pack_into("<H", ents, offs[i] + 2, offs[i + 1] // 4)
        buf = bytearray(base + (40 + len(names)) * SECTOR)
        buf[base + 32 * SECTOR:base + 32 * SECTOR + 28] = MAGIC + struct.pack("<II", 33, len(ents))
        buf[base + 33 * SECTOR:base + 33 * SECTOR + len(ents)] = ents
        for i, n in enumerate(names):
            p = base + (40 + i) * SECTOR
            buf[p:p + len(files[n])] = files[n]
        return bytes(buf)

    d = tempfile.mkdtemp()
    for base in (0, 0x2080000):
        p = os.path.join(d, f"t{base}.iso")
        open(p, "wb").write(image({"default.xex": b"X" * 300, "Media": b"m"}, base))
        r = root_files(p)
        assert set(r) == {"default.xex", "media"}, r
        off, size = r["default.xex"]
        with open(p, "rb") as f:
            f.seek(off); assert f.read(size) == b"X" * 300
    open(os.path.join(d, "junk.iso"), "wb").write(b"\0" * 100000)
    assert root_files(os.path.join(d, "junk.iso")) == {}
    assert root_files(os.path.join(d, "missing.iso")) == {}
    print("ok")
