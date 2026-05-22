---
"gampan": patch
---

`NativeStyle.targeting` is now preserved verbatim as the SOAP `Targeting`
complex type. The previous v0.1 model decoded the payload into a flat
`{ad_units, custom}` shape whose keys did not match the WSDL
(`inventoryTargeting`, `customTargeting`, `geoTargeting`, ...). The
mismatch had two consequences:

- **Import was lossy.** Every imported NativeStyle landed in YAML with
  `ad_units: []` / `custom: {}` regardless of what the remote actually
  carried; a production network's NativeStyles all hid real
  `inventoryTargeting.targetedAdUnits` payloads behind that placeholder.
- **Apply was silently destructive.** `to_remote()` re-emitted the same
  flat shape, which `googleads`' SOAP packer dropped during
  `updateNativeStyles` (the WSDL has no `adUnits` field). The remote
  `Targeting` would have been overwritten with an empty payload on the
  first apply that touched an imported NativeStyle. Drift detection did
  not surface the problem because both sides agreed on "empty
  targeting".

This release stores the SOAP shape opaquely so `import → plan → apply`
round-trips byte-for-byte:

- `Targeting` model is removed. `NativeStyle.targeting: dict[str, Any]
  | None` carries the raw SOAP payload (or `None` when GAM returns no
  wrapper at all).
- `from_remote` keeps the dict as-is. `to_remote` re-emits it as-is.
  The `writer._to_user_yaml` mirrors the dict into the YAML, so the
  user can read the full nested structure (and edit it once a v0.2
  schema lands).
- A `@model_validator` migrates the legacy `{ad_units, custom}` shape:
  empty payloads (the only thing v0.1 could produce) become `None`
  silently; populated legacy payloads — which were always a lie —
  raise `LegacyTargetingError` asking the caller to re-run `gampan
  import` instead of applying a destructive empty targeting to the
  remote.

**Migration:** existing YAMLs imported by gampan <= 0.1.x must be
re-imported before the next `apply`. The model accepts the legacy
shape only when empty, so a stale `targeting: {ad_units: [], custom:
{}}` block keeps working until you re-import. Anything else now
raises at parse time.
