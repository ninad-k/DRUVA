# DHRUVA: Complete Implementation Plan & Documentation

**Project Name:** DHRUVA - Ultra-Fast Trading Platform for Indian Markets (NSE/BSE)
**Architecture:** .NET 10 + Angular 18+ (Modular Monolith)
**Timeline:** 22.5 Days
**Status:** Production-Ready MVP1
**Date:** 2026-04-16

---

## Table of Contents

1. Executive Summary
2. Architecture Overview
3. Technology Stack
4. System Design Diagrams
5. Data Flow Diagrams
6. Implementation Timeline (22.5 Days)
7. Phase 1: Frontend gRPC Integration
8. Implementation Prompts
9. Deployment Guide
10. Configuration & Setup

---

## 1. Executive Summary

### Vision
DHRUVA is a professional-grade, ultra-fast algorithmic trading platform for Indian markets (NSE/BSE). It combines portfolio management, real-time strategy execution, pre-market scanning, and comprehensive reporting with a focus on performance (< 30ms order latency) and modularity.

### Key Features
- **Ultra-Fast Execution:** < 30ms order placement (3-5x faster than Python)
- **Multi-Account Support:** 5+ accounts across 23+ Indian brokers
- **Strategy Execution:** Modular strategy framework with backtesting
- **Portfolio Management:** Holdings, analytics, risk metrics, rebalancing
- **Pre-Market Scanner:** Concept-based screening (Momentum, MeanReversion, etc.)
- **Real-Time Dashboards:** SignalR WebSocket updates (no polling)
- **Email Alerts:** Event-driven notifications (trade execution, risk alerts, scanner signals)
- **Comprehensive Reports:** 8 report types (PDF, Excel, CSV)
- **Production-Grade:** Structured logging, distributed tracing, audit trail, monitoring

### Target User
Personal algo trader in India managing multiple accounts across NSE/BSE, wanting to run custom strategies with professional portfolio management and risk controls.

### Success Metrics
- Order latency: < 30ms ✅
- Uptime: 99.9% ✅
- Broker support: 23+ (start with 5) ✅
- Scalability: 50+ strategies, 10+ accounts ✅
- Single-user mode (MVP1), RBAC-ready for future ✅

---

## 2. Architecture Overview

### Modular Monolith Design (Single Process)

```
┌─────────────────────────────────────────────────────────┐
│          DHRUVA.Web (ASP.NET Core 10 Host)              │
│  Frontend (Angular SPA) + Backend (gRPC + WebSocket)    │
└─────────────────────────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌─────────┐     ┌────────────┐     ┌──────────┐
    │ gRPC    │     │ SignalR    │     │  REST   │
    │ Calls   │     │ WebSocket  │     │  API    │
    │ (Phase1)│     │ (Real-time)│     │ (Phase2)│
    └─────────┘     └────────────┘     └──────────┘
         │                 │                 │
    ┌────────────────────────────────────────────────┐
    │         DI Container (Program.cs)              │
    │                                                │
    │  ┌──────────────┐  ┌────────────────────┐    │
    │  │  Services    │  │  Infrastructure    │    │
    │  ├──────────────┤  ├────────────────────┤    │
    │  │ Execution    │  │ Logging (Serilog)  │    │
    │  │ Portfolio    │  │ Caching (Redis)    │    │
    │  │ Strategy     │  │ Tracing (OTel)     │    │
    │  │ Scanner      │  │ Database (EF Core) │    │
    │  │ Broker       │  │ Auth (JWT)         │    │
    │  │ Reports      │  │ Cache Service      │    │
    │  │ Notification │  │ Config Service     │    │
    │  │ Audit        │  │ Email Service      │    │
    │  └──────────────┘  └────────────────────┘    │
    └────────────────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌──────────┐     ┌──────────┐     ┌──────────┐
    │PostgreSQL│     │   Redis  │     │RabbitMQ │
    │+ TimescaleDB   │  Cache   │     │(Future) │
    └──────────┘     └──────────┘     └──────────┘
```

### Service Projects (Separate DLLs, Single Process)

```
DHRUVA.sln
├── DHRUVA.Web                (Main host, controllers, SignalR hubs)
├── DHRUVA.Execution          (Order engine, position tracking, risk)
├── DHRUVA.Portfolio          (Holdings, analytics, risk metrics)
├── DHRUVA.Strategy           (Strategy execution, backtesting)
├── DHRUVA.Scanner            (Pre-market scanning, concepts)
├── DHRUVA.Data               (Market data pipeline, OHLCV)
├── DHRUVA.Broker             (23+ broker adapters, token refresh)
├── DHRUVA.Notification       (Email, SMS, in-app alerts)
├── DHRUVA.Reports            (PDF, Excel, CSV generation)
├── DHRUVA.Audit              (Audit logging, event sourcing)
├── DHRUVA.Core               (Models, interfaces, enums)
├── DHRUVA.Infrastructure     (Logging, caching, DB, tracing)
├── DHRUVA.Auth               (JWT, user management)
└── DHRUVA.Common             (Utilities, extensions)
```

**Key Points:**
- All services in same process (no network latency)
- Direct method calls via DI: `await executionService.PlaceOrder(...)`
- Can split to gRPC/microservices later without code changes
- Frontend calls gRPC endpoints directly (Phase 1)

---

## 3. Technology Stack

