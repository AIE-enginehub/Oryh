"""The arithmetic of a document line, in one place below every API module.

A line's amount is quantity × unit_price — computed by the server, stored,
never asked of the person. Tax is NOT derived: `tax_rate` is a percentage and
the amount may be tax-inclusive (tax-inclusive price) or not, which is the tenant's
practice, so `tax_amount` stays a stated fact. Raised here as
HTTP 422 because every caller is a request handler or the bulk importer,
and the message is the arithmetic the caller got wrong.

The three numbers live in `Numeric(12, 2)` columns, so they are reasoned
about at that scale and nowhere finer: a unit price of 0.335 cannot be
stored, and computing 0.67 from it then storing 0.34 beside it left a line
whose own columns disagreed (review 2026-10-10, R03). Input with more
decimals than the column keeps is refused with the arithmetic, the same
way a wrong amount is; the multiplication is done in Decimal.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException, status

SCALE = Decimal("0.01")


def _plain(number: Decimal) -> str:
    """100, not 1E+2; 12.5, not 12.50 — the number as a person would write it."""
    text = f"{number:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _decimal(value, *, label: str) -> Decimal:
    """The value as the column will hold it. A float arrives as its shortest
    repr (0.1, not 0.1000000000000000055…), which is what the person typed."""
    try:
        number = Decimal(repr(value)) if isinstance(value, float) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{label} {value!r} is not a number"
        ) from None
    if number != number.quantize(SCALE, rounding=ROUND_HALF_UP):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"{label} {_plain(number)} has more than two decimals; the document keeps two — "
                "state the price the line is actually charged at, and put a finer rate in the notes"
            ),
        )
    return number.quantize(SCALE)


def derive_line_amount(quantity, unit_price, amount, *, is_gift: bool = False, label: str = "amount"):
    """A line's amount is quantity × unit_price — computed here, stored, and
    never asked of the person.

    Agents used to leave `amount` empty (so the line read as null and every
    total had to re-derive it) or, worse, type one that did not match the
    price: an order line at 100 × 10 stored as 900 with no discount anywhere
    to explain it. The rule now:

      * a priced line's amount IS quantity × unit_price (2 dp); a gift is 0;
      * a stated amount is accepted only when it equals that product — a
        different one is refused with the arithmetic, because a line-level
        discount belongs in an adjustment, not in a number nobody can audit;
      * an unpriced line (no unit_price) keeps a stated amount as its lump
        sum, or none;
      * quantity, unit price and amount carry at most two decimals — the
        scale the columns keep — or the request is refused.
    """
    if is_gift:
        return 0.0
    if unit_price is None:
        return None if amount is None else float(_decimal(amount, label=label))
    qty = _decimal(quantity or 0, label="quantity")
    price = _decimal(unit_price, label="unit_price")
    computed = (qty * price).quantize(SCALE, rounding=ROUND_HALF_UP)
    if amount is not None and _decimal(amount, label=label) != computed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"{label} {_plain(_decimal(amount, label=label))} is not quantity × unit_price ({_plain(qty)} × "
                f"{_plain(price)} = {_plain(computed)}); leave it out — the server computes it — "
                "and put a discount in an adjustment"
            ),
        )
    return float(computed)
