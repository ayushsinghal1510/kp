
"""Deterministic packing-size evaluator.

The LLM no longer computes a packing-size number. It extracts a canonical
*packing-size string* (e.g. "12x1.2L", "55GMX5PX6B", "6 x (12 x 130g)") and
this module turns that string into an integer packing size plus a human
readable calculation expression.

Rules (see assets/prompts/ingestion.md for the grounding examples):

* A number carrying a weight/volume unit (l, ml, g, gm, kg ...) or an unknown
  unit contributes 1 -- it can never be a packing multiplier.
* Lettered packaging tiers resolve outer-to-inner: B (Bags/Boxes/Cartons) >
  P (Packs/Packets) > S (Small items/Sachets). The highest tier present wins;
  lower lettered tiers collapse to 1.
* Bare numbers (no unit) always count, as does the B tier.
* An S-tier number only counts when no bare number, B or P tier shares its
  scope (so "18GX8SX10" -> 10, but "24s x 45g" -> 24).
* A parenthesised group that contains an S tier is inner sachet packaging and
  collapses to 1 ("24 x (12 x 20s)" -> 24), otherwise brackets multiply through
  ("6 x (12 x 130g)" -> 72).

Special token — "igno":
  Appending "igno" to a number forces that atom to be disqualified (treated as
  1) even when it would otherwise be a bare multiplier.  Used by the LLM for
  supplier-specific cases where the leading segment must be skipped.
  Example: "240ignoX24PCKS" -> 1 × 24 = 24  (vs "240X24PCKS" -> 240 × 24).
  The token is stored in the canonical string but stripped before display.
"""

import re

from typing import Any

# Weight / volume units. A number wearing one of these is never a pack count.
DISQUALIFY_UNITS : set[str] = {
    'l' , 'ml' , 'cl' , 'dl' , 'lt' , 'ltr' ,
    'g' , 'gm' , 'gms' , 'gr' , 'grm' , 'kg' , 'mg' ,
    'oz' , 'lb' , 't'
}

# Outermost packaging tier (cartons / boxes / bags). NB: "box" is intentionally
# absent -- the 'x' would collide with the multiplier delimiter. Grocery
# invoices here use CTN / carton.
B_TIER_UNITS : set[str] = {
    'b' , 'bag' , 'bags' , 'ctn' , 'ctns' ,
    'carton' , 'cartons' , 'outctn' , 'pkgctn'
}

# Middle tier (packs / packets).
P_TIER_UNITS : set[str] = {
    'p' , 'pk' , 'pkt' , 'pkts' , 'pack' , 'packs' ,
    'packet' , 'packets' , 'pck' , 'pcks' , 'pcks' , 'dp'
}

# Innermost tier (sachets / pieces).
S_TIER_UNITS : set[str] = {
    's' , 'pc' , 'pcs' , 'sachet' , 'sachets'
}

_MUL_CHARS : set[str] = {'x' , 'X' , '*'}
_PAREN_OPEN : set[str] = {'(' , '[' , '{'}
_PAREN_CLOSE : set[str] = {')' , ']' , '}'}
_PAREN_CHARS : set[str] = _PAREN_OPEN | _PAREN_CLOSE

# A clean atom is a number then an optional unit, and nothing else. Anything
# else that still carries a digit ("T6", "7+3", "50G44G", date codes ...) is an
# expression we cannot read and is treated as a single unknown atom worth 1.
_NUMBER_UNIT : re.Pattern = re.compile(r'^(\d+\.?\d*)([a-zA-Z]*)$')


def _classify(unit : str) -> str :

    if unit == '' :
        return 'bare'

    if unit in B_TIER_UNITS :
        return 'B'

    if unit in P_TIER_UNITS :
        return 'P'

    if unit in S_TIER_UNITS :
        return 'S'

    # Weight/volume AND anything we do not recognise -> cannot be a count.
    return 'disq'


