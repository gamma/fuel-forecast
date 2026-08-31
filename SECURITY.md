# Security Policy

## Supported version

Only the latest version on the `master` branch is actively maintained.

## Reporting a vulnerability

Please **do not open a public issue** for a suspected security vulnerability,
credential exposure, or a way to make excessive Tankerkönig API requests.

Contact the maintainer at **gerry.w@gammaproduction.de** with:

- a short description and affected version or commit;
- steps to reproduce safely;
- potential impact; and
- any suggested remediation.

You should receive an acknowledgement within seven days. Please allow a
reasonable time for investigation and a fix before disclosing details publicly.

## Local data

`memory/` contains the active Tankerkönig API key and generated local price data.
It is intentionally excluded from Git. Before publishing a fork, verify with
`git check-ignore memory/config.json` that local runtime data remains ignored.
