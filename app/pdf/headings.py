from __future__ import annotations

from collections import Counter

H1_SIZE_RATIO = 1.5
H2_SIZE_RATIO = 1.2


def compute_body_font_size(blocks: list[dict]) -> float:
    """Calcula el tamaño de fuente más común (body text) ponderado por caracteres."""
    chars_by_size: Counter[float] = Counter()
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if text:
                    chars_by_size[round(span["size"], 1)] += len(text)
    return chars_by_size.most_common(1)[0][0] if chars_by_size else 0.0


def block_to_markdown(block: dict, body_size: float, text: str = "") -> str:
    """Convierte un bloque a Markdown detectando headings por tamaño de fuente.
    
    Args:
        block: Bloque del PDF
        body_size: Tamaño de fuente base
        text: Texto ya extraído (usado para OCR). Si está vacío, se extrae del bloque.
    """
    # Usar el texto proporcionado o extraer del bloque
    if text:
        block_text = text
    else:
        block_text = "".join(
            span.get("text", "")
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        )
    
    sizes = [
        round(span["size"], 1)
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip()
    ]
    ratio = max(sizes) / body_size if sizes and body_size > 0 else 0
    
    clean_text = block_text.replace("\n", " ")
    if ratio >= H1_SIZE_RATIO:
        return f"# {clean_text}"
    if ratio >= H2_SIZE_RATIO:
        return f"## {clean_text}"
    return clean_text