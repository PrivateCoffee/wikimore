import json
import logging
import os
import pathlib
import re
import sys
import time
import urllib.error
from typing import Text, Tuple, Union
from urllib.parse import quote, unquote, urlencode, urlparse

from bs4 import BeautifulSoup
from flask import (
    Flask,
    Response,
    redirect,
    request,
    url_for,
)
from flask import (
    render_template as flask_render_template,
)

from .cache import cache
from .config import DEBUG_ENABLED, get_retry_after, get_version, urlopen
from .fetchers import (
    fetch_article_content,
    fetch_article_info,
    fetch_article_summary,
    fetch_badge_data,
    fetch_category_members,
    fetch_file_info,
    fetch_file_page_content,
    fetch_interwiki_map,
    fetch_license_info,
    fetch_search_results,
    get_active_users,
    get_wikimedia_projects,
)

logger = logging.getLogger(__name__)


def create_app():
    """Create and configure the Flask app."""
    app = Flask(__name__)
    app.static_folder = pathlib.Path(__file__).parent / "static"
    if app.logger.handlers:
        app.logger.removeHandler(app.logger.handlers[0])
    cache.init_app(app)
    return app


app = create_app()


_SITEMATRIX_MAX_RETRIES = 5
_SITEMATRIX_DEFAULT_WAIT = 60

for _attempt in range(_SITEMATRIX_MAX_RETRIES):
    try:
        app.wikimedia_projects, app.languages = get_wikimedia_projects()
        break
    except urllib.error.HTTPError as e:
        if e.code == 429 and _attempt < _SITEMATRIX_MAX_RETRIES - 1:
            wait = get_retry_after(e) or _SITEMATRIX_DEFAULT_WAIT
            logger.warning(
                f"Rate limited fetching sitematrix, retrying in {wait}s "
                f"(attempt {_attempt + 1}/{_SITEMATRIX_MAX_RETRIES})"
            )
            time.sleep(wait)
        else:
            logger.fatal(f"Failed to fetch Wikimedia sitematrix at startup: {e}")
            sys.exit(1)
    except Exception as e:
        logger.fatal(f"Failed to fetch Wikimedia sitematrix at startup: {e}")
        sys.exit(1)

logger.debug(
    f"Loaded {len(app.wikimedia_projects)} Wikimedia projects and {len(app.languages)} languages"
)


if os.environ.get("WIKIMORE_NO_LANGSORT", os.environ.get("NO_LANGSORT", False)):
    LANGSORT = []
elif (
    langsort_env := os.environ.get("WIKIMORE_LANGSORT", os.environ.get("LANGSORT"))
) == "auto":
    LANGSORT = [lang for lang, _ in get_active_users(app.languages)[:50]]
elif langsort_env:
    LANGSORT = langsort_env.split(",")
else:
    LANGSORT = ["en", "es", "ja", "de", "fr", "zh", "ru", "it", "pt", "pl", "nl", "ar"]


def langsort(input: list[dict], key: str = "lang") -> list[dict]:
    """Sort a list of dicts so that languages in LANGSORT come first.

    Args:
        input: List of dicts each containing a language code under `key`.
        key: The dict key holding the language code (default: ``"lang"``).

    Returns:
        The re-ordered list, with LANGSORT languages first in that order,
        followed by all remaining languages in their original order.
    """
    if not LANGSORT:
        return input

    output = []
    for lang in LANGSORT:
        for item in input:
            if item[key] == lang:
                output.append(item)
    for item in input:
        if item[key] not in LANGSORT:
            output.append(item)
    return output


logger.debug("Initialized language sort order")

app_languages = [
    {"lang": lang, "name": data["name"]} for lang, data in app.languages.items()
]
app_languages = langsort(app_languages)
app.languages = {entry["lang"]: app.languages[entry["lang"]] for entry in app_languages}

# Build reverse domain -> (project, lang, base_url) lookup for O(1) route resolution
app.domain_to_wiki_info = {}
for _lang, _lang_data in app.languages.items():
    for _project, _project_url in _lang_data["projects"].items():
        _netloc = urlparse(_project_url).netloc
        app.domain_to_wiki_info[_netloc] = (_project, _lang, _project_url)

