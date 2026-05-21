---
"gampan": patch
---

Fix `gampan apply` for NativeStyle and stop archived resources from
re-appearing in every `plan` cycle. Three independent fixes uncovered while
running the documented `init → import → plan → apply` smoke test against a
sandbox network:

- **`fix(rest)`: deterministic `mime_types` order.** GAM's REST endpoint
  returns ASSET-variable `mime_types` in a non-deterministic order — the same
  template can yield `['PNG','GIF','JPG']` then `['JPG','PNG','GIF']` on
  consecutive `list()` calls. Without normalisation every `gampan plan`
  immediately after `gampan import` flagged ~25 spurious CreativeTemplate
  UPDATEs. The import path now sorts the enum names alphabetically so YAML
  and remote views stay aligned.
- **`fix(native-style-soap)`: SOAP create/update roundtrip.** `to_remote()`
  was nesting `isFluid` inside `Size` (the SOAP WSDL puts it at the
  `NativeStyle` root) and emitting a flat `targeting.{adUnits,
  customTargeting}` shape that does not match the deeply nested SOAP
  `Targeting` complex type. Both caused `createNativeStyles` /
  `updateNativeStyles` to raise `KeyError` inside `googleads`. `isFluid` now
  lives at the payload root, `targeting` is omitted entirely while it is
  empty (a v0.2 mapping will fill it in), and `from_remote()` keeps a
  backwards-compat read for the old nested shape.
- **`feat(config)`: `include_archived` toggle.** ARCHIVED NativeStyles were
  re-surfacing as DESTROY candidates on every `plan` because
  `getNativeStylesByStatement` returns them regardless of `executor.delete`'s
  prior archive call. A new `include_archived` config field (`false` by
  default) and matching `--include-archived` / `--no-include-archived` CLI
  flags on `plan`, `apply`, and `import` add a PQL status filter. A
  `MissingRemoteError` planner guard prevents the foot-gun where a tracked
  YAML whose remote got filtered out would otherwise be reinterpreted as a
  brand-new CREATE.
