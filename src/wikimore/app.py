from flask import (
    render_template as flask_render_template,
    Flask,
    request,
    redirect,
    url_for,
    Response,
)
import urllib.request
from urllib.parse import urlencode, urlparse, quote
from html import escape
import json
import os
import logging
import pathlib
from typing import Dict, Union, Tuple, Text
from bs4 import BeautifulSoup
from .cache import cache
import hashlib

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)


def create_app():
    """Create and configure the Flask app."""
    # TODO: Make this a little more configurable
    app = Flask(__name__)
    app.static_folder = pathlib.Path(__file__).parent / "static"
    app.logger.removeHandler(app.logger.handlers[0])
    cache.init_app(app)
    return app


app = create_app()

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

HEADERS = {
    "User-Agent": "Wikimore/dev (https://git.private.coffee/privatecoffee/wikimore)"
}


@cache.cached(timeout=86400, key_prefix="wikimedia_projects")
def get_wikimedia_projects() -> (
    Tuple[Dict[str, str], Dict[str, Dict[str, Union[str, Dict[str, str]]]]]
):
    """Fetch Wikimedia projects and languages from the Wikimedia API.

    Returns:
        Tuple[Dict[str, str], Dict[str, Dict[str, Union[str, Dict[str, str]]]]]:
            A tuple containing two dictionaries:
            - The first dictionary maps Wikimedia project codes to project names.
            - The second dictionary maps language codes to dictionaries containing:
                - A dictionary mapping Wikimedia project codes to project URLs.
                - The language name.
    """
    url = "https://meta.wikimedia.org/w/api.php?action=sitematrix&format=json"
    with urllib.request.urlopen(url, timeout=30) as response:
        try:
            data = json.loads(response.read().decode())
        except json.JSONDecodeError as e:
            logger.fatal("Error decoding JSON response")
            raise
        except urllib.error.HTTPError as e:
            logger.fatal(f"HTTP error fetching Wikimedia projects and languages: {e}")
            raise
        except urllib.error.URLError as e:
            logger.fatal(f"URL error fetching Wikimedia projects and languages: {e}")
            raise
        except Exception as e:
            logger.fatal("Error fetching Wikimedia projects and languages")
            raise

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

    languages["special"] = {
        "projects": {},
        "name": "Special",
    }

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


app.wikimedia_projects, app.languages = get_wikimedia_projects()
app.licenses = {}

logger.debug(
    f"Loaded {len(app.wikimedia_projects)} Wikimedia projects and {len(app.languages)} languages"
)


# Get number of active Wikipedia users for each language
def get_active_users() -> Dict[str, int]:
    """Fetch the number of active Wikipedia users for each language.

    Returns:
        Dict[str, int]: A dictionary mapping language codes to the number of active Wikipedia users.
    """
    path = "/w/api.php?action=query&format=json&meta=siteinfo&siprop=statistics"

    active_users = {}

    for lang, data in app.languages.items():
        try:
            url = f"{data['projects']['wiki']}{path}"
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read().decode())
                active_users[lang] = data["query"]["statistics"]["activeusers"]
        except Exception as e:
            logger.error(f"Error fetching active users for {lang}: {e}")

    return sorted(active_users.items(), key=lambda x: x[1], reverse=True)


if os.environ.get("NO_LANGSORT", False):
    LANGSORT = []
elif os.environ.get("LANGSORT") == "auto":
    LANGSORT = [lang for lang, _ in get_active_users()[:50]]
elif os.environ.get("LANGSORT"):
    LANGSORT = os.environ["LANGSORT"].split(",")
else:
    # Opinionated sorting of languages
    LANGSORT = [
        "en",
        "es",
        "ja",
        "de",
        "fr",
        "zh",
        "ru",
        "it",
        "pt",
        "pl",
        "nl",
        "ar",
    ]


