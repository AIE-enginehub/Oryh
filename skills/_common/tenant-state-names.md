> **Status names belong to the workspace.** Only `draft` and `submitted` are
> guaranteed to exist. Every other name below — `approved`, `returned`,
> `confirmed`, `shipped`, `sent`, `paid`, `received`, `closed` — is the shipped
> default, and this workspace may have renamed it (a consulting firm running
> `confirmed → in_delivery → delivered` has no `shipped` at all).
>
> Filtering on a name it does not use is refused with **422**, and the error
> lists the states it does use — retry with one of those. Read them up front
> with `GET /object-type-definitions?object_type=<type>` when you plan to work
> a queue by state.
