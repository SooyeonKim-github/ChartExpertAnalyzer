from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from bs4 import BeautifulSoup


XML_ENCODING_RE = re.compile(br"encoding=[\"']([^\"']+)[\"']", re.I)
TARGET_SUFFIXES = (".xml", ".html", ".htm", ".xhtml")
CONTRACT_KEYWORDS = (
    "단일판매", "공급계약", "계약금액", "계약상대방", "최근매출액", "매출액대비", "계약기간"
)


@dataclass(frozen=True)
class DocumentPart:
    name: str
    text: str
    score: float


def decode_document(data: bytes) -> str:
    encodings: list[str] = []
    match = XML_ENCODING_RE.search(data[:300])
    if match:
        try:
            encodings.append(match.group(1).decode("ascii", errors="ignore"))
        except Exception:
            pass
    encodings.extend(["utf-8-sig", "utf-8", "euc-kr", "cp949"])

    seen = set()
    for encoding in encodings:
        key = encoding.casefold()
        if not encoding or key in seen:
            continue
        seen.add(key)
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def normalize_cell(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


class DartDocumentParser:
    VERSION = "DART_DOCUMENT_V1_1"

    @staticmethod
    def _score(name: str, text: str) -> float:
        lower_name = name.casefold()
        score = 0.0
        for keyword in CONTRACT_KEYWORDS:
            if keyword in text:
                score += 10.0
        if "정정" in text[:5000]:
            score += 3.0
        if lower_name.endswith(".xml"):
            score += 2.0
        score += min(len(text) / 20000.0, 5.0)
        return score

    def extract_parts(self, archive: bytes) -> list[DocumentPart]:
        try:
            with ZipFile(BytesIO(archive)) as zf:
                parts: list[DocumentPart] = []
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename
                    if not name.casefold().endswith(TARGET_SUFFIXES):
                        continue
                    data = zf.read(info)
                    if not data:
                        continue
                    text = decode_document(data)
                    parts.append(DocumentPart(name=name, text=text, score=self._score(name, text)))
                return parts
        except BadZipFile as exc:
            raise ValueError("OpenDART document payload is not a valid ZIP") from exc

    def select_contract_document(self, archive: bytes) -> DocumentPart:
        parts = self.extract_parts(archive)
        if not parts:
            raise ValueError("ZIP contains no XML/HTML document")
        parts.sort(key=lambda part: (-part.score, -len(part.text), part.name))
        return parts[0]

    @staticmethod
    def table_rows(text: str) -> list[list[str]]:
        soup = BeautifulSoup(text, "html.parser")
        rows: list[list[str]] = []
        for tr in soup.find_all("tr"):
            cells = [normalize_cell(cell.get_text(" ", strip=True)) for cell in tr.find_all(["td", "th"])]
            cells = [cell for cell in cells if cell]
            if len(cells) >= 2:
                rows.append(cells)
        return rows
