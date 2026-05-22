---
"gampan": patch
---

`gampan plan` and `gampan apply` now refuse CreativeTemplate write
intents at plan time instead of letting them fall through to the
executor and crash with `NotImplementedError`.

GAM's REST Beta exposes `list` / `get` for CreativeTemplate but not
the write verbs, so v0.1 has always been read-only for that kind. The
old behaviour rendered the plan, prompted for confirmation, then
raised `NotImplementedError` inside `executor.execute_plan` — late
enough that an operator who chained other resources in the same plan
might already have applied them by the time the CT row blew up.

A new `validate_v0_1_constraints(plan.changes)` helper scans the diff
for any non-`NO_CHANGE` action on a `CreativeTemplate:*` key and
raises `CreativeTemplateReadOnlyError` with the offending list and a
recovery hint (edit through the GAM UI + `gampan import`, or revert
the YAML). `plan` still renders the diff so the operator can see what
would have been touched before the abort. Both CLIs exit 1 on the
error.
