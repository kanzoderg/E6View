import os, time
import json, sys
import sqlite3
from PIL import Image
import natsort
from config import *
import math, random
import download

data_type = [
    "jpg",
    "png",
    "jpeg",
    "jpg",
    "gif",
    "webp",
    "webm",
    "bmp",
    "mp4",
    "flv",
    "avi",
    "mkv",
    "mov",
    "m4v",
    "mpg",
    "mpeg",
    "ogg",
    "ogv",
    "3gp",
    "swf",
]
current_download_tag = ""

artists = []
all_tags = []
all_tags_count = {}

download_queue = []


def init_db(db: sqlite3.Connection):
    db_exec(
        """
        CREATE TABLE IF NOT EXISTS posts (
            post_id INTEGER PRIMARY KEY,
            file_id TEXT,
            main_tag_name TEXT,
            score INTEGER
        )
    """,
        db=db,
        cache=False,
    )
    db_exec(
        """
        CREATE INDEX IF NOT EXISTS posts_main_tag_name ON posts (main_tag_name)
        """,
        db=db,
        cache=False,
    )
    db_exec(
        """
        CREATE TABLE IF NOT EXISTS tags (
            post_id INTEGER,
            tag TEXT,
            PRIMARY KEY (post_id, tag)
        )
    """,
        db=db,
        cache=False,
    )
    db_exec(
        """
        CREATE INDEX IF NOT EXISTS tags_post_id ON tags (post_id)
        """,
        db=db,
        cache=False,
    )
    db_exec(
        """
        CREATE INDEX IF NOT EXISTS tags_tag ON tags (tag)
        """,
        db=db,
        cache=False,
    )
    # Add composite index for better query performance
    db_exec(
        """
        CREATE INDEX IF NOT EXISTS tags_tag_post ON tags (tag, post_id)
        """,
        db=db,
        cache=False,
    )
    db_exec(
        """
        CREATE TABLE IF NOT EXISTS pools (
            pool_id INTEGER PRIMARY KEY,
            name TEXT,
            description TEXT,
            post_count INTEGER,
            cover_post_id INTEGER,
            cover_file_id TEXT
        )
    """,
        db=db,
        cache=False,
    )
    db_exec(
        """
        CREATE TABLE IF NOT EXISTS pool_posts (
            pool_id INTEGER,
            post_id INTEGER,
            file_id TEXT,
            position INTEGER,
            PRIMARY KEY (pool_id, post_id)
        )
    """,
        db=db,
        cache=False,
    )
    db_exec(
        """
        CREATE INDEX IF NOT EXISTS pool_posts_pool_id ON pool_posts (pool_id)
        """,
        db=db,
        cache=False,
    )
    db_exec(
        """
        CREATE INDEX IF NOT EXISTS pool_posts_post_id ON pool_posts (post_id)
        """,
        db=db,
        cache=False,
    )


query_cache = dict()


def clear_query_cache():
    global query_cache
    query_cache = dict()


def db_exec(
    query,
    params=(),
    db: sqlite3.Connection = None,
    cache=True,
    fetchone=False,
    commit=False,
):
    global query_cache
    # clear cache if it grows too big
    if len(query_cache) > 5000:
        print("Clearing query cache...")
        clear_query_cache()
    if not isinstance(params, tuple):
        params = tuple(params)
    key = (query, params)
    if cache and key in query_cache:
        # print("DB QUERY CACHE HIT:", query, params)
        return query_cache[key]
    elif cache:
        pass
        # print("DB QUERY CACHE MISS:", query, params)
    else:
        pass
        # print("DB QUERY:", query, params)
    cursor = db.cursor()
    cursor.execute(query, params)
    if fetchone:
        res = cursor.fetchone()
    else:
        res = cursor.fetchall()
    if cache:
        query_cache[key] = res
    cursor.close()
    if commit:
        db.commit()
    return res


