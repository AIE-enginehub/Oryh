## Keeping the original

Extracting a document's numbers is not keeping the document. The file itself —
the supplier's PDF, the scan of a tax invoice, the payslip you produced — is
the evidence the extracted figures are *about*, and the only thing that
settles a dispute about what was actually billed. Attach it.

**Uploading.** `POST /attachments` with the file base64-encoded, **all files in
one batch** — uploads do not depend on each other. Then put the id in the
record's `attachment_id`.

Uploads are idempotent per file content, and the response code says which
happened: **201 = these bytes are new to this workspace, 200 = the server
already held them**. A 200 is a fact worth reporting: the same file has been
filed before, which on a bill or a receipt usually means a duplicate entry
rather than a coincidence. Say so before filing against it.

When you can run Python, prefer the bundled `scripts/upload_attachment.py` (in
this skill's own directory — the path is relative to the skill, not to wherever
you happen to be running). It does the base64, the 10 MB pre-check, and reports
`already_existed` per file.

**Reading it back.** An attachment is reached **through the document that
carries it**, never by its id alone: the server asks "may this person see this
document" and only then serves the bytes. Each skill names its own route; the
shape is the document's collection, its id, then `/attachments/{id}/content`.

Reading by id alone is the workspace administrator's route. If you get a 403
there, that is **the wrong URL, not a capability to ask for** — asking an
administrator to grant you `users.manage` because a download failed is asking
for the keys to the workspace to open one PDF.
