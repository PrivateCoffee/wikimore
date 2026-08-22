import json
import logging
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import escape
from typing import Dict, List, Tuple, Union
from urllib.parse import quote

from .cache import cache
from .config import urlopen

logger = logging.getLogger(__name__)

# Per-wiki license cache (license is the same for every page on a given wiki)
_licenses: Dict[str, dict | None] = {}


@cache.cached(timeout=86400, key_prefix="wikimedia_projects")
def get_wikimedia_projects() -> Tuple[
    Dict[str, str], Dict[str, Dict[str, Union[str, Dict[str, str]]]]
]:
    """Fetch the Wikimedia sitematrix and return ``(projects, languages)``.

    ``projects`` maps project code → display name (e.g. ``"wiki"`` → ``"Wikipedia"``).
    ``languages`` maps language code → ``{"name": str, "projects": {code: url}}``.
    Cached for 24 hours.
    """
    url = "https://meta.wikimedia.org/w/api.php?action=sitematrix&format=json"
    with urlopen(url) as response:
        data = json.loads(response.read().decode())

    projects = {}
    languages = {}

    for key, value in data["sitematrix"].items():
        if key.isdigit():
            language = value["name"]
            language_code = value["code"]
            language_projects = {}

            for site in value["site"]:
                language_projects[site["code"]] = site["url"]
                if language_code == "en":
                    projects[site["code"]] = site["sitename"]

            if language_projects:
                languages[language_code] = {
                    "projects": language_projects,
                    "name": language,
                }

    languages["special"] = {"projects": {}, "name": "Special"}

    for special in data["sitematrix"]["specials"]:
        sitename = special["sitename"]
        code = special["code"]
        language_code = special["lang"]

        if sitename == "Wikipedia":
            logger.warning(
                f"Wikipedia special project {code} in {language_code} has site name {sitename}"
            )
            sitename = code

        if language_code not in languages:
            language_code = "special"

        if code not in projects:
            projects[code] = sitename

        languages[language_code]["projects"][code] = special["url"]

    return projects, languages


def get_active_users(languages: dict) -> List[Tuple[str, int]]:
    """Return ``(lang_code, active_user_count)`` pairs sorted descending by count.

    Used to build the automatic language sort order when ``WIKIMORE_LANGSORT=auto``.
    Languages whose Wikipedia API call fails are silently omitted.
    """
    path = "/w/api.php?action=query&format=json&meta=siteinfo&siprop=statistics"
    active_users = {}

    def _fetch(lang, data):
        try:
            url = f"{data['projects']['wiki']}{path}"
            with urlopen(url) as response:
                result = json.loads(response.read().decode())
            return lang, result["query"]["statistics"]["activeusers"]
        except Exception as e:
            logger.error(f"Error fetching active users for {lang}: {e}")
            return lang, None

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {
            pool.submit(_fetch, lang, data): lang for lang, data in languages.items()
        }
        for future in as_completed(futures):
            lang, count = future.result()
            if count is not None:
                active_users[lang] = count

    return sorted(active_users.items(), key=lambda x: x[1], reverse=True)


@cache.memoize(timeout=3600)
def fetch_article_content(base_url: str, title: str, variant=None) -> str:
    """Fetch raw Parsoid HTML for ``title`` from the REST v1 API. Cached 1 h.

    Pass ``variant`` to request a specific language variant via ``Accept-Language``.
    Re-raises ``HTTPError`` so callers can handle 404/429 themselves.
    """
    logger.debug(f"Fetching article content for {title} from {base_url}")
    api_url = (
        f"{base_url}/api/rest_v1/page/html/"
        f"{escape(quote(title.replace(' ', '_')), True).replace('/', '%2F')}"
    )
    logger.debug(f"Article content URL: {api_url}")

    headers = {}
    if variant:
        headers["Accept-Language"] = variant

    try:
        with urlopen(api_url, headers) as response:
            return response.read().decode()
    except urllib.error.HTTPError:
        raise


@cache.memoize(timeout=1800)
def fetch_search_results(base_url: str, query: str) -> list:
    """Search ``base_url`` via the Action API and return the ``search`` result list. Cached 30 min."""
    srquery = escape(quote(query.replace(" ", "_")), True)
    url = (
        f"{base_url}/w/api.php?action=query&format=json&list=search&srsearch={srquery}"
    )
    logger.debug(f"Fetching search results from {url}")

    try:
        with urlopen(url) as response:
            data = json.loads(response.read().decode())
        return data["query"]["search"]
    except Exception as e:
        logger.error(f"Error fetching search results: {e}")
        raise


@cache.memoize(timeout=3600)
def fetch_article_info(base_url: str, title: str) -> dict:
    """Fetch page metadata (info, pageprops, langlinks, categories) from the Action API. Cached 1 h."""
    logger.debug(f"Fetching article info for {title} from {base_url}")
    url = (
        f"{base_url}/w/api.php?action=query&format=json"
        f"&titles={escape(quote(title.replace(' ', '_')), True)}"
        f"&prop=info|pageprops|categoryinfo|langlinks|categories"
        f"&lllimit=500&cllimit=500&llprop=url"
    )
    with urlopen(url) as response:
        logger.debug(f"Tried to fetch info for {title} from {url}")
        return json.loads(response.read().decode())


