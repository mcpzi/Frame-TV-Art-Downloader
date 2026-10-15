"""
Native Python image source adapters.

Each adapter exposes:
get_candidate() -> str | None
get_image(candidate) -> (BytesIO, str) | (None, None)
NAME: str
"""

import logging
import os
import random
from io import BytesIO

import requests

log = logging.getLogger(__name__)

_bing_cache = []
_met_cache = {}
_smithsonian_cache = {}
_nga_cache = {}


class BaseArtSource:
    session_headers = {"User-Agent": "FrameTVArt/1.0"}

    def _get_json(self, url, **kwargs):
        r = requests.get(url, timeout=20, headers=self.session_headers, **kwargs)
        r.raise_for_status()
        return r.json()

    def get_image(self, url):
        r = requests.get(url, timeout=60, headers=self.session_headers)
        r.raise_for_status()
        return BytesIO(r.content), "JPEG"


class BingSource(BaseArtSource):
    NAME = "bing_wallpapers"

    def get_candidate(self):
        global _bing_cache
        if not _bing_cache:
            log.info("Fetching Bing wallpaper index...")
            r = requests.get("https://bing.npanuhin.me/US/en.min.json", timeout=15, headers=self.session_headers)
            r.raise_for_status()
            _bing_cache = [item["url"] for item in r.json() if "url" in item]
            log.info("Cached %d Bing wallpaper URLs", len(_bing_cache))
        return random.choice(_bing_cache) if _bing_cache else None


class NGALandscapeSource(BaseArtSource):
    NAME = "nga_landscapes"
    SEARCHES = ["Monet landscape", "Sisley landscape", "Pissarro landscape", "Renoir landscape"]

    def get_candidate(self):
        global _nga_cache
        if not _nga_cache.get(self.NAME):
            import re
            candidates = []
            for q in self.SEARCHES:
                r = requests.get(
                    "https://www.nga.gov/collection-search-result.html",
                    params={
                        "artobj_artist": "",
                        "artobj_title": q,
                        "artobj_downloadopenaccess": "Open Access",
                        "sortOrder": "DEFAULT",
                        "lastFacet": "artobj_downloadopenaccess",
                        "pageNumber": 1,
                    },
                    timeout=20,
                    headers=self.session_headers,
                )
                r.raise_for_status()
                text = r.text
                matches = re.findall(r"https://api\\.nga\\.gov/iiif/[^\"']+/[^\"']*default\\.jpg", text)
                candidates.extend(matches)
            seen = set()
            deduped = []
            for url in candidates:
                if url not in seen:
                    seen.add(url)
                    deduped.append(url)
            _nga_cache[self.NAME] = deduped
            log.info("Cached %d NGA image URLs", len(_nga_cache[self.NAME]))
        urls = _nga_cache.get(self.NAME, [])
        return random.choice(urls) if urls else None


class MetJapanesePrintsSource(BaseArtSource):
    NAME = "met_japanese_prints"
    QUERY = "japanese woodblock landscape"

    def get_candidate(self):
        return self._pick_met_candidate(self.NAME, self.QUERY)

    def _pick_met_candidate(self, cache_key, query):
        global _met_cache
        if cache_key not in _met_cache:
            data = self._get_json(
                "https://collectionapi.metmuseum.org/public/collection/v1/search",
                params={"q": query, "hasImages": "true"},
            )
            _met_cache[cache_key] = data.get("objectIDs") or []
            log.info("Cached %d Met object IDs for %s", len(_met_cache[cache_key]), cache_key)

        ids = _met_cache[cache_key]
        if not ids:
            return None

        sample = random.sample(ids, min(len(ids), 12))
        for object_id in sample:
            try:
                obj = self._get_json("https://collectionapi.metmuseum.org/public/collection/v1/objects/%s" % object_id)
            except Exception:
                continue
            if obj.get("isPublicDomain") and obj.get("primaryImage"):
                return obj["primaryImage"]
        return None


class MetEuropeanLandscapesSource(MetJapanesePrintsSource):
    NAME = "met_european_landscapes"
    QUERY = "european landscape painting"

    def get_candidate(self):
        return self._pick_met_candidate(self.NAME, self.QUERY)


class SmithsonianLandscapeSource(BaseArtSource):
    NAME = "smithsonian_landscapes"
    QUERY = "landscape art"

    def __init__(self):
        self.api_key = os.environ.get("SMITHSONIAN_API_KEY")

    def get_candidate(self):
        global _smithsonian_cache
        if not self.api_key:
            log.warning("SMITHSONIAN_API_KEY not set; Smithsonian source disabled")
            return None

        if self.NAME not in _smithsonian_cache:
            data = self._get_json(
                "https://api.si.edu/openaccess/api/v1.0/search",
                params={
                    "api_key": self.api_key,
                    "q": self.QUERY,
                    "rows": 100,
                    "start": 0,
                },
            )
            rows = data.get("response", {}).get("rows", [])
            candidates = []
            for row in rows:
                media = row.get("content", {}).get("descriptiveNonRepeating", {}).get("online_media", {}).get("media", [])
                for item in media:
                    if item.get("type") == "Images" and item.get("content"):
                        candidates.append(item["content"])
            _smithsonian_cache[self.NAME] = candidates
            log.info("Cached %d Smithsonian image URLs", len(candidates))

        urls = _smithsonian_cache.get(self.NAME, [])
        return random.choice(urls) if urls else None


class MediaFolderSource:
    NAME = "media_folder"

    def __init__(self, folder):
        self.folder = folder

    def get_candidate(self):
        exts = (".jpg", ".jpeg", ".png")
        files = []
        for root, _, names in os.walk(self.folder):
            for filename in names:
                if filename.lower().endswith(exts):
                    files.append(os.path.join(root, filename))
        if not files:
            log.info("No images found in media folder: %s", self.folder)
            return None
        return random.choice(files)

    def get_image(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        file_type = "PNG" if path.lower().endswith(".png") else "JPEG"
        with open(path, "rb") as fh:
            return BytesIO(fh.read()), file_type


def build_sources(config):
    enabled = config.get("enabled_sources", [])
    mapping = {
        "bing_wallpapers": BingSource,
        "nga_landscapes": NGALandscapeSource,
        "met_japanese_prints": MetJapanesePrintsSource,
        "met_european_landscapes": MetEuropeanLandscapesSource,
        "smithsonian_landscapes": SmithsonianLandscapeSource,
    }

    sources = []
    for name in enabled:
        if name == "media_folder":
            folder = config.get("media_folder_path", "/config/www/frame")
            sources.append(MediaFolderSource(folder))
        elif name in mapping:
            sources.append(mapping[name]())
        else:
            log.warning("Unknown source '%s', skipping", name)
    return sources