logger.debug(f"Indexed {len(app.domain_to_wiki_info)} wiki domains")


def render_template(*args, **kwargs) -> Text:
    """Wrapper around Flask's ``render_template`` that injects ``languages`` and
    ``wikimedia_projects`` into every template context."""
    kwargs.setdefault("lang", "en")
    kwargs.setdefault("project", "wiki")
    kwargs.setdefault("domain", None)
    return flask_render_template(
        *args,
        **kwargs,
        languages=app.languages,
        wikimedia_projects=app.wikimedia_projects,
    )


def get_proxy_url(url: str) -> str:
    """Return a ``/proxy?url=...`` URL for Wikimedia Commons/Maps URLs; pass
    all other URLs through unchanged."""
    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith("https://upload.wikimedia.org/") and not url.startswith(
        "https://maps.wikimedia.org/"
    ):
        logger.debug(f"Not generating proxy URL for {url}")
        return url

    logger.debug(f"Generating proxy URL for {url}")
    return f"/proxy?{urlencode({'url': url})}"


def render_rate_limited(
    retry_after: int | None,
    lang: str = "en",
    project: str = "wiki",
    domain: str | None = None,
) -> tuple:
    content = "<p>The upstream server is rate-limiting requests."
    if retry_after:
        content += f' This page will reload automatically in <span id="wm-countdown">{retry_after}</span> seconds.'
    else:
        content += " Please try again later."
    content += "</p>"
    return (
        render_template(
            "article.html",
            title="Too Many Requests",
            content=content,
            retry_after=retry_after,
            lang=lang,
            project=project,
            domain=domain,
        ),
        429,
    )


_WIKIMEDIA_THUMB_SIZES = [
    24,
    48,
    120,
    200,
    240,
    320,
    400,
    640,
    800,
    1024,
    1280,
    1920,
    2560,
]
_WIKIMEDIA_THUMB_RE = re.compile(
    r"(upload\.wikimedia\.org/.+/thumb/.+/)(\d+)(px-[^/]+)$"
)


def _snap_thumb_size(url: str) -> str:
    m = _WIKIMEDIA_THUMB_RE.search(url)
    if not m:
        return url
    requested = int(m.group(2))
    snapped = next(
        (s for s in _WIKIMEDIA_THUMB_SIZES if s >= requested),
        _WIKIMEDIA_THUMB_SIZES[-1],
    )
    if snapped == requested:
        return url
    return url[: m.start(2)] + str(snapped) + url[m.end(2) :]


@app.route("/proxy")
def proxy() -> bytes:
    """Proxy Wikimedia Commons and Wikimedia Maps assets through this server."""
    url = request.args.get("url")

    if not url or not (
        url.startswith("https://upload.wikimedia.org/")
        or url.startswith("https://maps.wikimedia.org/")
    ):
        logger.error(f"Invalid URL for proxying: {url}")
        return "Invalid URL"

    logger.debug(f"Proxying {url}")

    try:
        response = urlopen(url)
    except urllib.error.HTTPError as e:
        return Response(status=e.code)

    content_type = response.headers.get("Content-Type", "application/octet-stream")

    def stream():
        try:
            while chunk := response.read(65536):
                yield chunk
        finally:
            response.close()

    return Response(stream(), content_type=content_type)


@app.route("/")
def home(project=None, lang=None) -> Text:
    """Render the home page."""
    return render_template("home.html", project=project, lang=lang)


@app.route("/search", methods=["GET", "POST"])
def search() -> Union[Text, Response]:
    """Handle search form submission; redirect to search results or the project main page."""
    if request.method == "POST":
        query = request.form["query"]
        lang = request.form["lang"]
        project = request.form["project"]

        if not lang or not project:
            return render_template(
                "article.html",
                title="Error",
                content="Please select a language and a project.",
            )

        base_url = _resolve_base_url(project, lang)
        if not base_url:
            return render_template(
                "article.html",
                title="Error",
                content=f"Project {project}/{lang} not found.",
            )

        domain = urlparse(base_url).netloc

        if not query:
            return redirect(url_for("index_php_redirect_by_domain", domain=domain))

        return redirect(url_for("search_results_by_domain", domain=domain, query=query))
    return render_template("search.html")


