from urllib.parse import quote


def content_disposition_header(filename: str) -> str:
    """Return a correctly quoted Content-Disposition header value.

    Uses both the plain `filename` parameter (with unsafe characters stripped)
    and the RFC 5987 `filename*` parameter for full Unicode support.
    """
    safe_name = filename.replace('"', '').replace('\\', '')
    encoded = quote(filename, safe='')
    return f'attachment; filename="{safe_name}"; filename*=UTF-8\'{encoded}'
