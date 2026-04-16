# DHRUVA - Ultra-Fast Algo Trading Platform

**DHRUVA** (Sanskrit: Pole Star) is a production-grade, cloud-scalable algorithmic trading + portfolio management platform for Indian markets (NSE/BSE).

## 🚀 Key Features

- **Ultra-fast execution**: < 30ms order placement (3-5x faster than Python)
- **Multi-broker support**: 23+ Indian brokers (Zerodha, Upstox, Dhan, Fyers, 5Paisa, and more)
- **Portfolio management**: Consolidated holdings, multi-account support
- **Professional analytics**: Sharpe ratio, Sortino, Calmar, max drawdown, VaR
- **Risk management**: Real-time risk checks, concentration limits, stress testing
- **Strategy execution**: Template strategies + custom strategy support, backtesting
- **Pre-market dashboard**: Concept-based scanner, setup quality scoring
- **Real-time dashboards**: Live updates via SignalR (no polling)
- **Email alerts**: Configurable notifications for trades, risk events
- **Comprehensive reports**: 8+ report types (PDF, Excel, CSV)
- **Enterprise logging**: Distributed tracing, structured JSON logs, audit trail
- **Cloud-ready**: Kubernetes-ready, scalable microservices architecture

## 📊 Technology Stack

**Backend:**
- **.NET 10** (C# 13) - Ultra-fast modular monolith
- **ASP.NET Core 10** - REST API, SignalR WebSockets
- **PostgreSQL 15+** - Relational data
- **TimescaleDB** - Time-series OHLCV data
- **Redis 7+** - Real-time caching (positions, prices)
- **RabbitMQ** - Async job processing (future phases)

**Frontend:**
- **Angular 18+** - SPA with Vite build
- **Tailwind CSS** - Utility-first styling
- **shadcn/ui** - Component library
- **ng-apexcharts** - Interactive charts
- **SignalR client** - Real-time WebSocket updates

**DevOps:**
- **Docker** - Containerization
- **Kubernetes** - Orchestration (MVP2+)
- **Microsoft Aspire** - Local development dashboard
- **OpenTelemetry** - Distributed tracing
- **Serilog** - Structured logging

## 📋 Project Structure

```
DHRUVA/
├── docs/
│   ├── DHRUVA_Complete_Plan.md                    (Architecture + diagrams)
│   ├── DHRUVA_Phase1_Implementation_Prompt.md    (Days 1-6 implementation)
│   └── DHRUVA_Logo_Design_Prompt.md              (Logo design guide)
│
├── backend/                                       (To be created)
│   ├── DHRUVA.Web/                              (ASP.NET Core host)
│   ├── DHRUVA.Execution/                        (Order engine)
│   ├── DHRUVA.Portfolio/                        (Holdings & analytics)
│   ├── DHRUVA.Strategy/                         (Strategy execution)
│   ├── DHRUVA.Scanner/                          (Pre-market scanner)
│   ├── DHRUVA.Data/                             (Market data)
│   ├── DHRUVA.Broker/                           (Broker adapters)
│   ├── DHRUVA.Notification/                     (Alerts)
│   ├── DHRUVA.Reports/                          (Report generation)
│   ├── DHRUVA.Audit/                            (Audit logging)
│   ├── DHRUVA.Core/                             (Models, interfaces)
│   ├── DHRUVA.Infrastructure/                   (Logging, caching, DB)
│   ├── DHRUVA.Auth/                             (JWT, auth)
│   └── DHRUVA.Common/                           (Utilities)
│
├── frontend/                                      (To be created)
│   ├── src/
│   │   ├── app/
│   │   │   ├── core/                            (Auth, guards, interceptors)
│   │   │   ├── shared/                          (Reusable components)
│   │   │   └── features/                        (Trading, Portfolio, Strategy, Scanner)
│   │   ├── assets/
│   │   │   └── dhruva-logo.svg
│   │   └── environments/
│   └── package.json
│
├── docker-compose.yml                            (Local dev environment)
├── .gitignore                                    (.NET + Node)
└── README.md                                     (This file)
```

## 🏗️ Architecture

DHRUVA uses a **modular monolith** design:
- **Single process** (port 5000) hosts all services for MVP1
- **13 separate projects** with dependency injection
- **Migratable to microservices** - Can split to gRPC/separate services without code changes
- **Direct method calls** - No HTTP/RPC overhead within process
- **SignalR WebSockets** - Real-time bidirectional communication with frontend

**Timeline**: 22.5 days (production-ready MVP1)

## 📦 Getting Started

### Prerequisites

- .NET 10 SDK
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL 15+ (or Docker)
- Redis 7+ (or Docker)

### Quick Start (Local Development)

```bash
# Clone repository
git clone <your-repo-url>
cd DHRUVA

# Start databases & services
docker-compose up -d

# (Coming soon)
# Build and run backend
# cd backend
# dotnet build
# dotnet run --project DHRUVA.Web

# Build and run frontend
# cd frontend
# npm install
# npm start
```

Visit:
- **API**: https://localhost:5001/api/v1
- **Swagger UI**: https://localhost:5001/swagger
- **Health**: https://localhost:5001/health/ready
- **Jaeger Tracing**: http://localhost:16686
- **Frontend**: https://localhost:4200

### Database

```bash
# Run migrations
cd backend
dotnet ef database update -s DHRUVA.Web

# Seed initial data
dotnet run --project DHRUVA.Web --seed
```

## 📚 Documentation

- **[DHRUVA_Complete_Plan.md](./DHRUVA_Complete_Plan.md)** - Full architecture, diagrams, data flows
- **[DHRUVA_Phase1_Implementation_Prompt.md](./DHRUVA_Phase1_Implementation_Prompt.md)** - Days 1-6 detailed implementation guide
- **[DHRUVA_Logo_Design_Prompt.md](./DHRUVA_Logo_Design_Prompt.md)** - Logo design concepts and brand guidelines

## 🎯 MVP1 Timeline (22.5 Days)

### Phase 1: Core Infrastructure (Days 1-6)
- Project setup, DI container, logging, tracing
- JWT authentication, Redis caching
- PostgreSQL schema, EF Core, event sourcing
- Execution service (< 30ms orders)
- Broker adapters, token refresh
- Strategy service, backtesting

### Phase 2: Portfolio & Analytics (Days 7-12)
- Holdings management, multi-account support
- Sharpe, Sortino, Calmar calculations
- VaR, concentration, stress testing
- Rebalancing service
- 8+ report types

### Phase 3: Real-Time Communication (Days 13-15)
- SignalR live dashboards
- Email alerts, notifications
- Microsoft Aspire monitoring

### Phase 4: Frontend (Days 16-18)
- Angular SPA with gRPC integration
- Trading, Portfolio, Strategy, Scanner dashboards
- Charts, tables, responsive design
- Dark/light theme, multi-language (English + Hindi)

### Phase 5: Testing & Deployment (Days 19-22.5)
- Integration & E2E tests
- Security hardening
- Docker containerization
- Kubernetes manifests
- Cloud deployment (AWS/Azure)

## 🔐 Security

- JWT Bearer tokens (15-min access, 7-day refresh)
- Encrypted broker credentials (DPAPI)
- Immutable audit trail (append-only)
- Real-time risk checks
- Role-based access control (MVP2+)

## 🚀 Deployment

**Local**: Docker Compose (postgres, redis, rabbitmq, jaeger)  
**Cloud**: Kubernetes (AWS EKS, Azure AKS)  
**CI/CD**: GitHub Actions

## 📞 Support

For issues, feature requests, or questions:
- Open an issue on GitHub
- Check documentation in root folder

## 📄 License

MIT License - See LICENSE file

## 🎓 Learning Resources

- [.NET 10 Documentation](https://learn.microsoft.com/dotnet/)
- [Entity Framework Core](https://docs.microsoft.com/ef/core/)
- [SignalR](https://docs.microsoft.com/aspnet/core/signalr/)
- [Angular](https://angular.io/)
- [OpenTelemetry](https://opentelemetry.io/)

---

**Status**: Phase 1 Planning Complete ✅  
**Next**: Day 1 Implementation (Project Setup)  
**Vision**: Ultra-fast algo trading for Indian markets, professional-grade platform

🚀 Trade with DHRUVA Precision