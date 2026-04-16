# DHRUVA Protocol Buffers

Canonical source of truth for gRPC contracts shared between the Python backend and React frontend.

- Backend stubs generated into `backend/app/api/grpc/_generated/` via `backend/scripts/generate_proto.sh`.
- Frontend stubs generated into `frontend/src/api/grpc/_generated/` via `npm run proto:generate` (buf config in `frontend/buf.gen.yaml`).

## Layout

```
proto/dhruva/v1/
├── common.proto      (shared enums + Money + Page)
├── auth.proto        (AuthService)
├── orders.proto      (OrderService)
├── portfolio.proto   (PortfolioService)
├── strategies.proto  (StrategyService)
├── scanner.proto     (ScannerService)
└── reports.proto     (ReportService)
```

## Conventions

- **Monetary values** are `string` in Decimal representation (`"1234.56"`) — never `float`.
- **Timestamps** use `google.protobuf.Timestamp`.
- **Pagination** via shared `Page` / `PageInfo`.
- **Enums** are upper-snake-case with an `*_UNSPECIFIED = 0` default.
- Breaking changes require a new `v2` folder; never modify `v1` fields.
