import os
import re
import shutil
import argparse
from pathlib import Path

CONTENT_DIR = Path("content")
IMAGES_DIR = Path("assets/images")
PUBLIC_IMG_PATH = "/images/"
OK = "✅"
ERROR = "❌"
PROCESSING = "🍄"
SCAN = "🔍"
FINISHED = "✨"
SKIP = "⏭️"


def slugify(text):
    """Converts scientific name to slug (lowercase, underscores)."""
    return text.lower().strip().replace(" ", "_")


def get_frontmatter_value(content, key):
    """Extracts a value from YAML frontmatter."""
    match = re.search(rf'^{key}:\s*["\']?(.*?)["\']?\s*$', content, re.MULTILINE)
    return match.group(1) if match else None


def update_backlinks(old_slug, new_slug):
    """Scans all markdown files to update internal hyperlinks."""
    print(f"   {SCAN} Scanning content for links to '{old_slug}'...")
    count = 0

    link_pattern = re.compile(rf'(/svampar/){re.escape(old_slug)}(/|["\)])')

    for path in CONTENT_DIR.rglob("*.md"):
        try:
            original_content = path.read_text(encoding="utf-8")
            if old_slug in original_content:
                # careful replacement
                new_content = link_pattern.sub(rf"\1{new_slug}\2", original_content)

                if original_content != new_content:
                    path.write_text(new_content, encoding="utf-8")
                    print(f"      Updated link in: {path.name}")
                    count += 1
        except Exception as e:
            print(f"      {ERROR} Error reading {path}: {e}")

    if count > 0:
        print(f"   {OK} Updated {count} files with new links.")


def process_mushroom(file_path, bulk_mode=False):
    file_path = Path(file_path)
    if not file_path.exists():
        if not bulk_mode:
            print(f"{ERROR} File not found: {file_path}")
        return

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        if not bulk_mode:
            print(f"{ERROR} Could not read file: {e}")
        return

    scientific_name = get_frontmatter_value(content, "scientificName")
    current_slug = get_frontmatter_value(content, "slug")

    if not current_slug:
        current_slug = file_path.stem

    if not scientific_name:
        if not bulk_mode:
            print(f"{ERROR} No 'scientificName' found in {file_path.name}")
        return

    new_slug = slugify(scientific_name)

    if current_slug == new_slug:
        if not bulk_mode:
            print(f"{OK} {file_path.name} is already named correctly.")
        return

    print(f"{PROCESSING} Processing: {file_path.name}")
    print(f"   Target: {current_slug} -> {new_slug}")

    found_images = list(IMAGES_DIR.glob(f"{current_slug}*"))
    image_map = {}  # old_filename -> new_filename

    if found_images:
        print(f"   Found {len(found_images)} images to rename.")
        for img_path in found_images:
            new_img_name = img_path.name.replace(current_slug, new_slug, 1)
            new_img_path = IMAGES_DIR / new_img_name

            shutil.move(img_path, new_img_path)
            print(f"   Moved image: {img_path.name} -> {new_img_name}")

            image_map[img_path.name] = new_img_name
    else:
        print("   No images found in assets/images matching the slug.")

    lines = content.splitlines()
    new_lines = []
    in_frontmatter = False
    fm_count = 0

    for line in lines:
        if line.strip() == "---":
            fm_count += 1
            in_frontmatter = fm_count == 1

        updated_line = line

        if in_frontmatter:
            if line.startswith("slug:"):
                updated_line = f'slug: "{new_slug}"'

            if "image:" in line or "- url:" in line:
                for old_img, new_img in image_map.items():
                    if old_img in line:
                        updated_line = line.replace(old_img, new_img)
        else:
            for old_img, new_img in image_map.items():
                if old_img in line:
                    updated_line = line.replace(old_img, new_img)

        new_lines.append(updated_line)

    new_content = "\n".join(new_lines) + "\n"

    new_file_path = file_path.parent / f"{new_slug}.md"
    new_file_path.write_text(new_content, encoding="utf-8")
    print(f"   Created new file: {new_file_path.name}")

    os.remove(file_path)
    print("   Removed old file.")

    update_backlinks(current_slug, new_slug)
    print("---------------------------------------------------")


def scan_all_mushrooms():
    print(f"{SCAN} Scanning all files in {CONTENT_DIR}...")
    files = list(CONTENT_DIR.rglob("*.md"))
    print(
        f"{SCAN} Found {len(files)} markdown files. Checking for scientific name mismatches...\n"
    )

    for file_path in files:
        process_mushroom(file_path, bulk_mode=True)

    print(f"\n{FINISHED} Scan complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rename mushroom file and assets based on Scientific Name.",
    )
    # nargs='?' makes the argument optional
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to the markdown file to process. If omitted, scans all files.",
    )

    args = parser.parse_args()

    if args.path:
        # Specific file mode
        process_mushroom(args.path, bulk_mode=False)
    else:
        # Bulk mode
        scan_all_mushrooms()
