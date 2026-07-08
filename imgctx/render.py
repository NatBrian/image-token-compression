"""Text -> PNG page renderer (reportlab -> PDF -> pdf2image -> PIL).

Renders dense black-on-white text pages sized to stay under a vision encoder's
downscale threshold, with a visible marker at every hard newline so the model
can tell real line breaks from soft wraps.
"""
from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional
from xml.sax.saxutils import escape

from pdf2image import convert_from_bytes
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate

from .config import Settings

_RE_CJK = re.compile(r"[一-鿿぀-ヿ가-힯]")
_RE_MULTISPACE = re.compile(r"  +")
# Red literal "\n" drawn where every hard newline was. Dense (lines reflow to
# fill the column) yet unambiguous. Falls back to <br/> when markers are off.
_NL_MARKER = '<font color="#cc0000">\\n</font>'
_LINES_PER_PARAGRAPH = 30
_REGISTERED: set[str] = set()


@dataclass
class RenderedPage:
    b64: str
    width: int
    height: int
    pixels: int


@lru_cache(maxsize=8)
def _register_font(path: str, is_cjk: bool) -> str:
    """Register a TTF with reportlab once; return the internal font name."""
    name = f"imgctx_{'cjk' if is_cjk else 'latin'}_{abs(hash(path)) % 10**8}"
    if name not in _REGISTERED:
        pdfmetrics.registerFont(TTFont(name, path))
        _REGISTERED.add(name)
    return name


def _preprocess(text: str, marker: bool) -> str:
    """Escape XML, preserve indentation, and join lines with the newline marker."""
    # Drop zero-width / soft-hyphen chars that confuse layout.
    text = text.replace("\xad", "").replace("​", "")
    text = text.replace("\t", "    ")
    join = _NL_MARKER if marker else "<br/>"
    out_paragraphs: list[str] = []
    lines = text.split("\n")
    for i in range(0, len(lines), _LINES_PER_PARAGRAPH):
        chunk = lines[i : i + _LINES_PER_PARAGRAPH]
        rendered = []
        for line in chunk:
            esc = escape(line)
            # Preserve runs of spaces (reportlab collapses whitespace otherwise).
            esc = _RE_MULTISPACE.sub(lambda m: "&nbsp;" * len(m.group(0)), esc)
            rendered.append(esc)
        out_paragraphs.append(join.join(rendered))
    return "<br/>".join(out_paragraphs)


def _text_to_pdf_bytes(text: str, settings: Settings) -> bytes:
    font_path = settings.font_path
    is_cjk = bool(_RE_CJK.search(text)) and bool(settings.cjk_font_path)
    if is_cjk:
        font_path = settings.cjk_font_path
    font_name = _register_font(font_path, is_cjk)

    style = ParagraphStyle(
        name="body",
        fontName=font_name,
        fontSize=settings.font_size,
        leading=settings.line_height,
        wordWrap="CJK" if is_cjk else None,
        spaceAfter=0,
        spaceBefore=0,
    )
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=10,
        rightMargin=10,
        topMargin=10,
        bottomMargin=10,
    )
    body = _preprocess(text, settings.newline_marker)
    story = [Paragraph(para, style) for para in body.split("<br/><br/>") if para] or [
        Paragraph(body or "&nbsp;", style)
    ]
    doc.build(story)
    return buf.getvalue()


def _autocrop(img: Image.Image) -> Image.Image:
    """Trim surrounding whitespace to cut pixel cost."""
    gray = img.convert("L")
    # Invert so text (dark) is bright; getbbox finds the content box.
    inverted = Image.eval(gray, lambda p: 255 - p)
    bbox = inverted.getbbox()
    if not bbox:
        return img
    pad = 4
    left = max(0, bbox[0] - pad)
    top = max(0, bbox[1] - pad)
    right = min(img.width, bbox[2] + pad)
    bottom = min(img.height, bbox[3] + pad)
    return img.crop((left, top, right, bottom))


def _downscale(img: Image.Image, max_pixels: int) -> Image.Image:
    w, h = img.size
    if w * h <= max_pixels or w * h == 0:
        return img
    scale = (max_pixels / (w * h)) ** 0.5
    nw = max(1, int(w * scale))
    nh = max(1, int(h * scale))
    return img.resize((nw, nh), Image.LANCZOS)


def render_text_to_pages(text: str, settings: Settings) -> list[RenderedPage]:
    """Render `text` into one or more base64 PNG pages."""
    if not text:
        return []
    pdf_bytes = _text_to_pdf_bytes(text, settings)
    images = convert_from_bytes(pdf_bytes, dpi=settings.dpi)
    pages: list[RenderedPage] = []
    for img in images:
        img = _autocrop(img)
        img = _downscale(img, settings.max_pixels_per_image)
        out = io.BytesIO()
        img.convert("RGB").save(out, format="PNG", optimize=True)
        data = out.getvalue()
        pages.append(
            RenderedPage(
                b64=base64.b64encode(data).decode("ascii"),
                width=img.width,
                height=img.height,
                pixels=img.width * img.height,
            )
        )
    return pages
