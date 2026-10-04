"""
Re-download the article XML used as test fixtures into tests/data/.

Usage: python tests/refresh_fixtures.py

Set NCBI_API_KEY to use a higher rate limit. Review the resulting git diff before
committing, as NCBI occasionally changes the XML it serves for an article.
"""

import os
import time

import requests

# (database, id, fixture name)
FIXTURES = [
    ("pubmed", "20628391", "pubmed_20628391"),
    ("pmc", "PMC3203921", "PMC3203921"),
    ("pmc", "PMC9000000", "PMC9000000"),
    ("pmc", "PMC8466798", "PMC8466798"),
]

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def fetch_xml(article_id: str, db_name: str, retries: int = 5) -> str:
    """
    https://www.ncbi.nlm.nih.gov/pmc/tools/get-full-text/
    """
    params = {"db": db_name, "id": article_id, "rettype": "xml"}
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key

    for attempt in range(retries):
        resp = requests.get(EFETCH_URL, params=params)
        if resp.status_code != 429 or attempt == retries - 1:
            break
        time.sleep(2**attempt)
    resp.raise_for_status()
    return resp.text


def main():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    for db_name, article_id, name in FIXTURES:
        xml = fetch_xml(article_id, db_name)
        path = os.path.join(data_dir, name + ".xml")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(xml)
        print(f"Saved {db_name}:{article_id} to {path}")
        time.sleep(1)


if __name__ == "__main__":
    main()
