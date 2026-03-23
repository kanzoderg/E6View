from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    send_from_directory,
    send_file,
    make_response,
    Response,
)
import sqlite3, os, re, json, threading
import requests, time, natsort
from contextlib import contextmanager
import mimetypes

import utils
from config import *
import logger
import download

url_base = url_base.strip("/")
if url_base:
    url_base = "/" + url_base

print(f"URL base set to: '{url_base}'")

app = Flask(__name__)


# Set cache control for static resources in production
@app.after_request
def add_cache_control(response):
    if debug == 0 and response.status_code in (200, 304):
        # Only cache static files (CSS, JS, images, etc.)
        if (
            request.path.startswith(f"{url_base}/static/")
            or request.path.startswith(f"{url_base}/file/")
            or request.path.startswith(f"{url_base}/thumb/")
        ):
            response.headers["Cache-Control"] = "public, max-age=3600"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@contextmanager
def get_db():
    db = sqlite3.connect("posts.db", timeout=10.0)
    db.execute("PRAGMA journal_mode=WAL")
    try:
        yield db
    finally:
        db.close()

db = sqlite3.connect("posts.db", check_same_thread=False)

def send_file_partial(path):
    range_header = request.headers.get("Range", None)
    if not range_header:
        return send_file(path)

    size = os.path.getsize(path)
    byte1, byte2 = 0, None

    m = re.search(r"(\d+)-(\d*)", range_header)
    g = m.groups()

    if g[0]:
        byte1 = int(g[0])
    if g[1]:
        byte2 = int(g[1])

    length = size - byte1
    if byte2 is not None:
        length = byte2 - byte1 + 1

    data = None
    with open(path, "rb") as f:
        f.seek(byte1)
        data = f.read(length)

    rv = Response(
        data,
        206,
        headers={
            "Content-Range": f"bytes {byte1}-{byte1 + length - 1}/{size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Type": mimetypes.guess_type(path)[0] or "application/octet-stream",
        },
    )
    return rv


