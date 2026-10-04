import os


def data_file_path(filepath):
    return os.path.join(os.path.dirname(__file__), "data", filepath)


def load_xml(name: str) -> str:
    """
    Load a saved E-utilities efetch response from tests/data/<name>.xml.

    These are committed so the tests don't hit the NCBI API (and its rate limits).
    Regenerate them with tests/refresh_fixtures.py.
    """
    with open(data_file_path(name + ".xml"), encoding="utf-8") as f:
        return f.read()