@app.route("/<domain>/<path:url>")
def inbound_redirect(domain: str, url: str) -> Union[Text, Response, Tuple[Text, int]]:
    """Catch-all for domain-prefixed URLs not matched by a more specific route."""
    if domain not in app.domain_to_wiki_info:
        return (
            render_template(
                "article.html",
                title="Project does not exist",
                content=f"Sorry, {domain} is not a recognized wiki.",
            ),
            404,
        )
    return (
        render_template(
            "article.html",
            title="Page not found",
            content=f"The requested path was not found on {domain}.",
            domain=domain,
        ),
        404,
    )


def _resolve_base_url(project: str, lang: str) -> str | None:
    base_url = app.languages.get(lang, {}).get("projects", {}).get(project)
    if not base_url:
        base_url = app.languages.get("special", {}).get("projects", {}).get(project)
    return base_url


def _resolve_for_domain(domain: str) -> tuple[str, str, str] | None:
    """Return ``(project, lang, base_url)`` for a known wiki domain, or ``None``."""
    return app.domain_to_wiki_info.get(domain)


def _wikimore_url_for_external(url: str) -> str | None:
    """Return a wikimore route URL for a Wikimedia URL, or None if unrecognised.

    Handles ``//`` protocol-relative URLs by assuming ``https``.  Returns None
    for non-Wikimedia domains so callers can fall back to linking externally.
    """
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith("https://"):
        return None
    parts = urlparse(url)
    netloc = parts.netloc
    if netloc not in app.domain_to_wiki_info:
        return None
    path_parts = parts.path.split("/")
    target_title = unquote("/".join(path_parts[2:])) if len(path_parts) >= 3 else None
    if target_title:
        return url_for("wiki_article_by_domain", domain=netloc, title=target_title)
    return url_for("index_php_redirect_by_domain", domain=netloc)