### Backend (.NET 10 Modular Monolith)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | ASP.NET Core 10 | Single host, routing, SignalR |
| **Projects** | C# 13, .NET 10 | 9 service projects + shared projects |
| **Database** | PostgreSQL + TimescaleDB | Core data + time-series |
| **Cache** | Redis 7 | Positions, prices, metrics (1-sec to 5-min TTL) |
| **Real-Time** | SignalR WebSocket | Live dashboards (orders, positions, alerts) |
| **Logging** | Serilog JSON → PostgreSQL | Structured logging, distributed tracing |
| **Tracing** | OpenTelemetry | 9 spans per order (troubleshooting in production) |
| **ORM** | Entity Framework Core | Database abstraction, migrations |
| **DI** | Built-in Microsoft.Extensions | Service registration, dependency injection |
| **Auth** | JWT Bearer Tokens | Single-user, 15-min token, 7-day refresh |
| **gRPC** | gRPC .NET (Phase 1) | Frontend calls backend directly |
| **Testing** | xUnit, Moq, Testcontainers | Unit, integration, E2E tests |
| **Monitoring** | Microsoft Aspire | Local dev dashboard, observability |
| **CLI** | .NET CLI | Build, run, test, publish |

### Frontend (Angular 18+)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | Angular 18+ with Vite | SPA, routing, components |
| **UI Library** | shadcn/ui + Tailwind CSS | Professional component library |
| **Charts** | ng-apexcharts | Equity curve, allocation, drawdown charts |
| **Tables** | Angular CDK Virtual Scroll | Performance (1000+ rows) |
| **State** | NgRx or Akita | Global state management |
| **HTTP** | gRPC-web client (Phase 1) | Direct calls to backend gRPC |
| **Real-Time** | SignalR client | WebSocket connections |
| **i18n** | @angular/localize + @ngx-translate | English + Hindi (extensible) |
| **Styling** | Tailwind CSS | Responsive design, dark/light theme |
| **Build** | Vite | Fast development, optimized bundles |
| **Testing** | Jasmine + Karma | Unit and integration tests |

### Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Containers** | Docker | Containerize .NET + PostgreSQL + Redis |
| **Orchestration** | Kubernetes (future) | Multi-pod deployment, scaling |
| **Cloud** | AWS (EKS) or Azure (AKS) | Cloud deployment, managed services |
| **CI/CD** | GitHub Actions | Build, test, deploy pipeline |
| **Logging** | Serilog + PostgreSQL | Immutable audit trail (7-year retention) |
| **Monitoring** | Aspire (local) + Prometheus (future) | Observability dashboards |

---

## 4. System Design Diagrams

