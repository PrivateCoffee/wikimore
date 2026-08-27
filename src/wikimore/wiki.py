import logging
import urllib.error
from dataclasses import dataclass, field

from .fetchers import (
    fetch_article_content,
    fetch_article_content_parsed,
    fetch_article_info,
    fetch_article_summary,
    fetch_category_members,
    fetch_file_info,
    fetch_file_page_content,
    fetch_revision_content,
    fetch_interwiki_map,
    fetch_license_info,
    fetch_search_results,
)

logger = logging.getLogger(__name__)


@dataclass
class Wiki:
    """Represents a single wiki instance (one domain)."""

    domain: str
    project: str
    lang: str
    base_url: str
    action_api_url: str
    has_rest_api: bool = field(default=True)
    path_prefix: str = field(default="")

    def fetch_article(self, title: str, variant: str | None = None) -> str:
        """Fetch article HTML, using REST API when available, action=parse otherwise.

        On a 403 or 404 from the REST API, falls back to action=parse and marks
        this wiki as REST-API-less so future calls skip the probe.
        """
        if not self.has_rest_api:
            return fetch_article_content_parsed(title, self.action_api_url)
        try:
            return fetch_article_content(self.base_url, title, variant)
        except urllib.error.HTTPError as e:
            if e.code not in (403, 404):
                raise
            result = fetch_article_content_parsed(title, self.action_api_url)
            self.has_rest_api = False
            logger.debug(f"Marked {self.base_url} as no-REST-API wiki")
            return result

    def fetch_info(self, title: str) -> dict:
        return fetch_article_info(title, self.action_api_url)

    def fetch_search(self, query: str) -> list:
        return fetch_search_results(query, self.action_api_url)

    def fetch_interwiki_map(self) -> dict[str, str]:
        return fetch_interwiki_map(self.action_api_url)

    def fetch_category_members(self, title: str) -> list:
        return fetch_category_members(title, self.action_api_url)

    def fetch_file_info(self, title: str) -> dict:
        return fetch_file_info(title, self.action_api_url)

    def fetch_file_page_content(self, title: str) -> str:
        return fetch_file_page_content(title, self.action_api_url)

    def fetch_summary(self, title: str) -> dict:
        return fetch_article_summary(self.base_url, title)

    def fetch_license(self, title: str) -> dict | None:
        return fetch_license_info(self.base_url, title)

    def fetch_revision_content(self, title: str) -> str:
        return fetch_revision_content(title, self.action_api_url)