@app.route("/<domain>/wiki/<path:title>")
def wiki_article_by_domain(
    domain: str, title: str
) -> Union[Text, Response, Tuple[Text, int]]:
    """Fetch and render a Wikimedia article for the given wiki domain (canonical URL format)."""
    info = _resolve_for_domain(domain)
    if not info:
        return (
            render_template(
                "article.html",
                title="Project does not exist",
                content=f"Sorry, {domain} is not a recognized wiki.",
            ),
            404,
        )
    project, lang, base_url = info

    title = unquote(title)

    prefix, sep, rest = title.partition(":")
    if sep and prefix in app.languages:
        target_project_url = app.languages.get(prefix, {}).get("projects", {}).get(project)
        if target_project_url:
            target_domain = urlparse(target_project_url).netloc
            return redirect(url_for("wiki_article_by_domain", domain=target_domain, title=rest))
        return redirect(url_for("wiki_article_by_domain", domain=domain, title=rest))

    if sep:
        try:
            interwiki_map = fetch_interwiki_map(base_url)
        except Exception:
            interwiki_map = {}
        if prefix in interwiki_map:
            ext_url = interwiki_map[prefix].replace(
                "$1", quote(rest.replace(" ", "_"), safe=":@!$&'()*+,;=")
            )
            return redirect(_wikimore_url_for_external(ext_url) or ext_url)

    try:
        article_info = fetch_article_info(base_url, title)
        page = article_info["query"]["pages"].popitem()[1]

        category_members = []
        interwiki = []
        badges = []
        categories = []

        langlinks = page.get("langlinks", [])
        logger.debug(f"Original Interwiki links for {title}: {langlinks}")

        for link in langlinks:
            try:
                interwiki_lang = link["lang"]
                interwiki_title = link["*"]

                logger.debug(
                    f"Generating interwiki link for: {interwiki_lang}.{project}/{interwiki_title}"
                )

                if interwiki_lang in app.languages:
                    target_project_url = app.languages[interwiki_lang].get("projects", {}).get(project)
                    if target_project_url:
                        link["url"] = url_for(
                            "wiki_article_by_domain",
                            domain=urlparse(target_project_url).netloc,
                            title=interwiki_title,
                        )
                    link["langname"] = app.languages[interwiki_lang]["name"]
                else:
                    parts = urlparse(link["url"])
                    if parts.netloc in app.domain_to_wiki_info:
                        link["url"] = url_for(
                            "wiki_article_by_domain",
                            domain=parts.netloc,
                            title=interwiki_title,
                        )
                        _, matched_lang, _ = app.domain_to_wiki_info[parts.netloc]
                        link["langname"] = app.languages.get(matched_lang, {}).get(
                            "name", interwiki_lang
                        )
                    else:
                        logger.debug(
                            f"No language match found for {interwiki_lang} ({link['url']}), using raw URL"
                        )
                        link["langname"] = interwiki_lang

                interwiki.append(link)

            except KeyError as e:
                logger.error(
                    f"Error processing interwiki link for title {title} in language {lang}: {e}"
                )

        props = page.get("pageprops", {})
        for prop in props:
            if prop.startswith("wikibase-badge-"):
                try:
                    badge_id = prop.replace("wikibase-badge-", "")
                    badge_data = fetch_badge_data(badge_id, lang)
                    badge = badge_data["entities"][badge_id]["labels"][lang]["value"]
                    badge_image = badge_data["entities"][badge_id]["claims"]["P18"][0][
                        "mainsnak"
                    ]["datavalue"]["value"]
                    badges.append(
                        {
                            "title": badge,
                            "url": f"https://www.wikidata.org/wiki/{badge_id}",
                            "image": get_proxy_url(
                                f"https://commons.wikimedia.org/wiki/Special:Redirect/file/{badge_image}"
                            ),
                        }
                    )
                except Exception as e:
                    logger.error(f"Error fetching badge {prop}: {e}")

        if "categoryinfo" in page:
            category_members = fetch_category_members(base_url, title)
            for member in category_members:
                member["url"] = url_for(
                    "wiki_article_by_domain", domain=domain, title=member["title"]
                )

        if "categories" in page:
            categories = page["categories"]
            for category in categories:
                category["url"] = url_for(
                    "wiki_article_by_domain", domain=domain, title=category["title"]
                )

    except urllib.error.HTTPError as e:
        if e.code == 429:
            return render_rate_limited(
                get_retry_after(e), lang=lang, project=project, domain=domain
            )
        logger.error(f"Error fetching article info: {e}")
        return (
            render_template(
                "article.html",
                title="Error",
                content=f"An error occurred while fetching information about the article {title}.",
                lang=lang,
                project=project,
                domain=domain,
            ),
            500,
        )
    except Exception as e:
        logger.error(f"Error fetching article info: {e}")
        return (
            render_template(
                "article.html",
                title="Error",
                content=f"An error occurred while fetching information about the article {title}.",
                lang=lang,
                project=project,
                domain=domain,
            ),
            500,
        )

    interwiki = langsort(interwiki)

    if page.get("ns") == 6:
        try:
            file_info = fetch_file_info(base_url, title)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                return render_rate_limited(
                    get_retry_after(e), lang=lang, project=project, domain=domain
                )
            raise

        if file_info.get("url"):
            file_info["proxied_url"] = get_proxy_url(file_info["url"])

        size = file_info.get("size", 0)
        if size < 1024:
            file_info["size_str"] = f"{size} B"
        elif size < 1024 * 1024:
            file_info["size_str"] = f"{size / 1024:.1f} KB"
        else:
            file_info["size_str"] = f"{size / (1024 * 1024):.1f} MB"

        try:
            file_desc_html = fetch_file_page_content(base_url, title)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                return render_rate_limited(
                    get_retry_after(e), lang=lang, project=project, domain=domain
                )
            raise

        if file_desc_html:
            desc_soup = BeautifulSoup(file_desc_html, "html.parser")

            for a in desc_soup.find_all("a", href=True) + desc_soup.find_all(
                "area", href=True
            ):
                href = a["href"]
                if href.startswith("/wiki/"):
                    a["href"] = f"/{domain}{href}"

            for span in desc_soup.find_all("span", class_="mw-editsection"):
                span.decompose()

            for style in desc_soup.find_all("style"):
                style.decompose()

            for img in desc_soup.find_all("img"):
                img["src"] = get_proxy_url(img["src"])
                img["loading"] = "lazy"

            for source in desc_soup.find_all("source"):
                source["src"] = get_proxy_url(source["src"])

            file_desc_html = str(desc_soup)

        license = fetch_license_info(base_url, title)

        return render_template(
            "file.html",
            title=title.replace("_", " "),
            file_info=file_info,
            content=file_desc_html,
            lang=lang,
            project=project,
            domain=domain,
            license=license,
            categories=categories,
            interwiki=interwiki,
        )

    try:
        variant = request.args.get("variant", None)
        article_html = fetch_article_content(base_url, title, variant)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return (
                render_template(
                    "article.html",
                    title="Article not found",
                    content=f"Sorry, the article {title} was not found on {domain}.",
                    lang=lang,
                    project=project,
                    domain=domain,
                ),
                404,
            )
        elif e.code == 429:
            return render_rate_limited(
                get_retry_after(e), lang=lang, project=project, domain=domain
            )
        else:
            logger.error(f"Error fetching article {title} from {domain}: {e}")
            logger.debug(f"Response: {e.read()}")
            return (
                render_template(
                    "article.html",
                    title="Error",
                    content=f"An error occurred while fetching the article {title} from {domain}.",
                    lang=lang,
                    project=project,
                    domain=domain,
                ),
                500,
            )

    soup = BeautifulSoup(article_html, "html.parser")
    body = soup.find("body")

    if not body:
        article_html = f"<div class='mw-body-content parsoid-body mediawiki mw-parser-output'>{article_html}</div>"
        soup = BeautifulSoup(article_html, "html.parser")
        body = soup.find("div", class_="mw-body-content")

    body.name = "div"

    redirect_message = soup.find("div", class_="redirectMsg")
    if redirect_message and not (request.args.get("redirect") == "no"):
        redirect_dest = redirect_message.find("a")["title"]
        logger.debug(f"Redirecting to {redirect_dest}")
        destination = url_for("wiki_article_by_domain", domain=domain, title=redirect_dest)
        logger.debug(f"Redirect URL: {destination}")
        return redirect(destination)

    try:
        article_interwiki_map = fetch_interwiki_map(base_url)
    except Exception:
        article_interwiki_map = {}

    for a in soup.find_all("a", href=True) + soup.find_all("area", href=True):
        href = a["href"]

        if href.startswith("/wiki/"):
            a["href"] = f"/{domain}{href}"
        elif href.startswith("//") or href.startswith("https://"):
            wikimore_url = _wikimore_url_for_external(href)
            if wikimore_url:
                a["href"] = wikimore_url
            elif href.startswith("//"):
                pass
            else:
                parts = urlparse(href)
                target_domain_url = f"https://{parts.netloc}"
                for language, lang_data in app.languages.items():
                    for project_name, project_url in lang_data["projects"].items():
                        if (
                            language == "en"
                            and project_url.replace("en.", "www.") == target_domain_url
                        ):
                            a["href"] = url_for(
                                "home", project=project_name, lang=language
                            )
        elif href.startswith("./") and ":" in href:
            iw_part = unquote(href[2:])
            iw_prefix, iw_sep, iw_rest = iw_part.partition(":")
            if iw_sep:
                if iw_prefix in app.languages:
                    target_project_url = app.languages[iw_prefix].get("projects", {}).get(project)
                    if target_project_url:
                        a["href"] = url_for(
                            "wiki_article_by_domain",
                            domain=urlparse(target_project_url).netloc,
                            title=iw_rest,
                        )
                elif iw_prefix in article_interwiki_map:
                    ext_url = article_interwiki_map[iw_prefix].replace(
                        "$1", quote(iw_rest.replace(" ", "_"), safe=":@!$&'()*+,;=")
                    )
                    a["href"] = _wikimore_url_for_external(ext_url) or ext_url

    for span in soup.find_all("span", class_="mw-editsection"):
        span.decompose()

    rtl = bool(soup.find("div", class_="mw-parser-output", dir="rtl"))
    if request.args.get("variant") == "ku-arab":
        rtl = True
        body["dir"] = "rtl"

    toc_entries = []
    for heading in soup.find_all(["h2", "h3", "h4"]):
        heading_id = heading.get("id")
        if not heading_id:
            headline = heading.find("span", class_="mw-headline")
            if headline:
                heading_id = headline.get("id")
        if heading_id:
            heading_text = heading.get_text(strip=True)
            if heading_text:
                toc_entries.append(
                    {
                        "level": int(heading.name[1]),
                        "id": heading_id,
                        "text": heading_text,
                    }
                )

    for style in soup.find_all("style"):
        style.decompose()

    for img in soup.find_all("img"):
        img["src"] = get_proxy_url(img["src"])
        img["loading"] = "lazy"

    for source in soup.find_all("source"):
        source["src"] = get_proxy_url(source["src"])

    for video in soup.find_all("video"):
        video["poster"] = get_proxy_url(video["poster"])

    for link in soup.find_all("link", rel="mw:PageProp/Category"):
        link.name = "a"
        link.string = link["href"][2:].replace("_", " ")
        link["class"] = "category-link"

    for li in soup.find_all("li"):
        if any(cls in li.get("class", []) for cls in ["nv-view", "nv-talk", "nv-edit"]):
            li.decompose()

    for span in soup.find_all(class_="mw-reflink-text"):
        parent = span.parent
        if parent.attrs.get("data-mw-group", None):
            span["class"] = span.get("class", []) + [parent.attrs["data-mw-group"]]

    processed_html = str(body)
    license = fetch_license_info(base_url, title)

    return render_template(
        "article.html",
        title=title.replace("_", " "),
        content=processed_html,
        lang=lang,
        project=project,
        domain=domain,
        rtl=rtl,
        license=license,
        interwiki=interwiki,
        badges=badges,
        categories=categories,
        category_members=category_members,
        toc=toc_entries,
    )


