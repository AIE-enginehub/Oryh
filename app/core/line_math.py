"""The arithmetic of a document line, in one place below every API module.

A line's amount is quantity × unit_price — computed by the server, stored,
never asked of the person. Tax is NOT derived: `tax_rate` is a percentage and
the amount may be tax-inclusive (含税价) or not, which is the tenant's
practice, so `tax_amount` stays a stated fact. Raised here as
HTTP 422 because every caller is a request handler or the bulk importer,
and the message is the arithmetic the caller got wrong.
"""

from __future__ import annotations

from fastapi import HTTPException, status


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
        sum, or none.
    """
    if is_gift:
        return 0.0
    if unit_price is None:
        return None if amount is None else round(float(amount), 2)
    computed = round(float(quantity or 0) * float(unit_price), 2)
    if amount is not None and abs(float(amount) - computed) > 0.005:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{label} {float(amount):g} is not quantity × unit_price ({float(quantity or 0):g} × "
                f"{float(unit_price):g} = {computed:g}); leave it out — the server computes it — "
                "and put a discount in an adjustment"
            ),
        )
    return computed
