"""
legal_text.py -- parse the WORD form of a legal description and cross-check
it against the numeral form.

Why this matters more than it looks:
Surveyors write every value twice -- "seventeen hundred ninety-one and
eighty-nine hundredths (1791.89) feet", "North thirty-eight degrees fifty
minutes, thirty seconds East (N.38 50'30"E.)". The two forms are
independent encodings of the same number, so each checks the other.

That redundancy is precisely the antidote to the failure mode that has
broken every historic plat in this project: single-digit corruption
(50.59 -> 0.59, 119 -> 110, 30 deg -> 3 deg). Digits carry no redundancy, so
a dropped glyph is undetectable in isolation. Words carry heavy redundancy --
they are dictionary tokens, they are longer, and OCR confusions between
"eighty" and "eight" are far rarer and far more detectable than between
"80" and "8". When the numeral and the word form disagree, the WORD FORM IS
NORMALLY THE SURVIVOR, and it can be used to repair the numeral.
"""
from __future__ import annotations

import re

UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
SCALES = {"hundred": 100, "thousand": 1000}


def _tokens(text: str):
    t = text.lower().replace("-", " ").replace(",", " ")
    return [w for w in re.split(r"\s+", t) if w]


VOCAB = set(UNITS) | set(TENS) | set(SCALES) | {
    "and", "hundredths", "hundreths", "tenths", "thousandths"}


def extract_number_phrase(text: str) -> str | None:
    """Pull the number-word span out of surrounding prose.

    Essential for real OCR output: the phrase arrives as
    "a distdnee of seventeen hundred ninety - one and eighty -nine
    hundredths (179.82) feet" -- prose before, a corrupted numeral after,
    and OCR noise in the connecting words. Requiring the whole string to be
    number-words (the first implementation) returned None on every genuine
    OCR line, which defeated the entire point of the word channel.

    Strategy: take the LONGEST contiguous run of number-vocabulary tokens.
    Trailing/leading bare "and" is trimmed."""
    toks = _tokens(re.sub(r"\(.*?\)", " ", text))
    best, cur = [], []
    for w in toks:
        if w in VOCAB:
            cur.append(w)
        else:
            if len(cur) > len(best):
                best = cur
            cur = []
    if len(cur) > len(best):
        best = cur
    while best and best[0] == "and":
        best = best[1:]
    while best and best[-1] == "and":
        best = best[:-1]
    return " ".join(best) if best else None


def words_to_number(text: str) -> float | None:
    """Convert a spelled-out cardinal to a number.

    Handles the surveyor's idiom "seventeen hundred ninety-one" (= 1791),
    which is NOT standard English "one thousand seven hundred ninety-one"
    but is ubiquitous in legal descriptions, and the fractional tail
    "and eighty-nine hundredths" (= .89)."""
    toks = _tokens(text)
    if not toks:
        return None

    # split off a fractional tail: "... and <words> hundredths/tenths"
    frac = 0.0
    denom = None
    for i, w in enumerate(toks):
        if w in ("hundredths", "hundreths"):
            denom = 100.0
        elif w == "tenths":
            denom = 10.0
        elif w == "thousandths":
            denom = 1000.0
        if denom is not None:
            # find the preceding "and"
            j = None
            for k in range(i - 1, -1, -1):
                if toks[k] == "and":
                    j = k
                    break
            if j is None:
                return None
            frac_words = toks[j + 1:i]
            fv = _plain(frac_words)
            if fv is None:
                return None
            frac = fv / denom
            toks = toks[:j]
            break

    whole = _plain(toks)
    if whole is None:
        return None
    return whole + frac


def _plain(toks) -> float | None:
    """Cardinal words -> int, supporting the 'seventeen hundred' idiom."""
    if not toks:
        return None
    total = 0
    current = 0
    seen = False
    for w in toks:
        if w in ("and", "of", "a"):
            continue
        if w in UNITS:
            current += UNITS[w]
            seen = True
        elif w in TENS:
            current += TENS[w]
            seen = True
        elif w in SCALES:
            if not seen and w == "hundred":
                current = 1
            # "seventeen hundred" -> 17*100; "thirty-six hundred" -> 3600
            current *= SCALES[w]
            total += current
            current = 0
            seen = True
        else:
            return None
    return float(total + current) if seen else None


BEARING_WORDS = re.compile(
    r"(north|south)\s+(.*?)\s+degrees?\s*,?\s*(.*?)\s+minutes?\s*,?\s*"
    r"(?:(.*?)\s+seconds?\s*,?\s*)?(east|west)",
    re.IGNORECASE | re.DOTALL)


def words_to_bearing(text: str) -> str | None:
    """'North thirty-eight degrees fifty minutes, thirty seconds East'
    -> N38 deg 50'30\"E"""
    m = BEARING_WORDS.search(text)
    if not m:
        return None
    ns, dw, mw, sw, ew = m.groups()
    d = _plain(_tokens(dw))
    mi = _plain(_tokens(mw))
    se = _plain(_tokens(sw)) if sw else 0.0
    if d is None or mi is None or se is None:
        return None
    if not (0 <= d <= 90 and 0 <= mi < 60 and 0 <= se < 60):
        return None
    return (f"{ns[0].upper()}{int(d):02d}°{int(mi):02d}'{int(se):02d}\""
            f"{ew[0].upper()}")


NUMERAL_IN_PARENS = re.compile(r"\(\s*([0-9]+(?:\.[0-9]+)?)\s*\)")
BEARING_IN_PARENS = re.compile(
    r"\(\s*([NS])\s*\.?\s*([0-9]{1,2})\s*[°*]\s*([0-9]{1,2})\s*'\s*"
    r"([0-9]{1,2})?\s*\"?\s*([EW])\s*\.?\s*\)", re.IGNORECASE)


def cross_check_distance(phrase: str) -> dict:
    """Given a phrase carrying both forms, compare them."""
    span = extract_number_phrase(phrase)
    w = words_to_number(span) if span else None
    m = NUMERAL_IN_PARENS.search(phrase)
    n = float(m.group(1)) if m else None
    out = dict(phrase=phrase.strip(), words=w, numeral=n)
    if w is None or n is None:
        out["status"] = "incomplete"
    elif abs(w - n) < 0.005:
        out["status"] = "AGREE"
    else:
        out["status"] = "DISAGREE"
        out["repair"] = w        # word form is the survivor
    return out


def cross_check_bearing(phrase: str) -> dict:
    w = words_to_bearing(re.sub(r"\(.*?\)", " ", phrase))
    m = BEARING_IN_PARENS.search(phrase)
    n = None
    if m:
        ns, d, mi, se, ew = m.groups()
        n = f"{ns.upper()}{int(d):02d}°{int(mi):02d}'{int(se or 0):02d}\"{ew.upper()}"
    out = dict(phrase=phrase.strip()[:70], words=w, numeral=n)
    if w is None or n is None:
        out["status"] = "incomplete"
    elif w == n:
        out["status"] = "AGREE"
    else:
        out["status"] = "DISAGREE"
        out["repair"] = w
    return out