def scan_posts(main_tag_name, db: sqlite3.Connection):
    tag_dir = os.path.join(data_dir, main_tag_name)

    for filename in os.listdir(tag_dir):
        if filename.endswith(tuple(data_type)):
            try:
                post_id, file_id = filename.split("_", 1)
            except:
                print(main_tag_name, filename, "\nfilename not correct.")
                file_id = filename
                post_id = -int("".join([str(ord(i) % 10) for i in filename[:8]]))
                print("Assigned a random postid", post_id)

            tags = [main_tag_name]
            score = 0

            # Read individual JSON metadata file
            json_filename = filename + ".json"
            json_path = os.path.join(tag_dir, json_filename)
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r") as f:
                        meta_data = json.load(f)
                        tags = meta_data.get("tags", "").split()
                        if not tags:
                            tags = [main_tag_name]
                        score = meta_data.get("score", 0)
                except Exception as e:
                    print(f"Error reading {json_filename}: {e}")

            db_exec(
                """
                INSERT OR REPLACE INTO posts (post_id, file_id, main_tag_name, score) VALUES (?, ?, ?, ?)
                """,
                (post_id, file_id, main_tag_name, score),
                db=db,
                cache=False,
            )
            for tag in tags:
                db_exec(
                    """
                    INSERT OR REPLACE INTO tags (post_id, tag) VALUES (?, ?)
                    """,
                    (post_id, tag),
                    db=db,
                    cache=False,
                )
    db.commit()


def add_fav(post_id, db: sqlite3.Connection):
    db_exec(
        """
        INSERT OR REPLACE INTO tags (post_id, tag) VALUES (?, ?)
        """,
        (post_id, "fav:me"),
        db=db,
        cache=False,
        commit=True,
    )


def remove_fav(post_id, db: sqlite3.Connection):
    db_exec(
        """
        DELETE FROM tags WHERE post_id = ? AND tag = ?
        """,
        (post_id, "fav:me"),
        db=db,
        cache=False,
        commit=True,
    )


def is_fav(post_id, db: sqlite3.Connection):
    # check if post_id has tag "fav:me"
    result = db_exec(
        """
        SELECT tag FROM tags WHERE post_id = ? AND tag = ?
        """,
        (post_id, "fav:me"),
        db=db,
        fetchone=True,
        cache=False,
    )
    return bool(result)


def get_posts_by_tags(tags, db: sqlite3.Connection, sort_type="id", cache=True):
    tags = list(set(tags))

    # Check if there's a pool: tag
    pool_tag = None
    for tag in tags:
        if tag.startswith("pool:"):
            pool_tag = tag
            break

    # If pool: tag exists, only use that tag and ignore others
    if pool_tag:
        try:
            pool_id = int(pool_tag.split(":")[1])
        except (ValueError, IndexError):
            return []

        # Query posts from pool_posts table, ordered by position
        # Use LEFT JOIN to include pool items even if posts don't exist yet
        return db_exec(
            """
            SELECT 
                COALESCE(p.post_id, pp.post_id) as post_id,
                COALESCE(p.file_id, pp.file_id) as file_id,
                COALESCE(p.main_tag_name, '') as main_tag_name,
                COALESCE(p.score, 0) as score
            FROM pool_posts pp
            LEFT JOIN posts p ON pp.post_id = p.post_id
            WHERE pp.pool_id = ?
            ORDER BY pp.position
            """,
            (pool_id,),
            db=db,
            cache=cache,
        )

    # Filter out special tags except fav:me
    for tag in list(tags):
        if ":" in tag and tag != "fav:me":
            tags.remove(tag)
    tags = tuple(tags)
    if "fav:me" in tags:
        cache = False  # disable cache for fav:me queries
    if tags:
        # Split tags into positive and negative
        positive_tags = [tag for tag in tags if not tag.startswith("-")]
        negative_tags = [tag[1:] for tag in tags if tag.startswith("-")]

        # Dynamic ORDER BY clause
        if sort_type == "random":
            order_by_clause = ""
        elif sort_type == "score":
            order_by_clause = "ORDER BY p.score DESC"
        else:
            order_by_clause = "ORDER BY p.post_id DESC"

        if positive_tags:
            # Use INTERSECT strategy for multiple positive tags - much faster than JOIN + GROUP BY + HAVING
            if len(positive_tags) == 1:
                # Single tag optimization
                query = """
                    SELECT p.post_id, p.file_id, p.main_tag_name, p.score
                    FROM posts p
                    INNER JOIN tags t ON p.post_id = t.post_id
                    WHERE t.tag = ?
                """
                if negative_tags:
                    query += """
                        AND p.post_id NOT IN (
                            SELECT post_id FROM tags WHERE tag IN ({}))
                    """.format(
                        ",".join("?" * len(negative_tags))
                    )
                query += " " + order_by_clause
                params = positive_tags + negative_tags
            else:
                # Multiple positive tags: use INTERSECT for better performance
                intersect_parts = []
                for _ in positive_tags:
                    intersect_parts.append("SELECT post_id FROM tags WHERE tag = ?")
                intersect_query = (
                    "\n                    INTERSECT\n                    ".join(
                        intersect_parts
                    )
                )

                query = """
                    SELECT p.post_id, p.file_id, p.main_tag_name, p.score
                    FROM posts p
                    WHERE p.post_id IN (
                        {}
                    )
                """.format(
                    intersect_query
                )

                if negative_tags:
                    query += """
                        AND p.post_id NOT IN (
                            SELECT post_id FROM tags WHERE tag IN ({}))
                    """.format(
                        ",".join("?" * len(negative_tags))
                    )
                query += " " + order_by_clause
                params = positive_tags + negative_tags

            results = db_exec(query, params, db=db, cache=cache)
            if sort_type == "random":
                random.shuffle(results)
            return results
        elif negative_tags:
            # Only negative tags: exclude posts with these tags
            query = """
                SELECT p.post_id, p.file_id, p.main_tag_name, p.score
                FROM posts p
                WHERE p.post_id NOT IN (
                    SELECT post_id FROM tags WHERE tag IN ({}))
                {}
            """.format(
                ",".join("?" * len(negative_tags)), order_by_clause
            )
            params = negative_tags
            results = db_exec(query, params, db=db, cache=cache)
            if sort_type == "random":
                random.shuffle(results)
            return results
        return []
    else:
        # No tags - return all posts
        if sort_type == "id":
            return db_exec(
                """
                SELECT post_id, file_id, main_tag_name, score FROM posts
                ORDER BY post_id DESC
                """,
                db=db,
                cache=cache,
            )
        elif sort_type == "score":
            return db_exec(
                """
                SELECT post_id, file_id, main_tag_name, score FROM posts
                ORDER BY score DESC
                """,
                db=db,
                cache=cache,
            )
        else:  # random
            results = db_exec(
                """
                SELECT post_id, file_id, main_tag_name, score FROM posts
                ORDER BY score DESC
                """,
                db=db,
                cache=cache,
            )
            random.shuffle(results)
            return results


