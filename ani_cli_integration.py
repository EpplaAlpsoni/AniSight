import json
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from typing import Dict, List


def find_ani_cli() -> str:
    """Return the path to ani-cli, or a fallback command name."""
    candidates = [
        os.environ.get("ANI_CLI_PATH"),
        shutil.which("ani-cli"),
        os.path.expanduser("~/.local/bin/ani-cli"),
        "/usr/local/bin/ani-cli",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return "ani-cli"


def build_ani_cli_command(query: str, episode: int | None = None) -> str:
    """Build an ani-cli command string for a search or watch request."""
    binary = find_ani_cli()
    parts = [binary, query]
    if episode is not None:
        parts.append(str(episode))
    return " ".join(parts)


def strip_html(value: str) -> str:
    cleaned = re.sub(r"<.*?>", " ", value or "")
    cleaned = html_unescape(cleaned)
    return " ".join(cleaned.split())


def html_unescape(value: str) -> str:
    value = value.replace("&amp;", "&")
    value = value.replace("&#039;", "'")
    value = value.replace("&quot;", '"')
    value = value.replace("&lt;", "<")
    value = value.replace("&gt;", ">")
    return value


def fetch_anilist_results(query: str, limit: int = 8) -> List[Dict[str, str]]:
    """Query AniList for results, poster art, banners, and synopsis for the UI."""
    graphql = """
    query ($search: String, $page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        media(search: $search, type: ANIME, sort: [POPULARITY_DESC]) {
          id
          siteUrl
          title {
            romaji
            english
            native
          }
          description
          coverImage {
            large
            medium
          }
          bannerImage
          episodes
          averageScore
          season
          seasonYear
          genres
        }
      }
    }
    """
    payload = {
        "query": graphql,
        "variables": {"search": query.strip(), "page": 1, "perPage": limit},
    }
    request = urllib.request.Request(
        "https://graphql.anilist.co",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Madomi/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    media = body.get("data", {}).get("Page", {}).get("media", [])
    results: List[Dict[str, str]] = []
    seen = set()
    for item in media:
        title_data = item.get("title", {})
        title = (
            title_data.get("english")
            or title_data.get("romaji")
            or title_data.get("native")
            or "Unknown title"
        )
        if title in seen:
            continue
        seen.add(title)
        cover = (item.get("coverImage") or {}).get("large") or (item.get("coverImage") or {}).get("medium")
        banner = item.get("bannerImage") or cover or ""
        description = strip_html(item.get("description") or "")
        results.append({
            "title": title,
            "description": description,
            "poster_url": cover or "",
            "banner_url": banner or "",
            "episodes": str(item.get("episodes") or "-"),
            "score": str(item.get("averageScore") or "-"),
            "season": (item.get("season") or "").title(),
            "season_year": str(item.get("seasonYear") or ""),
            "genres": ", ".join(item.get("genres") or []),
            "site_url": item.get("siteUrl") or "",
        })
    return results


def fetch_trending_anime(limit: int = 8) -> List[Dict[str, str]]:
    """Fetch trending anime for the home screen."""
    graphql = """
    query ($page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        media(type: ANIME, sort: [TRENDING_DESC], isAdult: false) {
          id
          siteUrl
          title { romaji english native }
          description
          coverImage { large medium }
          bannerImage
          episodes
          averageScore
          season
          seasonYear
          genres
        }
      }
    }
    """
    request = urllib.request.Request(
        "https://graphql.anilist.co",
        data=json.dumps({
            "query": graphql,
            "variables": {"page": 1, "perPage": limit},
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Madomi/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    media = body.get("data", {}).get("Page", {}).get("media", [])
    results: List[Dict[str, str]] = []
    for item in media:
        title_data = item.get("title", {})
        title = title_data.get("english") or title_data.get("romaji") or title_data.get("native") or "Unknown title"
        cover = (item.get("coverImage") or {}).get("large") or (item.get("coverImage") or {}).get("medium")
        banner = item.get("bannerImage") or cover or ""
        results.append({
            "title": title,
            "description": strip_html(item.get("description") or ""),
            "poster_url": cover or "",
            "banner_url": banner or "",
            "episodes": str(item.get("episodes") or "-"),
            "score": str(item.get("averageScore") or "-"),
            "season": (item.get("season") or "").title(),
            "season_year": str(item.get("seasonYear") or ""),
            "genres": ", ".join(item.get("genres") or []),
            "site_url": item.get("siteUrl") or "",
        })
    return results


def fetch_anime_seasons(title: str) -> List[Dict[str, str]]:
    """Return the TV/ONA prequel-sequel chain containing ``title``."""
    fields = """
      id
      siteUrl
      format
      startDate { year month day }
      title { romaji english native }
      description
      coverImage { large medium }
      bannerImage
      episodes
      averageScore
      season
      seasonYear
      genres
      relations {
        edges {
          relationType
          node { id type format }
        }
      }
    """
    search_query = f"query ($search: String) {{ Media(search: $search, type: ANIME) {{ {fields} }} }}"
    id_query = f"query ($id: Int) {{ Media(id: $id, type: ANIME) {{ {fields} }} }}"

    def request_media(query: str, variables: Dict) -> Dict:
        request = urllib.request.Request(
            "https://graphql.anilist.co",
            data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Madomi/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8")).get("data", {}).get("Media") or {}
        except Exception:
            return {}

    first = request_media(search_query, {"search": title.strip()})
    if not first:
        return []

    media_by_id = {}
    pending = [first]
    while pending and len(media_by_id) < 20:
        item = pending.pop(0)
        media_id = item.get("id")
        if not media_id or media_id in media_by_id:
            continue
        media_by_id[media_id] = item
        for edge in (item.get("relations") or {}).get("edges", []):
            node = edge.get("node") or {}
            if (
                edge.get("relationType") in {"PREQUEL", "SEQUEL"}
                and node.get("type") == "ANIME"
                and node.get("format") in {"TV", "TV_SHORT", "ONA"}
                and node.get("id") not in media_by_id
            ):
                related = request_media(id_query, {"id": node.get("id")})
                if related:
                    pending.append(related)

    def to_result(item: Dict) -> Dict[str, str]:
        title_data = item.get("title") or {}
        display_title = title_data.get("english") or title_data.get("romaji") or title_data.get("native") or "Unknown title"
        cover_data = item.get("coverImage") or {}
        cover = cover_data.get("large") or cover_data.get("medium") or ""
        start_date = item.get("startDate") or {}
        return {
            "title": display_title,
            "description": strip_html(item.get("description") or ""),
            "poster_url": cover,
            "banner_url": item.get("bannerImage") or cover,
            "episodes": str(item.get("episodes") or "-"),
            "score": str(item.get("averageScore") or "-"),
            "season": (item.get("season") or "").title(),
            "season_year": str(item.get("seasonYear") or ""),
            "genres": ", ".join(item.get("genres") or []),
            "site_url": item.get("siteUrl") or "",
            "start_year": str(start_date.get("year") or ""),
            "start_month": str(start_date.get("month") or ""),
        }

    results = [to_result(item) for item in media_by_id.values()]
    results.sort(key=lambda item: (item.get("start_year") or "9999", item.get("start_month") or "99", item["title"]))
    return results


def fetch_search_results(query: str) -> List[Dict[str, str]]:
    """Return live anime data for the UI from AniList."""
    if not query or not query.strip():
        return fetch_trending_anime(8)
    return fetch_anilist_results(query, limit=10)


def search_anime(query: str) -> List[str]:
    """Compatibility wrapper returning title strings."""
    return [item["title"] for item in fetch_search_results(query)]


def watch_episode(
    query: str,
    episode: int | None = None,
    window_id: int | None = None,
    ipc_socket: str | None = None,
) -> str:
    """Launch ani-cli, optionally embedding mpv into an existing window."""
    binary = find_ani_cli()
    cmd = [binary, "-S", "1"]
    if episode is not None:
        cmd.extend(["-e", str(episode)])
    cmd.append(query)
    env = os.environ.copy()
    if window_id is not None:
        env["ANI_CLI_MENU"] = "grep"
        env["ANI_CLI_PLAYER_FLAGS"] = " ".join(
            flag for flag in (
                f"--wid={window_id}",
                f"--input-ipc-server={ipc_socket}" if ipc_socket else "",
                "--force-window=yes",
                "--keep-open=no",
            ) if flag
        )
    try:
        subprocess.Popen(cmd, env=env)
    except FileNotFoundError:
        return "ani-cli was not found. Install it or set ANI_CLI_PATH."
    return "Loading stream…"