@app.route("/<project>/<lang>/wiki/<path:title>")
def wiki_article(project: str, lang: str, title: str) -> Response:
    """Legacy route: 301-redirect to the canonical domain-based URL."""
    base_url = _resolve_base_url(project, lang)
    if not base_url:
        return (
            render_template(
                "article.html",
                title="Project does not exist",
                content=f"Sorry, the project {project} does not exist in the {lang} language.",
            ),
            404,
        )
    return redirect(
        url_for("wiki_article_by_domain", domain=urlparse(base_url).netloc, title=title),
        301,
    )


@app.route("/<domain>/search/<path:query>")
def search_results_by_domain(domain: str, query: str) -> Union[Text, Tuple[Text, int]]:
    """Fetch and render search results from the Wikimedia Action API."""
    info = _resolve_for_domain(domain)
    if not info:
        return (
            render_template(
                "article.html",
                title="Project does not exist",
                content=f"Sorry, {domain} is not a recognized wiki.",
            ),
            404,
        )
    project, lang, base_url = info

    logger.debug(f"Searching {base_url} for {query}")

    try:
        results = fetch_search_results(base_url, query)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return render_rate_limited(
                get_retry_after(e), lang=lang, project=project, domain=domain
            )
        return (
            render_template(
                "article.html",
                title="Search Error",
                content="An error occurred while fetching search results. Please try again later.",
            ),
            500,
        )
    except Exception:
        return (
            render_template(
                "article.html",
                title="Search Error",
                content="An error occurred while fetching search results. Please try again later.",
            ),
            500,
        )

    return render_template(
        "search_results.html",
        query=query,
        search_results=results,
        project=project,
        lang=lang,
        domain=domain,
    )


