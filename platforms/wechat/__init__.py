"""Convert blog posts into WeChat official account articles.

The package turns the **content-unit repository** (``content/units/``,
produced by ``tools/build-content-units.py``) -- into WeChat-ready HTML
and pushes it to the official account draft box.  The adapter reads that
repository directly; it does not read the site's copy of it.

Modules are layered so each one can be tested on its own:

- ``posts``     discover articles and validate them against WeChat's limits
- ``slugs``     the adapter's own slug rule (URL segments)
- ``mdparse``   Markdown -> block AST (pure)
- ``render``    AST -> WeChat HTML (pure)
- ``highlight`` code -> inline-styled HTML
- ``mermaid``   mermaid diagrams -> PNG
- ``assets``    image compression and sizing
- ``publish``   WeChat API client (network)
- ``state``     idempotency bookkeeping
"""
