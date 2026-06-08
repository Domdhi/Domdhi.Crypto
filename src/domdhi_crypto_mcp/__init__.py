"""domdhi_crypto_mcp — the agent-facing layer over the Domdhi.Crypto engine.

A SEPARATE top-level package (ships in the same distribution as ``domdhi_crypto``)
holding the surfaces an LLM agent talks to: the FastMCP stdio ``server`` and the
FR-23 ``decision`` contract. The dependency arrow points one way — this package
imports FROM ``domdhi_crypto`` (db/context/factors), never the reverse — so the
engine stays usable with no agent code on the path. The ``mcp`` SDK remains an
optional extra (``pip install domdhi-crypto[mcp]``); see ``server.build_server``.
"""
