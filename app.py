from flask import Flask, render_template, request, redirect, url_for
import urllib.request
from urllib.parse import urlencode, urlparse
from html import escape
import json
import logging
from bs4 import BeautifulSoup

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)


def get_wikimedia_projects():
    url = "https://meta.wikimedia.org/w/api.php?action=sitematrix&format=json"
    with urllib.request.urlopen(url) as response:
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

    return projects, languages


def get_proxy_url(url):
    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith("https://upload.wikimedia.org/"):
        logger.debug(f"Not generating proxy URL for {url}")
        return url

    logger.debug(f"Generating proxy URL for {url}")
    return f"/proxy?{urlencode({'url': url})}"


@app.route("/proxy")
def proxy():
    url = request.args.get("url")

    if not url or not url.startswith("https://upload.wikimedia.org/"):
        logger.error(f"Invalid URL for proxying: {url}")
        return "Invalid URL"

    logger.debug(f"Proxying {url}")

    with urllib.request.urlopen(url) as response:
        data = response.read()
    return data


@app.route("/")
def home():
    return render_template(
        "home.html",
        wikimedia_projects=app.wikimedia_projects,
        languages=app.languages,
    )


@app.route("/search", methods=["GET", "POST"])
def search():
    if request.method == "POST":
        query = request.form["query"]
        lang = request.form["lang"]
        project = request.form["project"]
        return redirect(
            url_for("search_results", project=project, lang=lang, query=query)
        )
    return render_template(
        "search.html",
        wikimedia_projects=app.wikimedia_projects,
        languages=app.languages,
    )


@app.route("/<project>/<lang>/wiki/<title>")
def wiki_article(project, lang, title):
    language_projects = app.languages.get(lang, {}).get("projects", {})
    base_url = language_projects.get(project)

    if not base_url:
        return "Invalid language or project"

    logger.debug(f"Fetching {title} from {base_url}")

    url = f"{base_url}/w/api.php?action=query&format=json&titles={escape(title.replace(" ", "_"), True)}&prop=revisions&rvprop=content&rvparse=1"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode())
    pages = data["query"]["pages"]
    article_html = next(iter(pages.values()))["revisions"][0]["*"]

    soup = BeautifulSoup(article_html, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if href.startswith("/wiki/"):
            a["href"] = f"/{project}/{lang}{href}"

        elif href.startswith("//") or href.startswith("https://"):
            parts = urlparse(href)

            target_domain = parts.netloc
            path_parts = parts.path.split("/")

            if len(path_parts) > 4:
                target_title = "/".join(path_parts[4:])
                target_lang = target_domain.split(".")[0]

                found = False
                for language, language_projects in app.languages.items():
                    for project_name, project_url in language_projects.items():
                        if target_domain == project_url:
                            a["href"] = (
                                f"/{project_name}/{target_lang}/wiki/{target_title}"
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

    for li in soup.find_all("li"):
        if any(cls in li.get("class", []) for cls in ["nv-view", "nv-talk", "nv-edit"]):
            li.decompose()

    processed_html = str(soup)
    return render_template(
        "article.html",
        title=title.replace("_", " "),
        content=processed_html,
        wikimedia_projects=app.wikimedia_projects,
        languages=app.languages,
    )


@app.route("/<project>/<lang>/search/<query>")
def search_results(project, lang, query):
    language_projects = app.languages.get(lang, {}).get("projects", {})
    base_url = language_projects.get(project)

    if not base_url:
        return "Invalid language or project"

    logger.debug(f"Searching {base_url} for {query}")

    url = f"{base_url}/w/api.php?action=query&format=json&list=search&srsearch={query}"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode())
    search_results = data["query"]["search"]
    return render_template(
        "search_results.html",
        query=query,
        search_results=search_results,
        project=project,
        lang=lang,
        wikimedia_projects=app.wikimedia_projects,
        languages=app.languages,
    )


@app.route("/<project>/<lang>/wiki/Special:Search/<query>")
def search_redirect(project, lang, query):
    return redirect(url_for("search_results", project=project, lang=lang, query=query))


app.wikimedia_projects, app.languages = get_wikimedia_projects()

print(len(app.wikimedia_projects), len(app.languages))

if __name__ == "__main__":
    app.run(debug=True)
