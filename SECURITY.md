# Security

## Secrets

- `.env` is gitignored; `.env.example` holds empty values only.
- `bin/secret-scan` runs in `bin/check.sh` and fails on token shapes, the
  owner id and private host paths.
- A missing or blank value is an error that names the key; nothing falls back
  to an empty token.

## Reporting

Open a private security advisory on the repository, or email the maintainer
listed in the repository profile. Do not file a public issue for a credential
leak; rotate the credential first, then report.

## If a token leaks

1. Revoke it at the provider (Discord developer portal, Slack app settings,
   or your model provider).
2. Issue a replacement into your local `.env`.
3. Run `bin/secret-scan` to confirm the tree is clean.
