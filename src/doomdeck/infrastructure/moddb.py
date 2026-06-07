"""ModDB page parsing and download selection."""
from __future__ import annotations

import html
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Optional

from doomdeck.domain.downloads import DownloadPolicy
from doomdeck.domain.models import DoomDeckError, ModDBDownload
from doomdeck.infrastructure.downloads import DEFAULT_USER_AGENT

MODDB_BASE_URL = "https://www.moddb.com"
BRUTAL_DOOM_MODDB_URL = "https://www.moddb.com/mods/brutal-doom"
BRUTAL_DOOM_DOWNLOADS_URL = "https://www.moddb.com/mods/brutal-doom/downloads"


def fetch_text_url(
    url: str,
    logger: Optional[logging.Logger] = None,
    allowed_hosts: Optional[set[str]] = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> str:
    DownloadPolicy.for_hosts(allowed_hosts).validate_url(url)
    if logger:
        logger.debug("Fetch metadata page: %s", url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    # URL policy is validated before opening the request.
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
        content_type = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(content_type, errors="replace")


def safe_download_name(value: str, fallback: str) -> str:
    name = value.rstrip("/").split("/")[-1].split("?")[0]
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return name or fallback


def strip_html(text: str) -> str:
    text = re.sub(r"(?is)<script\b.*?</script>", " ", text)
    text = re.sub(r"(?is)<style\b.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def html_text_lines(text: str) -> list[str]:
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|dt|dd|tr|td|th)>", "\n", text)
    text = re.sub(r"(?is)<script\b.*?</script>", " ", text)
    text = re.sub(r"(?is)<style\b.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    lines = [re.sub(r"\s+", " ", html.unescape(line)).strip() for line in text.splitlines()]
    return [line for line in lines if line]


def html_links(text: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for match in re.finditer(r"""(?is)<a\b[^>]*\bhref\s*=\s*["'](?P<href>[^"']+)["'][^>]*>(?P<body>.*?)</a>""", text):
        href = html.unescape(match.group("href")).strip()
        body = strip_html(match.group("body"))
        if href:
            links.append((href, body))
    return links


def absolute_moddb_url(href: str, base: str = MODDB_BASE_URL) -> str:
    return urllib.parse.urljoin(base, html.unescape(href).strip())


def line_after_label(lines: list[str], label: str) -> str:
    label_lower = label.lower()
    for idx, line in enumerate(lines):
        normalized = line.rstrip(":").strip().lower()
        if normalized != label_lower:
            continue
        for candidate in lines[idx + 1 : idx + 4]:
            if candidate.rstrip(":").strip().lower() != label_lower:
                return candidate.strip()
    return ""


def extract_moddb_download_link(page_html: str, page_url: str) -> str:
    for href, text in html_links(page_html):
        if re.search(r"/(?:downloads|addons)/start/", href) and "download" in text.lower():
            return absolute_moddb_url(href, page_url)
    for href, _text in html_links(page_html):
        if re.search(r"/(?:downloads|addons)/start/", href):
            return absolute_moddb_url(href, page_url)
    match = re.search(r"""(?i)href\s*=\s*["'](?P<href>[^"']*/(?:downloads|addons)/start/\d+[^"']*)["']""", page_html)
    if match:
        return absolute_moddb_url(match.group("href"), page_url)
    raise DoomDeckError(f"Could not find a ModDB start-download link on {page_url}")


def resolve_moddb_download_url(start_url: str, page_url: str, logger: logging.Logger, user_agent: str = DEFAULT_USER_AGENT) -> str:
    def first_mirror(html_text: str, base_url: str) -> Optional[str]:
        for href, _text in html_links(html_text):
            if re.search(r"/(?:downloads|addons)/mirror/", href):
                return absolute_moddb_url(href, base_url)
        return None

    try:
        start_html = fetch_text_url(start_url, logger, user_agent=user_agent)
    except urllib.error.URLError as exc:
        raise DoomDeckError(f"Could not read ModDB download page {start_url}: {exc}") from exc

    mirror = first_mirror(start_html, start_url)
    if mirror:
        return mirror

    mirrors_url = start_url.rstrip("/") + "/all"
    try:
        mirrors_html = fetch_text_url(mirrors_url, logger, user_agent=user_agent)
    except urllib.error.URLError as exc:
        logger.warning("Could not read ModDB mirror list %s: %s", mirrors_url, exc)
        return start_url
    mirror = first_mirror(mirrors_html, mirrors_url)
    if mirror:
        return mirror
    logger.warning("No explicit ModDB mirror found; using start URL directly: %s", start_url)
    return start_url


def extract_brutal_doom_pages(page_html: str, base_url: str) -> list[tuple[str, str]]:
    pages: OrderedDict[str, str] = OrderedDict()

    def title_quality(value: str) -> int:
        lower = value.lower()
        if "brutal doom" in lower:
            return 100
        if re.search(r"\bbd\s*v?\d+", lower):
            return 80
        if "comments" in lower or lower.startswith("image:"):
            return 0
        return 10 if value else 0

    for href, text in html_links(page_html):
        url = absolute_moddb_url(href, base_url)
        parsed = urllib.parse.urlparse(url)
        if not parsed.path.startswith("/mods/brutal-doom/downloads/"):
            continue
        title = text.strip()
        if not title:
            title = parsed.path.rstrip("/").split("/")[-1].replace("-", " ").title()
        if url not in pages or title_quality(title) > title_quality(pages[url]):
            pages[url] = title
    return [(title, url) for url, title in pages.items()]


def brutal_doom_candidate_score(title: str, url: str, channel: str, index: int) -> int:
    slug = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]
    lower = f"{title} {slug}".lower()
    title_compact = re.sub(r"[^a-z0-9]+", "", title.lower())
    slug_compact = re.sub(r"[^a-z0-9]+", "", slug.lower())
    if "brutaldoom" not in title_compact and "brutaldoomv" not in slug_compact and not re.search(r"\bbd\s*v?\d+", title.lower()):
        return -1000
    rejected = [
        "platinum",
        "kickass",
        "monsters only",
        "monster only",
        "metal soundtrack",
        "soundtrack",
        "eday",
        "extermination day",
        "bolognese",
        "meatgrinder",
        "black edition",
        "addon",
        "launcher",
    ]
    if any(token in lower for token in rejected):
        return -1000
    score = 100 - index
    versions: list[int] = []
    for value in re.findall(r"\bv\s*(\d+)", lower):
        # ModDB slugs sometimes collapse dots, e.g. v21.50.0 -> v21500.
        major_text = value[:2] if len(value) >= 4 else value
        versions.append(int(major_text))
    if versions:
        score += max(versions) * 10
    is_test = any(token in lower for token in ["beta", "test", "demo"])
    if channel == "stable":
        score += 100 if not is_test else -200
    else:
        score += 30 if is_test else 0
    if "full version" in lower:
        score += 20
    return score


def select_brutal_doom_download(channel: str, logger: logging.Logger, user_agent: str = DEFAULT_USER_AGENT) -> ModDBDownload:
    pages: list[tuple[str, str]] = []
    errors: list[str] = []
    for source_url in [BRUTAL_DOOM_MODDB_URL, BRUTAL_DOOM_DOWNLOADS_URL]:
        try:
            pages.extend(extract_brutal_doom_pages(fetch_text_url(source_url, logger, user_agent=user_agent), source_url))
        except urllib.error.URLError as exc:
            errors.append(f"{source_url}: {exc}")

    seen: set[str] = set()
    unique_pages: list[tuple[str, str]] = []
    for title, url in pages:
        if url in seen:
            continue
        seen.add(url)
        unique_pages.append((title, url))
    if not unique_pages:
        detail = "; ".join(errors) if errors else "no matching download links found"
        raise DoomDeckError(f"Could not discover Brutal Doom downloads on ModDB: {detail}")

    ranked = sorted(
        enumerate(unique_pages),
        key=lambda item: brutal_doom_candidate_score(item[1][0], item[1][1], channel, item[0]),
        reverse=True,
    )
    for index, (title, page_url) in ranked:
        if brutal_doom_candidate_score(title, page_url, channel, index) <= 0:
            continue
        logger.info("Selected Brutal Doom ModDB page: %s", title)
        try:
            page_html = fetch_text_url(page_url, logger, user_agent=user_agent)
        except urllib.error.URLError as exc:
            logger.warning("Could not read Brutal Doom page %s: %s", page_url, exc)
            continue
        lines = html_text_lines(page_html)
        filename = line_after_label(lines, "Filename") or safe_download_name(page_url, "brutal-doom.zip")
        updated = line_after_label(lines, "Updated")
        md5 = line_after_label(lines, "MD5 Hash")
        start_url = extract_moddb_download_link(page_html, page_url)
        return ModDBDownload(
            title=title,
            page_url=page_url,
            filename=safe_download_name(filename, "brutal-doom.zip"),
            download_url=resolve_moddb_download_url(start_url, page_url, logger, user_agent=user_agent),
            updated=updated,
            md5=md5,
        )

    raise DoomDeckError(f"Could not find a suitable Brutal Doom ModDB download for channel '{channel}'")


def select_moddb_wad_download(page_url: str, logger: logging.Logger, user_agent: str = DEFAULT_USER_AGENT) -> ModDBDownload:
    parsed = urllib.parse.urlparse(page_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc.endswith("moddb.com"):
        raise DoomDeckError(f"--moddb-wad-url must be a ModDB URL, got: {page_url}")

    try:
        page_html = fetch_text_url(page_url, logger, user_agent=user_agent)
    except urllib.error.URLError as exc:
        raise DoomDeckError(f"Could not read ModDB page {page_url}: {exc}") from exc

    lines = html_text_lines(page_html)
    title = next((line for line in lines if line.lower() not in {"hello guest", "description"}), page_url)
    filename = line_after_label(lines, "Filename") or safe_download_name(page_url, "moddb-wad.zip")
    updated = line_after_label(lines, "Updated")
    md5 = line_after_label(lines, "MD5 Hash")
    start_url = extract_moddb_download_link(page_html, page_url)
    return ModDBDownload(
        title=title,
        page_url=page_url,
        filename=safe_download_name(filename, "moddb-wad.zip"),
        download_url=resolve_moddb_download_url(start_url, page_url, logger, user_agent=user_agent),
        updated=updated,
        md5=md5,
    )
