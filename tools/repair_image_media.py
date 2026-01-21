import sqlite3
import subprocess
import time
import uuid
from pathlib import Path


def main() -> int:
    base_dir = Path(".").resolve()
    db_path = base_dir / "data/led.db"
    if not db_path.exists():
        print(f"db not found: {db_path}")
        return 1

    image_exts = {".jpg", ".jpeg", ".png", ".pngg", ".gif", ".bmp", ".webp"}
    image_dir = base_dir / "resources/media/image"
    image_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("select id, name, type, path from media").fetchall()

    fixed = []
    skipped = []
    for r in rows:
        name = r["name"] or ""
        name_ext = Path(name).suffix.lower()
        if name_ext not in image_exts:
            continue

        src = Path(r["path"])
        if not src.exists():
            skipped.append((r["id"], "missing_file", str(src)))
            continue

        src_ext = src.suffix.lower()
        if src_ext in image_exts:
            if src_ext == ".pngg":
                dst = src.with_suffix(".png")
                try:
                    src.rename(dst)
                    src = dst
                except Exception:
                    pass
            conn.execute("update media set type=?, path=? where id=?", ("image", str(src), r["id"]))
            fixed.append((r["id"], "image", str(src)))
            continue

        if src_ext == ".mp4":
            out = image_dir / f"{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
            p = subprocess.run(
                ["ffmpeg", "-y", "-i", str(src), "-frames:v", "1", str(out)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if p.returncode == 0 and out.exists() and out.stat().st_size > 0:
                conn.execute("update media set type=?, path=? where id=?", ("image", str(out), r["id"]))
                fixed.append((r["id"], "image", str(out)))
            else:
                skipped.append((r["id"], "extract_failed", str(src)))
            continue

        skipped.append((r["id"], "unsupported_source_ext", str(src)))

    conn.commit()
    conn.close()

    print("fixed", len(fixed))
    for item in fixed:
        print(item)
    if skipped:
        print("skipped", len(skipped))
        for item in skipped:
            print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

