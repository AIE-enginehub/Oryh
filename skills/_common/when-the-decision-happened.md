**Do not send `acted_at`.** The server stamps the moment of your call, and for
an approval made through this API that IS when the decision happened.

It used to be required, and a required timestamp is a question you cannot
answer: you have no clock, so you would take the most plausible date in view —
and the date in view belongs to the document you are approving, which is older
than the row. That is how a production trail came to hold approvals recorded
before the record they decide existed.

Send one only when the person you act for has told you the decision happened at
another time, using a time they gave you or one the record already carries
(backfilling a missing `submitted` fact from the document's own `submitted_at`
is the normal case, and it is a stored fact rather than an estimate). Never
infer it from a date on the document, and never send one because a field
exists. A future time and a time before the target existed are both refused.
