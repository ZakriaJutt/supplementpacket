"""Remove location and other embedded metadata from uploaded photos (MH-05, TRD 8.6, B1-011).

Standard library only, byte-level: JPEG APP1 (Exif, XMP, where GPS lives), APP3 to APP13,
APP15 and comment segments are dropped; JFIF (APP0), ICC profiles (APP2) and Adobe (APP14)
are kept so colours render the same. PNG eXIf, tEXt, zTXt, iTXt and tIME chunks are dropped.
Pixels are not decoded or re-encoded (re-encoding to 2,000 pixels needs an image library and
is not done). HEIC cannot be cleaned this way and is refused by the caller.
"""

from __future__ import annotations

import struct

__all__ = ["MetadataError", "strip_metadata"]

_JPEG_KEEP_APP = {0xE0, 0xE2, 0xEE}  # APP0 JFIF, APP2 ICC profile, APP14 Adobe
_PNG_DROP = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


class MetadataError(ValueError):
    """The file could not be read as the image type its content claims."""


def strip_metadata(data: bytes, content_type: str) -> tuple[bytes, int]:
    """Return the cleaned bytes and the number of metadata blocks removed."""
    if content_type == "image/jpeg":
        return _jpeg(data)
    if content_type == "image/png":
        return _png(data)
    raise MetadataError(f"metadata removal is not supported for {content_type}")


def _jpeg(data: bytes) -> tuple[bytes, int]:
    if not data.startswith(b"\xff\xd8"):
        raise MetadataError("not a JPEG")
    out = bytearray(b"\xff\xd8")
    i, removed = 2, 0
    while i < len(data):
        if data[i] != 0xFF:
            raise MetadataError("corrupt JPEG segment")
        while i < len(data) and data[i] == 0xFF:  # fill bytes
            i += 1
        if i >= len(data):
            raise MetadataError("truncated JPEG")
        marker = data[i]
        i += 1
        if marker == 0xD9:  # EOI
            out += b"\xff\xd9"
            return bytes(out), removed
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:  # standalone markers
            out += bytes((0xFF, marker))
            continue
        if i + 2 > len(data):
            raise MetadataError("truncated JPEG")
        (length,) = struct.unpack(">H", data[i : i + 2])
        if length < 2 or i + length > len(data):
            raise MetadataError("corrupt JPEG segment length")
        segment = data[i : i + length]
        i += length
        if marker == 0xDA:  # start of scan: the entropy-coded data and the rest are kept as they are
            out += bytes((0xFF, marker)) + segment + data[i:]
            return bytes(out), removed
        is_app = 0xE0 <= marker <= 0xEF
        if (is_app and marker not in _JPEG_KEEP_APP) or marker == 0xFE:
            removed += 1
            continue
        out += bytes((0xFF, marker)) + segment
    raise MetadataError("JPEG without image data")


def _png(data: bytes) -> tuple[bytes, int]:
    if not data.startswith(_PNG_SIG):
        raise MetadataError("not a PNG")
    out = bytearray(_PNG_SIG)
    i, removed = len(_PNG_SIG), 0
    while i < len(data):
        if i + 8 > len(data):
            raise MetadataError("truncated PNG")
        length, kind = struct.unpack(">I4s", data[i : i + 8])
        end = i + 12 + length
        if end > len(data):
            raise MetadataError("corrupt PNG chunk length")
        if kind in _PNG_DROP:
            removed += 1
        else:
            out += data[i:end]
        i = end
        if kind == b"IEND":
            return bytes(out), removed
    raise MetadataError("PNG without IEND")
