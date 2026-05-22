---
"gampan": patch
---

`gampan import` now deletes the stale on-disk YAML when a remote
resource is renamed (same `_gam_id`, new slug). Previously the new
file landed under the new slug while the old-slug `<stem>.<kind>.yaml`
plus its `.html` / `.css` side files lingered as orphans, tripping
`validate_no_duplicates` on the next `plan` until the operator
deleted them manually.

The new logic scans `native-styles/`, `creative-templates/`, and
`native-formats/` before writing, builds a `_gam_id → existing yaml`
map, and removes the old path (plus `.html` / `.css` siblings) when
`write_resource` lands the file at a new path. YAMLs without
`_gam_id` (user-authored drafts that have not been imported yet) are
intentionally never touched — only previously-imported files
participate in rename cleanup. A trailing audit line surfaces the
removed orphans.
