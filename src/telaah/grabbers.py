"""Deteksi sumber paper dari link + base class grabber per sumber."""
import urllib.parse


def detect_source(url_or_query):
    """Return 'scopus' | 'openalex' | 'other'."""
    if not url_or_query.startswith("http"):
        return "other"
    netloc = urllib.parse.urlparse(url_or_query).netloc
    if "scopus" in netloc:
        return "scopus"
    if "openalex" in netloc:
        return "openalex"
    return "other"


class BaseGrabber:
    """Interface grabber per sumber. Subclass override run()."""

    source = "other"

    def run(self, query_or_url, out, max_n=0, delay=2.0):
        raise NotImplementedError
