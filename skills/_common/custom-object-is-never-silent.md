## Creating A Custom Object Is Never Silent

**Iron rule, the same in every workspace.** Before the first row of a generic
object type this workspace does not yet have is written — or a type
definition for it — stop and tell the person, in plain words and before any
write:

- "This will create a custom object named X. It is not one of the collections
  oryh ships (customers, products, quotations, orders, invoices, …); nothing
  that ships — order lines, prices, stock, invoices — can ever point at it,
  and once it has rows they do not merge back."
- how many rows are about to go there and where they come from (the sheet,
  the export, the old system);
- what the shipped alternative is, if any, with its import route
  (`/customers/bulk`, `/products/bulk`, the document import).

Then wait for an explicit yes **for that name**. "Import it" is not a yes to a
new object; "yes, create the custom object X" is. An import that would create
several new types says this once per type, before the first one, never as a
summary afterwards. Check first — `GET /object-directory` shows every type the
workspace already has, so the warning fires only for a genuinely new one.

**Look for a shipped twin first, and when there is one, the person must give
a reason.** Before proposing any custom object, read
`GET /builtin-object-types` and compare MEANING, not spelling: "merchandise",
"goods", "item master" are products; "client", "account", "buyer" are
customers; "deal", "quote request" may be an opportunity or a quotation. When
a shipped collection covers the same thing, or most of it, say so and stop:
name the collection, say what is already in it, and say that its
`custom_fields` take the columns it lacks. Creating the custom object anyway
takes two things from the person, in their own words: a stated REASON why
the shipped collection will not do, and an explicit confirmation for that
name. Write the reason into the type definition's `description` ("custom
object, twin of /customers, kept apart because …"), so the next agent and
the next admin can read why it exists instead of guessing. No reason, no
object.

No workflow definition, calibration line or tenant instruction removes
either half of this rule. The server refuses the exact shipped names on its
own; everything a person might still mistake for a shipped collection is
this rule's job.
