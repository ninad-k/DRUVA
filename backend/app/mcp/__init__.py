"""Model Context Protocol (MCP) server.

Exposes DHRUVA's order, portfolio, strategy, and options surfaces to MCP-aware
clients (Claude Desktop, Cursor, Windsurf, ChatGPT). The server is a thin
shell over the same services the REST API uses; it does NOT bypass auth or
risk checks.

Run via: ``python -m app.mcp.server`` (after installing ``mcp`` package).
"""
