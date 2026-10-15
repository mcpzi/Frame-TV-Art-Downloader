"""
Samsung Frame TV Art — Pyscript entrypoint.

Required configuration.yaml:
pyscript:
  allow_all_imports: true
  hass_is_global: true
"""

CONFIG = {
    "tv_host": "192.168.1.141",
    "token_file": "/config/pyscript/.samsungtvws_token",
    "aspect_ratio_tolerance": 0.428,
    "max_attempts_per_source": 10,
    "enabled_sources": [
        "bing_wallpapers",
        "nga_landscapes",
        "met_japanese_prints",
        "met_european_landscapes",
        "media_folder",
    ],
    "media_folder_path": "/config/www/frame",
}

import logging
import os
import random
import sys
from io import BytesIO

if "/config/pyscript_modules" not in sys.path:
    sys.path.append("/config/pyscript_modules")

from frame_tv_native.image_sources_native import build_sources
from frame_tv_native.image_prep_native import prepare_frame_image
from frame_tv_native.samsung_api_native import upload_and_select

log = logging.getLogger(__name__)


def _path_exists(path):
    return os.path.exists(path)


def _read_file_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


async def _run_refresh(cfg, source_override=None, dry_run=False):
    sources = build_sources(cfg)
    if source_override:
        filtered = []
        for s in sources:
            if s.NAME == source_override:
                filtered.append(s)
        sources = filtered

    if not sources:
        return {"success": False, "message": "No enabled sources available"}

    if not source_override:
        random.shuffle(sources)

    tolerance = cfg.get("aspect_ratio_tolerance", 0.18)
    max_attempts = cfg.get("max_attempts_per_source", 10)

    for source in sources:
        log.info("Trying source: %s", source.NAME)
        last_failure = None

        for attempt in range(1, max_attempts + 1):
            log.info("Source %s attempt %d/%d", source.NAME, attempt, max_attempts)

            try:
                candidate = await task.executor(source.get_candidate)
            except Exception as exc:
                last_failure = "Candidate fetch failed: %s" % exc
                log.error("Source %s candidate lookup failed on attempt %d: %s", source.NAME, attempt, exc)
                continue

            if not candidate:
                last_failure = "No candidate returned"
                log.warning("Source %s returned no candidate on attempt %d", source.NAME, attempt)
                continue

            try:
                image_data, file_type = await task.executor(source.get_image, candidate)
            except Exception as exc:
                last_failure = "Download failed: %s" % exc
                log.error("Source %s image fetch failed on attempt %d: %s", source.NAME, attempt, exc)
                continue

            if image_data is None:
                last_failure = "Download failed"
                log.warning("Source %s failed to download image on attempt %d", source.NAME, attempt)
                continue

            try:
                result = await task.executor(prepare_frame_image, image_data, tolerance)
            except Exception as exc:
                last_failure = "Image prep failed: %s" % exc
                log.error("Image prep failed for source %s on attempt %d: %s", source.NAME, attempt, exc)
                continue

            if not result.get("ok"):
                last_failure = result.get("message", "Image rejected")
                log.warning("Image from %s rejected on attempt %d: %s", source.NAME, attempt, last_failure)
                continue

            remote_filename = None
            if not dry_run:
                try:
                    remote_filename = await task.executor(
                        upload_and_select,
                        cfg["tv_host"],
                        result["output"],
                        "JPEG",
                        cfg.get("token_file"),
                    )
                except Exception as exc:
                    log.error("Upload failed: %s", exc)
                    return {
                        "success": False,
                        "source": source.NAME,
                        "attempt": attempt,
                        "candidate": candidate,
                        "original_size": list(result["original_size"]) if result.get("original_size") else None,
                        "final_size": list(result["final_size"]) if result.get("final_size") else None,
                        "selected_image": None,
                        "uploaded": False,
                        "tv_host": cfg["tv_host"],
                        "message": str(exc),
                    }

            return {
                "success": True,
                "source": source.NAME,
                "attempt": attempt,
                "candidate": candidate,
                "original_size": list(result["original_size"]),
                "final_size": list(result["final_size"]),
                "selected_image": remote_filename,
                "uploaded": not dry_run,
                "tv_host": cfg["tv_host"],
                "crop_applied": result.get("crop_applied"),
                "message": "dry_run" if dry_run else result.get("message", "ok"),
            }

        log.warning("Source %s exhausted after %d attempts: %s", source.NAME, max_attempts, last_failure)

    return {"success": False, "message": "All sources exhausted without a usable image"}

