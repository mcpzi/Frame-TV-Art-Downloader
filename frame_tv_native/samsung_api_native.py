"""Thin native wrapper around samsungtvws for art upload and selection."""

import logging
from io import BytesIO

log = logging.getLogger(__name__)


def upload_and_select(
    tv_host: str,
    image_data: BytesIO,
    file_type: str = "JPEG",
    token_file: str | None = None,
) -> str:
    """
    Upload image_data to the TV and select it as current art.

    Returns the remote filename assigned by the TV.
    """
    from samsungtvws import SamsungTVWS

    kwargs = {}
    if token_file:
        kwargs["token_file"] = token_file

    tv = None
    try:
        tv = SamsungTVWS(tv_host, **kwargs)

        art = tv.art()
        if not art.supported():
            raise RuntimeError(f"TV at {tv_host} does not support art mode")

        log.info("Uploading image to TV at %s", tv_host)
        image_data.seek(0)
        remote_filename = art.upload(
            image_data.getvalue(),
            file_type=file_type,
            matte="none",
        )

        if not remote_filename:
            raise RuntimeError("TV returned no remote filename after upload")

        log.info("Selecting art %s on TV at %s", remote_filename, tv_host)
        art.select_image(remote_filename, show=True)
        return remote_filename

    finally:
        try:
            if tv and hasattr(tv, "close"):
                tv.close()
        except Exception:
            pass