def langsort(input: list[dict], key: str = "lang") -> list[dict]:
    """Sorting of language data.

    Sorts a list of dictionaries containing "lang" keys such that the most common languages are first.

    Allows specifying a custom order using the `LANGSORT` environment variable.

    Args:
        input (list[dict]): A list of dictionaries containing "lang" keys.

    Returns:
        list[dict]: The sorted list of dictionaries.
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

app.languages = {
    lang: app.languages[lang] for lang in [lang["lang"] for lang in app_languages]
}


def render_template(*args, **kwargs) -> Text:
    """A wrapper around Flask's `render_template` that adds the `languages` and `wikimedia_projects` context variables.

    Args:
        *args: Positional arguments to pass to `flask.render_template`.
        **kwargs: Keyword arguments to pass to `flask.render_template`.

    Returns:
        Text: The rendered template.
    """
    kwargs.setdefault("lang", "en")
    kwargs.setdefault("project", "wiki")

    return flask_render_template(
        *args,
        **kwargs,
        languages=app.languages,
        wikimedia_projects=app.wikimedia_projects,
    )


def get_proxy_url(url: str) -> str:
    """Generate a proxy URL for a given URL.

    Will only generate a proxy URL for URLs that are on Wikimedia Commons or Wikimedia Maps.
    For other URLs, the original URL is returned.

    Args:
        url (str): The URL to generate a proxy URL for.

    Returns:
        str: The proxy URL, or the original URL if it should not be proxied.
    """
    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith("https://upload.wikimedia.org/") and not url.startswith(
        "https://maps.wikimedia.org/"
    ):
        logger.debug(f"Not generating proxy URL for {url}")
        return url

    logger.debug(f"Generating proxy URL for {url}")
    return f"/proxy?{urlencode({'url': url})}"


@app.route("/proxy")
def proxy() -> bytes:
    """A simple proxy for Wikimedia Commons and Wikimedia Maps URLs.

    Returns:
        bytes: The content of the proxied URL.
    """
    url = request.args.get("url")

    if not url or not (
        url.startswith("https://upload.wikimedia.org/")
        or url.startswith("https://maps.wikimedia.org/")
    ):
        logger.error(f"Invalid URL for proxying: {url}")
        return "Invalid URL"

    logger.debug(f"Proxying {url}")

    with urllib.request.urlopen(url) as response:
        data = response.read()
    return data


@app.route("/")
def home(project=None, lang=None) -> Text:
    """Renders the home page.

    Returns:
        Text: The rendered home page.
    """
    return render_template("home.html", project=project, lang=lang)


@app.route("/search", methods=["GET", "POST"])
def search() -> Union[Text, Response]:
    """Renders the search page.

    If a search query is submitted, redirects to the search results page.

    Returns:
        str|Response: The rendered search page, or a redirect to the search results page.
    """
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

        if not query:
            return redirect(url_for("index_php_redirect", project=project, lang=lang))

        return redirect(
            url_for("search_results", project=project, lang=lang, query=query)
        )
    return render_template("search.html")


@app.route("/<domain>/<path:url>")
def inbound_redirect(domain: str, url: str) -> Union[Text, Response, Tuple[Text, int]]:
    """Redirects to the appropriate project/language combination given the domain name of a Wikimedia project

    Args:
        domain (str): The domain of the Wikimedia project.
        url (str): The URL path.

    Returns:
        Response: A redirect to the corresponding route
    """
    # TODO: Make this the default route scheme instead of a redirect

    for language, language_projects in app.languages.items():
        for project_name, project_url in language_projects["projects"].items():
            if project_url == f"https://{domain}":
                return redirect(f"{url_for('home')}{project_name}/{language}/{url}")

    for project_name, project_url in app.languages["special"]["projects"].items():
        if project_url == f"https://{domain}":
            return redirect(f"{url_for('home')}/{project_name}/{language}/{url}")

    # TODO / IDEA: Handle non-Wikimedia Mediawiki projects here?

    return (
        render_template(
            "article.html",
            title="Project does not exist",
            content=f"Sorry, the project {domain} does not exist.",
        ),
        404,
    )


@cache.memoize(timeout=3600)  # 1 hour
def fetch_article_content(base_url, title, variant=None):
    """Fetches article content from the Wikimedia API with caching."""
    logger.debug(f"Fetching article content for {title} from {base_url}")

    # Create a unique cache key for the article
    api_request = urllib.request.Request(
        f"{base_url}/api/rest_v1/page/html/{escape(quote(title.replace(' ', '_')), True).replace('/', '%2F')}",
        headers=HEADERS,
    )

    logger.debug(f"Article content URL: {api_request.full_url}")

    if variant:
        api_request.add_header("Accept-Language", f"{variant}")

    try:
        with urllib.request.urlopen(api_request) as response:
            article_html = response.read().decode()
            return article_html
    except urllib.error.HTTPError as e:
        # Re-raise the error to be handled by the calling function
        raise


@cache.memoize(timeout=1800)  # 30 minutes
def fetch_search_results(base_url, query):
    """Fetches search results from the Wikimedia API with caching."""
    srquery = escape(quote(query.replace(" ", "_")), True)
    url = (
        f"{base_url}/w/api.php?action=query&format=json&list=search&srsearch={srquery}"
    )

    logger.debug(f"Fetching search results from {url}")

    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
        return data["query"]["search"]
    except Exception as e:
        logger.error(f"Error fetching search results: {e}")
        raise


@cache.memoize(timeout=3600)  # 1 hour
def fetch_article_info(base_url, title):
    """Fetches article metadata from the Wikimedia API with caching."""
    logger.debug(f"Fetching article info for {title} from {base_url}")

    info_api_request = urllib.request.Request(
        f"{base_url}/w/api.php?action=query&format=json&titles={escape(quote(title.replace(' ', '_')), True)}&prop=info|pageprops|categoryinfo|langlinks|categories&lllimit=500&cllimit=500",
        headers=HEADERS,
    )

    with urllib.request.urlopen(info_api_request) as response:
        logger.debug(
            f"Tried to fetch info for {title} from {info_api_request.full_url}"
        )
        data = json.loads(response.read().decode())
        return data


@cache.memoize(timeout=86400)  # 24 hours
def fetch_badge_data(badge_id, lang):
    """Fetches badge data from Wikidata with caching."""
    badge_request = urllib.request.Request(
        f"https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&ids={badge_id}&languages={lang}",
        headers=HEADERS,
    )

    with urllib.request.urlopen(badge_request) as badge_response:
        logger.debug(f"Tried to fetch badge {badge_id} from {badge_request.full_url}")
        return json.loads(badge_response.read().decode())


@cache.memoize(timeout=3600)  # 1 hour
def fetch_category_members(base_url, title, project, lang):
    """Fetches category members with caching."""
    category_api_url = f"{base_url}/w/api.php?action=query&format=json&list=categorymembers&cmtitle={escape(quote(title.replace(' ', '_')), True)}&cmlimit=500"

    category_api_request = urllib.request.Request(
        category_api_url,
        headers=HEADERS,
    )

    all_members = []

    with urllib.request.urlopen(category_api_request) as category_api_response:
        logger.debug(
            f"Tried to fetch category members for {title} from {category_api_request.full_url}"
        )
        data = json.loads(category_api_response.read().decode())
        category_members = data["query"]["categorymembers"]
        all_members += category_members

        if "continue" in data:
            continue_params = f"&cmcontinue={data['continue']['cmcontinue']}"
            category_api_request = urllib.request.Request(
                category_api_url + continue_params,
                headers=HEADERS,
            )

            with urllib.request.urlopen(category_api_request) as category_api_response:
                data = json.loads(category_api_response.read().decode())
                all_members += data["query"]["categorymembers"]

    for member in all_members:
        member["url"] = url_for(
            "wiki_article",
            project=project,
            lang=lang,
            title=member["title"],
        )

    return all_members


@cache.memoize(timeout=86400)  # 24 hours
def fetch_license_info(base_url, title):
    """Fetches license information with caching."""
    if base_url not in app.licenses:
        try:
            mediawiki_api_request = urllib.request.Request(
                f"{base_url}/w/rest.php/v1/page/{escape(quote(title.replace(' ', '_')), True)}",
                headers=HEADERS,
            )
            mediawiki_api_response = urllib.request.urlopen(mediawiki_api_request)
            mediawiki_api_data = json.loads(mediawiki_api_response.read().decode())
            app.licenses[base_url] = license = mediawiki_api_data["license"]
        except Exception:
            license = None
    else:
        license = app.licenses[base_url]

    return license


@app.route("/<project>/<lang>/wiki/<path:title>")
def wiki_article(
    project: str, lang: str, title: str
) -> Union[Text, Response, Tuple[Text, int]]:
    """Fetches and renders a Wikimedia article.

    Handles redirects and links to other Wikimedia projects, and proxies images and videos.

    Args:
        project (str): The Wikimedia project code.
        lang (str): The language code.
        title (str): The article title.

    Returns:
        str|Response|Tuple[str, int]: The rendered article, a redirect to another article, or an error message with a status code.
    """
    # Check if the project and language are valid
    language_projects = app.languages.get(lang, {}).get("projects", {})
    base_url = language_projects.get(project)

    if not base_url:
        special_projects = app.languages.get("special", {}).get("projects", {})
        base_url = special_projects.get(project)

    if not base_url:
        return (
            render_template(
                "article.html",
                title="Project does not exist",
                content=f"Sorry, the project {project} does not exist in the {lang} language.",
            ),
            404,
        )

    # Get article info using cached function
    try:
        article_info = fetch_article_info(base_url, title)
        page = article_info["query"]["pages"].popitem()[1]

        category_members = []
        interwiki = []
        badges = []
        categories = []

        langlinks = page.get("langlinks", [])

        logger.debug(f"Original Interwiki links for {title}: {langlinks}")

        # Get interwiki links and translate them to internal links where possible
        for link in langlinks:
            try:
                interwiki_lang = link["lang"]
                interwiki_title = link["*"]

                logger.debug(
                    f"Generating interwiki link for: {interwiki_lang}.{project}/{interwiki_title}"
                )

                interwiki_url = url_for(
                    "wiki_article",
                    project=project,
                    lang=interwiki_lang,
                    title=interwiki_title,
                )
                link["url"] = interwiki_url

                link["langname"] = app.languages[interwiki_lang]["name"]

                interwiki.append(link)

            except KeyError as e:
                logger.error(
                    f"Error processing interwiki link for title {title} in language {lang}: {e}"
                )

        # Get badges (e.g. "Good Article", "Featured Article")
        props = page.get("pageprops", {})

        for prop in props:
            if prop.startswith("wikibase-badge-"):
                try:
                    badge_id = prop.replace("wikibase-badge-", "")

                    # Fetch the badge data from Wikidata
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

        # If the article is a category, fetch the category members
        if "categoryinfo" in page:
            category_members = fetch_category_members(base_url, title, project, lang)

        # Get categories the article is in
        if "categories" in page:
            categories = page["categories"]

            for category in categories:
                category["url"] = url_for(
                    "wiki_article",
                    project=project,
                    lang=lang,
                    title=category["title"],
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
            ),
            500,
        )

    interwiki = langsort(interwiki)

    # Fetch article content using cached function
    try:
        variant = request.args.get("variant", None)
        article_html = fetch_article_content(base_url, title, variant)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return (
                render_template(
                    "article.html",
                    title="Article not found",
                    content=f"Sorry, the article {title} was not found in the {project} project in the {lang} language.",
                    lang=lang,
                    project=project,
                ),
                404,
            )
        else:
            logger.error(f"Error fetching article {title} from {lang}.{project}: {e}")
            logger.debug(f"Response: {e.read()}")
            return (
                render_template(
                    "article.html",
                    title="Error",
                    content=f"An error occurred while fetching the article {title} from the {project} project in the {lang} language.",
                    lang=lang,
                    project=project,
                ),
                500,
            )

    soup = BeautifulSoup(article_html, "html.parser")

    body = soup.find("body")

    if not body:
        article_html = f"<div class='mw-body-content parsoid-body mediawiki mw-parser-output'>{article_html}</div>"
        soup = BeautifulSoup(article_html, "html.parser")
        body = soup.find("div", class_="mw-body-content")

    # Turn the body into a div
    body.name = "div"

    # If the article is a redirect, follow the redirect, unless the `redirect=no` query parameter is present
    redirect_message = soup.find("div", class_="redirectMsg")
    if redirect_message and not (request.args.get("redirect") == "no"):
        redirect_dest = redirect_message.find("a")["title"]
        logger.debug(f"Redirecting to {redirect_dest}")
        destination = url_for(
            "wiki_article", project=project, lang=lang, title=redirect_dest
        )
        logger.debug(f"Redirect URL: {destination}")
        return redirect(destination)

    # Update links to other articles
    for a in soup.find_all("a", href=True) + soup.find_all("area", href=True):
        href = a["href"]

        # Internal links
        if href.startswith("/wiki/"):
            a["href"] = f"/{project}/{lang}{href}"

        # External links
        elif href.startswith("//") or href.startswith("https://"):
            parts = urlparse(href)

            target_domain = f"https://{parts.netloc}"
            path_parts = parts.path.split("/")

            target_title = None

            if len(path_parts) >= 3:
                target_title = "/".join(path_parts[2:])

            found = False

            # Check if it is an interwiki link
            for language, language_projects in app.languages.items():
                for project_name, project_url in language_projects["projects"].items():
                    if project_url == target_domain:
                        if target_title:
                            a["href"] = url_for(
                                "wiki_article",
                                project=project_name,
                                lang=language,
                                title=target_title,
                            )
                        else:
                            a["href"] = url_for(
                                "index_php_redirect",
                                project=project_name,
                                lang=language,
                            )
                        found = True

                    # Try to check if it is a link to the "main page" of a project
                    elif (
                        language == "en"
                        and project_url.replace("en.", "www.") == target_domain
                    ):
                        a["href"] = url_for("home", project=project_name, lang=language)
                if found:
                    break

    # Remove edit sections and styles
    for span in soup.find_all("span", class_="mw-editsection"):
        span.decompose()

    for style in soup.find_all("style"):
        style.decompose()

    # Proxy images and videos
    for img in soup.find_all("img"):
        img["src"] = get_proxy_url(img["src"])

        # While we're at it, ensure that images are loaded lazily
        img["loading"] = "lazy"

    for source in soup.find_all("source"):
        source["src"] = get_proxy_url(source["src"])

    for video in soup.find_all("video"):
        video["poster"] = get_proxy_url(video["poster"])

    # Convert category elements to links
    for link in soup.find_all("link", rel="mw:PageProp/Category"):
        link.name = "a"
        link.string = link["href"][2:].replace("_", " ")
        link["class"] = "category-link"

    # Remove meta links
    for li in soup.find_all("li"):
        if any(cls in li.get("class", []) for cls in ["nv-view", "nv-talk", "nv-edit"]):
            li.decompose()

    # Add classes to reference links
    for span in soup.find_all(class_="mw-reflink-text"):
        parent = span.parent
        if parent.attrs.get("data-mw-group", None):
            span["class"] = span.get("class", []) + [parent.attrs["data-mw-group"]]

    # Check if the article is in a right-to-left language
    rtl = bool(soup.find("div", class_="mw-parser-output", dir="rtl"))

    # Edge case: When passing the `ku-arab` variant, the article is in Arabic
    # script but the direction returned in the API response is still LTR.
    if request.args.get("variant") == "ku-arab":
        rtl = True
        body["dir"] = "rtl"

    processed_html = str(body)

    # Get license information for the article
    license = fetch_license_info(base_url, title)

    # Render the article
    return render_template(
        "article.html",
        title=title.replace("_", " "),
        content=processed_html,
        lang=lang,
        project=project,
        rtl=rtl,
        license=license,
        interwiki=interwiki,
        badges=badges,
        categories=categories,
        category_members=category_members,
    )


@app.route("/<project>/<lang>/search/<path:query>")
def search_results(project, lang, query):
    language_projects = app.languages.get(lang, {}).get("projects", {})
    base_url = language_projects.get(project)

    if not base_url:
        special_projects = app.languages.get("special", {}).get("projects", {})
        base_url = special_projects.get(project)

    if not base_url:
        return (
            render_template(
                "article.html",
                title="Project does not exist",
                content=f"Sorry, the project {project} does not exist in the {lang} language.",
            ),
            404,
        )

    logger.debug(f"Searching {base_url} for {query}")

    try:
        search_results = fetch_search_results(base_url, query)
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
        search_results=search_results,
        project=project,
        lang=lang,
    )


@app.route("/<project>/<lang>/wiki/Special:Search/<query>")
def search_redirect(project: str, lang: str, query: str) -> Response:
    """Redirects to the search results page.

    Args:
        project (str): The Wikimedia project code.
        lang (str): The language code.
        query (str): The search query.

    Returns:
        Response: A redirect to the search results page.
    """
    return redirect(url_for("search_results", project=project, lang=lang, query=query))


@app.route("/<project>/<lang>/w/index.php")
def index_php_redirect(project, lang) -> Response:
    """Redirects to the main page of a Wikimedia project.

    Args:
        project (str): The Wikimedia project code.
        lang (str): The language code.

    Returns:
        Response: A redirect to the main page of the Wikimedia project.
    """
    # TODO: Handle query string

    try:
        url = f"{app.languages[lang]['projects'][project]}/w/api.php?action=query&format=json&meta=siteinfo&siprop=general"
    except KeyError:
        try:
            url = f"{app.languages['special']['projects'][project]}/w/api.php?action=query&format=json&meta=siteinfo&siprop=general"
        except KeyError:
            return (
                render_template(
                    "article.html",
                    title="Project does not exist",
                    content=f"Sorry, the project {project} does not exist in the {lang} language.",
                ),
            )
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode())
    main_page = data["query"]["general"]["mainpage"]

    return redirect(
        url_for("wiki_article", project=project, lang=lang, title=main_page)
    )


def main():
    """Start the Flask app."""
    port = int(os.environ.get("PORT", 8109))
    host = os.environ.get("HOST", "0.0.0.0")
    debug = os.environ.get("DEBUG", False)
    app.run(port=port, host=host, debug=debug)


if __name__ == "__main__":
    main()