@app.route("/<project>/<lang>/search/<path:query>")
def search_results(project: str, lang: str, query: str) -> Response:
    """Legacy route: 301-redirect to the canonical domain-based search URL."""
    base_url = _resolve_base_url(project, lang)
    if not base_url:
        return (
            render_template(
                "article.html",
                title="Project does not exist",
                content=f"Sorry, the project {project} does not exist in the {lang} language.",
            ),
            404,
        )
    return redirect(
        url_for(
            "search_results_by_domain", domain=urlparse(base_url).netloc, query=query
        ),
        301,
    )


@app.route("/<domain>/wiki/Special:Search/<query>")
def search_redirect_by_domain(domain: str, query: str) -> Response:
    """Redirect MediaWiki ``Special:Search`` URLs to the Wikimore search results route."""
    return redirect(url_for("search_results_by_domain", domain=domain, query=query))


@app.route("/<project>/<lang>/wiki/Special:Search/<query>")
def search_redirect(project: str, lang: str, query: str) -> Response:
    """Legacy route: redirect to the canonical domain-based search URL."""
    base_url = _resolve_base_url(project, lang)
    if not base_url:
        return redirect(url_for("home"))
    return redirect(
        url_for(
            "search_results_by_domain", domain=urlparse(base_url).netloc, query=query
        ),
        301,
    )


