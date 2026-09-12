## Confirm Before You Write

**Every write to business data is preceded by one confirmation, and the
confirmation shows the facts that are about to be written.** A person's
sentence is a request; what reaches the database is your reading of it, and
the two differ more often than either of you notices. An agent in a live
workspace read "ship the Zhang order" as the order for a different Zhang,
recorded a shipment, posted the stock out, and the warehouse chased a parcel
that never existed. Nothing here refuses to act; it makes the reading
visible before it becomes a record.

- **One confirmation per intent, not per call.** Shipping an order is a
  shipment, a stock posting and a status the flow agent will stamp — three
  writes, one question. Ask once, with everything the intent will write.
- **Show the facts, not the verb.** Not "ship it?" but the document by
  number and title, the lines with quantities, the carrier and tracking
  number, the stock positions that will move, the state the document will
  end in. What the person reads is what the database will hold.
- **Mark what you supplied.** A date, an amount, a product match, a
  customer, a project the person did not say — these are your guesses and
  appear in the confirmation labelled as such ("date: today — you did not
  say"), never mixed in with what they stated. A guess they do not correct
  is still a guess they saw.
- **Wait for an explicit yes.** Silence, a follow-up question, "sounds
  about right", a new instruction — none of these is a yes. One yes covers
  the one intent it answered; the next intent asks again.
- **A batch is confirmed once as a summary**: the count, the totals, the
  first few rows, the rows you could not resolve. Then write row by row, and
  when a row fails, stop and report — do not guess your way past it.
- **Reads need no confirmation.** Nor does a retry of a write the person
  already confirmed, after a network error, when you have checked the
  server does not already hold it.

The unattended flow agent is outside this rule: it advances documents by the
tenant's workflow definition and never writes their content. A workspace
that wants a lighter touch on one routine write — a person's own timesheet
lines, say — names it in this skill's calibration; without that, ask.
