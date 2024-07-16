from flask import Flask, render_template, request, redirect, url_for
import urllib.request
from urllib.parse import urlencode
from html import escape
import json
from bs4 import BeautifulSoup

app = Flask(__name__)

WIKIMEDIA_PROJECTS = {
    "wikipedia": "wikipedia.org",
    "wiktionary": "wiktionary.org",
    # TODO: Add more Wikimedia projects
}


def get_proxy_url(url):
    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith("https://upload.wikimedia.org/"):
        return url

    return f"/proxy?{urlencode({'url': url})}"


@app.route("/proxy")
def proxy():
    url = request.args.get("url")

    if not url or not url.startswith("https://upload.wikimedia.org/"):
        return "Invalid URL"

    with urllib.request.urlopen(url) as response:
        data = response.read()
    return data


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/search", methods=["GET", "POST"])
def search():
    if request.method == "POST":
        query = request.form["query"]
        lang = request.form["lang"]
        project = request.form["project"]
        return redirect(
            url_for("search_results", project=project, lang=lang, query=query)
        )
    return render_template("search.html")


@app.route("/<project>/<lang>/wiki/<title>")
def wiki_article(project, lang, title):
    base_url = WIKIMEDIA_PROJECTS.get(project, "wikipedia.org")
    url = f"https://{lang}.{base_url}/w/api.php?action=query&format=json&titles={escape(title.replace(" ", "_"), True)}&prop=revisions&rvprop=content&rvparse=1"
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
            parts = href.split("/")
            if len(parts) > 4:
                target_project = ".".join(parts[2].split(".")[1:])
                target_lang = parts[2].split(".")[0]
                target_title = "/".join(parts[4:])
                if target_project in WIKIMEDIA_PROJECTS.values():
                    target_project = list(WIKIMEDIA_PROJECTS.keys())[
                        list(WIKIMEDIA_PROJECTS.values()).index(target_project)
                    ]
                    a["href"] = f"/{target_project}/{target_lang}/wiki/{target_title}"

    for span in soup.find_all("span", class_="mw-editsection"):
        span.decompose()

    for style in soup.find_all("style"):
        style.decompose()

    for img in soup.find_all("img"):
        img["src"] = get_proxy_url(img["src"])

    for li in soup.find_all("li"):
        # If "nv-view", "nv-talk", "nv-edit" classes are on the li element, remove it
        if any(cls in li.get("class", []) for cls in ["nv-view", "nv-talk", "nv-edit"]):
            li.decompose()

    processed_html = str(soup)
    return render_template("article.html", title=title, content=processed_html)


@app.route("/<project>/<lang>/search/<query>")
def search_results(project, lang, query):
    base_url = WIKIMEDIA_PROJECTS.get(project, "wikipedia.org")
    url = f"https://{lang}.{base_url}/w/api.php?action=query&format=json&list=search&srsearch={query}"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode())
    search_results = data["query"]["search"]
    return render_template(
        "search_results.html",
        query=query,
        search_results=search_results,
        project=project,
        lang=lang,
    )


@app.route("/<project>/<lang>/wiki/Special:Search/<query>")
def search_redirect(project, lang, query):
    return redirect(url_for("search_results", project=project, lang=lang, query=query))


if __name__ == "__main__":
    app.run(debug=True)
