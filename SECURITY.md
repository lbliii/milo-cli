# Security Policy

## Supported versions

Security fixes target the latest release on PyPI and the `main` branch. Older
pre-1.0 releases receive fixes only when the maintainer determines that a safe
backport is practical. Upgrade to the latest release before reporting a bug
that may already be fixed.

## Report a vulnerability privately

Email the maintainer at
[mrlawrencelane@gmail.com](mailto:mrlawrencelane@gmail.com) with the subject
`milo-cli security report`. Do not include secrets in a public issue,
discussion, pull request, test fixture, or terminal transcript.

Include enough information to reproduce and assess the report:

- affected Milo and Python versions, including whether the GIL is enabled;
- operating system and installation method;
- the smallest safe reproducer;
- expected and observed behavior;
- impact and any known preconditions;
- whether MCP stdio, gateway, registry/config paths, subprocesses, templates,
  or terminal state are involved; and
- suggested remediation, if known.

The maintainer will coordinate questions, a fix, credit, and disclosure timing
through a private channel. Please avoid public disclosure until a fixed release
or coordinated advisory is available.

## Security boundaries

Milo owns CLI/MCP dispatch, schema generation, gateway and child-process
lifecycle, registry/config persistence, terminal cleanup, and scaffolded
defaults. Applications built with Milo own their authorization, credentials,
business rules, network policy, and the safety of the functions they expose.

MCP annotations such as `readOnlyHint` and `destructiveHint` inform host policy;
they are not authorization. Keep secrets and private paths out of schemas,
llms.txt, logs, structured errors, snapshots, and examples. MCP stdout is a
JSON-RPC transport and must not contain diagnostic prints.
