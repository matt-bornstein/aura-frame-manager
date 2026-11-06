"""
Find duplicate and near-duplicate images in a folder using imagededup's PHash.

For each group of duplicates the best copy is kept (highest resolution, then
JPEG over HEIC, then largest file) and the rest are moved into a `_dupes/`
subfolder alongside a `report.json`.

Usage:
    uv run python dedupe_images.py images/deduped [--threshold 4] [--dry-run]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, List, Tuple

import numpy as np
from imagededup.methods import PHash
from PIL import Image, ImageOps

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".heic"}
DUPES_DIRNAME = "_dupes"


def heic_pixel_count(path: str) -> int:
    out = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", path],
        capture_output=True, text=True, check=True,
    ).stdout
    dims = dict(re.findall(r"(pixelWidth|pixelHeight): (\d+)", out))
    return int(dims["pixelWidth"]) * int(dims["pixelHeight"])


def load_for_hashing(path: str) -> Tuple[np.ndarray, int]:
    """Return a downscaled RGB array of the image and its full pixel count."""
    if os.path.splitext(path)[1].lower() == ".heic":
        # Pillow can't read HEIC, so decode it with macOS's built-in sips.
        pixels = heic_pixel_count(path)
        with tempfile.TemporaryDirectory() as tmp:
            jpg = os.path.join(tmp, "image.jpg")
            subprocess.run(
                ["sips", "-s", "format", "jpeg", "-Z", "512", path, "--out", jpg],
                capture_output=True, check=True,
            )
            with Image.open(jpg) as img:
                return np.array(ImageOps.exif_transpose(img).convert("RGB")), pixels

    with Image.open(path) as img:
        pixels = img.width * img.height
        img.draft("RGB", (512, 512))
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((512, 512))
        return np.array(img), pixels


def group_duplicates(duplicates: Dict[str, List[Tuple[str, int]]]) -> List[List[str]]:
    """Merge pairwise matches into connected groups."""
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for name, matches in duplicates.items():
        for other, _ in matches:
            parent[find(name)] = find(other)

    groups: Dict[str, List[str]] = {}
    for name in parent:
        groups.setdefault(find(name), []).append(name)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def keeper_sort_key(name: str, folder: str, pixels: Dict[str, int]):
    is_jpeg = os.path.splitext(name)[1].lower() in {".jpg", ".jpeg"}
    size = os.path.getsize(os.path.join(folder, name))
    return (-pixels[name], not is_jpeg, -size, name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", help="Folder of images to deduplicate")
    parser.add_argument("--threshold", type=int, default=4,
                        help="Max Hamming distance (0-64) between hashes to count as duplicates (default: 4)")
    parser.add_argument("--dry-run", action="store_true", help="Write the report without moving any files")
    args = parser.parse_args()

    folder = args.folder
    dupes_dir = os.path.join(folder, DUPES_DIRNAME)

    names = sorted(
        n for n in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, n)) and os.path.splitext(n)[1].lower() in IMAGE_EXTENSIONS
    )
    print(f"Hashing {len(names)} images in {folder}...")

    hasher = PHash(verbose=False)
    encodings: Dict[str, str] = {}
    pixels: Dict[str, int] = {}
    unreadable: List[str] = []
    for i, name in enumerate(names, 1):
        try:
            array, pixels[name] = load_for_hashing(os.path.join(folder, name))
            encoding = hasher.encode_image(image_array=array)
        except Exception as e:
            encoding = None
            print(f"  Could not read {name}: {e}")
        if encoding:
            encodings[name] = encoding
        else:
            unreadable.append(name)
        if i % 200 == 0:
            print(f"  {i}/{len(names)}")

    duplicates = hasher.find_duplicates(
        encoding_map=encodings, max_distance_threshold=args.threshold, scores=True
    )
    groups = group_duplicates(duplicates)

    report_groups = []
    moved = 0
    if not args.dry_run and groups:
        os.makedirs(dupes_dir, exist_ok=True)
    for group in groups:
        ordered = sorted(group, key=lambda n: keeper_sort_key(n, folder, pixels))
        keep, extras = ordered[0], ordered[1:]
        distances = {
            other: int(score) for other, score in duplicates.get(keep, []) if other in extras
        }
        report_groups.append({
            "kept": keep,
            "moved": extras,
            "distance_from_kept": distances,
        })
        if not args.dry_run:
            for name in extras:
                shutil.move(os.path.join(folder, name), os.path.join(dupes_dir, name))
                moved += 1

    os.makedirs(dupes_dir, exist_ok=True)
    report_path = os.path.join(dupes_dir, "report.json")
    with open(report_path, "w") as f:
        json.dump({
            "threshold": args.threshold,
            "dry_run": args.dry_run,
            "images_scanned": len(names),
            "unreadable": unreadable,
            "groups": report_groups,
        }, f, indent=2)

    would_move = sum(len(g["moved"]) for g in report_groups)
    print()
    print(f"Images scanned:   {len(names)}")
    print(f"Unreadable:       {len(unreadable)}")
    print(f"Duplicate groups: {len(groups)}")
    if args.dry_run:
        print(f"Would move:       {would_move}")
    else:
        print(f"Moved:            {moved} -> {dupes_dir}")
    print(f"Report:           {report_path}")


if __name__ == "__main__":
    main()
