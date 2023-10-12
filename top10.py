import os, random, re, requests, ruamel.yaml, sqlite3, time
from contextlib import closing
from datetime import datetime, timedelta
from lxml import html

now = datetime.now()
base = "https://flixpatrol.com"
expiration_days = 180
use_sleep = False
last_request = None
header = {
    "Accept-Language": "en-US,en;q=0.5",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0"
}

flix_data = {p: {} for p in [
    "netflix", "hbo", "disney", "amazon_prime", "apple_tv", "chili", "freevee", "globoplay", "google", "hulu",
    "itunes", "osn", "paramount_plus", "rakuten_tv", "shahid", "star_plus", "starz", "viaplay", "vudu"
]}

db_path = os.path.join(os.path.dirname(__file__), "ids.db")

with sqlite3.connect(db_path) as con:
    con.row_factory = sqlite3.Row
    with closing(con.cursor()) as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS flixpatrol_map (key INTEGER PRIMARY KEY, "
                    "flixpatrol_id TEXT UNIQUE, tmdb_id TEXT, media_type TEXT, expiration_date TEXT)")


def query_flixpatrol_map(flixpatrol_url, media_type):
    id_to_return = None
    expired = None
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            cursor.execute(f"SELECT * FROM flixpatrol_map WHERE flixpatrol_id = ? AND media_type = ?", (flixpatrol_url, media_type))
            row = cursor.fetchone()
            if row and row["tmdb_id"]:
                datetime_object = datetime.strptime(row["expiration_date"], "%Y-%m-%d")
                time_between_insertion = datetime.now() - datetime_object
                if "_" in row["tmdb_id"]:
                    id_to_return = row["tmdb_id"]
                else:
                    try:
                        id_to_return = int(row["tmdb_id"])
                    except ValueError:
                        id_to_return = row["tmdb_id"]
                expired = time_between_insertion.days > expiration_days
    return id_to_return, expired


def update_flixpatrol_map(expired, flixpatrol_url, tmdb_id, media_type):
    expiration_date = datetime.now() if expired is True else (datetime.now() - timedelta(days=random.randint(1, expiration_days)))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            cursor.execute(f"INSERT OR IGNORE INTO flixpatrol_map(flixpatrol_id) VALUES(?)", (flixpatrol_url,))
            cursor.execute("UPDATE flixpatrol_map SET tmdb_id = ?, expiration_date = ?, media_type = ? WHERE flixpatrol_id= ?",
                           (tmdb_id, expiration_date.strftime("%Y-%m-%d"), media_type, flixpatrol_url))


def inline_list(*li):
    ret = ruamel.yaml.comments.CommentedSeq(li) # noqa
    ret.fa.set_flow_style()
    return ret


def _request(url):
    global last_request
    url = f"{base}{url}"
    print(url)
    if use_sleep:
        last_request = random.randint(5, 15)
        print(f"Sleep: {last_request}")
        time.sleep(last_request)
    return html.fromstring(requests.get(url, headers=header).content)


def get_tmdb_id(flixpatrol_url, is_movie=True):
    media_type = "movie" if is_movie else "show"
    tmdb_id, expired = query_flixpatrol_map(flixpatrol_url, media_type)
    if tmdb_id and expired is False:
        return tmdb_id
    ids = _request(flixpatrol_url).xpath("//script[@type='application/ld+json']/text()")
    if len(ids) > 0 and ids[0] and "https://www.themoviedb.org" in ids[0]:
        match = re.search("(\\d+)", str(ids[0].split("https://www.themoviedb.org")[1]))
        if match:
            tmdb_id = int(match.group(1))
            update_flixpatrol_map(expired, flixpatrol_url, tmdb_id, media_type)
            return tmdb_id
    raise ValueError(f"TMDb {media_type.capitalize()} ID not found at {flixpatrol_url}: {ids}")


response = _request(f"/top10/streaming/world/{now.strftime('%Y-%m-%d')}/")
for p in flix_data:
    movie_links = response.xpath(f"//div[@id='{p.replace('_', '-')}-1']//td/a/@href")
    show_links = response.xpath(f"//div[@id='{p.replace('_', '-')}-2']//td/a/@href")
    if movie_links or show_links:
        flix_data[p]["world"] = {}
        if movie_links:
            flix_data[p]["world"]["movies"] = inline_list()
            for m in movie_links:
                try:
                    flix_data[p]["world"]["movies"].append(get_tmdb_id(m))
                except ValueError as e:
                    print(e)
        if show_links:
            flix_data[p]["world"]["shows"] = inline_list()
            for m in show_links:
                try:
                    flix_data[p]["world"]["shows"].append(get_tmdb_id(m, is_movie=False))
                except ValueError as e:
                    print(e)

country_links = response.xpath(f"//div[child::button[contains(text(), 'Worldwide')]]//a/@href")

for country_link in country_links:
    country = country_link.split("/")[3].replace("-", "_")
    print(country)
    response = _request(country_link)
    for p in flix_data:
        platform_link = f"//div[descendant::h2/span[contains(@class, 'platform-{p.replace('_', '-')}')]]/div/"
        movie_links = response.xpath(f"{platform_link}div[descendant::h3[text()='TOP 10 Movies']]//tr/td/a/@href")
        show_links = response.xpath(f"{platform_link}div[descendant::h3[text()='TOP 10 TV Shows']]//tr/td/a/@href")
        if movie_links or show_links:
            flix_data[p][country] = {}
            if movie_links:
                flix_data[p][country]["movies"] = inline_list()
                for m in movie_links:
                    try:
                        flix_data[p][country]["movies"].append(get_tmdb_id(m))
                    except ValueError as e:
                        print(e)
            if show_links:
                flix_data[p][country]["shows"] = inline_list()
                for m in show_links:
                    try:
                        flix_data[p][country]["shows"].append(get_tmdb_id(m, is_movie=False))
                    except ValueError as e:
                        print(e)

yaml = ruamel.yaml.YAML()
yaml.indent(mapping=2, sequence=2)
yaml.width = 4096
with open("top10.yml", 'w', encoding="utf-8") as fp:
    yaml.dump(flix_data, fp)

with open("README.md", "r") as f:
    readme_data = f.readlines()

readme_data[1] = f"Last generated at: {datetime.utcnow().strftime('%B %d, %Y %I:%M %p')} UTC\n"

with open("README.md", "w") as f:
    f.writelines(readme_data)
