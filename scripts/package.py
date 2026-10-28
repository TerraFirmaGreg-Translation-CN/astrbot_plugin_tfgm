"""Build an installable archive from the current source tree, including local edits."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "main.py",
    "metadata.yaml",
    "requirements.txt",
    "_conf_schema.json",
    "README.md",
    "LICENSE",
]
FILES += [str(p.relative_to(ROOT)) for p in sorted((ROOT / "bridge").glob("*.py"))]
FILES += [str(p.relative_to(ROOT)) for p in sorted((ROOT / "docs").glob("*.md"))]
output = ROOT / "dist" / "astrbot_plugin_tfgm.zip"
output.parent.mkdir(exist_ok=True)
with ZipFile(output, "w", ZIP_DEFLATED) as archive:
    for name in FILES:
        archive.write(ROOT / name, "astrbot_plugin_tfgm/" + name)
with ZipFile(output) as archive:
    assert archive.testzip() is None
    assert "astrbot_plugin_tfgm/_conf_schema.json" in archive.namelist()
print(output)
