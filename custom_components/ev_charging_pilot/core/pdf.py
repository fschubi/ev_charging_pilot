"""A tiny PDF writer – text, lines, rectangles – without third-party packages.

Home Assistant integrations should not pull heavy requirements for a monthly
report, so this writes PDF 1.4 directly with the 14 standard fonts
(Helvetica, Helvetica-Bold) in WinAnsi encoding, which covers German umlauts,
ß and €.
"""

from __future__ import annotations

import zlib

A4 = (595.28, 841.89)

# Helvetica advance widths (1/1000 em) for the characters a report uses;
# everything else falls back to an average width.
_WIDTHS = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667, "'": 191,
    "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333, ".": 278, "/": 278,
    ":": 278, ";": 278, "<": 584, "=": 584, ">": 584, "?": 556, "@": 1015, "€": 556,
    "–": 556, "·": 278, "°": 400, "ä": 556, "ö": 556, "ü": 556, "ß": 611, "Ä": 667,
    "Ö": 778, "Ü": 722, "→": 1000, "Ø": 778, "|": 260,
    **dict.fromkeys("0123456789", 556),
    **dict.fromkeys("abcdeghnopqsuvxyz", 556), **dict.fromkeys("fjt", 278),
    **dict.fromkeys("il", 222), "k": 500, "m": 833, "r": 333, "w": 722,
    **dict.fromkeys("ABEKPSVXY", 667), **dict.fromkeys("CDHNRUw", 722),
    **dict.fromkeys("GOQ", 778), "F": 611, "T": 611, "Z": 611, "I": 278, "J": 500,
    "L": 556, "M": 833, "W": 944,
}
_BOLD_FACTOR = 1.06


def text_width(text: str, size: float, bold: bool = False) -> float:
    width = sum(_WIDTHS.get(ch, 556) for ch in text) * size / 1000
    return width * (_BOLD_FACTOR if bold else 1)


def _escape(text: str) -> bytes:
    raw = text.replace("→", "->").encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _color(rgb: tuple[float, float, float]) -> str:
    return " ".join(f"{c:.3f}" for c in rgb)


class PdfDocument:
    def __init__(self, size: tuple[float, float] = A4, title: str = "") -> None:
        self.width, self.height = size
        self.title = title
        self.pages: list[list[bytes]] = []
        self.new_page()

    def new_page(self) -> None:
        self.pages.append([])

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def _op(self, data: bytes | str) -> None:
        self.pages[-1].append(data.encode("latin-1") if isinstance(data, str) else data)

    def text(self, x: float, y: float, text: str, size: float = 10, *, bold: bool = False,
             color: tuple[float, float, float] = (0, 0, 0), align: str = "left") -> None:
        if align != "left":
            width = text_width(text, size, bold)
            x -= width if align == "right" else width / 2
        font = "F2" if bold else "F1"
        self._op(f"BT /{font} {size:.1f} Tf {_color(color)} rg {x:.2f} {y:.2f} Td (")
        self._op(_escape(text))
        self._op(b") Tj ET\n")

    def line(self, x1: float, y1: float, x2: float, y2: float, width: float = 0.5,
             color: tuple[float, float, float] = (0.75, 0.75, 0.75)) -> None:
        self._op(f"{width:.2f} w {_color(color)} RG {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S\n")

    def rect(self, x: float, y: float, w: float, h: float, *,
             fill: tuple[float, float, float] | None = None,
             stroke: tuple[float, float, float] | None = None) -> None:
        ops = f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re "
        if fill and stroke:
            self._op(f"{_color(fill)} rg {_color(stroke)} RG {ops}B\n")
        elif fill:
            self._op(f"{_color(fill)} rg {ops}f\n")
        else:
            self._op(f"{_color(stroke or (0, 0, 0))} RG {ops}S\n")

    def to_bytes(self) -> bytes:
        objects: list[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        catalog = add(b"")  # placeholder, filled below
        pages_id = add(b"")
        font = b"/Type /Font /Subtype /Type1 /Encoding /WinAnsiEncoding /BaseFont "
        f1 = add(b"<< " + font + b"/Helvetica >>")
        f2 = add(b"<< " + font + b"/Helvetica-Bold >>")
        page_ids = []
        for ops in self.pages:
            stream = zlib.compress(b"".join(ops))
            content = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream)
                          + stream + b"\nendstream")
            page_ids.append(add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] "
                b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
                % (pages_id, self.width, self.height, f1, f2, content)))
        kids = b" ".join(b"%d 0 R" % i for i in page_ids)
        objects[pages_id - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))
        objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id
        info = add(b"<< /Title (" + _escape(self.title) + b") /Producer (EV Charging Pilot) >>")

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        for offset in offsets:
            out += b"%010d 00000 n \n" % offset
        out += (b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (len(objects) + 1, catalog, info, xref))
        return bytes(out)
