"""Inspect PNG headers and chunk structure without decoding the raster."""

from hashlib import sha256
from zlib import crc32

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_header_dimensions(data: bytes) -> tuple[int, int] | None:
    """Return positive pixel dimensions from PNG bytes, or None for an invalid header."""
    if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return (width, height) if width > 0 and height > 0 else None


def inspect_png(data: bytes) -> tuple[tuple[int, int], str] | None:
    """Verify PNG chunk boundaries and CRCs and fingerprint compressed image data.

    Returns None for a missing or corrupt container. The scan does not decode pixels.
    """
    size = png_header_dimensions(data)
    if size is None:
        return None
    # The PNG layout specifies a 13-byte IHDR and length/type/CRC around each chunk.
    offset, header_size, chunk_overhead = len(PNG_SIGNATURE), 13, 12
    stream = memoryview(data)
    image_data = sha256()
    has_image_data = False
    while offset + chunk_overhead <= len(stream):
        length = int.from_bytes(stream[offset : offset + 4], "big")
        kind = data[offset + 4 : offset + 8]
        end = offset + chunk_overhead + length
        if end > len(stream) or crc32(stream[offset + 4 : end - 4]) != int.from_bytes(
            stream[end - 4 : end], "big"
        ):
            return None  # A readable signature cannot establish a complete capture.
        if kind == b"IHDR" and (length != header_size or offset != len(PNG_SIGNATURE)):
            return None  # A PNG has exactly one initial header.
        if kind == b"IDAT" and length:
            image_data.update(stream[offset + 8 : end - 4])
            has_image_data = True
        if kind == b"IEND":
            # Trailing bytes or an empty data stream are not complete capture evidence.
            return (
                (size, image_data.hexdigest())
                if end == len(stream) and not length and has_image_data
                else None
            )
        offset = end
    return None
