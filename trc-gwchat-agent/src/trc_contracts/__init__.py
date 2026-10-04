"""Typed tool contracts. PRODUCER: the FastMCP server validates every response against these models (fail closed).
CONSUMER: the agent treats `data` as opaque JSON that it forwards verbatim into GWChat blocks (it reads only a handful of fields for composite-tool
headlines), and CI contract tests assert the MCP server and the agent allow-list never drift. On-prem API shapes never appear here.
"""
