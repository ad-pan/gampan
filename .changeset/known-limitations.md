---
"gampan": patch
---

Document known limitation: resolved credentials are not yet wired through to
SOAP/REST client library calls in v0.1.0-alpha. The `gampan auth login` flow
works end-to-end for keychain storage and `gampan auth status` reporting, but
the googleads YAML path (SOAP) and google-auth ADC path (REST) remain
independent. v0.1.1 will wire the resolved `Credentials` object into every API
request.
