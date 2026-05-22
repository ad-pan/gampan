# Security Policy

## Supported Versions

gampan is in **v0.1 alpha**. Only the latest released version on the
`main` branch receives security fixes; older `v0.1.x` patch releases
are not back-patched. Once v1.0 lands, the last two minor lines will
be supported in parallel.

| Version | Supported          |
| ------- | ------------------ |
| `0.1.x` | :white_check_mark: (latest only) |
| `< 0.1` | :x:                |

## Reporting a Vulnerability

**Do not open a public issue for vulnerabilities.**

Use GitHub's [private vulnerability reporting](https://github.com/ad-pan/gampan/security/advisories/new)
("Report a vulnerability" button on the Security tab). That keeps the
report off the public timeline until a fix is ready and gives us a
private thread for back-and-forth.

If you cannot use GitHub for some reason, email the maintainer
listed in `pyproject.toml` directly with `gampan security:` as the
subject prefix.

### What to include

- A description of the issue and its impact
- Steps to reproduce (a minimal proof-of-concept is ideal)
- Affected versions / commits
- Whether the issue is already public (other tools, prior advisories, etc.)

### Response expectations

| Step | Target |
| --- | --- |
| Acknowledge receipt | within 3 business days |
| Initial assessment + severity | within 7 business days |
| Fix + advisory published | depends on severity; CVSS ≥ 7 within 30 days |

If you would like credit in the advisory, mention the name / handle
you want listed.

## Out of Scope

- Findings against unreleased branches or stale forks
- Issues that require physical access to a developer machine
- Anything that depends on a malicious package being installed
  alongside gampan (supply-chain auditing of dependencies is
  handled separately via Dependabot + CodeQL)

## Acknowledgements

CodeQL (security-and-quality query pack) runs on every push to `main`
and every PR; Dependabot sweeps the `pip` and `github-actions`
ecosystems weekly. Most low-hanging findings are already filtered out
before they reach maintainers.