def get_tags_by_post_id(post_id, db):
    rows = db_exec(
        """
        SELECT tag FROM tags WHERE post_id = ?
        """,
        (post_id,),
        db=db,
    )
    # try:
    #     tags_with_count = [(row[0], all_tags_count.get(row[0], 0)) for row in rows]
    # except:
    #     tags_with_count = [(row[0], 0) for row in rows]
    tags_with_count = []
    for row in rows:
        tag = row[0]
        count = all_tags_count.get(tag, 0)
        tags_with_count.append((tag, count))
    tags_with_count = natsort.natsorted(tags_with_count, key=lambda x: x[1])[::-1]
    return tags_with_count


def get_post_by_id(post_id, db):
    # print("Fetching post by ID:", post_id)
    row = db_exec(
        """
        SELECT post_id, file_id, main_tag_name, score FROM posts WHERE post_id = ?
        """,
        (post_id,),
        db=db,
        fetchone=True,
    )
    if row:
        return row
    else:
        return None


def get_pools_by_post_id(post_id, db):
    """Get all pools that contain this post"""
    return db_exec(
        """
        SELECT p.pool_id, p.name 
        FROM pools p
        INNER JOIN pool_posts pp ON p.pool_id = pp.pool_id
        WHERE pp.post_id = ?
        """,
        (post_id,),
        db=db,
    )


def check_post_exists(post_id, db) -> str:
    row = db_exec(
        """
        SELECT main_tag_name FROM posts WHERE post_id = ?
        """,
        (post_id,),
        db=db,
        fetchone=True,
        cache=False,
    )
    if row:
        return row[0]
    else:
        return ""


def get_all_tags(db):
    global all_tags, artists, all_tags_count
    if not all_tags:
        tag_results = db_exec(
            """
            SELECT tag, COUNT(*) as count 
            FROM tags 
            GROUP BY tag 
            ORDER BY count DESC
            """,
            db=db,
        )
        ext_tags = ["order:score", "order:random", "order:id", "fav:me", "order:rank"]
        all_tags = [(ext_tag, "") for ext_tag in ext_tags]
        all_tags += tag_results

        # Build all_tags_count dict
        all_tags_count = {}
        for tag, count in all_tags:
            all_tags_count[tag] = count

        # Add pool tags
        pools = db_exec(
            """
            SELECT pool_id, post_count FROM pools ORDER BY post_count DESC
            """,
            db=db,
        )
        for pool_id, post_count in pools:
            pool_tag = f"pool:{pool_id}"
            all_tags.append((pool_tag, post_count))
            all_tags_count[pool_tag] = post_count

    # Build artists list
    artists = []
    for i in os.listdir(data_dir):
        if i in all_tags_count:
            artists.append((i, all_tags_count[i]))
    artists = natsort.natsorted(artists, key=lambda x: x[1])[::-1]

    return all_tags


