"""Restore verified migration images into the persistent media volume."""
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reservastoresupa.core.settings")
import django
django.setup()
from django.conf import settings
from django.db import connection

root = Path(settings.MEDIA_ROOT).resolve()
with connection.cursor() as cursor:
    cursor.execute("SELECT path, content, sha256 FROM reservastore.import_media ORDER BY path")
    rows = cursor.fetchall()
for name, content, digest in rows:
    target = (root / name).resolve()
    if not target.is_relative_to(root) or target.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise RuntimeError("Unsafe imported media path")
    payload = bytes(content)
    if hashlib.sha256(payload).hexdigest() != digest:
        raise RuntimeError("Imported media checksum mismatch")
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError("Existing media differs; refusing overwrite")
        continue
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(payload)
print(f"Verified {len(rows)} imported media files.", flush=True)