@cache.memoize(timeout=86400)
def fetch_badge_data(badge_id: str, lang: str) -> dict:
    """Fetch Wikidata entity data for a badge (e.g. "Featured Article"). Cached 24 h."""
    url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&ids={badge_id}&languages={lang}"
    with urlopen(url) as response:
        logger.debug(f"Tried to fetch badge {badge_id} from {url}")
        return json.loads(response.read().decode())


@cache.memoize(timeout=3600)
def fetch_category_members(base_url: str, title: str) -> list:
    """Fetch members of a category page via the Action API. Cached 1 h.

    Returns raw member dicts (``pageid``, ``ns``, ``title``); URL generation
    is left to the caller so this function stays cache-safe and Flask-free.
    """
    base_api_url = (
        f"{base_url}/w/api.php?action=query&format=json&list=categorymembers"
        f"&cmtitle={escape(quote(title.replace(' ', '_')), True)}&cmlimit=500"
    )
    all_members = []
    next_url = base_api_url

    while next_url:
        with urlopen(next_url) as response:
            logger.debug(f"Fetching category members for {title} from {next_url}")
            data = json.loads(response.read().decode())

        all_members += data["query"]["categorymembers"]

        if "continue" in data:
            next_url = base_api_url + f"&cmcontinue={data['continue']['cmcontinue']}"
        else:
            next_url = None

    return all_members


@cache.memoize(timeout=86400)
def fetch_license_info(base_url: str, title: str) -> dict | None:
    """Return the license dict for the wiki at ``base_url``. Cached 24 h.

    The license is the same for every page on a given wiki, so results are also
    stored in the module-level ``_licenses`` dict to avoid redundant API calls
    within the same process lifetime.
    """
    if base_url not in _licenses:
        try:
            url = f"{base_url}/w/rest.php/v1/page/{escape(quote(title.replace(' ', '_')), True)}"
            with urlopen(url) as response:
                data = json.loads(response.read().decode())
            _licenses[base_url] = data["license"]
        except Exception:
            _licenses[base_url] = None
    return _licenses[base_url]


@cache.memoize(timeout=1800)
def fetch_file_info(base_url: str, title: str) -> dict:
    """Fetch imageinfo metadata (URL, size, MIME type, uploader) for a File page. Cached 30 min."""
    url = (
        f"{base_url}/w/api.php?action=query&format=json"
        f"&titles={escape(quote(title.replace(' ', '_')), True)}"
        f"&prop=imageinfo&iiprop=url|size|mime|user|timestamp|mediatype"
    )
    try:
        with urlopen(url) as response:
            data = json.loads(response.read().decode())
        pages = data["query"]["pages"]
        page = next(iter(pages.values()))
        return page.get("imageinfo", [{}])[0]
    except urllib.error.HTTPError:
        raise
    except Exception as e:
        logger.error(f"Error fetching file info for {title}: {e}")
        return {}


@cache.memoize(timeout=86400)
def fetch_interwiki_map(base_url: str) -> dict[str, str]:
    """Fetch the interwiki prefix→URL-template map for the wiki at base_url. Cached 24 h.

    Returns a dict mapping each prefix to its URL template, where ``$1`` is
    the placeholder for the article title.  Returns an empty dict on failure
    so callers can treat missing entries as non-interwiki titles.
    """
    url = f"{base_url}/w/api.php?action=query&format=json&meta=siteinfo&siprop=interwikimap"
    with urlopen(url) as response:
        data = json.loads(response.read().decode())
    return {
        entry["prefix"]: entry["url"]
        for entry in data.get("query", {}).get("interwikimap", [])
    }


@cache.memoize(timeout=3600)
def fetch_article_summary(base_url: str, title: str) -> dict:
    """Fetch REST v1 page summary for article hover previews. Cached 1 h.

    Returns a dict with title, description, extract, and thumbnail keys
    (only those present in the upstream response).
    Re-raises ``HTTPError`` so callers can handle 404/429 themselves.
    """
    url = f"{base_url}/api/rest_v1/page/summary/{escape(quote(title.replace(' ', '_')), True)}"
    try:
        with urlopen(url) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError:
        raise
    return {
        k: data[k]
        for k in ("title", "description", "extract", "thumbnail")
        if k in data
    }


@cache.memoize(timeout=1800)
def fetch_file_page_content(base_url: str, title: str) -> str:
    """Fetch the rendered HTML description of a File page via the parse API. Cached 30 min."""
    url = (
        f"{base_url}/w/api.php?action=parse&format=json"
        f"&page={escape(quote(title.replace(' ', '_')), True)}&prop=text"
    )
    try:
        with urlopen(url) as response:
            data = json.loads(response.read().decode())
        return data.get("parse", {}).get("text", {}).get("*", "")
    except urllib.error.HTTPError:
        raise
    except Exception as e:
        logger.error(f"Error fetching file description for {title}: {e}")
        return ""
