"""Türkçe finans terim sözlüğü: glossary/*.md dosyalarını terim nesnelerine ayrıştırır.

Biçim (her terim):
    ### Terim adı
    Eş: eş anlamlı, kısaltma, ...
    Tanım: ...
    Örnek: ...
    Uygulamada: ...
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

GLOSSARY_DIR = Path(__file__).parent / "glossary"
FIELDS = ("Eş", "Tanım", "Örnek", "Uygulamada")


@dataclass(frozen=True)
class Term:
    name: str
    category: str
    aliases: tuple[str, ...]
    definition: str
    example: str
    where: str
    source: str = field(default="", compare=False)

    def as_chunk(self) -> str:
        """İsteme eklenecek metin parçası."""
        return f"[{self.name}]\nTanım: {self.definition}\nÖrnek: {self.example}\nUygulamada: {self.where}"


def parse_file(path: Path) -> list[Term]:
    text = path.read_text(encoding="utf-8")
    cat = re.search(r"^# (.+)$", text, re.M)
    category = cat.group(1).strip() if cat else path.stem
    terms: list[Term] = []
    for block in re.split(r"^### ", text, flags=re.M)[1:]:
        lines = block.strip().splitlines()
        name = lines[0].strip()
        values: dict[str, str] = {}
        for line in lines[1:]:
            m = re.match(r"^(Eş|Tanım|Örnek|Uygulamada):\s*(.+)$", line.strip())
            if m:
                values[m.group(1)] = m.group(2).strip()
        missing = [f for f in FIELDS if not values.get(f)]
        if missing:
            raise ValueError(f"{path.name}: '{name}' teriminde eksik alan: {', '.join(missing)}")
        aliases = tuple(a.strip() for a in values["Eş"].split(",") if a.strip())
        terms.append(
            Term(
                name=name,
                category=category,
                aliases=aliases,
                definition=values["Tanım"],
                example=values["Örnek"],
                where=values["Uygulamada"],
                source=path.name,
            )
        )
    return terms


@lru_cache(maxsize=1)
def load_glossary(directory: Path = GLOSSARY_DIR) -> tuple[Term, ...]:
    terms: list[Term] = []
    for path in sorted(directory.glob("*.md")):
        terms.extend(parse_file(path))
    return tuple(terms)