def get_score(post_id, db):
    score = db_exec(
        """
        SELECT score FROM posts WHERE post_id = ?
        """,
        (post_id,),
        db=db,
        fetchone=True,
    )
    if score:
        return score[0]
    else:
        return 0


def get_all_pools(db):
    pools = db_exec(
        """
        SELECT pool_id, name, description, post_count, cover_post_id, cover_file_id FROM pools
        """,
        db=db,
    )
    # Convert to old format for compatibility: (pool_id, name, description, post_count, cover)
    result = []
    for pool_id, name, description, post_count, cover_post_id, cover_file_id in pools:
        result.append(
            (pool_id, name, description, post_count, cover_post_id, cover_file_id)
        )
    return result


def get_pool_info(pool_id, db):
    pool = db_exec(
        """
        SELECT pool_id, name, description, post_count, cover_post_id, cover_file_id FROM pools WHERE pool_id = ?
        """,
        (pool_id,),
        db=db,
        fetchone=True,
    )
    if not pool:
        return None
    pool_id_result, name, description, post_count, cover_post_id, cover_file_id = pool

    # Fetch items from pool_posts table
    items_results = db_exec(
        """
        SELECT post_id, file_id FROM pool_posts WHERE pool_id = ? ORDER BY position
        """,
        (pool_id,),
        db=db,
    )
    items = [(row[0], row[1]) for row in items_results]
    cover = [cover_post_id, cover_file_id] if cover_post_id else ["", ""]
    return pool_id_result, name, description, post_count, cover, items


