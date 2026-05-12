"""Rule-based classifier for cosmetic products.

Maps free-text product fields (title, type, tags, description) onto three axes:
  - seccion: Facial | Corporal | Capilar | Otros
  - funcion: list of needs (arrugas, manchas, hidratacion, ...) — multi-label
  - tipo:    single product format (serum, crema, limpiador, ...)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def _normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s\-+]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


SECCION_RULES: dict[str, list[str]] = {
    "Capilar": [
        "champu", "shampoo", "acondicionador", "conditioner", "mascarilla capilar",
        "hair mask", "cuero cabelludo", "scalp", "anticaida", "anti caida",
        "hair", "pelo", "cabello", "leave-in", "leave in",
    ],
    "Corporal": [
        "corporal", "cuerpo", "body", "manos", "hand cream", "crema de manos",
        "pies", "foot", "busto", "gluteos", "vientre", "celulitis", "estrias",
        "desodorante", "deodorant", "bath", "ducha", "shower", "exfoliante corporal",
    ],
    "Facial": [
        "facial", "rostro", "cara", "face", "contorno de ojos", "eye cream",
        "contorno ojos", "contorno labios", "lip", "labios", "serum facial",
        "crema facial", "mascarilla facial", "tonico facial", "limpiador facial",
        "agua micelar", "espuma limpiadora", "leche limpiadora", "doble limpieza",
    ],
}

FUNCION_RULES: dict[str, list[str]] = {
    "Anti-edad / Arrugas": [
        "arrugas", "antiarrugas", "anti edad", "antiedad", "anti-edad", "antiaging",
        "anti aging", "anti-aging", "lifting", "firmness", "firmeza", "reafirmante",
        "retinol", "peptidos", "bakuchiol", "colageno", "rejuvenecedor",
    ],
    "Manchas / Pigmentacion": [
        "manchas", "antimanchas", "anti manchas", "despigmentante", "pigmentacion",
        "melasma", "tono", "discromias", "luminosity", "spots", "dark spots",
    ],
    "Hidratacion": [
        "hidrat", "moistur", "humect", "hialuronico", "hyaluronic", "glicerina",
        "panthenol", "ceramidas", "barrera",
    ],
    "Acne / Imperfecciones": [
        "acne", "imperfecciones", "granos", "puntos negros", "salicilico", "bha",
        "azelaico", "poros", "sebo", "matificante", "piel grasa", "oily",
    ],
    "Sensibilidad / Rojeces": [
        "sensible", "sensitive", "rojeces", "calmante", "centella", "rosacea",
        "anti-redness", "soothing", "irritacion",
    ],
    "Luminosidad / Glow": [
        "luminos", "glow", "radiance", "iluminador", "brillo", "vitamina c",
        "niacinamida", "aha", "alpha hydroxy", "glycolic", "glicolico",
    ],
    "Limpieza / Poros": [
        "limpieza", "limpiador", "cleansing", "cleanser", "desmaquillante",
        "exfoliante", "peeling", "scrub", "poros",
    ],
    "Proteccion solar": [
        "spf", "solar", "sunscreen", "sun protect", "fotoprotector", "uv",
        "after sun", "aftersun",
    ],
    "Ojeras / Contorno": [
        "ojeras", "dark circles", "bolsas", "puffy", "contorno de ojos", "eye contour",
    ],
    "Anticaida / Crecimiento capilar": [
        "anticaida", "anti caida", "hair loss", "growth", "crecimiento", "densidad",
    ],
}

TIPO_RULES: list[tuple[str, list[str]]] = [
    ("SPF / Protector solar", ["spf", "sunscreen", "fotoprotector", "protector solar"]),
    ("Contorno de ojos", ["contorno de ojos", "eye cream", "eye contour", "contorno ojos"]),
    ("Mascarilla capilar", ["mascarilla capilar", "hair mask"]),
    ("Mascarilla", ["mascarilla", "mask"]),
    ("Champu", ["champu", "shampoo"]),
    ("Acondicionador", ["acondicionador", "conditioner"]),
    ("Serum", ["serum", "ampolla", "concentrado"]),
    ("Tonico / Esencia", ["tonico", "toner", "esencia", "essence", "bruma facial"]),
    ("Limpiador / Desmaquillante", [
        "limpiador", "cleanser", "agua micelar", "espuma limpiadora",
        "leche limpiadora", "desmaquillante", "gel limpiador",
    ]),
    ("Exfoliante / Peeling", ["exfoliante", "peeling", "scrub"]),
    ("Aceite", ["aceite", "oil"]),
    ("Bruma / Mist", ["bruma", "mist", "spray facial"]),
    ("Crema de manos", ["crema de manos", "hand cream"]),
    ("Crema corporal / Locion", ["crema corporal", "body lotion", "locion corporal", "manteca"]),
    ("Desodorante", ["desodorante", "deodorant"]),
    ("Tratamiento labial", ["labial", "lip balm", "lip mask"]),
    ("Crema / Gel facial", ["crema", "cream", "gel-crema", "gel crema", "balsamo facial"]),
]


@dataclass
class Classification:
    seccion: str
    funcion: list[str]
    tipo: str


def _match_any(haystack: str, needles: list[str]) -> bool:
    return any(n in haystack for n in needles)


def classify(title: str, product_type: str = "", tags: str = "", description: str = "") -> Classification:
    title_n = _normalize(title)
    weighted = _normalize(" ".join([title, title, product_type, tags]))  # title twice = more weight
    full = _normalize(" ".join([title, product_type, tags, description]))

    seccion = "Otros"
    for name, keywords in SECCION_RULES.items():
        if _match_any(weighted, keywords):
            seccion = name
            break
    if seccion == "Otros" and _match_any(full, SECCION_RULES["Facial"]):
        seccion = "Facial"

    funciones = [name for name, keywords in FUNCION_RULES.items() if _match_any(full, keywords)]

    tipo = "Otro"
    for name, keywords in TIPO_RULES:
        if _match_any(title_n, keywords) or _match_any(_normalize(product_type), keywords):
            tipo = name
            break
    if tipo == "Otro":
        for name, keywords in TIPO_RULES:
            if _match_any(full, keywords):
                tipo = name
                break

    # Tipos that are virtually always facial unless explicit corporal/capilar tag.
    facial_default_tipos = {
        "Serum", "Tonico / Esencia", "Contorno de ojos",
        "Limpiador / Desmaquillante", "Exfoliante / Peeling",
        "Tratamiento labial", "Crema / Gel facial",
        "SPF / Protector solar",
    }
    if seccion == "Otros" and tipo in facial_default_tipos:
        seccion = "Facial"

    return Classification(seccion=seccion, funcion=funciones, tipo=tipo)