### 4.1 High-Level Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│                    DHRUVA PLATFORM                          │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  FRONTEND (Angular 18+)                              │   │
│  │  • Trading Dashboard (orders, positions, P&L)        │   │
│  │  • Portfolio Dashboard (holdings, allocation)        │   │
│  │  • Strategy Manager (create, backtest, monitor)      │   │
│  │  • Pre-Market Scanner (concept-based screening)      │   │
│  │  • Reports (view, download, schedule)                │   │
│  │  • Risk Dashboard (VaR, concentration, stress test)  │   │
│  │                                                       │   │
│  │  Communication: gRPC-web + SignalR WebSocket         │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                   │
│                    ┌──────┴──────┐                           │
│                    │             │                           │
│                 gRPC          SignalR                        │
│             (Method Calls)    (Live Updates)                │
│                    │             │                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  BACKEND (ASP.NET Core 10)                           │   │
│  │                                                       │   │
│  │  Service Layer (DI Injected):                        │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │ • Execution Service (< 30ms order placement)   │  │   │
│  │  │ • Portfolio Service (holdings, allocation)     │  │   │
│  │  │ • Strategy Service (execution, backtesting)    │  │   │
│  │  │ • Scanner Service (concept-based screening)    │  │   │
│  │  │ • Data Service (OHLCV, tick data, cache)       │  │   │
│  │  │ • Broker Service (23+ adapters, token refresh) │  │   │
│  │  │ • Notification Service (email, SMS, in-app)    │  │   │
│  │  │ • Reports Service (PDF, Excel, CSV)            │  │   │
│  │  │ • Audit Service (immutable event log)          │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  │                                                       │   │
│  │  Infrastructure Layer:                               │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │ • Serilog Logging (structured JSON)           │  │   │
│  │  │ • OpenTelemetry Tracing (order flow)          │  │   │
│  │  │ • Redis Cache Service (positions, prices)     │  │   │
│  │  │ • EF Core (database abstraction)              │  │   │
│  │  │ • JWT Auth (single-user, refresh tokens)      │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                   │
│         ┌─────────────────┼─────────────────┐               │
│         │                 │                 │               │
│   ┌─────────────┐  ┌──────────────┐  ┌──────────┐          │
│   │PostgreSQL   │  │    Redis     │  │ RabbitMQ │          │
│   │+ TimescaleDB│  │   Cache      │  │ (Future) │          │
│   │(Core + TS)  │  │   (Real-time)│  │ (Async)  │          │
│   └─────────────┘  └──────────────┘  └──────────┘          │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  BROKER ADAPTERS (23+ Indian Brokers)                │   │
│  │  • Zerodha (Kite Connect REST API)                   │   │
│  │  • Upstox, Dhan, Fyers, 5Paisa, ... (REST APIs)     │   │
│  │  • Token Refresh: 08:55 AM IST (start of day)        │   │
│  │  • Health Monitor: Every 5 minutes                   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  SINGLE SERVER (MVP1)                        │
│                                                              │
│  Port 5000 / 5001 (HTTPS)                                   │
│                                                              │
│  ┌───────────────────────────────────────────────────┐     │
│  │  Docker Container: DHRUVA App                     │     │
│  │                                                   │     │
│  │  ┌─────────────────────────────────────────────┐ │     │
│  │  │ .NET 10 Process (Single)                    │ │     │
│  │  │                                             │ │     │
│  │  │  ┌─────────────────────────────────────┐  │ │     │
│  │  │  │ ASP.NET Core Host                  │  │ │     │
│  │  │  │ - REST Controllers (/api/v1/*)    │  │ │     │
│  │  │  │ - gRPC Services (Phase 1)         │  │ │     │
│  │  │  │ - SignalR Hubs                    │  │ │     │
│  │  │  │ - Static Files (Angular SPA)      │  │ │     │
│  │  │  └─────────────────────────────────────┘  │ │     │
│  │  │                                             │ │     │
│  │  │  ┌─────────────────────────────────────┐  │ │     │
│  │  │  │ 9 Service DLLs (DI Injected)       │  │ │     │
│  │  │  │ - Execution, Portfolio, Strategy   │  │ │     │
│  │  │  │ - Scanner, Data, Broker            │  │ │     │
│  │  │  │ - Notification, Reports, Audit     │  │ │     │
│  │  │  └─────────────────────────────────────┘  │ │     │
│  │  │                                             │ │     │
│  │  │  ┌─────────────────────────────────────┐  │ │     │
│  │  │  │ Infrastructure (Shared)             │  │ │     │
│  │  │  │ - Serilog Logging                  │  │ │     │
│  │  │  │ - OpenTelemetry Tracing           │  │ │     │
│  │  │  │ - Redis Cache Client               │  │ │     │
│  │  │  │ - EF Core DbContext                │  │ │     │
│  │  │  │ - JWT Auth Service                 │  │ │     │
│  │  │  └─────────────────────────────────────┘  │ │     │
│  │  │                                             │ │     │
│  │  └─────────────────────────────────────────────┘ │     │
│  │                                                   │     │
│  └───────────────────────────────────────────────────┘     │
│                           │                                  │
│         ┌─────────────────┼─────────────────┐              │
│         │                 │                 │              │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │PostgreSQL   │  │    Redis     │  │ RabbitMQ     │      │
│  │+ TimescaleDB│  │   Container  │  │ Container    │      │
│  │ Container   │  │              │  │ (Optional)   │      │
│  └─────────────┘  └──────────────┘  └──────────────┘      │
│                                                              │
└─────────────────────────────────────────────────────────────┘

SCALING PATH (MVP2+):
┌─────────────────────────────────────────────────────────────┐
│         Kubernetes Cluster (Multiple Pods)                  │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ DHRUVA.Web   │  │Execution Svc │  │Portfolio Svc │      │
│  │+ 7 Services  │  │(gRPC Server) │  │(gRPC Server) │      │
│  │ Replicas: 2  │  │Replicas: 5   │  │Replicas: 2   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                  │                 │              │
│         └──────────────────┼─────────────────┘              │
│                            │                                │
│           ┌────────────────┼────────────────┐               │
│           │                │                │               │
│    ┌────────────┐  ┌────────────┐  ┌────────────┐          │
│    │PostgreSQL  │  │   Redis    │  │ RabbitMQ   │          │
│    │(Managed)   │  │(Managed)   │  │(Managed)   │          │
│    └────────────┘  └────────────┘  └────────────┘          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Data Flow Diagrams

### 5.1 Order Placement Flow (Ultra-Fast Execution < 30ms)

```
User Click: "Place Order (BUY 100 RELIANCE @ 2450)"
            │
            ▼
┌─────────────────────────────────────────┐
│ Frontend (Angular)                      │
│ • Form validation                       │
│ • gRPC call to backend                  │
│ • Expected: PlaceOrderResponse          │
└─────────────────────────────────────────┘
            │
            │ gRPC-web (fast, binary protocol)
            │
            ▼
┌─────────────────────────────────────────┐
│ DHRUVA.Web (ASP.NET Core)               │
│ gRPC Endpoint: /dhruva.Execution/       │
│   PlaceOrder (PlaceOrderRequest)        │
│                                         │
│ Middleware:                             │
│ • Extract JWT token from header         │
│ • Get user_id                           │
│ • Create correlation_id for tracing     │
└─────────────────────────────────────────┘
            │
            │ Direct method call (same process)
            │
            ▼
┌─────────────────────────────────────────┐
│ ExecutionService.PlaceOrder()           │
│                                         │
│ Trace Span 1: "ValidateAuth"            │
│ ├─ Lookup user from cache               │
│ └─ Return user_id                       │
│                                         │
│ Trace Span 2: "RiskValidation" (~10ms)  │
│ ├─ Get positions from Redis             │
│ ├─ Check: margin > 1%?                  │
│ ├─ Check: concentration < 40%?          │
│ ├─ Check: daily_loss < limit?           │
│ └─ Return: Risk OK or REJECTED          │
│                                         │
│ Trace Span 3: "BrokerSelection" (~2ms)  │
│ ├─ Get account's broker_type            │
│ ├─ Get broker health status             │
│ ├─ Select: Zerodha (lowest fees)        │
│ └─ Return: broker_id                    │
│                                         │
│ Trace Span 4: "PlaceBrokerOrder" (~8ms) │
│ ├─ Call BrokerService.PlaceOrder()      │
│ │  ├─ REST call to Zerodha API          │
│ │  ├─ Request: { symbol, qty, price }   │
│ │  └─ Response: { broker_order_id }     │
│ └─ Catch exceptions, log error          │
│                                         │
│ Trace Span 5: "UpdatePosition" (~2ms)   │
│ ├─ Update position in Redis             │
│ │  ├─ position:RELIANCE:qty = 100       │
│ │  ├─ position:RELIANCE:price = 2450    │
│ │  └─ Set TTL = 1 second                │
│ └─ Return: position_updated             │
│                                         │
│ Trace Span 6: "RecordTrade" (~1ms)      │
│ ├─ Insert into PostgreSQL trades table  │
│ │  ├─ INSERT trades (account_id,...)    │
│ │  └─ Return: trade_id                  │
│ └─ Return: trade_recorded               │
│                                         │
│ Trace Span 7: "PublishSignalR" (~2ms)   │
│ ├─ Broadcast to TradingHub              │
│ │  ├─ Message: OrderExecuted            │
│ │  ├─ Data: { order_id, symbol, qty }   │
│ │  └─ All connected clients receive     │
│ └─ Return: broadcast_sent               │
│                                         │
│ Trace Span 8: "LogAudit" (~1ms)         │
│ ├─ Append to audit log                  │
│ │  ├─ user_id, action, details, timestamp
│ │  └─ Immutable (append-only)           │
│ └─ Return: audit_logged                 │
│                                         │
│ Trace Span 9: "ReturnResponse"          │
│ └─ Return PlaceOrderResponse            │
│    ├─ order_id = "ORD-123456"           │
│    ├─ status = "EXECUTED"               │
│    ├─ trace_id = "abc123xyz"            │
│    └─ latency_ms = 28                   │
└─────────────────────────────────────────┘
            │
            │ gRPC response (28ms total)
            │
            ▼
┌─────────────────────────────────────────┐
│ Frontend (Angular)                      │
│ • Parse gRPC response                   │
│ • Update UI: Order EXECUTED             │
│ • Show toast: "Order placed!"           │
│ • Subscribe to SignalR for updates      │
└─────────────────────────────────────────┘
            │
            │ SignalR WebSocket
            │
            ▼
┌─────────────────────────────────────────┐
│ Trading Dashboard Updates               │
│ • Position table: +100 RELIANCE         │
│ • P&L ticker: -₹0 (entry price)         │
│ • Recent trades: BUY 100 RELIANCE       │
│ • Account equity: Updated (live)        │
└─────────────────────────────────────────┘

TRACING OUTPUT (Aspire Dashboard):
┌─────────────────────────────────────────┐
│ Trace: ORD-123456                       │
│ Root Duration: 28ms                     │
│                                         │
│ ├─ ValidateAuth (2ms)                   │
│ ├─ RiskValidation (10ms)                │
│ ├─ BrokerSelection (2ms)                │
│ ├─ PlaceBrokerOrder (8ms) ← longest!    │
│ ├─ UpdatePosition (2ms)                 │
│ ├─ RecordTrade (1ms)                    │
│ ├─ PublishSignalR (2ms)                 │
│ └─ LogAudit (1ms)                       │
│                                         │
│ Status: SUCCESS                         │
│ Trace ID: abc123xyz                     │
└─────────────────────────────────────────┘
```

### 5.2 Strategy Execution Flow (1-Minute Candle Execution)

```
Every 1 Minute (After Candle Close at :01 seconds):
            │
            ▼
┌─────────────────────────────────────────┐
│ BackgroundService: StrategyExecutor      │
│ Timer: Every 60 seconds                  │
│ Trigger Time: 09:31:01, 09:32:01, etc.  │
└─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ foreach enabled_strategy:                │
│                                         │
│ GET latest candle from TimescaleDB:      │
│ • Query: SELECT * FROM ohlcv_1m         │
│ •   WHERE symbol = 'RELIANCE'            │
│ •   ORDER BY time DESC LIMIT 1           │
│ • Cache: Redis (check first)             │
│ • TTL: 1 minute                          │
│                                         │
│ Result: OHLCV = {                        │
│   symbol: RELIANCE,                      │
│   open: 2440,                            │
│   high: 2455,                            │
│   low: 2435,                             │
│   close: 2448,                           │
│   volume: 1000000,                       │
│   time: 09:31:00                         │
│ }                                        │
└─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ Compute Technical Indicators:            │
│                                         │
│ • EMA(20): 2450                          │
│ • RSI(14): 65                            │
│ • MACD: bullish signal                   │
│ • ATR(14): 15                            │
│ • Bollinger Bands: upper 2460, lower 2430
│ • Supertrend: uptrend, price > ST       │
│                                         │
│ Cache in Redis:                          │
│ • key: strategy:RELIANCE:indicators      │
│ • TTL: 5 minutes                         │
│ • Hit rate: ~80% (reused next minute)    │
└─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ Execute Strategy Logic:                  │
│                                         │
│ Strategy: "EMA_CROSS"                    │
│ if close > EMA(20) AND RSI < 70:        │
│   signal = "BUY"                         │
│   confidence = 85%                       │
│                                         │
│ Result: {                                │
│   action: BUY,                           │
│   symbol: RELIANCE,                      │
│   quantity: 100,                         │
│   confidence: 85%,                       │
│   reason: "Close above EMA-20, RSI<70"   │
│ }                                        │
└─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ Risk Check:                              │
│                                         │
│ if confidence < threshold (80%):         │
│   SKIP trade                             │
│   Log: "Confidence below threshold"      │
│   Return                                 │
│                                         │
│ ✓ Confidence = 85% >= 80%                │
│ → Proceed to trade                       │
└─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ Call ExecutionService.PlaceOrder()       │
│                                         │
│ • Pass full order with confidence       │
│ • Include trace_id (strategy execution)  │
│ • No risk check needed (strategy signal)│
│                                         │
│ Response:                                │
│ • order_id: ORD-234567                  │
│ • status: EXECUTED                      │
│ • latency: 26ms                         │
└─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ Update Strategy Performance:             │
│                                         │
│ INSERT INTO strategy_trades:             │
│ • strategy_id = EMA_CROSS-1              │
│ • order_id = ORD-234567                 │
│ • signal_time = 09:31:01                │
│ • entry_price = 2450                    │
│ • confidence = 85%                      │
│                                         │
│ Cache Update:                            │
│ • key: strategy:perf:EMA_CROSS-1         │
│ • win_rate: 65%                         │
│ • sharpe: 1.8                           │
│ • max_dd: 5%                            │
│ • TTL: 5 minutes                        │
└─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ Publish via SignalR:                     │
│                                         │
│ hub.Clients.All.SendAsync(               │
│   "StrategySignal",                     │
│   {                                     │
│     strategy: "EMA_CROSS",              │
│     symbol: "RELIANCE",                 │
│     action: "BUY",                      │
│     confidence: 85%,                    │
│     time: "09:31:01"                    │
│   }                                     │
│ )                                       │
│                                         │
│ Frontend Strategy Hub receives update:   │
│ • Log signal in execution log           │
│ • Update strategy performance card      │
│ • Notify user (toast)                   │
└─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ Log & Audit:                             │
│                                         │
│ Serilog:                                 │
│ {                                       │
│   "level": "Info",                      │
│   "message": "Strategy executed",       │
│   "strategy_id": "EMA_CROSS-1",         │
│   "symbol": "RELIANCE",                 │
│   "action": "BUY",                      │
│   "confidence": 85,                     │
│   "order_id": "ORD-234567",             │
│   "timestamp": "2025-04-16T09:31:01Z"   │
│ }                                       │
│                                         │
│ Audit Log:                               │
│ INSERT strategy_executions:              │
│ • user_id, strategy_id, order_id, time  │
└─────────────────────────────────────────┘
```

### 5.3 Real-Time Dashboard Flow (SignalR WebSocket)

```
BACKEND → FRONTEND (WebSocket, Real-Time)

Every 1-2 seconds:

┌─────────────────────────────────────────┐
│ Data Change Detected                    │
│ (Trade executed, position updated, etc.)│
└─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ Service broadcasts via SignalR:         │
│                                         │
│ await _hubContext.Clients.All           │
│   .SendAsync("OrderExecuted", order);   │
│                                         │
│ Payload (binary, fast):                 │
│ {                                       │
│   "order_id": "ORD-123456",             │
│   "symbol": "RELIANCE",                 │
│   "status": "EXECUTED",                 │
│   "filled_qty": 100,                    │
│   "price": 2450,                        │
│   "side": "BUY",                        │
│   "time": "2025-04-16T09:31:01Z"        │
│ }                                       │
└─────────────────────────────────────────┘
            │
            │ WebSocket Frame (< 5ms latency)
            │
            ▼
┌─────────────────────────────────────────┐
│ Frontend SignalR Client                 │
│                                         │
│ trading$.subscribe("OrderExecuted")     │
│   .subscribe(order => {                 │
│     // Update UI in real-time           │
│     orders.push(order);                 │
│     positions[RELIANCE] += 100;         │
│     updateUI();                         │
│   });                                   │
└─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ Angular Components Update (No Refresh)  │
│                                         │
│ • Trading Dashboard:                    │
│   Order Book: +1 row (BUY 100 REL)      │
│   Status indicator: Green ✓             │
│                                         │
│ • Portfolio Dashboard:                  │
│   Holdings: REL qty = 100               │
│   P&L: -₹0 (entry price)                │
│   Account equity: -commission           │
│                                         │
│ • Strategy Dashboard:                   │
│   Recent trades: [BUY 100 REL @ 2450]   │
│   Win rate: 65%                         │
│                                         │
│ All updates LIVE (no manual refresh)    │
└─────────────────────────────────────────┘
```

---

## 6. Implementation Timeline (22.5 Days)

See main plan document for detailed daily breakdown.

---

## 7. Phase 1: Frontend gRPC Integration

### Why gRPC in Phase 1?

**Benefits:**
- ✅ Binary protocol (faster than JSON/HTTP)
- ✅ Strongly typed (proto buffers)
- ✅ Perfect for real-time trading (low latency)
- ✅ Easy to upgrade to separate services later
- ✅ Bidirectional streaming support (future)

**Phase 1 Implementation:**

```
FRONTEND (Angular)
    ↓
gRPC-web client library
    ↓
Proto definitions (shared between frontend + backend)
    ↓
gRPC endpoints in ASP.NET Core
    ↓
Service methods (direct DI calls)
    ↓
Database + Cache
```

### Proto Definitions (Shared)

```protobuf
// dhruva/execution.proto
syntax = "proto3";
package dhruva.execution;

service ExecutionService {
  rpc PlaceOrder(PlaceOrderRequest) returns (PlaceOrderResponse) {}
  rpc GetPositions(GetPositionsRequest) returns (GetPositionsResponse) {}
  rpc CancelOrder(CancelOrderRequest) returns (CancelOrderResponse) {}
}

message PlaceOrderRequest {
  string account_id = 1;
  string symbol = 2;
  string side = 3; // BUY, SELL
  int32 quantity = 4;
  double price = 5;
  double stop_loss = 6;
  double take_profit = 7;
  int32 confidence = 8; // 0-100
}

message PlaceOrderResponse {
  string order_id = 1;
  string status = 2; // EXECUTED, REJECTED, PENDING
  string reason = 3;
  int32 latency_ms = 4;
  string trace_id = 5; // for troubleshooting
}
```

### Frontend gRPC Setup

```typescript
// frontend/src/services/execution.service.ts

import { ExecutionServiceClient } from '@generated/dhruva/execution_pb_service';
import { PlaceOrderRequest, PlaceOrderResponse } from '@generated/dhruva/execution_pb';

export class ExecutionService {
  private stub = new ExecutionServiceClient('http://localhost:5000');

  placeOrder(req: PlaceOrderRequest): Promise<PlaceOrderResponse> {
    return new Promise((resolve, reject) => {
      this.stub.placeOrder(req, {}, (err, response) => {
        if (err) reject(err);
        else resolve(response);
      });
    });
  }
}

// Usage in component
export class TradingDashboard {
  constructor(private execution: ExecutionService) {}

  placeOrder() {
    const req = new PlaceOrderRequest();
    req.setSymbol('RELIANCE');
    req.setQuantity(100);
    req.setPrice(2450);
    req.setSide('BUY');

    this.execution.placeOrder(req)
      .then(response => {
        console.log(`Order ${response.getOrderId()} executed in ${response.getLatencyMs()}ms`);
        this.updateUI(response);
      })
      .catch(err => console.error(err));
  }
}
```

### Backend gRPC Server

```csharp
// DHRUVA.Web/Services/ExecutionGrpcService.cs

using Grpc.Core;
using Dhruva.Execution;

public class ExecutionGrpcService : ExecutionService.ExecutionServiceBase
{
    private readonly IExecutionService _executionService;
    private readonly ILogger<ExecutionGrpcService> _logger;

    public ExecutionGrpcService(IExecutionService executionService, ILogger<ExecutionGrpcService> logger)
    {
        _executionService = executionService;
        _logger = logger;
    }

    public override async Task<PlaceOrderResponse> PlaceOrder(PlaceOrderRequest request, ServerCallContext context)
    {
        var traceId = context.RequestHeaders.FirstOrDefault(x => x.Key == "trace-id")?.Value ?? Guid.NewGuid().ToString();
        
        try
        {
            var order = await _executionService.PlaceOrder(new PlaceOrderDto
            {
                AccountId = request.AccountId,
                Symbol = request.Symbol,
                Side = request.Side,
                Quantity = request.Quantity,
                Price = request.Price,
                Confidence = request.Confidence,
                TraceId = traceId
            });

            return new PlaceOrderResponse
            {
                OrderId = order.Id,
                Status = order.Status.ToString(),
                LatencyMs = order.LatencyMs,
                TraceId = traceId
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "PlaceOrder failed for {Symbol}", request.Symbol);
            return new PlaceOrderResponse { Status = "REJECTED", Reason = ex.Message };
        }
    }
}

// Program.cs
builder.Services.AddGrpc();
app.MapGrpcService<ExecutionGrpcService>();
```

### Migration to REST (Phase 2)

When ready, can add REST endpoints alongside gRPC:

```csharp
// DHRUVA.Web/Controllers/ExecutionController.cs
[ApiController]
[Route("api/v1/execution")]
public class ExecutionController : ControllerBase
{
    private readonly IExecutionService _executionService;

    [HttpPost("orders")]
    public async Task<IActionResult> PlaceOrder([FromBody] PlaceOrderRequest request)
    {
        var order = await _executionService.PlaceOrder(/* ... */);
        return Ok(order);
    }
}
```

---

## 8. Implementation Prompts

### Prompt 1: Backend Setup (Day 1)

```
Create a .NET 10 modular monolith solution for DHRUVA trading platform.

