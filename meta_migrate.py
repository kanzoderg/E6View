#!/usr/bin/python3
"""
Migration script to convert old items.json format to individual JSON metadata files.

Old format: One items.json per tag containing all posts
  [["post_id", "file_url", "tags", "score"], ...]

New format: One JSON file per post/file named as filename.json
  {
    "post_id": "123456",
    "file_url": "https://...",
    "tags": "tag1 tag2 tag3",
    "score": "100"
  }
"""

import os
import json
import sys
from config import data_dir

def migrate_tag_directory(tag_path, tag_name, dry_run=False):
    """
    Migrate a single tag directory from items.json to individual JSON files.
    
    Args:
        tag_path: Path to the tag directory
        tag_name: Name of the tag
        dry_run: If True, only print what would be done without making changes
    """
    items_json_path = os.path.join(tag_path, "items.json")
    
    if not os.path.exists(items_json_path):
        print(f"  No items.json found in {tag_name}, skipping...")
        return 0
    
    try:
        with open(items_json_path, "r") as f:
            items = json.load(f)
    except Exception as e:
        print(f"  Error reading items.json in {tag_name}: {e}")
        return 0
    
    migrated_count = 0
    
    for item in items:
        if len(item) < 4:
            print(f"  Warning: Invalid item format in {tag_name}: {item}")
            continue
        
        post_id = item[0]
        file_url = item[1]
        tags = item[2]
        score = item[3]
        
        # Find the actual file with this post_id
        filename = None
        for f in os.listdir(tag_path):
            if f.startswith(f"{post_id}_") and not f.endswith(".json"):
                filename = f
                break
        
        if not filename:
            print(f"  Warning: No file found for post_id {post_id} in {tag_name}")
            continue
        
        # Create metadata JSON file
        json_filename = filename + ".json"
        json_path = os.path.join(tag_path, json_filename)
        
        # Skip if already exists
        if os.path.exists(json_path):
            continue
        
        meta_data = {
            "post_id": post_id,
            "file_url": file_url,
            "tags": tags,
            "score": score
        }
        
        if dry_run:
            print(f"  Would create: {json_filename}")
        else:
            try:
                with open(json_path, "w") as f:
                    json.dump(meta_data, f, indent=2)
                migrated_count += 1
            except Exception as e:
                print(f"  Error writing {json_filename}: {e}")
    
    return migrated_count


def migrate_all(dry_run=False):
    """
    Migrate all tag directories from old to new metadata format.
    
    Args:
        dry_run: If True, only print what would be done without making changes
    """
    if not os.path.exists(data_dir):
        print(f"Error: Data directory '{data_dir}' does not exist!")
        return
    
    print(f"Scanning data directory: {data_dir}")
    print(f"Mode: {'DRY RUN' if dry_run else 'MIGRATION'}")
    print("-" * 60)
    
    tag_dirs = [d for d in os.listdir(data_dir) 
                if os.path.isdir(os.path.join(data_dir, d))]
    
    total_migrated = 0
    
    for i, tag_name in enumerate(sorted(tag_dirs), 1):
        tag_path = os.path.join(data_dir, tag_name)
        print(f"[{i}/{len(tag_dirs)}] Processing {tag_name}...")
        
        count = migrate_tag_directory(tag_path, tag_name, dry_run)
        total_migrated += count
        
        if count > 0:
            print(f"  {'Would create' if dry_run else 'Created'} {count} metadata files")
    
    print("-" * 60)
    print(f"Total: {'Would create' if dry_run else 'Created'} {total_migrated} metadata files")
    
    if dry_run:
        print("\nTo perform the actual migration, run: python meta_migrate.py")
    else:
        print("\nMigration complete!")
        print("Note: Old items.json files are kept for backward compatibility.")


if __name__ == "__main__":
    # Check command line arguments
    dry_run = True
    
    if len(sys.argv) > 1:
        if sys.argv[1] in ["--run", "-r", "run"]:
            dry_run = False
        elif sys.argv[1] in ["--help", "-h", "help"]:
            print(__doc__)
            print("Usage:")
            print("  python meta_migrate.py           # Dry run (shows what would be done)")
            print("  python meta_migrate.py --run     # Actually perform migration")
            print("  python meta_migrate.py --help    # Show this help")
            sys.exit(0)
    
    migrate_all(dry_run)