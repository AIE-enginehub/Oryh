## Archived Is History, Not A Quieter Kind Of Live

Every master-data list answers with the ACTIVE rows unless you ask
otherwise: `status=archived` for the history, `status=all` for both. A bank
account entered by mistake, a product nobody sells, a store that closed — once
archived they leave the everyday answer, and their children go with them: an
archived account's register lines and an archived position's movements are
listed only when you name that account or position, or pass
`include_archived_accounts` / `include_archived_items`, and every such row
carries `account_status` / `item_status: archived`.

So: never sum an archived account into the cash position, never count an
archived position as stock, and when you do show archived rows — because the
person asked for history — say "archived" out loud next to them. A record
archived by mistake is revived by setting its status back to active; its
history was never lost, only kept out of the way.