REQUIREMENTS:
1. Solution Structure:
   - Create DHRUVA.sln with 13 projects
   - Projects: DHRUVA.Web (main), DHRUVA.Execution, DHRUVA.Portfolio, DHRUVA.Strategy, 
     DHRUVA.Scanner, DHRUVA.Data, DHRUVA.Broker, DHRUVA.Notification, DHRUVA.Reports, 
     DHRUVA.Audit, DHRUVA.Core, DHRUVA.Infrastructure, DHRUVA.Auth, DHRUVA.Common
   - All services reference DHRUVA.Core
   - DHRUVA.Web references all service projects (DI setup)

2. DHRUVA.Web (ASP.NET Core 10 Host):
   - Program.cs:
     a. Setup Serilog JSON logging (structured, PostgreSQL sink)
     b. Configure OpenTelemetry tracing (export to Aspire locally)
     c. Register all services via dependency injection
     d. Setup authentication (JWT Bearer)
     e. Configure SignalR hubs (TradingHub, PortfolioHub, StrategyHub, ScannerHub)
     f. Map gRPC services (ExecutionGrpcService, etc.)
     g. Map REST controllers (/api/v1/*)
     h. Configure CORS (frontend origin)
     i. Configure Swagger/OpenAPI documentation
   
   - appsettings.json:
     - PostgreSQL connection string
     - Redis connection string
     - JWT secret
     - gRPC configuration
     - Logging levels

3. DHRUVA.Core (Shared Models & Interfaces):
   - Models:
     a. User, Account, Strategy, Position, Trade, Order, Portfolio, etc.
     b. DTO classes (PlaceOrderDto, GetHoldingsDto, etc.)
     c. Enums: OrderStatus, TradeType, BrokerType, etc.
     d. Constants: Timeouts, limits, thresholds
   
   - Interfaces:
     a. IExecutionService (order placement, position tracking)
     b. IPortfolioService (holdings, allocation, analytics)
     c. IStrategyService (strategy CRUD, execution)
     d. IScannerService (pattern detection)
     e. IDataService (market data pipeline)
     f. IBrokerAdapter (broker abstraction)
     g. INotificationService (email alerts)
     h. IReportService (PDF, Excel generation)
     i. IAuditService (audit logging)
     j. ICacheService (Redis wrapper)
     k. IAuthService (JWT, user management)

4. DHRUVA.Infrastructure (Shared Services):
   - LoggingConfiguration.cs (Serilog setup)
   - TracingConfiguration.cs (OpenTelemetry setup)
   - CacheService.cs (ICache Service implementation, Redis)
   - DatabaseConfiguration.cs (EF Core DbContext setup)
   - HealthChecks.cs (liveness, readiness probes)

5. DHRUVA.Auth (Authentication):
   - AuthService.cs (login, refresh, logout, single-user)
   - TokenService.cs (JWT creation, validation)
   - PasswordService.cs (BCrypt hashing)
   - AuthMiddleware.cs (JWT token validation)

6. DHRUVA.Common (Utilities):
   - StringExtensions.cs
   - DateTimeExtensions.cs (IST timezone conversion)
   - MathHelpers.cs (Sharpe, Sortino, Calmar calculations)
   - EnumExtensions.cs

7. Docker & Database:
   - Docker-compose.yml (PostgreSQL + Redis, ngrok for Aspire)
   - database.sql (initial schema with all tables)
   - Migrations (EF Core migrations setup)

8. Health Checks:
   - /health/live (is app running?)
   - /health/ready (ready for traffic?)
   - Both return 200 if healthy, 503 if not

DELIVERABLE:
- Full project structure with all 13 projects
- DHRUVA.Web can compile and run (dotnet run)
- Serilog logging to console + PostgreSQL
- OpenTelemetry tracing visible in Aspire dashboard
- All services registered in DI container
- Docker stack (postgres, redis) running
- Base classes and interfaces defined
- Single-user auth working (admin@dhruva.local)
```

### Prompt 2: Frontend Setup (Days 16-18)

```
Create an Angular 18+ SPA frontend for DHRUVA trading platform using gRPC.

REQUIREMENTS:
1. Project Setup:
   - Create Angular 18+ project with Vite
   - Install: @ngx-translate/core, ng-apexcharts, @angular/cdk, tailwindcss, shadcn/ui
   - Setup gRPC-web client (@grpc/grpc-web, protobuf libraries)
   - Setup routing (AppRouting module)
   - Setup global styles (Tailwind dark mode, DHRUVA theme colors)

2. Authentication:
   - Auth service (login, logout, refresh token)
   - Auth guard (protect routes)
   - HttpInterceptor (add JWT to all requests)
   - Login page (email, password form)
   - Automatic token refresh on 401

3. Layout & Navigation:
   - Sidebar (collapsible, logo, menu)
   - TopBar (account selector, theme toggle, user menu)
   - Footer
   - Responsive (desktop, tablet, mobile)

4. gRPC Integration:
   - Generate TypeScript stubs from proto files
   - ExecutionService (gRPC calls to backend)
   - PortfolioService (gRPC calls)
   - StrategyService (gRPC calls)
   - DataService (gRPC calls)
   - ScannerService (gRPC calls)
   - Error handling + retry logic

5. SignalR Integration:
   - SignalR client connection (auto-connect on app startup)
   - TradingHub subscriber (orders, positions updates)
   - PortfolioHub subscriber (holdings updates)
   - StrategyHub subscriber (strategy signals)
   - ScannerHub subscriber (alerts)
   - Auto-reconnect with exponential backoff

6. Main Dashboards:
   - Trading Dashboard:
     a. Live order book (orders table, color-coded by status)
     b. Open positions (symbol, qty, entry, current, P&L)
     c. Recent trades (last 10)
     d. Live P&L ticker (today, week, month, YTD)
     e. Broker status indicators
   
   - Portfolio Dashboard:
     a. KPI cards (Total Equity, Cash, Invested, Daily P&L)
     b. Holdings table (sortable, filterable)
     c. Asset allocation charts (pie, bar)
     d. Performance chart (equity curve)
   
   - Strategy Dashboard:
     a. Strategy list (enable/disable toggle)
     b. Create strategy form
     c. Backtest results modal
     d. Performance metrics cards
   
   - Pre-Market Scanner:
     a. Market overview (Nifty futures, Asia market)
     b. Concept selector (Momentum, MeanReversion, etc.)
     c. Scanner results table
     d. Alerts list
   
   - Analytics & Risk:
     a. Performance metrics (Sharpe, Sortino, Calmar, max DD)
     b. Charts (equity curve, drawdown, rolling Sharpe)
     c. Risk metrics (VaR, concentration, correlation heatmap)
   
   - Multi-Account Matrix:
     a. Account cards (equity, daily P&L, Sharpe)
     b. Performance heatmap (accounts × metrics)
     c. Account comparison charts

7. Components & Features:
   - Loading spinners, skeleton loaders
   - Error toast (top-right, auto-dismiss)
   - Success toast (order placed, saved)
   - Empty states (no trades, no alerts)
   - Pagination on tables
   - Sortable/filterable columns
   - Keyboard navigation (Tab, Enter, Escape)
   - Accessibility (WCAG AA)

8. Theme & Styling:
   - Dark mode (default) + Light mode toggle
   - Tailwind CSS (responsive, mobile-first)
   - DHRUVA brand colors (dark #0F0F0F, light white, gold accent #C9A227)
   - Charts: ApexCharts with theme support
   - Status colors: Green (profit), Red (loss), Blue (neutral)

9. i18n (Multi-Language):
   - English (default) + Hindi (हिंदी)
   - Translation files (en.json, hi.json)
   - Language selector in TopBar
   - All UI text translatable

10. Build & Deployment:
    - ng build --prod (optimized bundle)
    - Output → wwwroot/ folder (served by ASP.NET Core)
    - Single-command deployment (dotnet publish)

DELIVERABLE:
- Full Angular 18+ SPA with all features
- gRPC integration working (can call backend)
- SignalR live updates (dashboards update without refresh)
- Professional UI with dark/light theme
- Multi-language support (English/Hindi)
- Responsive design (all screen sizes)
- No manual page refresh needed (WebSocket push)
```

### Prompt 3: Full System Integration (Day 19)

```
Integrate full DHRUVA system end-to-end.

REQUIREMENTS:
1. Backend Services (Days 1-15):
   - ExecutionService (place orders, track positions, risk checks)
   - PortfolioService (holdings, allocation, snapshots)
   - StrategyService (execution, backtesting, paper trading)
   - ScannerService (concept-based screening, alerts)
   - DataService (OHLCV candles, tick data, cache)
   - BrokerService (Zerodha, Upstox, Dhan adapters, token refresh)
   - NotificationService (email alerts, scheduling)
   - ReportsService (PDF, Excel, CSV generation)
   - AuditService (immutable event log, activity feed)

2. Integration Points:
   - gRPC: Frontend calls backend services directly
   - SignalR: Backend broadcasts updates to frontend (live dashboards)
   - PostgreSQL: Core data persistence
   - TimescaleDB: Time-series (OHLCV, events)
   - Redis: Real-time cache (positions, prices, metrics)
   - Serilog: Structured logging (JSON → PostgreSQL + console)
   - OpenTelemetry: Distributed tracing (order flow visibility)

3. End-to-End Flows (Test Each):
   a. User Login → Place Order → Position Updated → Dashboard Updates
   b. Strategy Execution → Signal Generated → Order Placed → P&L Calculated
   c. Backtest Run → Results Generated → Metrics Displayed
   d. Daily Snapshot → Analytics Calculated → Reports Generated
   e. Email Alert → Configured → Sent → Logged

4. Testing:
   - Unit tests (services, utilities)
   - Integration tests (database, cache, broker APIs)
   - E2E tests (full workflows)
   - Performance tests (order latency < 30ms)
   - Load tests (1000 concurrent users)

5. Monitoring:
   - Aspire dashboard (local dev)
   - Serilog logs (PostgreSQL + console)
   - OpenTelemetry traces (order flow, latency)
   - Health checks (/health/live, /health/ready)

6. Docker Deployment:
   - Build Docker image (DHRUVA.Web)
   - docker-compose up (all services)
   - Single command deployment

DELIVERABLE:
- Full system running end-to-end
- All integration points working
- All E2E workflows tested
- Performance benchmarks met
- Production-ready
```

---

## 9. Deployment Guide

### Local Development

```bash
# 1. Clone and setup
git clone <repo>
cd DHRUVA
dotnet restore

# 2. Docker stack (PostgreSQL, Redis, Aspire)
docker-compose up -d

# 3. Database migrations
dotnet ef database update --project DHRUVA.Infrastructure

# 4. Run backend
cd DHRUVA.Web
dotnet run

# Backend runs on: http://localhost:5000
# Aspire dashboard: http://localhost:18888

# 5. Frontend setup
cd ../frontend
npm install
ng serve

# Frontend runs on: http://localhost:4200

# 6. Login
# Go to http://localhost:4200
# Email: admin@dhruva.local
# Password: admin
# Change password on first login
```

### Docker Deployment (Single Server)

```bash
# Build Docker image
docker build -t dhruva:latest .

# Run container
docker run -d \
  -p 5000:5000 \
  -e "ConnectionStrings:DefaultConnection=postgres://..." \
  -e "Redis:Connection=redis:6379" \
  --name dhruva-app \
  dhruva:latest

# Verify
curl http://localhost:5000/health/live
```

### Kubernetes Deployment (MVP2+)

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dhruva-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: dhruva-app
  template:
    metadata:
      labels:
        app: dhruva-app
    spec:
      containers:
      - name: dhruva-app
        image: dhruva:latest
        ports:
        - containerPort: 5000
        env:
        - name: ConnectionStrings__DefaultConnection
          valueFrom:
            secretKeyRef:
              name: dhruva-secrets
              key: db-connection
        - name: Redis__Connection
          valueFrom:
            configMapKeyRef:
              name: dhruva-config
              key: redis-connection
        livenessProbe:
          httpGet:
            path: /health/live
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 5000
          initialDelaySeconds: 5
          periodSeconds: 5

---
apiVersion: v1
kind: Service
metadata:
  name: dhruva-service
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: 5000
  selector:
    app: dhruva-app
```

---

## 10. Configuration & Setup

### Environment Variables

```bash
# appsettings.Production.json
{
  "Logging": {
    "LogLevel": { "Default": "Information" }
  },
  "ConnectionStrings": {
    "DefaultConnection": "Server=postgres;Database=dhruva;User Id=postgres;Password=***;"
  },
  "Redis": {
    "Connection": "redis:6379"
  },
  "RabbitMQ": {
    "Host": "rabbitmq",
    "Username": "guest",
    "Password": "guest"
  },
  "JWT": {
    "Secret": "***",
    "ExpiryMinutes": 15,
    "RefreshExpiryDays": 7
  },
  "Broker": {
    "Zerodha": {
      "ApiBaseUrl": "https://api.kite.trade",
      "RequestTokenUrl": "https://kite.trade/connect/login"
    }
  }
}
```

### Database Setup

```sql
-- Initial schema (created by EF Core migrations)
-- Tables: Users, Accounts, Strategies, Positions, Trades, Orders,
--         Portfolio_Snapshots, Rebalance_Plans, Notifications,
--         Risk_Alerts, Reports, Audit_Logs, Logs

-- TimescaleDB hypertables (OHLCV):
SELECT create_hypertable('ohlcv_1m', 'time', if_not_exists => TRUE);
SELECT create_hypertable('ohlcv_5m', 'time', if_not_exists => TRUE);
SELECT create_hypertable('order_events', 'timestamp', if_not_exists => TRUE);
```

### Broker API Configuration

```csharp
// appsettings.json - Zerodha
{
  "Broker": {
    "Zerodha": {
      "ApiKey": "***",
      "ApiSecret": "***",
      "RedirectUrl": "https://dhruva.app/broker/zerodha/callback"
    }
  }
}
```

---

## Summary

This document provides the complete plan to build DHRUVA, an ultra-fast algorithmic trading platform for Indian markets. The key highlights are:

✅ **Architecture:** .NET 10 + Angular 18+ modular monolith (single process, can scale to microservices)
✅ **Performance:** < 30ms order latency (3-5x faster than Python)
✅ **Features:** Full trading, portfolio, analytics, risk, rebalancing, reports, scanners
✅ **Timeline:** 22.5 days to production-ready MVP1
✅ **Quality:** Structured logging, distributed tracing, audit trail, monitoring
✅ **Frontend:** gRPC calls (Phase 1), REST (Phase 2), SignalR live updates
✅ **Scalability:** Modular design, easy migration to microservices/Kubernetes

**Ready to build? Start with Day 1: Project Setup + Logging Infrastructure**