@app.route("/<domain>/w/index.php")
def index_php_redirect_by_domain(domain: str) -> Response:
    """Redirect ``/w/index.php`` to the wiki's main page."""
    info = _resolve_for_domain(domain)
    if not info:
        return (
            render_template(
                "article.html",
                title="Project does not exist",
                content=f"Sorry, {domain} is not a recognized wiki.",
            ),
            404,
        )
    _, _, base_url = info
    url = f"{base_url}/w/api.php?action=query&format=json&meta=siteinfo&siprop=general"
    with urlopen(url) as response:
        data = json.loads(response.read().decode())
    main_page = data["query"]["general"]["mainpage"]
    return redirect(url_for("wiki_article_by_domain", domain=domain, title=main_page))


@app.route("/<project>/<lang>/w/index.php")
def index_php_redirect(project: str, lang: str) -> Response:
    """Legacy route: redirect to the canonical domain-based main page."""
    base_url = _resolve_base_url(project, lang)
    if not base_url:
        return (
            render_template(
                "article.html",
                title="Project does not exist",
                content=f"Sorry, the project {project} does not exist in the {lang} language.",
            ),
            404,
        )
    return redirect(
        url_for("index_php_redirect_by_domain", domain=urlparse(base_url).netloc), 301
    )


@app.route("/<domain>/api/preview/<path:title>")
def article_preview_by_domain(domain: str, title: str) -> Response:
    """Return a JSON page summary used by the client-side hover preview tooltip."""
    info = _resolve_for_domain(domain)
    if not info:
        return Response(
            json.dumps({"error": "Project not found"}),
            status=404,
            mimetype="application/json",
        )
    _, _, base_url = info
    try:
        summary = fetch_article_summary(base_url, title)
    except urllib.error.HTTPError as e:
        return Response(
            json.dumps({"error": str(e.code)}),
            status=e.code,
            mimetype="application/json",
        )
    except Exception as e:
        logger.error(f"Error fetching summary for {title}: {e}")
        return Response(
            json.dumps({"error": "Internal error"}),
            status=500,
            mimetype="application/json",
        )
    if "thumbnail" in summary and "source" in summary.get("thumbnail", {}):
        summary["thumbnail"]["source"] = get_proxy_url(summary["thumbnail"]["source"])
    return Response(json.dumps(summary), mimetype="application/json")


@app.route("/<project>/<lang>/api/preview/<path:title>")
def article_preview(project: str, lang: str, title: str) -> Response:
    """Legacy route: 301-redirect to the canonical domain-based preview URL."""
    base_url = _resolve_base_url(project, lang)
    if not base_url:
        return Response(
            json.dumps({"error": "Project not found"}),
            status=404,
            mimetype="application/json",
        )
    return redirect(
        url_for(
            "article_preview_by_domain",
            domain=urlparse(base_url).netloc,
            title=title,
        ),
        301,
    )


@app.route("/version")
def version() -> Text:
    """Return the running application version as JSON."""
    return Response(
        json.dumps({"version": get_version()}),
        mimetype="application/json",
    )


def main():
    """Entry point: read configuration from environment variables and start Flask."""
    port = int(os.environ.get("WIKIMORE_PORT", os.environ.get("PORT", 8109)))
    host = os.environ.get("WIKIMORE_HOST", os.environ.get("HOST", "0.0.0.0"))
    debug = DEBUG_ENABLED
    socket = os.environ.get("WIKIMORE_SOCKET", os.environ.get("SOCKET", None))

    if socket:
        if os.path.exists(socket):
            os.remove(socket)
        if not socket.startswith("unix:"):
            if not socket.startswith("/"):
                logger.fatal("Socket path must be absolute")
                sys.exit(1)
            socket = f"unix://{socket}"
        app.run(debug=debug, host=socket)
    else:
        app.run(port=port, host=host, debug=debug)


if __name__ == "__main__":
    main()