def add_pool(pool_id, name, description, items, db):
    post_count = len(items)

    # Extract cover info
    if items:
        cover_post_id, cover_file = items[0]
        if isinstance(cover_file, str):
            cover_file = cover_file.split("/")[-1]  # only keep filename
    else:
        cover_post_id, cover_file = None, None

    # Insert or update pool
    db_exec(
        """
        INSERT OR REPLACE INTO pools (pool_id, name, description, post_count, cover_post_id, cover_file_id) 
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (pool_id, name, description, post_count, cover_post_id, cover_file),
        db=db,
        cache=False,
    )

    # Delete existing pool_posts entries
    db_exec(
        """
        DELETE FROM pool_posts WHERE pool_id = ?
        """,
        (pool_id,),
        db=db,
        cache=False,
    )

    # Insert pool_posts entries
    for position, (post_id, file_id) in enumerate(items):
        if isinstance(file_id, str):
            file_id = file_id.split("/")[-1]  # only keep filename
        db_exec(
            """
            INSERT INTO pool_posts (pool_id, post_id, file_id, position) VALUES (?, ?, ?, ?)
            """,
            (pool_id, post_id, file_id, position),
            db=db,
            cache=False,
        )


def download_worker(db):
    global download_queue, current_download_tag
    print("Starting download worker...")
    while True:
        try:
            if download_queue:
                item = download_queue.pop(0)
                print("Downloading:", item)
                current_download_tag = tag = item[0]
                type_ = item[1]
                main_tags = set()
                if not tag:
                    print("No tag to download, skipping...")
                    time.sleep(1)
                    continue
                if type_ == "id":
                    print("Downloading by ID:", tag)
                    tag = tag.replace("id:", "")
                    item, main_tag = download.search_by_id(tag)
                    items = [(item, main_tag)]
                    main_tags.add(main_tag)
                elif type_ == "tag":
                    items = download.search(tag)
                    items = [(item, tag) for item in items]
                    main_tags.add(tag)
                elif type_ == "pool":
                    print("Downloading pool:", tag)
                    pool_id = tag.replace("pool:", "")
                    pool_items, title, description = download.get_pool_items(pool_id)
                    print(f"Pool title: {title}")
                    items = []
                    items_to_dump = []
                    for i, (post_id, file_url) in enumerate(pool_items):
                        # Find if post already exists
                        if check_post_exists(post_id, db):
                            print(
                                f"[{i+1}/{len(pool_items)}] Post {post_id} already exists, download will be skipped."
                            )
                            items_to_dump.append((post_id, file_url))
                            continue
                        item, main_tag = download.search_by_id(post_id)
                        items.append((item, main_tag))
                        items_to_dump.append((post_id, file_url))
                        main_tags.add(main_tag)
                    # Save pool metadata
                    add_pool(pool_id, title, description, items_to_dump, db)
                    os.makedirs(os.path.join(data_dir, "pools"), exist_ok=True)
                    with open(
                        os.path.join(data_dir, "pools", f"{pool_id}.json"), "w"
                    ) as f:
                        json.dump(
                            {
                                "pool_id": pool_id,
                                "title": title,
                                "description": description,
                                "items": items_to_dump,
                            },
                            f,
                        )

                print(f"Found {len(items)} items for {current_download_tag}")
                print("downloading", len(items), "items")
                for i, (item, tag) in enumerate(items):
                    print(f"[{i+1}/{len(items)}]", item[0], end=" ")
                    download.download(item, tag)

                print(f"Rescanning {len(main_tags)} artist folders...")
                for main_tag in main_tags:
                    scan_posts(main_tag, db)
                clear_query_cache()

                current_download_tag = ""
        except Exception as e:
            print("Error in download worker:", e)
        finally:
            time.sleep(1)


def thumb(file_path):
    if ".." in file_path or '"' in file_path:
        raise ValueError("Invalid file path")
    file_name = file_path.split("/")[-1]
    isvid = file_name.split(".")[-1] in ["webm", "flv", "mp4", "avi", "swf"]
    thumb_path = os.path.expanduser(f"~/.cache/e6view/{file_name}_thumb.jpg")
    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
    if not os.path.exists(thumb_path) and os.path.exists(file_path):
        if isvid:
            if file_name.endswith("swf"):
                if os.system(f'ffmpeg -i "{file_path}" -vframes 1 "{thumb_path}"'):
                    # Failed to generate thumbnail, use placeholder
                    os.system(f'cp "static/flash.png" "{thumb_path}"')
            else:
                if os.system(
                    f'ffmpeg -i "{file_path}" -ss 00:00:00.001 -vframes 1 "{thumb_path}"'
                ):
                    # Failed to generate thumbnail, use placeholder
                    os.system(f'cp "static/vid.png" "{thumb_path}"')
        else:
            with Image.open(file_path) as img:
                img.thumbnail((400, 400))
                img = img.convert("RGB")
                img.save(thumb_path)
    return thumb_path


def test_file_type(s):
    ext = s.split(".")[-1]
    if ext in ["jpg", "jpeg", "png", "gif", "webp", "bmp"]:
        return "img"
    elif ext in [
        "webm",
        "mp4",
        "flv",
        "avi",
        "mkv",
        "mov",
        "m4v",
        "mpg",
        "mpeg",
        "ogg",
        "ogv",
        "3gp",
    ]:
        return "vid"
    elif ext == "swf":
        return "flash"
    else:
        return None


if __name__ == "__main__":
    tag = ""
    if len(sys.argv) == 2:
        tag = sys.argv[1].lower().strip()

    db = sqlite3.connect("posts.db")
    init_db(db)
    print("Scanning posts...")
    if tag:
        print(f"Scanning {tag}...")
        scan_posts(tag, db)
    else:
        main_tags = os.listdir(data_dir)
        for i, tag in enumerate(main_tags):
            print(f"[{i+1}/{len(main_tags)}] Scanning {tag}...")
            scan_posts(tag, db)
    print("Done.")
    print("Scanning pools...")
    pool_dir = os.path.join(data_dir, "pools")
    if os.path.exists(pool_dir):
        for filename in os.listdir(pool_dir):
            if filename.endswith(".json"):
                pool_id = filename[:-5]
                print(f"Scanning pool {pool_id}...")
                try:
                    with open(os.path.join(pool_dir, filename), "r") as f:
                        pool_data = json.load(f)
                        name = pool_data.get("title", "")
                        description = pool_data.get("description", "")
                        items = pool_data.get("items", [])
                        add_pool(pool_id, name, description, items, db)
                except Exception as e:
                    print(f"Error reading pool {pool_id}: {e}")
    print("Done.")
    db.close()
