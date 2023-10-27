import os, random, re, sys, time
from datetime import datetime, timedelta

if sys.version_info[0] != 3 or sys.version_info[1] < 11:
    print("Version Error: Version: %s.%s.%s incompatible please use Python 3.11+" % (sys.version_info[0], sys.version_info[1], sys.version_info[2]))
    sys.exit(0)

try:
    import requests
    from lxml import html
    from pmmutils import logging, util
    from pmmutils.args import PMMArgs
    from pmmutils.exceptions import Failed
    from pmmutils.yaml import YAML
except (ModuleNotFoundError, ImportError):
    print("Requirements Error: Requirements are not installed")
    sys.exit(0)

options = [
    {"arg": "ns", "key": "no-sleep",     "env": "NO_SLEEP",     "type": "bool", "default": False, "help": "Run without random sleep timers between requests."},
    {"arg": "tr", "key": "trace",        "env": "TRACE",        "type": "bool", "default": False, "help": "Run with extra trace logs."},
    {"arg": "lr", "key": "log-requests", "env": "LOG_REQUESTS", "type": "bool", "default": False, "help": "Run with every request logged."}
]
script_name = "TOP10"
base_dir = os.path.dirname(os.path.abspath(__file__))
pmmargs = PMMArgs("meisnate12/PMM-TOP10", base_dir, options, use_nightly=False)
logger = logging.PMMLogger(script_name, "stinger", os.path.join(base_dir, "logs"), is_trace=pmmargs["trace"], log_requests=pmmargs["log-requests"])
logger.screen_width = 160
logger.header(pmmargs, sub=True)
logger.separator("Parsing TOP10", space=False, border=False)
logger.start()
now = datetime.now()
base = "https://flixpatrol.com"
expiration_days = 180
header = {
    "Accept-Language": "en-US,en;q=0.5",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0"
}
platforms = [
    "netflix", "hbo", "disney", "amazon_prime", "apple_tv", "chili", "freevee", "globoplay", "google", "hulu",
    "itunes", "osn", "paramount_plus", "rakuten_tv", "shahid", "star_plus", "starz", "viaplay", "vudu"
]
ids = YAML(path=os.path.join(base_dir, "ids.yml"))
data = {}


def _request(url, return_time=False):
    sleep_time = 0 if pmmargs["no-sleep"] else random.randint(2, 6)
    logger.info(f"URL: {base}{url}{f' [Sleep: {sleep_time}]' if sleep_time else ''}")
    url_response = html.fromstring(requests.get(f"{base}{url}", headers=header).content)
    if sleep_time and return_time is False:
        time.sleep(sleep_time)
    if return_time:
        return url_response, sleep_time
    else:
        return url_response


def get_tmdb_ids(flixpatrol_urls, is_movie=True):
    output_ids = []
    for flixpatrol_url in flixpatrol_urls:
        tmdb_id = None
        flixpatrol_url = str(flixpatrol_url)
        expired = None
        if flixpatrol_url in ids:
            time_between_insertion = now - datetime.strptime(ids[flixpatrol_url]["saved_date"], "%Y-%m-%d")
            expired = time_between_insertion.days > expiration_days
            if expired is False:
                tmdb_id = ids[flixpatrol_url]["tmdb_id"]
        if tmdb_id is None:
            media_type = "movie" if is_movie else "show"
            url_response, sleep_time = _request(flixpatrol_url, return_time=True)
            id_list = url_response.xpath("//script[@type='application/ld+json']/text()")
            if len(id_list) > 0 and id_list[0] and "https://www.themoviedb.org" in id_list[0]:
                match = re.search(r"(\d+)", str(id_list[0].split("https://www.themoviedb.org")[1]))
                if match:
                    tmdb_id = int(match.group(1))
                    saved_date = now if expired is True else (now - timedelta(days=random.randint(1, expiration_days)))
                    ids[flixpatrol_url] = YAML.inline({"tmdb_id": tmdb_id, "media_type": media_type, "saved_date": saved_date.strftime("%Y-%m-%d")})
                    if sleep_time:
                        time.sleep(sleep_time)
                    tmdb_id = ids[flixpatrol_url]["tmdb_id"]
            if tmdb_id is None:
                logger.error(f"ERROR: TMDb {media_type.capitalize()} ID not found at {flixpatrol_url}: {id_list}")
                if sleep_time:
                    time.sleep(sleep_time)
        if tmdb_id:
            output_ids.append(tmdb_id)
    return output_ids


try:
    logger.info("\nWorld")
    response = _request(f"/top10/streaming/world/{now.strftime('%Y-%m-%d')}/")
    data["world"] = {}
    for platform in platforms:
        data["world"][platform] = {
            "movies": get_tmdb_ids(response.xpath(f"//div[@id='{platform.replace('_', '-')}-1']//td/a/@href")),
            "shows": get_tmdb_ids(response.xpath(f"//div[@id='{platform.replace('_', '-')}-2']//td/a/@href"), is_movie=False)
        }

    country_links = response.xpath(f"//div[child::button[contains(text(), 'Worldwide')]]//a/@href")
    num_countries = len(country_links)
    for i, country_link in enumerate(country_links, 1):
        country_name = country_link.split("/")[3].replace("-", "_")
        logger.info(f"\nCountry {i}/{num_countries}: {country_name}")
        response = _request(country_link)
        data[country_name] = {}
        for platform in platforms:
            platform_link = f"//div[descendant::h2/span[contains(@class, 'platform-{platform.replace('_', '-')}')]]/div/div[descendant::h3"
            data[country_name][platform] = {
                "movies": get_tmdb_ids(response.xpath(f"{platform_link}[text()='TOP 10 Movies']]//tr/td/a/@href")),
                "shows": get_tmdb_ids(response.xpath(f"{platform_link}[text()='TOP 10 TV Shows']]//tr/td/a/@href"), is_movie=False)
            }


    ids.yaml.width = 4096
    ids.save()
    ordinal = now.toordinal()
    os.makedirs(os.path.join(base_dir, "lists"), exist_ok=True)

    info_yaml = YAML(path=os.path.join(base_dir, "info.yml"), start_empty=True)
    info_yaml["platforms"] = platforms
    info_yaml["locations"] = [c for c in data]
    info_yaml.save()

    for country in data:
        country_yaml = YAML(path=os.path.join(base_dir, "lists", f"{country}.yml"), create=True)
        if ordinal not in country_yaml:
            country_yaml[ordinal] = None
        for platform, items in data[country].items():
            if items["movies"] or items["shows"]:
                if country_yaml[ordinal] is None:
                    country_yaml[ordinal] = {}
                country_yaml[ordinal][platform] = {}
                for media in ["movies", "shows"]:
                    if items[media]:
                        country_yaml[ordinal][platform][media] = YAML.inline(items[media])

        country_yaml.yaml.width = 4096
        keys = [k for k in country_yaml.data]
        keys.sort(reverse=True)
        country_yaml.data = {k: country_yaml[k] for i, k in enumerate(keys) if i < 30}
        country_yaml.save()

    with open("README.md", "r") as f:
        readme_data = f.readlines()

    readme_data[1] = f"Last generated at: {datetime.utcnow().strftime('%B %d, %Y %H:%M')} UTC\n"

    with open("README.md", "w") as f:
        f.writelines(readme_data)

    logger.separator(f"{script_name} Finished\nTotal Runtime: {logger.runtime()}")
except KeyboardInterrupt:
    ids.yaml.width = 4096
    ids.save()
    logger.info("IDs Saved")
