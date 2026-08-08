Key model, same as every flow family: **object status is NOT the workflow
position.** A document stays `submitted` while the flow runs. Nodes passed =
approval records; ball's current holder = open todos; where it may go next =
the workflow definition.

One thing is specific to money: **settlement is not a status at all.** How much
an invoice still owes is `outstanding_amount` on its detail, derived from the
核销 ledger. Never route on `paid`; route on the number.
