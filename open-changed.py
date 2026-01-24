#!/usr/bin/env python3
import subprocess
import webbrowser
import os
import socket
import re


def is_hugo_running(host="localhost", port=1313):
    """Check if Hugo is running by connecting to the port."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (socket.timeout, ConnectionRefusedError):
        return False


def get_changed_mushrooms():
    """Get a list of changed mushroom markdown files from git."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )

    except subprocess.CalledProcessError as e:
        print(f"Error running git: {e}")
        return []

    changed_files = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) < 2:
            continue

        file_path = parts[1]
        if not (file_path.startswith("content/svampar/") and file_path.endswith(".md")):
            continue

        if file_path.startswith('"') and file_path.endswith('"'):
            file_path = file_path[1:-1]
        changed_files.append(file_path)

    return changed_files


def get_slug_from_file(file_path):
    """Extract slug from front matter, or fall back to filename."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        match = re.search(r'^slug:\s*["\\]?([^"\\]+)["\\]?', content, re.MULTILINE)
        if match:
            return match.group(1)

    except Exception as e:
        print(f"Could not read {file_path}: {e}")

    filename = os.path.basename(file_path)
    return os.path.splitext(filename)[0]


def main():
    if not is_hugo_running():
        print("Hugo server is not running on localhost:1313. Exiting.")
        return

    changed_files = get_changed_mushrooms()

    if not changed_files:
        print("No changed mushroom files found.")
        return

    print(f"Found {len(changed_files)} changed mushroom(s). Opening tabs...")

    base_url = "http://localhost:1313/svampar/"

    for file_path in changed_files:
        slug = get_slug_from_file(file_path)
        url = f"{base_url}{slug}/"
        print(f"Opening {url}")
        webbrowser.open_new_tab(url)


if __name__ == "__main__":
    main()
