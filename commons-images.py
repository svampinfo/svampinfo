#!/usr/bin/env python3
"""
  ___ ___  _ __ ___  _ __ ___   ___  _ __  ___      (_)_ __ ___   __ _  __ _  ___  ___   _ __  _   _
 / __/ _ \| '_ ` _ \| '_ ` _ \ / _ \| '_ \/ __|_____| | '_ ` _ \ / _` |/ _` |/ _ \/ __| | '_ \| | | |
| (_| (_) | | | | | | | | | | | (_) | | | \__ \_____| | | | | | | (_| | (_| |  __/\__ \_| |_) | |_| |
 \___\___/|_| |_| |_|_| |_| |_|\___/|_| |_|___/     |_|_| |_| |_|\__,_|\__, |\___||___(_) .__/ \__, |
                                                                       |___/            |_|    |___/
"""

import os
import re
import time
import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
from typing import Optional, Dict, List, Tuple, Any

CONTENT_DIR = "content/svampar"
ASSETS_DIR = "assets/images"
USER_AGENT = "SvampinfoBot/1.0 (https://svampinfo.se)"

os.makedirs(ASSETS_DIR, exist_ok=True)


def get_ssl_context() -> ssl.SSLContext:
    """Creates a permissive SSL context."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def make_request(url: str, retries: int = 3) -> Optional[bytes]:
    """Performs an HTTP GET request with retries and rate limiting."""
    headers = {"User-Agent": USER_AGENT}
    req = urllib.request.Request(url, headers=headers)

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, context=get_ssl_context()) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait_time = int(e.headers.get("Retry-After", 5)) * (attempt + 1)
                print(f"Rate limited (429). Waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"HTTP Error {e.code}: {e.reason} for {url}")
                return None
        except Exception as e:
            print(f"Error requesting {url}: {e}")
            return None
    return None


def clean_author_name(artist_html: str) -> Tuple[str, Optional[str]]:
    """Extracts author name and URL from HTML or text."""
    author_text = "Unknown"
    author_url = None

    # Try to extract link from HTML
    link_match = re.search(
        r'<a\s+[^>]*href=["\']([^"\\]+)["\\]*[^>]*>(.*?)</a>',
        artist_html,
        re.IGNORECASE,
    )

    if link_match:
        url_part = link_match.group(1)
        text_part = link_match.group(2)

        if url_part.startswith("//"):
            url_part = "https:" + url_part

        author_url = url_part
        author_text = re.sub(r"<[^>]+>", "", text_part).strip()
    else:
        author_text = re.sub(r"<[^>]+>", "", artist_html).strip()

    # Clean boilerplate
    boilerplate_patterns = [
        r"^This image was created by user\s+",
        r"^This image was created by\s+",
        r"\s+at Mushroom Observer.*$",
        r"\(.*\)",
    ]
    for pattern in boilerplate_patterns:
        author_text = re.sub(pattern, "", author_text, flags=re.IGNORECASE).strip()

    return author_text, author_url


def get_commons_metadata(page_url: str) -> Optional[Dict[str, Any]]:
    """
    Fetches metadata for a Wikimedia Commons file.
    Handles standard wiki URLs and Media Viewer (Category) URLs.
    """
    # 1. Extract the filename part regardless of URL structure
    match = re.search(r"File:([^#\?&]+)", page_url)
    if not match:
        print(f"Could not parse filename from {page_url}")
        return None

    # 2. Decode the filename (removes %C3%B1 etc)
    raw_filename = match.group(1)
    filename = urllib.parse.unquote(raw_filename)

    # 3. Construct API request (re-encoded)
    params = {
        "action": "query",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|user",
        "titles": f"File:{filename}",
        "format": "json",
    }

    api_url = "https://commons.wikimedia.org/w/api.php"
    full_url = f"{api_url}?{urllib.parse.urlencode(params)}"
    response = make_request(full_url)

    if not response:
        return None

    data = json.loads(response)
    pages = data.get("query", {}).get("pages", {})

    # Flatten iteration
    page_data = next(iter(pages.values()), {})

    if "missing" in page_data:
        print(f"File not found via API: {filename}")
        return None

    if "imageinfo" not in page_data:
        return None

    info = page_data["imageinfo"][0]
    meta = info.get("extmetadata", {})

    artist_html = meta.get("Artist", {}).get("value", "Unknown")
    author_text, author_url = clean_author_name(artist_html)

    # Clean the output page URL (Decoded for Markdown)
    clean_page_url = f"https://commons.wikimedia.org/wiki/File:{filename}"

    return {
        "url": info.get("url"),
        "author": author_text,
        "author_url": author_url,
        "license": meta.get("LicenseShortName", {}).get("value", "Unknown"),
        "license_url": meta.get("LicenseUrl", {}).get("value", ""),
        "original_filename": filename,
        "page_url": clean_page_url,
    }


def download_image(url: str, save_path: str) -> bool:
    """Downloads an image from a URL to a local path."""
    response = make_request(url)
    if not response:
        return False

    with open(save_path, "wb") as f:
        f.write(response)
    return True


def get_next_image_index(slug: str) -> int:
    """Determines the next available index for a given slug."""
    existing_images = [f for f in os.listdir(ASSETS_DIR) if f.startswith(slug)]
    if not existing_images:
        return 1

    indices = []
    for img in existing_images:
        m = re.search(r"_(\d+)\.", img)
        if m:
            indices.append(int(m.group(1)))

    return max(indices) + 1 if indices else 1


def extract_links_from_body(body: str) -> Tuple[str, List[str]]:
    """Extracts Commons links from the body text and returns cleaned body."""
    lines = body.strip().split("\n")
    cleaned_lines = []
    links = []

    link_pattern = re.compile(r"(https?://commons\.wikimedia\.org/\S*File:\S+)")

    for line in lines:
        if "commons.wikimedia.org" in line and "File:" in line:
            url_match = link_pattern.search(line)
            if url_match:
                url = url_match.group(1).rstrip(").,")
                if url.endswith(")") and "(" not in url:
                    url = url.rstrip(")")

                links.append(url)
                continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines), links


def update_frontmatter_image(frontmatter: str, image_path: str) -> str:
    """
    Sets the main image in frontmatter ONLY if it is empty or missing.
    Prevents overwriting or corrupting existing image tags.
    """
    lines = frontmatter.split("\n")
    new_lines = []
    image_key_found = False

    for line in lines:
        # Match 'image:' key at start of line (ignoring indentation)
        if re.match(r"^\s*image:", line):
            parts = line.split(":", 1)
            # Get the value part, strip whitespace and quotes
            current_value = parts[1].strip().strip("\"'")

            # If the value is empty, we update it.
            if not current_value:
                new_lines.append(f'image: "{image_path}"')
            else:
                # Value exists, keep the line exactly as is
                new_lines.append(line)

            image_key_found = True
        else:
            new_lines.append(line)

    # If key wasn't found at all, append it
    if not image_key_found:
        new_lines.append(f'image: "{image_path}"')

    return "\n".join(new_lines)


def append_to_gallery(frontmatter: str, entries: List[Dict[str, str]]) -> str:
    """Appends new entries to the gallery section in frontmatter."""
    if not entries:
        return frontmatter

    # Convert inline empty arrays to block format
    frontmatter = re.sub(
        r"^(\s*gallery:)\s*\[\s*\]\s*$", r"\1", frontmatter, flags=re.MULTILINE
    )

    lines = frontmatter.split("\n")
    gallery_line_idx = -1

    # Find 'gallery:' key
    for i, line in enumerate(lines):
        if re.match(r"^\s*gallery:\s*($|#)", line):
            gallery_line_idx = i
            break

    new_items_lines = []
    for entry in entries:
        new_items_lines.append(f'  - url: "{entry["url"]}"')
        new_items_lines.append(f'    credit: "{entry["credit"]}"')

    if gallery_line_idx == -1:
        if lines and lines[-1].strip() == "":
            lines.pop()
        lines.append("gallery:")
        lines.extend(new_items_lines)
        return "\n".join(lines)

    # Find end of gallery block based on indentation
    key_indent = len(lines[gallery_line_idx]) - len(lines[gallery_line_idx].lstrip())
    insert_idx = len(lines)

    for i in range(gallery_line_idx + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            continue

        curr_indent = len(line) - len(line.lstrip())

        if curr_indent <= key_indent:
            insert_idx = i
            break

    final_lines = lines[:insert_idx] + new_items_lines + lines[insert_idx:]
    return "\n".join(final_lines)


def process_file(file_path: str):
    """Orchestrates the processing of a single markdown file."""
    with open(file_path, "r") as f:
        content = f.read()

    if not content.startswith("---"):
        return

    parts = content.split("---", 2)
    if len(parts) < 3:
        return

    raw_frontmatter = parts[1]
    body = parts[2]

    clean_body, links = extract_links_from_body(body)

    if not links:
        return

    print(f"Processing {len(links)} links in {file_path}")

    slug_match = re.search(r'slug:\s*["\']?([^"\']+)["\']?', raw_frontmatter)
    slug = (
        slug_match.group(1)
        if slug_match
        else os.path.basename(file_path).replace(".md", "")
    )

    next_index = get_next_image_index(slug)
    gallery_entries = []
    first_image_path = None

    for link in links:
        meta = get_commons_metadata(link)
        if not meta:
            print(f"Failed to get metadata for {link}")
            continue

        ext = os.path.splitext(meta["original_filename"])[1].lower() or ".jpg"
        new_filename = f"{slug}_{next_index:02d}{ext}"
        local_rel_path = f"/images/{new_filename}"
        local_abs_path = os.path.join(ASSETS_DIR, new_filename)

        print(f"Downloading {meta['original_filename']} -> {new_filename}")
        if not download_image(meta["url"], local_abs_path):
            print(f"Failed to download {link}")
            continue

        next_index += 1

        author_part = (
            f"[{meta['author']}]({meta['author_url']})"
            if meta["author_url"]
            else meta["author"]
        )

        license_part = meta["license"]
        if meta["license_url"]:
            license_part = f"[{meta['license']}]({meta['license_url']})"

        credit = f"{author_part}, {license_part}, via [Wikimedia Commons]({meta['page_url']})"

        gallery_entries.append({"url": local_rel_path, "credit": credit})

        if not first_image_path:
            first_image_path = local_rel_path

    if not gallery_entries:
        return

    # Update Frontmatter
    if first_image_path:
        raw_frontmatter = update_frontmatter_image(raw_frontmatter, first_image_path)

    raw_frontmatter = append_to_gallery(raw_frontmatter, gallery_entries)

    # Reconstruct and Save
    new_content = f"---\n{raw_frontmatter}\n---\n{clean_body}"
    with open(file_path, "w") as f:
        f.write(new_content)
    print(f"Updated {file_path}")


def main():
    if not os.path.exists(CONTENT_DIR):
        print(f"Error: Content directory '{CONTENT_DIR}' not found.")
        return

    files = [f for f in os.listdir(CONTENT_DIR) if f.endswith(".md")]
    print(f"Scanning {len(files)} files...")
    for filename in files:
        process_file(os.path.join(CONTENT_DIR, filename))


if __name__ == "__main__":
    main()