@service(supports_response="optional")
async def frame_tv_art_refresh(source_override=None, tv_host=None, dry_run=False):
    cfg = dict(CONFIG)
    if tv_host:
        cfg["tv_host"] = tv_host
    result = await _run_refresh(cfg, source_override=source_override, dry_run=dry_run)
    log.info("frame_tv_art_refresh result: %s", result)
    return result


@service(supports_response="optional")
async def frame_tv_art_test_source(source_name=None, tv_host=None):
    cfg = dict(CONFIG)
    if tv_host:
        cfg["tv_host"] = tv_host

    sources = build_sources(cfg)
    match = None
    for s in sources:
        if s.NAME == source_name:
            match = s
            break
    if not match:
        return {"success": False, "message": "Source '%s' not enabled or unknown" % source_name}

    tolerance = cfg.get("aspect_ratio_tolerance", 0.18)
    max_attempts = cfg.get("max_attempts_per_source", 10)
    last_failure = None

    for attempt in range(1, max_attempts + 1):
        try:
            candidate = await task.executor(match.get_candidate)
        except Exception as exc:
            last_failure = "Candidate fetch failed: %s" % exc
            continue

        if not candidate:
            last_failure = "No candidate returned"
            continue

        try:
            image_data, file_type = await task.executor(match.get_image, candidate)
        except Exception as exc:
            return {
                "success": False,
                "source": source_name,
                "attempt": attempt,
                "candidate": candidate,
                "message": "Download failed: %s" % exc,
            }

        if image_data is None:
            last_failure = "Download failed"
            continue

        try:
            result = await task.executor(prepare_frame_image, image_data, tolerance)
        except Exception as exc:
            return {
                "success": False,
                "source": source_name,
                "attempt": attempt,
                "candidate": candidate,
                "message": "Image prep failed: %s" % exc,
            }

        if result.get("ok"):
            return {
                "success": True,
                "source": source_name,
                "attempt": attempt,
                "candidate": candidate,
                "original_size": list(result["original_size"]) if result.get("original_size") else None,
                "final_size": list(result["final_size"]) if result.get("final_size") else None,
                "crop_applied": result.get("crop_applied"),
                "message": result.get("message", "ok"),
            }

        last_failure = result.get("message", "Image rejected")

    return {
        "success": False,
        "source": source_name,
        "attempts": max_attempts,
        "message": last_failure or "All attempts failed",
    }

@service(supports_response="optional")
async def frame_tv_art_upload_file(file_path=None, tv_host=None):
    cfg = dict(CONFIG)
    if tv_host:
        cfg["tv_host"] = tv_host

    if not file_path:
        return {"success": False, "message": "file_path is required"}

    exists = await task.executor(_path_exists, file_path)
    if not exists:
        return {"success": False, "message": "File not found: %s" % file_path}

    try:
        raw = await task.executor(_read_file_bytes, file_path)
    except Exception as exc:
        return {"success": False, "message": "Failed to read file: %s" % exc}

    image_data = BytesIO(raw)
    tolerance = cfg.get("aspect_ratio_tolerance", 0.18)

    try:
        result = await task.executor(prepare_frame_image, image_data, tolerance)
    except Exception as exc:
        return {"success": False, "message": "Image prep failed: %s" % exc}

    if not result.get("ok"):
        return {
            "success": False,
            "message": result.get("message"),
            "original_size": list(result["original_size"]) if result.get("original_size") else None,
        }

    try:
        remote_filename = await task.executor(
            upload_and_select,
            cfg["tv_host"],
            result["output"],
            "JPEG",
            cfg.get("token_file"),
        )
    except Exception as exc:
        return {"success": False, "message": str(exc)}

    return {
        "success": True,
        "source": "file",
        "original_size": list(result["original_size"]),
        "final_size": list(result["final_size"]),
        "selected_image": remote_filename,
        "uploaded": True,
        "tv_host": cfg["tv_host"],
        "crop_applied": result.get("crop_applied"),
        "message": result.get("message", "ok"),
    }
