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

app = Flask(__name__)
app.static_folder = pathlib.Path(__file__).parent / "static"

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

# Remove the default Flask logger
app.logger.removeHandler(app.logger.handlers[0])

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

HEADERS = {
    "User-Agent": "Wikimore/dev (https://git.private.coffee/privatecoffee/wikimore)"
}


def get_wikimedia_projects() -> (
    Tuple[Dict[str, str], Dict[str, Dict[str, Union[str, Dict[str, str]]]]]
):
    """Fetch Wikimedia projects and languages from the Wikimedia API.

    Returns:
        Tuple[Dict[str, str], Dict[str, Dict[str, Union[str, Dict[str, str]]]]]: A tuple containing two dictionaries:
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

logger.debug(
    f"Loaded {len(app.wikimedia_projects)} Wikimedia projects and {len(app.languages)} languages"
)


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
def home() -> Text:
    """Renders the home page.

    Returns:
        Text: The rendered home page.
    """
    return render_template("home.html")


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

    logger.debug(f"Fetching {title} from {base_url}")

    api_request = urllib.request.Request(
        f"{base_url}/api/rest_v1/page/html/{escape(quote(title.replace(" ", "_")), True).replace('/', '%2F')}",
        headers=HEADERS,
    )

    if request.args.get("variant", None):
        api_request.add_header("Accept-Language", f"{request.args['variant']}")

    try:
        with urllib.request.urlopen(api_request) as response:
            article_html = response.read().decode()
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
            logger.debug(f"Attempted URL: {api_request.full_url}")
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

    body.name = "div"

    redirect_message = soup.find("div", class_="redirectMsg")

    if redirect_message and not (request.args.get("redirect") == "no"):
        redirect_dest = redirect_message.find("a")["title"]
        logger.debug(f"Redirecting to {redirect_dest}")
        destination = url_for(
            "wiki_article", project=project, lang=lang, title=redirect_dest
        )
        logger.debug(f"Redirect URL: {destination}")
        return redirect(destination)

    for a in soup.find_all("a", href=True) + soup.find_all("area", href=True):
        href = a["href"]

        if href.startswith("/wiki/"):
            a["href"] = f"/{project}/{lang}{href}"

        elif href.startswith("//") or href.startswith("https://"):
            parts = urlparse(href)

            target_domain = f"https://{parts.netloc}"
            path_parts = parts.path.split("/")

            if len(path_parts) >= 3:
                target_title = "/".join(path_parts[2:])

                found = False
                for language, language_projects in app.languages.items():
                    for project_name, project_url in language_projects[
                        "projects"
                    ].items():
                        if project_url == target_domain:
                            a["href"] = url_for(
                                "wiki_article",
                                project=project_name,
                                lang=language,
                                title=target_title,
                            )
                            found = True
                            break
                    if found:
                        break

    for span in soup.find_all("span", class_="mw-editsection"):
        span.decompose()

    for style in soup.find_all("style"):
        style.decompose()

    for img in soup.find_all("img"):
        img["src"] = get_proxy_url(img["src"])

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

    rtl = bool(soup.find("div", class_="mw-parser-output", dir="rtl"))

    # Edge case: When passing the `ku-arab` variant, the article is in Arabic
    # script but the direction returned in the API response is still LTR.
    if request.args.get("variant") == "ku-arab":
        rtl = True
        body["dir"] = "rtl"

    processed_html = str(body)

    # Get license information from the article
    mediawiki_api_request = urllib.request.Request(
        f"{base_url}/w/rest.php/v1/page/{escape(quote(title.replace(" ", "_")), True)}",
        headers=HEADERS,
    )

    try:
        with urllib.request.urlopen(mediawiki_api_request) as response:
            data = json.loads(response.read().decode())
        license = data["license"]
    except Exception as e:
        logger.error(f"Error fetching license information: {e}")
        license = None

    return render_template(
        "article.html",
        title=title.replace("_", " "),
        content=processed_html,
        lang=lang,
        project=project,
        rtl=rtl,
        license=license,
    )


@app.route("/<project>/<lang>/search/<path:query>")
def search_results(
    project: str, lang: str, query: str
) -> Union[Text, Tuple[Text, int]]:
    """Retrieve search results from a Wikimedia project.

    Args:
        project (str): The Wikimedia project code.
        lang (str): The language code.
        query (str): The search query.

    Returns:
        str|Tuple[str, int]: The rendered search results, or an error message with a status code.
    """

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

    srquery = escape(quote(query.replace(" ", "_")), True)

    url = (
        f"{base_url}/w/api.php?action=query&format=json&list=search&srsearch={srquery}"
    )

    logger.debug(f"Fetching search results from {url}")

    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
        search_results = data["query"]["search"]
    except Exception as e:
        logger.error(f"Error fetching search results: {e}")
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