def _tokenize(text : str) -> list[tuple] :

    tokens : list[tuple] = []
    i : int = 0
    n : int = len(text)

    while i < n :

        ch : str = text[i]

        if ch in _MUL_CHARS :
            tokens.append(('mul' , ))
            i += 1

        elif ch in _PAREN_OPEN :
            tokens.append(('lp' , ))
            i += 1

        elif ch in _PAREN_CLOSE :
            tokens.append(('rp' , ))
            i += 1

        elif ch.isspace() :
            i += 1

        else :

            # A run is a maximal stretch bounded by delimiters, parens or space.
            j : int = i

            while j < n and not (
                text[j].isspace() or
                text[j] in _MUL_CHARS or
                text[j] in _PAREN_CHARS
            ) :
                j += 1

            run : str = text[i : j]
            i = j

            match : re.Match | None = _NUMBER_UNIT.match(run)

            if match is not None :
                tokens.append(('atom' , float(match.group(1)) , match.group(2).lower()))

            elif any(c.isdigit() for c in run) :
                # Has a digit but is not a clean "<number><unit>" -> unknown -> 1.
                tokens.append(('atom' , 1.0 , '?'))

            # else: pure descriptive text (no digits) -> ignored.

    return tokens


def _parse(tokens : list[tuple] , pos : int = 0) -> tuple[list , int] :

    children : list = []

    while pos < len(tokens) :

        kind : str = tokens[pos][0]

        if kind == 'rp' :
            return children , pos

        if kind == 'lp' :

            sub , pos = _parse(tokens , pos + 1)
            children.append(('group' , sub))
            pos += 1   # skip the matching ')'

        elif kind == 'mul' :
            pos += 1

        else :
            children.append(('atom' , tokens[pos][1] , tokens[pos][2]))
            pos += 1

    return children , pos


def _contains_s(children : list) -> bool :

    for child in children :

        if child[0] == 'atom' and _classify(child[2]) == 'S' :
            return True

        if child[0] == 'group' and _contains_s(child[1]) :
            return True

    return False


def _evaluate(children : list , is_paren : bool) -> tuple[int , str] :

    # A bracket holding a sachet tier is inner packaging -> 1.
    if is_paren and _contains_s(children) :
        return 1 , '1'

    has_bare : bool = False
    has_b : bool = False
    has_p : bool = False

    for child in children :

        if child[0] != 'atom' :
            continue

        tier : str = _classify(child[2])

        if tier == 'bare' : has_bare = True
        elif tier == 'B' : has_b = True
        elif tier == 'P' : has_p = True

    result : int = 1
    parts : list[str] = []

    for child in children :

        if child[0] == 'group' :

            sub_value , sub_expr = _evaluate(child[1] , is_paren = True)
            result *= sub_value
            parts.append(f'({sub_expr})')

            continue

        _ , value , unit = child
        tier : str = _classify(unit)

        if tier == 'bare' : contribution = int(value)
        elif tier == 'B' : contribution = int(value)
        elif tier == 'P' : contribution = 1 if has_b else int(value)
        elif tier == 'S' : contribution = 1 if (has_bare or has_b or has_p) else int(value)
        else : contribution = 1

        result *= contribution
        parts.append(str(contribution))

    if not parts :
        return 1 , '1'

    return result , ' × '.join(parts)


def parse_packing_size(packing_string : Any) -> tuple[int , str] :
    """Return (packing_size, calculation_expression) for a packing string.

    Always returns a packing size of at least 1. The expression mirrors the
    multiplication actually performed, e.g. "1 × 1 × 6 = 6".
    """

    if packing_string is None :
        return 1 , '1 = 1'

    text : str = str(packing_string).strip()

    if not text :
        return 1 , '1 = 1'

    tokens : list[tuple] = _tokenize(text)
    ast , _ = _parse(tokens , 0)

    value , expr = _evaluate(ast , is_paren = False)

    if value < 1 :
        value = 1

    return value , f'{expr} = {value}'
