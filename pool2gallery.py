#!/usr/bin/env python3
"""
pool2gallery.py - Create gallery folders with symlinks for each pool

This tool creates folders in /media/t/gallery/ for each pool in the database,
using the pool's title as the folder name. It then creates symlinks to all
files belonging to that pool, ordered by position.
"""

import sqlite3
import os
import sys
import re
from pathlib import Path

# Import config for data_dir
from config import data_dir
from utils import db_exec

# Gallery root directory
GALLERY_ROOT = "/media/t/gallery/"

# Database path
DB_PATH = "posts.db"


def sanitize_folder_name(name):
    """Sanitize pool name to be a valid folder name"""
    # Replace invalid characters with underscore
    for c in '<>:"/\|?*\n\t#\r':
        name = name.replace(c, " ")
    # Remove leading/trailing spaces and dots
    name = name.strip(" .")
    name = name.replace("Collection ", "")
    name = name.replace("Series ", "")
    name = name.strip("_")
    # Limit length to 255 characters (common filesystem limit)
    if len(name) > 255:
        name = name[:255]
    # Ensure it's not empty
    if not name:
        name = "unnamed_pool"
    return name.strip()


def get_file_path(user, post_id, file_id):
    """Get the actual file path for a given user, post_id, and file_id"""
    # Construct path based on data_dir structure
    file_path = os.path.join(data_dir, user, f"{post_id}_{file_id}")
    if os.path.exists(file_path):
        return file_path
    print(f"Warning: File not found at {file_path}")
    return None


def create_pool_galleries():
    """Main function to create gallery folders for all pools"""

    # Ensure gallery root exists
    os.makedirs(GALLERY_ROOT, exist_ok=True)

    # Connect to database
    try:
        db = sqlite3.connect(DB_PATH)
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        return 1

    # Get all pools
    pools = db_exec("SELECT pool_id, name FROM pools ORDER BY pool_id", db=db)

    if not pools:
        print("No pools found in database")
        return 0

    print(f"Found {len(pools)} pools")

    for pool_id, pool_name in pools:
        print(f"\nProcessing pool {pool_id}: {pool_name}")

        # Sanitize pool name for folder
        folder_name = sanitize_folder_name(pool_name)
        gallery_path = os.path.join(GALLERY_ROOT, f"{folder_name}({pool_id})")

        # Create gallery folder
        try:
            os.makedirs(gallery_path, exist_ok=True)
            print(f"  Created folder: {gallery_path}")
        except OSError as e:
            print(f"  Error creating folder: {e}")
            continue

        # Get all posts in this pool, ordered by position
        pool_posts = db_exec(
            """
            SELECT pp.file_id, p.post_id, p.main_tag_name, pp.position
            FROM pool_posts pp
            JOIN posts p ON pp.post_id = p.post_id
            WHERE pp.pool_id = ?
            ORDER BY pp.position
        """,
            (pool_id,),
            db=db,
        )

        if not pool_posts:
            print(f"  No posts found in pool")
            continue

        print(f"  Found {len(pool_posts)} posts")

        # Create symlinks for each file
        created_count = 0
        skipped_count = 0
        error_count = 0

        for file_id, post_id, user, position in pool_posts:
            # Get source file path
            source_path = get_file_path(user, post_id, file_id)

            if not source_path:
                print(f"    Warning: File not found for {user}/{file_id}")
                error_count += 1
                continue

            # Create symlink with position prefix for sorting
            # Format: 001_original_filename.ext
            link_name = f"{position:03d}_{file_id}"
            link_path = os.path.join(gallery_path, link_name)

            # Check if symlink already exists
            if os.path.lexists(link_path):
                # Check if it points to the correct target
                if os.path.islink(link_path):
                    existing_target = os.readlink(link_path)
                    if existing_target == source_path:
                        skipped_count += 1
                        continue
                    else:
                        # Remove incorrect symlink
                        os.remove(link_path)
                else:
                    # Not a symlink, skip to avoid overwriting
                    print(f"    Warning: {link_name} exists but is not a symlink")
                    skipped_count += 1
                    continue

            # Create symlink
            try:
                os.symlink(source_path, link_path)
                created_count += 1
                #if created_count>100:
                #    exit(0)
            except OSError as e:
                print(f"    Error creating symlink for {file_id}: {e}")
                error_count += 1

        print(
            f"  Created: {created_count}, Skipped: {skipped_count}, Errors: {error_count}"
        )

    db.close()
    print(f"\nGallery creation complete!")
    return 0


if __name__ == "__main__":
    try:
        exit_code = create_pool_galleries()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
