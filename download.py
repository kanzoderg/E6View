#!/usr/bin/python3

import os, sys, re
import requests
from bs4 import BeautifulSoup as Soup
import json, time
import config

headers = {
    "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36",
    "referer": "https://e621.net",
}

target_path = config.data_dir
proxies = config.proxies
if not proxies:
    proxies = {}
s = requests.Session()
s.proxies.update(proxies)
s.headers.update(headers)


def timeit(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"Function {func.__name__} took {end_time - start_time:.2f} seconds")
        return result

    return wrapper


def get(url: str) -> requests.Response:
    for i in range(3):  # 减少重试次数从6到3
        try:
            resp = s.get(url, timeout=15)  # 减少超时从30到15秒
            return resp
        except requests.Timeout:
            print(f"Timeout for {url}, retrying {i+1}/3")
        except Exception as e:
            print(f"Error: {e}, retrying {i+1}/3")
    print("Failed after 3 attempts.")
    return None  # 返回None而不是exit


def accept_tos():
    if os.path.exists("cookies.json"):
        with open("cookies.json", "r") as f:
            cookies = json.load(f)
            s.cookies.update(cookies)
        print("Loaded cookies from file.")
        return
    print("Accepting TOS...")
    # get auth-token first
    url = "https://e621.net/"
    resp = get(url)
    soup = Soup(resp.text, "html.parser")
    auth_token = soup.find(id="tos-form").input.attrs["value"]
    print("Auth token:", auth_token)
    # get cookies after accepting TOS
    url = "https://e621.net/terms_of_use/accept"
    payload = "authenticity_token=" + auth_token + "&age=on&terms=on&state=accepted"
    resp = s.post(url, data=payload, allow_redirects=False)
    print(resp.text)
    if resp is None:
        print("Failed to accept TOS.")
        return
    print("TOS acceptance response:", resp.cookies)
    if not "tos_accepted" in resp.cookies:
        print("Failed to accept TOS, no tos_accepted cookie found.")
        return
    print("Accepted TOS, cookies updated.")
    # save cookies to file
    with open("cookies.json", "w") as f:
        json.dump(s.cookies.get_dict(), f)


@timeit
def search(tag: str | list, page=1, limit=999):
    items = []
    cnt = 0
    while True:
        if isinstance(tag, list):
            tag = "+".join(tag)
        url = f"https://e621.net/posts?page={page}&tags={tag}"
        resp = get(url)
        if resp is None:
            print(f"Failed to fetch page {page} for tag {tag}")
            break
        html = resp.text
        soup = Soup(html, "html.parser")
        articles = []
        for article in soup.find_all("article"):
            data_id = article.attrs["data-id"]
            data_file_url = article.attrs["data-file-url"]
            data_tags = article.attrs["data-tags"]
            data_score = article.attrs["data-score"]
            articles.append((data_id, data_file_url, data_tags, data_score))
        if len(articles) == 0 or page > 100:
            break
        else:
            items += articles
        page += 1
        cnt += 1
        if cnt >= limit:
            break
    return items


# Exclude tags that are not artists or are warnings
ignore_tags = [
    "male",
    "female",
    "solo",
    "group",
    "futa",
    "futanari",
    "anthro",
    "feral",
    "mammal",
]

artists_tags_exclude = [
    "sound_warning",
    "sound warning",
    "conditional_dnp",
    "conditional dnp",
    "epilepsy_warning",
    "epilepsy warning",
    "third-party_edit",
    "third-party edit",
]


@timeit
def search_by_id(post_id: str):
    url = f"https://e621.net/posts/{post_id}"
    resp = get(url)
    if resp is None:
        raise Exception(f"Failed to fetch post {post_id}")
    html = resp.text
    # print(html)
    soup = Soup(html, "html.parser")
    data_file_url = soup.find(class_="ptbr-fullscreen").a.attrs["href"]
    artists = soup.find_all("a", {"itemprop": "author"})
    artists = [a.span.text.strip() for a in artists]
    artists = [a for a in artists if not a in artists_tags_exclude]
    if len(artists) == 0:
        artists = ["unknown_artist"]
    artist = artists[0]
    artist = (
        artist.lower()
        .replace("Uploaded by the artist".lower(), "")
        .replace("\n", "")
        .strip()
        .replace(" ", "_")
    )
    data_tags = soup.find(id="image-container").attrs["data-tags"]
    data_score = soup.find("span", {"class": "post-score"}).text.strip()
    return (
        post_id,
        data_file_url,
        data_tags,
        data_score,
    ), artist


def get_pool_items(pool_id: str):
    print(f"Fetching pool {pool_id}...")
    all_items = []
    page = 1
    title = ""
    description = ""
    while True:
        url = f"https://e621.net/pools/{pool_id}?page={page}"
        resp = get(url)
        if resp is None:
            print(f"Failed to fetch pool page {page} for pool {pool_id}")
            break
        html = resp.text
        with open("debug_pool.html", "w") as f:
            f.write(html)
        soup = Soup(html, "html.parser")
        if page == 1:
            title = soup.find("h2").text.strip()
            title = title.replace("\n", "")
            while "  " in title:
                title = title.replace("  ", " ")
            print(f"Pool title: {title}")
            # get description, keep only <br> tags
            description = soup.find(id="description").text.strip()
            print(f"Pool description: {description}")
        items = []
        for article in soup.find_all("article"):
            data_id = article.attrs["data-id"]
            data_file_url = article.attrs["data-file-url"]
            items.append((data_id, data_file_url))
        if len(items) == 0 or page > 100:
            break
        else:
            all_items += items
        page += 1
    # remove duplicates, while preserving order
    all_items = list(dict.fromkeys(all_items))
    return all_items, title, description


