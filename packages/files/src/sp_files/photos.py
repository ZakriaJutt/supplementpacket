"""Photo re-encoding: the only form in which a photo is stored (MH-05, TRD 8.6; B1-011, B2-S01).

Metadata is not stripped by parsing segments or chunks (a parser can always be bypassed:
segments between progressive scans, Multi-Picture secondary images, data after the end
marker, unknown PNG chunks). Instead each accepted photo is decoded to pixels and a new file
is written from those pixels alone:
- only JPEG and PNG are accepted, and the file must decode completely (truncated or
  malformed data is refused);
- at most 40 megapixels, checked from the header before decoding (ASVS 5.2.6);
- only the primary image is kept (a Multi-Picture JPEG's secondary images are dropped);
- the Exif orientation is applied to the pixels first, so the photo still displays upright;
- the long edge is reduced to at most 2,000 pixels (TRD 8.6);
- the new file is written with no Exif, XMP, ICC profile, comments, text chunks or any
  other ancillary data: JPEG as baseline JFIF, PNG with only IHDR, PLTE/tRNS where the
  mode needs them, IDAT and IEND;
- the output is decoded again and checked to carry no metadata before it is returned.
"""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

__all__ = ["MAX_EDGE", "MAX_PIXELS", "PhotoError", "ReencodedPhoto", "reencode_photo"]

MAX_PIXELS = 40_000_000
MAX_EDGE = 2000
_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG"}
_OUT_JPEG_MODES = ("RGB", "L")
_OUT_PNG_MODES = ("RGB", "RGBA", "L", "LA")


class PhotoError(ValueError):
    """The upload is not a JPEG or PNG photo that decodes cleanly within the limits."""


@dataclass(frozen=True)
class ReencodedPhoto:
    data: bytes
    content_type: str
    width: int
    height: int
    frames_dropped: int  # secondary images (for example Multi-Picture) not kept


def reencode_photo(data: bytes, content_type: str) -> ReencodedPhoto:
    """Decode ``data`` (already sniffed as ``content_type``) and return a metadata-free re-encode."""
    expected = _FORMATS.get(content_type)
    if expected is None:
        raise PhotoError("only JPEG and PNG photos are accepted")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
            if img.format not in (expected, "MPO" if expected == "JPEG" else expected):
                raise PhotoError("the file content does not match its image type")
            width, height = img.size
            if width * height > MAX_PIXELS:
                raise PhotoError("larger than 40 megapixels")
            frames = getattr(img, "n_frames", 1)
            img.seek(0)
            img.load()  # full decode of the primary image; truncated data raises
            upright = ImageOps.exif_transpose(img)
    except PhotoError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise PhotoError("the image could not be read") from exc
    pixels = _pixels_only(upright if upright is not None else img, content_type)
    pixels.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    if content_type == "image/jpeg":
        pixels.save(out, format="JPEG", quality=90, optimize=False, progressive=False)
    else:
        pixels.save(out, format="PNG", optimize=False)
    result = out.getvalue()
    _check_clean(result, expected)
    return ReencodedPhoto(result, content_type, pixels.width, pixels.height, max(0, frames - 1))


def _pixels_only(img: Image.Image, content_type: str) -> Image.Image:
    """A new image holding the pixel data only: no ``info`` dictionary, no palette metadata."""
    modes = _OUT_JPEG_MODES if content_type == "image/jpeg" else _OUT_PNG_MODES
    if img.mode not in modes:
        has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
        target = "RGBA" if has_alpha and content_type == "image/png" else ("L" if img.mode in ("1", "I", "I;16", "F") else "RGB")
        img = img.convert(target)
    fresh = Image.new(img.mode, img.size)
    fresh.paste(img)
    return fresh


_METADATA_KEYS = ("exif", "xmp", "XML:com.adobe.xmp", "icc_profile", "comment", "photoshop", "mp", "mpinfo", "adobe", "dpi")


def _check_clean(data: bytes, expected: str) -> None:
    with Image.open(io.BytesIO(data)) as check:
        if check.format != expected or getattr(check, "n_frames", 1) != 1:
            raise PhotoError("re-encoding did not produce a single image")
        found = [k for k in _METADATA_KEYS if k in check.info and k != "dpi"]
        if found or check.getexif():
            raise PhotoError("re-encoding left metadata in the file")
        if expected == "PNG" and getattr(check, "text", None):
            raise PhotoError("re-encoding left text in the file")
