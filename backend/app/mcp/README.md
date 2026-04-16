# DHRUVA MCP Server

Exposes DHRUVA's order, portfolio, and strategy operations to MCP-aware clients (Claude Desktop, Cursor, Windsurf, ChatGPT).

## Install

```bash
pip install mcp                              # not in default requirements
```

## Run

```bash
DHRUVA_MCP_TOKEN=<your-jwt> python -m app.mcp.server
```

The token is a normal DHRUVA access token (`POST /api/v1/auth/login`). Every tool call validates it against the same JWT verifier the REST API uses, so MCP can never bypass auth.

## Wire into Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dhruva": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "env": {
        "DHRUVA_MCP_TOKEN": "<your-jwt>",
        "DHRUVA_DB_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/dhruva",
        "DHRUVA_REDIS_URL": "redis://localhost:6379/0"
      },
      "cwd": "<absolute path to backend/>"
    }
  }
}
```

## Tools exposed

| Name | Description |
|---|---|
| `list_accounts` | All broker accounts owned by the token bearer |
| `list_positions(account_id)` | Open positions on an account |
| `list_orders(account_id, limit?)` | Recent orders |
| `place_order(account_id, symbol, exchange, side, quantity, ...)` | Place an order through the same risk + audit pipeline as REST |
| `list_strategies(account_id)` | Strategies on an account |
| `toggle_strategy(strategy_id, enabled)` | Enable/disable a strategy |

## What it does NOT bypass

- JWT validation
- Risk engine (market hours, qty freeze, lot size, margin, concentration, rate limit)
- Audit (every action records a row in `audit_events`)
- Approval gate (strategies with `requires_approval` still go through the Action Center)
- Telegram emission on fills