def stream_video_from_url(url, file_path):
    range_header = request.headers.get("Range", None)

    if os.path.exists(file_path):
        return send_file_partial(file_path)

    headers = {"Range": range_header} if range_header else {}
    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=30)
        if resp.status_code in [200, 206]:
            if resp.status_code == 200 and not range_header:
                with open(file_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return send_file_partial(file_path)
            else:
                def generate():
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            yield chunk

                return Response(
                    generate(), resp.status_code, headers=dict(resp.headers)
                )
        else:
            return jsonify({"status": "error", "message": "File not found"}), 404
    except Exception as e:
        print(f"Error streaming video: {e}")
        return jsonify({"status": "error", "message": "Stream failed"}), 500

@app.route(f"{url_base}/e6.webmanifest")
def webmanifest():
    ip = request.access_route[-1]
    logger.log(f" {ip} - /e6.webmanifest")
    return render_template("e6.webmanifest", url_base=url_base)

if not url_base:
    root_url = "/"
else:    
    root_url = url_base
    @app.route(f"/")
    def root():
        return redirect(url_for("index"))

@app.route(f"{root_url}/")
@app.route(f"{root_url}")
def index():
    ip = request.access_route[-1]

    # if not ("nw" in request.args or "nw" in request.cookies):
    #     logger.log(f" {ip} - / - No cookie found.")
    #     return render_template("warning.html", url_base=url_base)
    live = request.args.get("live", "0") == "1"
    page = request.args.get("page", 1, type=int)
    tags = request.args.get("tags", "").lower()
    tags = tags.split() if tags else []
    current_view_mode = request.args.get("view_mode", "grid")
    logger.log(f" {ip} - / - {dict(request.args)}")

    # Check if viewing a pool
    pool_info = None
    for tag in tags:
        if tag.startswith("pool:"):
            try:
                pool_id = int(tag.split(":")[1])
                result = utils.get_pool_info(pool_id, db)
                if result:
                    (
                        pool_id_result,
                        pool_name,
                        pool_description,
                        pool_post_count,
                        pool_cover,
                        pool_items,
                    ) = result
                    pool_info = {
                        "id": pool_id_result,
                        "name": pool_name,
                        "description": pool_description,
                        "post_count": pool_post_count,
                    }
            except (ValueError, TypeError):
                pass
            break

    if "order:score" in tags or "order:score_asc" in tags:
        show_score = True
    else:
        show_score = False

    if live:
        data = download.search(tags, page, 1)
        posts = []
        for line in data:
            post = []
            post.append(line[0])
            post.append(line[1].split("/")[-1])
            main_tag = utils.check_post_exists(line[0], db)
            if main_tag:
                post.append(main_tag)
            else:
                post.append("live")
            post.append(line[3])
            post.append(utils.test_file_type(line[1]))
            post.append(utils.is_fav(post[0], db))
            posts.append(post)
        max_page = 750
        cnt = len(posts)
    else:
        if "order:score" in tags:
            posts = utils.get_posts_by_tags(tags, db, sort_type="score")
        elif "order:score_asc" in tags:
            posts = utils.get_posts_by_tags(tags, db, sort_type="score")[::-1]
        elif "order:random" in tags:
            posts = utils.get_posts_by_tags(tags, db, sort_type="random")
        elif "order:id" in tags:
            posts = utils.get_posts_by_tags(tags, db)[::-1]
        else:
            posts = utils.get_posts_by_tags(tags, db)
        max_page = len(posts) // items_per_page + 1
        cnt = len(posts)
        posts = posts[(page - 1) * items_per_page : page * items_per_page]
        posts = [
            (*post, utils.test_file_type(post[1]), utils.is_fav(post[0], db))
            for post in posts
        ]

    tags = [tag.replace('"', '\\"') for tag in tags]
    # set cookie
    resp = make_response(
        render_template(
            "index.html",
            tags='","'.join(tags),
            tags_args=" ".join(tags),
            page=page,
            max_page=max_page,
            posts=posts,
            cnts=(page - 1) * items_per_page + 1,
            cnte=(page - 1) * items_per_page + len(posts),
            cnt=cnt,
            current_view_mode=current_view_mode,
            show_score=show_score,
            url_base=url_base,
            live=live,
            pool_info=pool_info,
        )
    )
    resp.set_cookie("nw", "1")
    return resp


@app.route(f"{url_base}/static/<file>")
def static_(file):
    return send_from_directory("static", file)


@app.route(f"{url_base}/add_fav")
def add_fav():
    post_id = request.args.get("post_id")
    with get_db() as conn:
        if utils.is_fav(post_id, conn):
            print(f"remove fav {post_id}")
            utils.remove_fav(post_id, conn)
            return jsonify({"status": "ok", "fav": False})
        else:
            print(f"add fav {post_id}")
            utils.add_fav(post_id, conn)
            return jsonify({"status": "ok", "fav": True})


@app.route(f"{url_base}/file/<user>/<file>")
def file_(user, file):
    live = request.args.get("live", "0") == "1"
    if live or user == "live":
        if not re.match(r"\d+_[a-zA-Z0-9_-]+", file):
            # return 404
            return jsonify({"status": "error", "message": "Invalid file name."}), 404
        id_, source = file.split("_", 1)
        source_url = (
            f"https://static1.e621.net/data/{source[0:2]}/{source[2:4]}/{source}"
        )
        print(f"Live file request: {source_url}")
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        file_path = os.path.join(cache_dir, file)

        # 对于视频文件，使用流式传输支持Range请求
        if file.lower().endswith((".mp4", ".webm", ".mov", ".avi", ".mkv", ".flv")):
            return stream_video_from_url(source_url, file_path)

        if os.path.exists(file_path):
            print(f"File {file} already exists in temp.")
            return send_file_partial(file_path)
        try:
            resp = download.get(source_url)
            if resp is None or resp.status_code != 200:
                return (
                    jsonify(
                        {"status": "error", "message": "File not found or timeout."}
                    ),
                    404,
                )
        except Exception as e:
            print(f"Error downloading file: {e}")
            return jsonify({"status": "error", "message": "Download failed."}), 500
        with open(file_path, "wb") as f:
            f.write(resp.content)
        response = make_response(send_file_partial(file_path))
        return response
    else:
        if file.startswith("-") and "_" in file:
            file = file.split("_")[-1]
        file_path = os.path.join(utils.data_dir, user, file)
        if not os.path.exists(file_path):
            return jsonify({"status": "error", "message": "File not found."}), 404
        # 对于本地文件也使用Range支持
        return send_file_partial(file_path)


@app.route(f"{url_base}/thumb/<user>/<file>")
def thumb_(user, file):
    live = request.args.get("live", "0") == "1"
    if live or user == "live":
        if file.endswith(".swf"):
            return send_file("static/flash.png")
        if not re.match(r"\d+_[a-zA-Z0-9_-]+", file):
            # return 404
            return jsonify({"status": "error", "message": "Invalid file name."}), 404
        id_, source = file.split("_", 1)
        # replace extension with .jpg
        if not source.endswith(".jpg"):
            source = source.rsplit(".", 1)[0] + ".jpg"
        source_url = f"https://static1.e621.net/data/preview/{source[0:2]}/{source[2:4]}/{source}"
        print(f"Live thumb request: {source_url}")
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        thumb_path = os.path.join(cache_dir, "thumb_" + file)
        if os.path.exists(thumb_path):
            print(f"Thumb {thumb_path} already exists in temp.")
            return send_file(thumb_path)
        try:
            resp = download.get(source_url)
            if resp is None or resp.status_code != 200:
                return (
                    jsonify(
                        {"status": "error", "message": "File not found or timeout."}
                    ),
                    404,
                )
        except Exception as e:
            print(f"Error downloading thumb: {e}")
            return (
                jsonify({"status": "error", "message": "Thumb download failed."}),
                404,
            )
        with open(thumb_path, "wb") as f:
            f.write(resp.content)
        response = make_response(send_file(thumb_path))
        return response
    else:
        if file.startswith("-") and "_" in file:
            file = file.split("_")[-1]
        id_ = file.split("_")[0]
        if not os.path.exists(os.path.join(utils.data_dir, user, file)):
            # try again with id only
            post = utils.get_post_by_id(id_, db)
            if post:
                user = post[2]
                file = f"{post[0]}_{post[1]}"
                if not os.path.exists(os.path.join(utils.data_dir, user, file)):
                    return (
                        jsonify({"status": "error", "message": "File not found."}),
                        404,
                    )
            else:
                return jsonify({"status": "error", "message": "File not found."}), 404
        return send_file(utils.thumb(os.path.join(utils.data_dir, user, file)))


@app.route(f"{url_base}/viewer/<user>/<file>")
def viewer_(user, file):
    """Wrapper page with iframe to prevent fullscreen exit on navigation"""
    q = request.args.get("q", "")
    page = request.args.get("page", 1, type=int)
    return render_template(
        "viewer.html",
        user=user,
        file=file,
        q=q,
        page=page,
        url_base=url_base,
    )


@app.route(f"{url_base}/view/<user>/<file>")
def view_(user, file):
    ip = request.access_route[-1]
    logger.log(f" {ip} - /view/ - {user} - {file}")
    file_type = utils.test_file_type(file)
    post_id = file.split("_")[0]

    # Get search context for navigation
    q = request.args.get("q", "")
    page = request.args.get("page", 1, type=int)

    # Determine next and previous items
    next_item = None
    prev_item = None

    if q:
        # Parse search parameters
        tags = q.split()
        sort_type = "id"
        if "order:score" in tags:
            sort_type = "score"
        elif "order:random" in tags:
            sort_type = "random"

        # Get posts from search results (cached)
        posts = utils.get_posts_by_tags(tags, db, sort_type=sort_type)

        # Find current post in results
        current_index = -1
        for i, post in enumerate(posts):
            if str(post[0]) == str(post_id):
                current_index = i
                break

        if current_index != -1:
            # Get next and prev items
            if current_index > 0:
                prev_post = posts[current_index - 1]
                prev_item = {
                    "user": prev_post[2],
                    "file": f"{prev_post[0]}_{prev_post[1]}",
                    "post_id": prev_post[0],
                }
            if current_index < len(posts) - 1:
                next_post = posts[current_index + 1]
                next_item = {
                    "user": next_post[2],
                    "file": f"{next_post[0]}_{next_post[1]}",
                    "post_id": next_post[0],
                }
    else:
        # Get all posts for navigation
        posts = utils.get_posts_by_tags([], db, sort_type="id")
        current_index = -1
        for i, post in enumerate(posts):
            if str(post[0]) == str(post_id):
                current_index = i
                break

        if current_index != -1:
            if current_index > 0:
                prev_post = posts[current_index - 1]
                prev_item = {
                    "user": prev_post[2],
                    "file": f"{prev_post[0]}_{prev_post[1]}",
                    "post_id": prev_post[0],
                }
            if current_index < len(posts) - 1:
                next_post = posts[current_index + 1]
                next_item = {
                    "user": next_post[2],
                    "file": f"{next_post[0]}_{next_post[1]}",
                    "post_id": next_post[0],
                }

    pools = utils.get_pools_by_post_id(post_id, db)

    if user == "live":
        (
            post_id,
            file_url,
            tags_str,
            score,
        ), artist = download.search_by_id(post_id)
        # print(tags_str)
        tags = tags_str.split(" ")
        tags = [(tag, "") for tag in tags]
        fav = False
    else:
        tags = utils.get_tags_by_post_id(post_id, db)
        score = utils.get_score(post_id, db)
        fav = utils.is_fav(post_id, db)
        artist = user
    return render_template(
        "view.html",
        user=user,
        artist=artist.replace(" ", "_"),
        pools=pools,
        file=file,
        tags=tags,
        file_type=file_type,
        score=score,
        post_id=int(post_id),
        fav=fav,
        url_base=url_base,
        next_item=next_item,
        prev_item=prev_item,
        q=q,
        page=page,
    )


@app.route(f"{url_base}/all_tags")
def all_tags():
    tags = utils.get_all_tags(db)[:1000]
    return render_template("all_tags.html", tags=tags, url_base=url_base)


@app.route(f"{url_base}/auto_complete")
def auto_complete():
    tag = request.args.get("tag", "").strip().lower()

    ip = request.access_route[-1]
    logger.log(f" {ip} - /auto_complete/ - {tag}")

    tag_list = []

    # Get all tags and artists
    all_tags = utils.get_all_tags(db)
    all_tags_count = {tag: count for tag, count in all_tags}

    if tag == "by":
        artists = []
        for i in os.listdir(data_dir):
            if i in all_tags_count:
                artists.append((i, all_tags_count[i]))
        artists = natsort.natsorted(artists, key=lambda x: x[1])[::-1]
        tag_list += artists
    for candidate in all_tags:
        if tag.replace("-", "") in candidate[0]:
            tag_list.append(candidate)
    # print(tag_list)
    return jsonify({"status": "ok", "suggestions": tag_list})


@app.route(f"{url_base}/downloader", methods=["GET", "POST"])
def downloader():
    ip = request.access_route[-1]
    logger.log(f" {ip} - /downloader/ - {dict(request.args)}")
    if request.method == "GET" and "json" in request.args:
        if utils.current_download_tag:
            return jsonify(
                {
                    "data": [utils.current_download_tag]
                    + [i[0] for i in utils.download_queue]
                }
            )
        else:
            return jsonify({"data": [i[0] for i in utils.download_queue]})
    elif request.method == "GET":
        return render_template("downloader.html", url_base=url_base)
    elif request.method == "POST":
        u_input = json.loads(request.data.decode("utf-8"))["input"]
        print("u_input:", u_input)
        if not u_input or u_input.endswith("tags="):
            return jsonify({"status": "error", "message": "No input provided."})
        print("-" * 10, u_input)
        if re.search(r"e621.net/posts/\d+", u_input) or u_input.isnumeric():
            tag = u_input.split("/")[-1]
            tag = tag.split("?")[0]
            tag = tag.replace("id:", "")
            tag = f"id:{tag}"
            type_ = "id"
        elif re.search(r"e621.net/pools/\d+", u_input) or "pool:" in u_input:
            if "tags=" in u_input:
                tags = u_input.split("tags=")[-1]
                tags = tags.split(" ")
                u_input = tags[0]
                if not u_input.startswith("pool:"):
                    return jsonify(
                        {
                            "status": "error",
                            "message": "Do not mix pool tag with other tags for download.",
                        }
                    )
            pool_id = u_input.split("/")[-1]
            pool_id = pool_id.split("?")[0]
            pool_id = pool_id.replace("pool:", "")
            tag = f"pool:{pool_id}"
            type_ = "pool"
        elif "tags=" in u_input or not u_input.isnumeric():
            tags = u_input.split("tags=")[-1]
            tags = tags.split(" ")
            if len(tags) == 0:
                return jsonify({"status": "error", "message": "No tags provided."})
            elif len(tags) > 1:
                print("Multiple tags provided, using the first one.")
            tag = tags[0]
            tag = tag.lower().strip()
            type_ = "tag"
        else:
            print("Invalid input format.")
            return jsonify({"status": "error", "message": "Invalid input format."})

        if (tag, type_) in utils.download_queue:
            return jsonify(
                {"status": "ok", "message": f"{tag} is already in the download queue."}
            )
        elif tag in download.ignore_tags or tag in download.artists_tags_exclude:
            return jsonify(
                {
                    "status": "error",
                    "message": f"{tag} is in the ignore list or excluded artists list.",
                }
            )
        else:
            utils.download_queue.append((tag, type_))
            return jsonify(
                {"status": "ok", "message": f"{tag} added to the download queue."}
            )


@app.route(f"{url_base}/pools")
def all_pools():
    q = request.args.get("q", "").strip().lower()
    page = request.args.get("page", 1, type=int)
    pools = utils.get_all_pools(db)
    items = []
    for pool in pools:
        id, name, desc, post_count, cover_post_id, cover_file_id = pool
        if q and q not in name.lower() and q not in str(id):
            continue
        cover_post = utils.get_post_by_id(cover_post_id, db)
        if not cover_post:
            cover_file = f"live/{cover_post_id}_{cover_file_id}"
        else:
            cover_file = f"{cover_post[2]}/{cover_post[0]}_{cover_post[1]}"
        items.append(
            {
                "id": id,
                "name": name,
                "description": desc,
                "post_count": post_count,
                "cover_file": cover_file,
            }
        )
    items = items[::-1]
    return render_template(
        "all_pools.html",
        pools=items[(page - 1) * 20 : page * 20],
        current_page=page,
        max_page=(len(items) + 19) // 20,
        url_base=url_base,
        q=q,
    )


@app.route(f"{url_base}/api/favs")
def api_favs():
    ip = request.access_route[-1]
    logger.log(f" {ip} - /api/favs/ - {dict(request.args)}")
    # return format [ (file_path1, timestamp1), (file_path2, timestamp2), ... ]
    with get_db() as conn:
        favs = utils.get_posts_by_tags(["fav:me"], conn, cache=False)
    favs = [
        (os.path.join(data_dir, f"{post[2]}/{post[0]}_{post[1]}"), time.time())
        for post in favs
    ]
    return jsonify(favs[::-1])


@app.route(f"{url_base}/to_main_tag")
def to_main_tag():
    ip = request.access_route[-1]
    post_id = request.args.get("id", "").strip()
    live = request.args.get("live", "0") == "1"
    if not post_id.isdigit():
        return jsonify({"status": "error", "message": "Invalid post ID."}), 400
    logger.log(f" {ip} - /to_main_tag/ - {post_id}")
    main_tag = utils.check_post_exists(post_id, db)
    if main_tag:
        return redirect(
            url_for(
                "index",
                tags=main_tag,
                live="1" if live else "0",
            )
        )
    else:
        print("Fetching main tag from live...")
        _, main_tag = download.search_by_id(post_id)
        if main_tag:
            return redirect(
                url_for(
                    "index",
                    tags=main_tag,
                    live="1" if live else "0",
                )
            )
        else:
            return jsonify({"status": "error", "message": "Post not found."}), 404


download_thread = threading.Thread(
    target=utils.download_worker, daemon=True, args=(db,)
)


def get_wsgi_app():
    utils.init_db(db)
    utils.get_all_tags(db)
    download_thread.start()
    return app


if __name__ == "__main__":
    utils.init_db(db)
    utils.get_all_tags(db)
    download_thread.start()
    app.run(host="0.0.0.0", debug=debug, port=port)
