# DHRUVA: Ultra-Fast Python Algo Trading Platform (OpenAlgo-Based)

**Status**: Master Plan Ready for Implementation  
**Timeline**: 22.5 days (MVP1 production-ready)  
**Stack**: Python 3.12 + FastAPI + Polars + Numba + PostgreSQL + Redis  
**Base**: OpenAlgo architecture, extended for Indian markets (NSE/BSE)  
**Target**: < 30ms order execution, 23+ broker support, professional-grade analytics  

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [OpenAlgo Leverage Strategy](#openalgo-leverage-strategy)
3. [Project Structure](#project-structure)
4. [Technology Stack](#technology-stack)
5. [Phase 1 Detailed Implementation (Days 1-6)](#phase-1-detailed-implementation-days-1-6)
6. [Master Implementation Prompt](#master-implementation-prompt)
7. [Deployment Guide](#deployment-guide)

---

## 🏗️ Architecture Overview

### DHRUVA = OpenAlgo + Indian Market Extensions + Performance Optimization

```
DHRUVA (Python FastAPI Monolith)
│
├─ Core Layer (OpenAlgo-based)
│  ├─ Broker Management (23+ Indian brokers)
│  ├─ Order Management & Execution
│  ├─ Position Tracking (Redis-cached)
│  ├─ Risk Management Engine
│  └─ Data Pipeline (Market data)
│
├─ Analysis Layer (Enhanced)
│  ├─ Technical Indicators (TA-Lib + Numba)
│  ├─ Portfolio Analytics (Sharpe, Sortino, Calmar)
│  ├─ Risk Analytics (VaR, concentration, stress testing)
│  └─ Attribution Analysis (sector, holding, strategy)
│
├─ Strategy Layer
│  ├─ Strategy Execution (1-min candles via APScheduler)
│  ├─ Backtesting Engine (VectorBT)
│  ├─ Paper Trading Simulator
│  └─ Strategy Performance Tracking
│
├─ Scanning Layer
│  ├─ Pre-market Scanner (concept-based)
│  ├─ Pattern Detection (momentum, mean reversion, breakout)
│  ├─ Setup Quality Scoring (0-100)
│  └─ Alert System (email, in-app)
│
├─ Reporting Layer
│  ├─ Strategy Reports (performance, trade journal, comparison)
│  ├─ Portfolio Reports (monthly, quarterly, annual)
│  ├─ Risk Reports (metrics, compliance, tax)
│  └─ Multi-Account Reports (consolidated, comparison)
│
├─ Real-Time Layer
│  ├─ WebSocket Hub (orders, positions, P&L)
│  ├─ SignalR equivalent (Python asyncio + WebSockets)
│  └─ Live dashboards (no polling, push updates)
│
├─ Notification Layer
│  ├─ Email alerts (SMTP)
│  ├─ SMS alerts (Twilio optional)
│  └─ In-app notifications (WebSocket)
│
└─ Infrastructure Layer
   ├─ Authentication (JWT + refresh tokens)
   ├─ Logging (Structured JSON via structlog)
   ├─ Tracing (OpenTelemetry + Jaeger)
   ├─ Caching (Redis for positions, prices, analytics)
   └─ Database (PostgreSQL + TimescaleDB for OHLCV)
```

---

## 🔄 OpenAlgo Leverage Strategy

### What We're Using from OpenAlgo:

```python
✅ OpenAlgo Core Components to Extend:
   ├─ Broker adapter pattern (abstract base class)
   ├─ Order management system (order lifecycle)
   ├─ Position tracking (in-memory + DB persistence)
   ├─ Risk engine (pre-trade checks)
   ├─ Data pipeline (OHLCV ingestion)
   └─ WebSocket communication layer

✅ What We're Keeping:
   ├─ OpenAlgo's FastAPI structure
   ├─ Broker adapter abstraction
   ├─ Order routing logic
   ├─ Database models (Orders, Positions, Trades, Accounts)
   └─ API endpoint patterns

🔄 What We're Extending:
   ├─ Add 23 Indian broker adapters (Zerodha, Upstox, Dhan, etc.)
   ├─ Add technical indicators library (TA-Lib + Numba JIT)
   ├─ Add portfolio analytics (Sharpe, Sortino, Calmar, VaR)
   ├─ Add strategy execution framework (APScheduler)
   ├─ Add backtesting engine (VectorBT integration)
   ├─ Add pre-market scanner (concept-based)
   ├─ Add comprehensive reporting (PDF/Excel generation)
   ├─ Add real-time dashboards (WebSocket-based)
   ├─ Add distributed tracing (OpenTelemetry)
   └─ Add audit trail (event sourcing)

❌ What We're Not Using:
   ├─ Backtrader (too slow for live trading)
   ├─ Limited indicator set
   └─ Single broker support
```

---

## 📁 Project Structure

```
DHRUVA/
├── app/
│   ├── __init__.py
│   ├── main.py                          (FastAPI app entry)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1.py                        (API router)
│   │   ├── routes/
│   │   │   ├── execution.py             (Order placement, cancellation)
│   │   │   ├── positions.py             (Position management)
│   │   │   ├── orders.py                (Order history)
│   │   │   ├── portfolio.py             (Holdings, allocation, snapshots)
│   │   │   ├── analytics.py             (Sharpe, Sortino, Calmar, VaR)
│   │   │   ├── risk.py                  (Risk metrics, concentration)
│   │   │   ├── strategy.py              (Strategy CRUD, execution)
│   │   │   ├── backtest.py              (Backtest API)
│   │   │   ├── scanner.py               (Pre-market scanner, alerts)
│   │   │   ├── reports.py               (Report generation, download)
│   │   │   ├── auth.py                  (Login, refresh token)
│   │   │   └── health.py                (Health checks)
│   │   │
│   │   └── websocket/
│   │       ├── manager.py               (WebSocket connection manager)
│   │       ├── handlers.py              (Message handlers)
│   │       └── events.py                (Real-time event broadcasting)
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                    (Settings, environment variables)
│   │   ├── logging.py                   (Structured logging setup)
│   │   ├── tracing.py                   (OpenTelemetry tracing)
│   │   ├── security.py                  (JWT, encryption)
│   │   └── constants.py                 (Trading constants, thresholds)
│   │
│   ├── brokers/
│   │   ├── __init__.py
│   │   ├── base.py                      (Abstract broker adapter)
│   │   ├── zerodha.py                   (Zerodha adapter)
│   │   ├── upstox.py                    (Upstox adapter)
│   │   ├── dhan.py                      (Dhan adapter)
│   │   ├── fyers.py                     (Fyers adapter)
│   │   ├── 5paisa.py                    (5Paisa adapter)
│   │   ├── broker_factory.py            (Broker creation & routing)
│   │   └── health_monitor.py            (Broker health checks)
│   │
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── order_engine.py              (Order placement < 30ms)
│   │   ├── risk_engine.py               (Pre-trade risk validation)
│   │   ├── position_tracker.py          (Real-time position tracking)
│   │   └── trade_logger.py              (Trade event logging)
│   │
│   ├── indicators/
│   │   ├── __init__.py
│   │   ├── base.py                      (Base indicator class)
│   │   ├── ma.py                        (EMA, SMA, DEMA, TEMA, HMA)
│   │   ├── momentum.py                  (RSI, MACD, Stochastic, KDJ)
│   │   ├── volatility.py                (Bollinger, ATR, StdDev)
│   │   ├── trend.py                     (ADX, Supertrend, SAR)
│   │   ├── volume.py                    (OBV, VWAP, CMF, VP)
│   │   ├── advanced.py                  (Kalman, ALMA, ZigZag)
│   │   └── jit_compiled.py              (Numba JIT-compiled indicators)
│   │
│   ├── portfolio/
│   │   ├── __init__.py
│   │   ├── portfolio_service.py         (Holdings, allocations)
│   │   ├── analytics_service.py         (Sharpe, Sortino, Calmar, drawdown)
│   │   ├── risk_analytics.py            (VaR, Beta, correlation)
│   │   ├── attribution_service.py       (Sector, holding, strategy attribution)
│   │   └── rebalancing_service.py       (Rebalancing plans & execution)
│   │
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── strategy_service.py          (Strategy CRUD, registry)
│   │   ├── strategy_executor.py         (1-min candle execution)
│   │   ├── backtest_engine.py           (VectorBT-based backtesting)
│   │   ├── paper_trader.py              (Paper trading simulation)
│   │   ├── templates/
│   │   │   ├── ema_cross.py             (EMA crossover template)
│   │   │   ├── rsi_mean_reversion.py    (RSI mean reversion)
│   │   │   ├── bollinger_squeeze.py     (Bollinger band squeeze)
│   │   │   ├── macd_divergence.py       (MACD divergence)
│   │   │   └── supertrend_breakout.py   (Supertrend breakout)
│   │   └── performance_tracker.py       (Trade tracking, metrics)
│   │
│   ├── scanner/
│   │   ├── __init__.py
│   │   ├── scanner_service.py           (Concept-based scanning)
│   │   ├── pattern_detector.py          (Momentum, mean reversion, breakout)
│   │   ├── setup_scorer.py              (Quality scoring 0-100)
│   │   └── scheduler.py                 (Pre-market scanning jobs)
│   │
│   ├── reports/
│   │   ├── __init__.py
│   │   ├── report_service.py            (Report generation)
│   │   ├── pdf_generator.py             (PDF reports)
│   │   ├── excel_generator.py           (Excel reports)
│   │   ├── csv_exporter.py              (CSV export)
│   │   └── templates/
│   │       ├── strategy_performance.py
│   │       ├── trade_journal.py
│   │       ├── portfolio_monthly.py
│   │       ├── risk_metrics.py
│   │       └── tax_report.py
│   │
│   ├── notifications/
│   │   ├── __init__.py
│   │   ├── notification_service.py      (Email, SMS, in-app)
│   │   ├── email_sender.py              (SMTP)
│   │   ├── templates/
│   │   │   ├── order_alert.html
│   │   │   ├── risk_alert.html
│   │   │   └── daily_digest.html
│   │   └── scheduler.py                 (Email scheduling)
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   ├── data_service.py              (OHLCV fetching, caching)
│   │   ├── historical_data.py           (Historical data from brokers)
│   │   ├── benchmark_data.py            (NIFTY50, Sensex, indices)
│   │   ├── cache_service.py             (Redis wrapper)
│   │   └── data_ingestion.py            (Real-time data pipeline)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py                      (User model)
│   │   ├── account.py                   (Account model)
│   │   ├── order.py                     (Order model)
│   │   ├── position.py                  (Position model)
│   │   ├── trade.py                     (Trade model)
│   │   ├── strategy.py                  (Strategy model)
│   │   ├── portfolio_snapshot.py        (Daily portfolio snapshot)
│   │   ├── audit_log.py                 (Audit trail)
│   │   └── notification_config.py       (Notification preferences)
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                      (SQLAlchemy base)
│   │   ├── session.py                   (Async session management)
│   │   ├── migrations/                  (Alembic migrations)
│   │   └── seed.py                      (Database seeding)
│   │
│   ├── cache/
│   │   ├── __init__.py
│   │   ├── redis_client.py              (Redis connection pool)
│   │   └── cache_keys.py                (Cache key constants)
│   │
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth_middleware.py           (JWT validation)
│   │   ├── logging_middleware.py        (Request/response logging)
│   │   ├── error_handler.py             (Global error handling)
│   │   └── tracing_middleware.py        (OpenTelemetry integration)
│   │
│   └── utils/
│       ├── __init__.py
│       ├── helpers.py                   (Utility functions)
│       ├── validators.py                (Input validation)
│       ├── formatters.py                (Data formatting)
│       ├── math_helpers.py              (Sharpe, Sortino, Calmar calc)
│       └── timezone.py                  (IST timezone handling)
│
├── backtest/
│   ├── __init__.py
│   ├── vectorbt_engine.py               (VectorBT-based backtesting)
│   ├── portfolio.py                     (Portfolio tracking)
│   └── metrics.py                       (Performance metrics calculation)
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                      (Pytest fixtures)
│   ├── test_execution.py                (Order execution tests)
│   ├── test_indicators.py               (Indicator accuracy tests)
│   ├── test_risk_engine.py              (Risk check tests)
│   ├── test_backtest.py                 (Backtesting tests)
│   ├── test_brokers.py                  (Broker adapter tests)
│   └── test_analytics.py                (Analytics calculation tests)
│
├── config/
│   ├── logging_config.yaml              (Logging configuration)
│   ├── .env.example                     (Environment template)
│   └── docker-compose.yml               (Local dev environment)
│
├── scripts/
│   ├── init_db.py                       (Database initialization)
│   ├── seed_data.py                     (Seed demo data)
│   ├── migrate.py                       (Run migrations)
│   └── health_check.py                  (Health check script)
│
├── requirements.txt                     (Python dependencies)
├── requirements-dev.txt                 (Development dependencies)
├── Dockerfile                           (Docker image)
├── docker-compose.yml                   (Compose file)
├── .gitignore
├── README.md
└── main.py                              (Entry point)
```

---

## 🛠️ Technology Stack

### **Backend Framework**
```python
fastapi==0.104.0              # Async web framework
uvicorn==0.24.0               # ASGI server
uvloop==0.19.0                # 2-4x faster event loop
pydantic==2.5.0               # Data validation (V2: 10x faster)
python-multipart==0.0.6       # File upload support
```

### **Database & Caching**
```python
asyncpg==0.29.0               # PostgreSQL async driver
sqlalchemy==2.0.23            # ORM with async support
alembic==1.12.0               # Database migrations
aioredis==2.0.1               # Redis async client
redis==5.0.0                  # Redis client
```

### **Data Processing**
```python
polars==0.19.0                # 10-50x faster than Pandas
numpy==1.24.0                 # Numerical computing
numba==0.58.0                 # JIT compilation (1000x speedup)
ta-lib==0.4.28                # Technical indicators (C extension)
scipy==1.11.0                 # Scientific computing
```

### **Real-Time & WebSockets**
```python
websockets==12.0              # WebSocket support
python-socketio==5.9.0        # Socket.IO alternative
aiofiles==23.2.1              # Async file handling
```

### **Strategy & Backtesting**
```python
vectorbt==0.25.0              # Vectorized backtesting (10-100x faster)
backtrader==1.9.78            # Alternative backtesting
ccxt==4.0.0                   # Multi-exchange API
yfinance==0.2.32              # Yahoo Finance data
```

### **Logging & Monitoring**
```python
structlog==23.2.0             # Structured logging (JSON)
python-json-logger==2.0.7     # JSON formatter
opentelemetry-api==1.20.0     # Distributed tracing
opentelemetry-sdk==1.20.0
opentelemetry-exporter-jaeger==1.20.0
```

### **Authentication & Security**
```python
python-jose==3.3.0            # JWT handling
passlib==1.7.4                # Password hashing
bcrypt==4.0.1                 # Bcrypt hashing
cryptography==41.0.0          # Encryption
```

### **Email & Notifications**
```python
aiosmtplib==3.0.0             # Async SMTP
jinja2==3.1.2                 # Template rendering
```

### **Task Scheduling**
```python
apscheduler==3.10.4           # Scheduler for 1-min strategies
python-cron==0.4.1            # Cron expressions
```

### **Report Generation**
```python
reportlab==4.0.7              # PDF generation
openpyxl==3.1.0               # Excel generation
python-docx==0.8.11           # Word documents (optional)
```

### **Machine Learning (Optional, MVP2+)**
```python
scikit-learn==1.3.0
xgboost==2.0.0
lightgbm==4.0.0
catboost==1.2.0
```

### **Testing**
```python
pytest==7.4.0
pytest-asyncio==0.21.0
pytest-cov==4.1.0
httpx==0.25.0                 # Async HTTP client for testing
```

---

## 📅 Phase 1 Detailed Implementation (Days 1-6)

### **Day 1: Project Setup + Core Infrastructure + Logging**

**Tasks:**

1. **Project Structure Setup**
   ```bash
   mkdir -p DHRUVA/app/{api/routes,core,brokers,execution,indicators,portfolio,strategy,scanner,reports,notifications,data,models,db,cache,middleware,utils}
   cd DHRUVA
   ```

2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

3. **Initialize Git**
   ```bash
   git init
   git add .
   git commit -m "Initial project structure"
   ```

4. **Create main.py (FastAPI App)**
   ```python
   from fastapi import FastAPI
   from fastapi.middleware.cors import CORSMiddleware
   from app.core.config import settings
   from app.core.logging import setup_logging
   from app.core.tracing import setup_tracing
   from app.api.v1 import router as api_router
   from app.api.websocket.handlers import router as ws_router

   # Setup logging
   setup_logging()

   # Setup tracing
   setup_tracing()

   # Create app
   app = FastAPI(
       title="DHRUVA",
       description="Ultra-fast algo trading platform for Indian markets",
       version="1.0.0"
   )

   # CORS
   app.add_middleware(
       CORSMiddleware,
       allow_origins=settings.CORS_ORIGINS,
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )

   # Include routers
   app.include_router(api_router, prefix="/api/v1", tags=["Trading"])
   app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])

   @app.get("/health/live")
   async def health_live():
       return {"status": "ok"}

   @app.get("/health/ready")
   async def health_ready():
       # Check DB, Redis, Broker connections
       return {"status": "ready"}

   if __name__ == "__main__":
       import uvicorn
       uvicorn.run(
           app,
           host=settings.HOST,
           port=settings.PORT,
           loop="uvloop"  # Fast event loop
       )
   ```

5. **Create Core Config (app/core/config.py)**
   ```python
   from pydantic_settings import BaseSettings
   from typing import List

   class Settings(BaseSettings):
       # App
       APP_NAME: str = "DHRUVA"
       API_V1_STR: str = "/api/v1"
       ENVIRONMENT: str = "development"
       DEBUG: bool = True
       
       # Server
       HOST: str = "0.0.0.0"
       PORT: int = 8000
       
       # Database
       DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/dhruva"
       
       # Redis
       REDIS_URL: str = "redis://localhost:6379"
       
       # JWT
       JWT_SECRET_KEY: str = "your-secret-key-min-32-chars"
       JWT_ALGORITHM: str = "HS256"
       ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
       REFRESH_TOKEN_EXPIRE_DAYS: int = 7
       
       # CORS
       CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:4200"]
       
       # Email
       SMTP_HOST: str = "smtp.gmail.com"
       SMTP_PORT: int = 587
       SMTP_USER: str = ""
       SMTP_PASSWORD: str = ""
       
       # Brokers
       ZERODHA_API_KEY: str = ""
       ZERODHA_API_SECRET: str = ""
       
       class Config:
           env_file = ".env"

   settings = Settings()
   ```

6. **Setup Structured Logging (app/core/logging.py)**
   ```python
   import structlog
   import logging
   from pythonjsonlogger import jsonlogger

   def setup_logging():
       """Configure structured JSON logging"""
       
       # Console handler with JSON formatter
       console_handler = logging.StreamHandler()
       formatter = jsonlogger.JsonFormatter()
       console_handler.setFormatter(formatter)
       
       # Root logger
       root_logger = logging.getLogger()
       root_logger.addHandler(console_handler)
       root_logger.setLevel(logging.INFO)
       
       # Structlog config
       structlog.configure(
           processors=[
               structlog.stdlib.filter_by_level,
               structlog.stdlib.add_logger_name,
               structlog.stdlib.add_log_level,
               structlog.stdlib.PositionalArgumentsFormatter(),
               structlog.processors.TimeStamper(fmt="iso"),
               structlog.processors.StackInfoRenderer(),
               structlog.processors.format_exc_info,
               structlog.processors.UnicodeDecoder(),
               structlog.processors.JSONRenderer()
           ],
           context_class=dict,
           logger_factory=structlog.stdlib.LoggerFactory(),
           cache_logger_on_first_use=True,
       )
   ```

7. **Setup OpenTelemetry Tracing (app/core/tracing.py)**
   ```python
   from opentelemetry import trace, metrics
   from opentelemetry.sdk.trace import TracerProvider
   from opentelemetry.sdk.trace.export import BatchSpanProcessor
   from opentelemetry.exporter.jaeger.thrift import JaegerExporter
   from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
   from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
   from opentelemetry.instrumentation.redis import RedisInstrumentor

   def setup_tracing():
       """Configure OpenTelemetry distributed tracing"""
       
       jaeger_exporter = JaegerExporter(
           agent_host_name="localhost",
           agent_port=6831,
       )
       
       trace.set_tracer_provider(TracerProvider())
       trace.get_tracer_provider().add_span_processor(
           BatchSpanProcessor(jaeger_exporter)
       )
       
       # Instrument libraries
       FastAPIInstrumentor().instrument()
       SQLAlchemyInstrumentor().instrument()
       RedisInstrumentor().instrument()
   ```

8. **Create docker-compose.yml**
   ```yaml
   version: '3.8'
   services:
     postgres:
       image: timescale/timescaledb:latest-pg15
       environment:
         POSTGRES_USER: postgres
         POSTGRES_PASSWORD: postgres
         POSTGRES_DB: dhruva
       ports:
         - "5432:5432"
       volumes:
         - postgres_data:/var/lib/postgresql/data

     redis:
       image: redis:7-alpine
       ports:
         - "6379:6379"

     jaeger:
       image: jaegertracing/all-in-one:latest
       ports:
         - "16686:16686"
         - "6831:6831/udp"

   volumes:
     postgres_data:
   ```

9. **Initial Commit**
   ```bash
   git add -A
   git commit -m "Day 1: Project setup, logging, tracing infrastructure"
   ```

**Deliverable:** FastAPI app running, structured logging working, tracing connected to Jaeger

---

### **Day 2: Authentication + Redis Caching + Background Jobs**

**Tasks:**

1. **JWT Authentication (app/core/security.py)**
   - Login endpoint
   - Token generation (access + refresh)
   - Password hashing (bcrypt)

2. **Redis Cache Service (app/cache/redis_client.py)**
   - Cache position: `position:{account_id}:{symbol}` (1-sec TTL)
   - Cache price: `price:{symbol}` (5-sec TTL)
   - Cache holdings: `holdings:{account_id}` (1-min TTL)

3. **Background Job Scheduler (APScheduler)**
   - Strategy execution every 1 minute
   - Daily portfolio snapshot at 3:30 PM
   - Token refresh at 8:55 AM

4. **Database Session Management (app/db/session.py)**
   - Async session factory
   - Connection pooling

**Deliverable:** Login working, Redis caching active, scheduled jobs running

---

### **Day 3: Database Schema + EF Core Models + Event Sourcing**

**Tasks:**

1. **SQLAlchemy Models (app/models/)**
   - User, Account, Strategy, Position, Trade, Order
   - PortfolioSnapshot, AuditLog, RefreshToken

2. **Migrations (Alembic)**
   - Create initial schema
   - Run migrations

3. **Event Sourcing (app/models/audit_log.py)**
   - OrderPlacedEvent, TradeExecutedEvent, PositionUpdatedEvent

**Deliverable:** Database initialized, models created, migrations working

---

### **Day 4: Execution Service + Risk Engine + < 30ms Order Placement**

**Tasks:**

1. **Order Execution Engine (app/execution/order_engine.py)**
   ```python
   @app.post("/api/v1/execution/orders")
   async def place_order(request: PlaceOrderRequest) -> PlaceOrderResponse:
       # Risk validation (2-5ms)
       risk_check = await risk_engine.validate_order(request)
       if not risk_check.passed:
           return PlaceOrderResponse(status="REJECTED", reason=risk_check.reason)
       
       # Position update in Redis (1-2ms)
       await position_tracker.update_position(request)
       
       # Broker API call (15-25ms)
       broker_response = await broker.place_order(request)
       
       # Database insert (asyncpg, 1-2ms)
       trade = await db.save_trade(broker_response)
       
       # Broadcast via WebSocket (< 1ms)
       await ws_manager.broadcast_order(trade)
       
       # Audit log (< 1ms)
       await audit_service.log_order(request, trade)
       
       return PlaceOrderResponse(status="SUCCESS", order_id=trade.id)
   ```

2. **Risk Engine (app/execution/risk_engine.py)**
   - Margin check
   - Concentration check
   - Exposure check
   - Daily loss limit

3. **Position Tracker (app/execution/position_tracker.py)**
   - Redis-backed real-time positions
   - P&L calculation
   - Portfolio aggregation

**Deliverable:** < 30ms order execution verified

---

### **Day 5: Broker Adapters + Token Refresh**

**Tasks:**

1. **Abstract Broker Adapter (app/brokers/base.py)**
   ```python
   class BrokerAdapter(ABC):
       async def authenticate(self, credentials): pass
       async def place_order(self, order): pass
       async def get_positions(self): pass
       async def refresh_token(self): pass
   ```

2. **Broker Implementations**
   - Zerodha adapter
   - Upstox adapter
   - Dhan adapter
   - Fyers adapter
   - 5Paisa adapter

3. **Start-of-Day Token Refresh (8:55 AM)**
   - Refresh all broker tokens
   - Check connectivity
   - Alert if failures

**Deliverable:** Multi-broker support working

---

### **Day 6: Strategy Service + Backtesting + Templates**

**Tasks:**

1. **Strategy Service (app/strategy/strategy_service.py)**
   - CRUD operations
   - Enable/disable strategies
   - Execute strategies every 1 minute

2. **Strategy Templates**
   - EMA Cross
   - RSI Mean Reversion
   - Bollinger Squeeze
   - MACD Divergence
   - Supertrend Breakout

3. **Backtesting Engine (app/backtest/vectorbt_engine.py)**
   - VectorBT integration
   - Fast backtests (< 500ms for 1000 trades)

4. **Paper Trading (app/strategy/paper_trader.py)**
   - Simulate trades without real money

**Deliverable:** Strategy execution, backtesting, templates working

---

## 📝 Master Implementation Prompt

See next section: **Master Implementation Prompt for DHRUVA (Python + OpenAlgo)**

---

## 🚀 Deployment Guide

### **Local Development**

```bash
# 1. Clone repo
git clone <repo-url>
cd DHRUVA

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start services
docker-compose up -d

# 5. Initialize database
python scripts/init_db.py

# 6. Run app
python main.py

# 7. Visit
# API: http://localhost:8000
# Swagger: http://localhost:8000/docs
# Jaeger: http://localhost:16686
```

### **Docker Production**

```bash
docker build -t dhruva:latest .
docker run -d -p 8000:8000 \
  -e DATABASE_URL=postgresql://... \
  -e REDIS_URL=redis://... \
  dhruva:latest
```

### **Kubernetes**

```bash
kubectl create namespace dhruva
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

---

## 📊 Expected Performance

| Operation | Target | Expected | Notes |
|-----------|--------|----------|-------|
| Order placement | < 30ms | 22-38ms | Broker latency dominates |
| Risk check | < 5ms | 2-5ms | NumPy vectorized |
| Position update | < 2ms | 1-2ms | Redis cached |
| Backtest (1000 trades) | < 500ms | 100-300ms | VectorBT vectorized |
| Dashboard update | < 100ms | 50-100ms | WebSocket push |

---

## 🎯 MVP1 Completion Checklist

- ✅ Days 1-6: Core infrastructure + execution + brokers + strategies
- ✅ Days 7-12: Portfolio + analytics + risk + rebalancing + reports
- ✅ Days 13-15: Real-time dashboards + alerts + monitoring
- ✅ Days 16-18: Frontend (Angular) with gRPC integration
- ✅ Days 19-22.5: Testing + security + Docker + Kubernetes + docs

---

## 📋 Next: Master Implementation Prompt

See the next document: **DHRUVA_Master_Implementation_Prompt.md**

---

**Status**: Plan Complete ✅  
**Stack**: Python 3.12 + FastAPI + Polars + Numba + PostgreSQL + Redis  
**Base**: OpenAlgo architecture extended for Indian markets  
**Timeline**: 22.5 days to production MVP1

🚀 Ready to implement!
