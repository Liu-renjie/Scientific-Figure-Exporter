"""Build a deterministic, allowlisted install ZIP using Python 3 standard library.

This is a release tool, not an Abaqus runtime dependency. Run from any folder:
    python scripts/build_release.py --output-dir dist
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = (
    "scientificFigureExporter_plugin.py",
    "scientificFigureExporter_form.py",
    "scientificFigureExporter_kernel.py",
    "scientificFigureExporter_state.py",
    "scientificFigureExporter_jpeg.py",
    "colorMaps.py",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args()
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", version):
        raise ValueError("VERSION must be a numeric version without a v prefix")
    if tuple(int(part) for part in version.split(".")) < (0, 2):
        raise ValueError("This workflow must not replace the v0.1 baseline")
    plugin = (ROOT / RUNTIME[0]).read_text(encoding="utf-8")
    if "version='%s'" % version not in plugin:
        raise ValueError("VERSION does not match the plug-in registration version")
    notes = "docs/releases/v%s.md" % version
    files = sorted(set(RUNTIME + (
        "install_plugin.py", "README.md", "CHANGELOG.md", "LICENSE",
        "CONTRIBUTING.md", "VERSION", "docs/README.md",
        "docs/INSTALLATION.md", "docs/ScientificFigureExporter_User_Guide.docx",
        "docs/VALIDATION_V0.2.md", "docs/PERFORMANCE_UPDATE_20261011.md",
        "docs/assets/README.md", "docs/assets/ui_v0.2.png",
        "docs/assets/field_outputs_v0.2.png",
        "docs/assets/contour_style_reference.png",
        "docs/assets/contour_style_reference1.png", notes,
        "diagnostics/components_regression.py",
        "diagnostics/performance_components.py", "scripts/build_release.py",
    )))
    for name in files:
        if not (ROOT / name).is_file():
            raise FileNotFoundError("Missing release file: %s" % name)
    for name in RUNTIME + ("install_plugin.py",):
        ast.parse((ROOT / name).read_bytes(), filename=name)
    # Standard-library installer smoke test in a disposable, isolated target.
    with tempfile.TemporaryDirectory(prefix="sfe-install-check-") as directory:
        subprocess.run([sys.executable, str(ROOT / "install_plugin.py"), directory],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for name in RUNTIME:
            if (Path(directory) / name).read_bytes() != (ROOT / name).read_bytes():
                raise AssertionError("Installer changed runtime bytes: %s" % name)
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ("Scientific-Figure-Exporter-V%s.zip" % version)
    prefix = "Scientific-Figure-Exporter-V%s/" % version
    manifest = {"version": version, "tag": "v%s" % version, "files": {}}
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as bundle:
        for name in files:
            payload = (ROOT / name).read_bytes()
            manifest["files"][name] = hashlib.sha256(payload).hexdigest()
            info = zipfile.ZipInfo(prefix + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, payload)
        info = zipfile.ZipInfo(prefix + "RELEASE_MANIFEST.json",
                               date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        bundle.writestr(info, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise AssertionError("ZIP integrity check failed")
        if len(bundle.namelist()) != len(files) + 1:
            raise AssertionError("Unexpected package entry count")
    guide = output / "ScientificFigureExporter_User_Guide.docx"
    shutil.copyfile(ROOT / "docs/ScientificFigureExporter_User_Guide.docx", guide)
    checksums = []
    for path in (archive, guide):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksums.append("%s  %s\n" % (digest, path.name))
    (output / "SHA256SUMS.txt").write_text("".join(checksums), encoding="ascii")
    print("Built V%s: %d allowlisted files + manifest" % (version, len(files)))
    print("Installer smoke test and ZIP integrity: PASS")
    print("".join(checksums), end="")


if __name__ == "__main__":
    main()