def download(item, tag):
    data_id, data_file_url, data_tags, data_score = item
    tag_path = os.path.join(target_path, tag)
    filename = f"{data_id}_{data_file_url.split('/')[-1]}"
    meta_filename = filename + ".json"

    # Handle old filename format (without post_id prefix)
    if os.path.exists(os.path.join(tag_path, filename.split("_")[-1])):
        print(
            "Renaming",
            os.path.join(tag_path, filename.split("_")[-1]),
            "->",
            os.path.join(tag_path, filename),
        )
        os.rename(
            os.path.join(tag_path, filename.split("_")[-1]),
            os.path.join(tag_path, filename),
        )

    # Save metadata for the file
    os.makedirs(tag_path, exist_ok=True)
    meta_data = {
        "post_id": data_id,
        "file_url": data_file_url,
        "tags": data_tags,
        "score": data_score,
    }
    with open(os.path.join(tag_path, meta_filename), "w") as f:
        json.dump(meta_data, f, indent=2)

    if os.path.exists(os.path.join(tag_path, filename)):
        print("skip." + " " * 10, flush=True)
        return
    if os.path.exists(os.path.join(config.cache_dir, filename)):
        print("Found in temp, copying to target path.")
        os.system(f'cp "{os.path.join(config.cache_dir, filename)}" "{tag_path}"')
        print("Copied." + " " * 10, flush=True)
        return
    resp = get(data_file_url)
    if resp is None:
        print(f"Failed to download {data_file_url}")
        return
    bin_ = resp.content
    try:
        with open(os.path.join(tag_path, filename), "wb") as f:
            f.write(bin_)
        print("done." + " " * 10, flush=True)
    except Exception as e:
        print(f"Failed to save file {filename}: {e}")
        return


accept_tos()

if __name__ == "__main__":
    # tags_to_get = []
    # if len(sys.argv) >= 2:
    #     tags = sys.argv[1:]
    #     for tag in tags:
    #         if "tags=" in tag:
    #             tag = tag.split("tags=")[-1]
    #         if re.match(r"https://e621.net/posts/\d+", tag):
    #             tag = tag.split("/")[-1]
    #             if "?" in tag:
    #                 tag = tag.split("?")[0]
    #             if "/" in tag:
    #                 tag = tag.strip("/")
    #         if tag.endswith("/"):
    #             tag = tag[:-1]
    #         if "/" in tag:
    #             tag = tag.split("/")[-1]
    #         tag = tag.strip().lower()
    #         tags_to_get.append(tag)
    # else:
    #     tag = input(">>").strip().lower()
    #     tags_to_get.append(tag)
    # print(tags_to_get)
    # for tag in tags_to_get:
    #     # print("-" * 20)
    #     print(tag)
    #     if tag.isnumeric():
    #         item, tag = search_by_id(tag)
    #         print("artist:", tag)
    #         items = [item]
    #     else:
    #         items = search(tag)
    #     print(f"Found {len(items)} items for {tag}.")
    #     print("downloading...")
    #     for i, item in enumerate(items):
    #         print(f"[{i+1}/{len(items)}]", item[0], end=" ")
    #         download(item, tag)
    #     print()
    pools_to_get = []
    if len(sys.argv) >= 2:
        pool_ids = sys.argv[1:]
        for pool_id in pool_ids:
            if "pools/" in pool_id:
                pool_id = pool_id.split("pools/")[-1]
            if "?" in pool_id:
                pool_id = pool_id.split("?")[0]
            if "/" in pool_id:
                pool_id = pool_id.strip("/")
            pool_id = pool_id.strip().lower()
            pools_to_get.append(pool_id)
    else:
        pool_id = input(">>").strip().lower()
        pools_to_get.append(pool_id)
    print(pools_to_get)
    for pool_id in pools_to_get:
        print(pool_id)
        item_ids, title, description = get_pool_items(pool_id)
        print(title)
        print(description)
        print(f"Found {len(item_ids)} items for pool {pool_id}.")
        print("Downloading items...")

        artist_tags = set()
        for i, (post_id, file_url) in enumerate(item_ids):
            try:
                print(f"[{i+1}/{len(item_ids)}] Fetching post {post_id}...", end=" ")
                item, artist = search_by_id(post_id)
                artist_tags.add(artist)
                # Download the file to artist folder
                download(item, artist)
                print()
            except Exception as e:
                print(f"Error downloading post {post_id}: {e}")

        print(f"\nPool {pool_id} download complete!")
        print(f"Files saved to artist folders: {', '.join(sorted(artist_tags))}")
