#!/usr/bin/env python3
"""Download the OULAD dataset from its UCI Machine Learning Repository mirror.

Provenance
----------
OULAD (Open University Learning Analytics Dataset) was created by
Kuzilek, Hlosta & Zdrahal at The Open University / Knowledge Media Institute
and released in December 2015. The canonical request page is
https://analyse.kmi.open.ac.uk/open_dataset (now redirecting to
https://research.stem.open.ac.uk/ouanalyse/), where the download sits
behind a request form.

The UCI Machine Learning Repository hosts the same December-2015 release
as dataset 349, with a DOI, and serves the original zip directly:

    https://archive.ics.uci.edu/static/public/349/open+university+learning+analytics+dataset.zip
    DOI: https://doi.org/10.24432/C5KK69

That zip is what this script downloads. Its SHA-256 (checked 2026-10-27) is
pinned below; the script refuses to proceed if a future download differs,
so a silent upstream change can never slip into the analysis.

Licence: CC BY 4.0 (attribution required). The raw CSVs are ~464 MB
uncompressed (studentVle.csv alone is ~433 MB), so they are NOT committed
to this repository -- run this script instead. See data/README_DATA.md.
"""
import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://archive.ics.uci.edu/static/public/349/open+university+learning+analytics+dataset.zip"
EXPECTED_SHA256 = "f2ed1902616c1fe8d2824d872c0b7d2d72be435bf0124d077044fe4be2c6d3e4"
EXPECTED_FILES = {
    "assessments.csv",
    "courses.csv",
    "studentAssessment.csv",
    "studentInfo.csv",
    "studentRegistration.csv",
    "studentVle.csv",
    "vle.csv",
    "OULAD.names",
}

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_DIR / "oulad_uci.zip"
    if not zip_path.exists():
        print(f"Downloading {URL} ...")
        urllib.request.urlretrieve(URL, zip_path)
    digest = sha256_of(zip_path)
    print(f"SHA-256: {digest}")
    if digest != EXPECTED_SHA256:
        print(
            "ERROR: checksum does not match the pinned UCI release.\n"
            "Do not use this file -- investigate the upstream change first.",
            file=sys.stderr,
        )
        return 1
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        missing = EXPECTED_FILES - names
        if missing:
            print(f"ERROR: zip is missing expected files: {sorted(missing)}", file=sys.stderr)
            return 1
        z.extractall(RAW_DIR)
    zip_path.unlink()
    print(f"Extracted {len(EXPECTED_FILES)} files to {RAW_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
