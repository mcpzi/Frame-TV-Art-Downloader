"""Image validation and resize/crop to Samsung Frame resolution."""

from io import BytesIO

from PIL import Image

TARGET_WIDTH = 3840
TARGET_HEIGHT = 2160
TARGET_RATIO = TARGET_WIDTH / TARGET_HEIGHT
MIN_WIDTH = 1920
MIN_HEIGHT = 1080


def _clone_bytesio(image_data: BytesIO) -> BytesIO:
    image_data.seek(0)
    return BytesIO(image_data.read())


def prepare_frame_image(image_data: BytesIO, tolerance: float = 0.05) -> dict:
    """
    Validate, reject portrait images, aspect-ratio-filter, center-crop, and resize to 3840x2160.

    Returns:
    {
      "ok": bool,
      "original_size": (w, h) | None,
      "final_size": (3840, 2160) | None,
      "crop_applied": bool,
      "output": BytesIO | None,
      "message": str,
    }
    """
    img_io = _clone_bytesio(image_data)

    with Image.open(img_io) as img:
        orig_w, orig_h = img.size

        if orig_w <= orig_h:
            return {
                "ok": False,
                "original_size": (orig_w, orig_h),
                "final_size": None,
                "crop_applied": False,
                "output": None,
                "message": f"Portrait or square image rejected: {orig_w}x{orig_h}",
            }

        if orig_w < MIN_WIDTH or orig_h < MIN_HEIGHT:
            return {
                "ok": False,
                "original_size": (orig_w, orig_h),
                "final_size": None,
                "crop_applied": False,
                "output": None,
                "message": f"Resolution too low: {orig_w}x{orig_h} (minimum {MIN_WIDTH}x{MIN_HEIGHT})",
            }

        ratio = orig_w / orig_h
        if abs(ratio - TARGET_RATIO) > tolerance:
            return {
                "ok": False,
                "original_size": (orig_w, orig_h),
                "final_size": None,
                "crop_applied": False,
                "output": None,
                "message": f"Aspect ratio {ratio:.3f} outside tolerance (target {TARGET_RATIO:.3f} ±{tolerance})",
            }

        img = img.convert("RGB")

        if ratio > TARGET_RATIO:
            new_h = TARGET_HEIGHT
            new_w = int(new_h * ratio)
        else:
            new_w = TARGET_WIDTH
            new_h = int(new_w / ratio)

        img = img.resize((new_w, new_h), Image.LANCZOS)

        left = (new_w - TARGET_WIDTH) // 2
        top = (new_h - TARGET_HEIGHT) // 2
        img = img.crop((left, top, left + TARGET_WIDTH, top + TARGET_HEIGHT))

        output = BytesIO()
        img.save(output, format="JPEG", quality=90)
        output.seek(0)

        return {
            "ok": True,
            "original_size": (orig_w, orig_h),
            "final_size": (TARGET_WIDTH, TARGET_HEIGHT),
            "crop_applied": (orig_w, orig_h) != (TARGET_WIDTH, TARGET_HEIGHT),
            "output": output,
            "message": "ok",
        }
