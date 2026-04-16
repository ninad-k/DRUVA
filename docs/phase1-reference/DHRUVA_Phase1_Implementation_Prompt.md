# DHRUVA Phase 1 Implementation Prompt (Days 1-6)

## Executive Summary

Build Phase 1 (Core Infrastructure) of DHRUVA—an ultra-fast algo trading platform for Indian markets (NSE/BSE). This prompt covers Days 1-6 of the 22.5-day MVP1 timeline. Deliver a modular monolith (.NET 10 + ASP.NET Core) with:

- **Ultra-fast execution**: < 30ms order placement with real-time risk checks
- **Multi-broker support**: Zerodha, Upstox, Dhan, Fyers, 5Paisa (extensible to 23+)
- **Enterprise logging**: Serilog JSON logs to PostgreSQL + console
- **Distributed tracing**: OpenTelemetry spans for order flow troubleshooting
- **Real-time caching**: Redis for positions (< 1-sec latency)
- **Production-grade security**: JWT authentication, encrypted broker credentials
- **Modular architecture**: 13 projects (1 host, 9 services, 4 shared), DI-injected, migratable to gRPC/microservices

---

## Architecture Overview

### Modular Monolith Design

**Single Process**: One ASP.NET Core 10 process (port 5000) hosts all services.

```
DHRUVA.sln
├── DHRUVA.Web (ASP.NET Core 10 Host)
│   ├── Controllers/ (REST API endpoints)
│   ├── Hubs/ (SignalR hubs)
│   ├── Middleware/ (auth, logging, error handling)
│   └── wwwroot/ (Angular SPA static files)
│
├── Service Projects (9)
│   ├── DHRUVA.Execution (Order engine, risk checks, position tracking)
│   ├── DHRUVA.Portfolio (Holdings, analytics, snapshots)
│   ├── DHRUVA.Strategy (Strategy registry, execution, backtesting)
│   ├── DHRUVA.Scanner (Pre-market scanning, pattern detection)
│   ├── DHRUVA.Data (Market data pipeline, OHLCV, caching)
│   ├── DHRUVA.Broker (23+ broker adapters, token refresh)
│   ├── DHRUVA.Notification (Email, SMS, in-app alerts)
│   ├── DHRUVA.Reports (PDF, Excel, CSV generation)
│   └── DHRUVA.Audit (Audit logging, event sourcing)
│
├── Shared Projects (4)
│   ├── DHRUVA.Core (Models, interfaces, enums, constants)
│   ├── DHRUVA.Infrastructure (Logging, caching, DB, health checks)
│   ├── DHRUVA.Auth (JWT, token management, user lookup)
│   └── DHRUVA.Common (Utilities, extensions, helpers)
│
└── Data Layer
    ├── PostgreSQL (Users, Accounts, Strategies, Orders, Positions, Trades, etc.)
    └── TimescaleDB hypertables (OHLCV, Order_Events, Trade_Events, P&L_Snapshots)
```

### Service Interaction Pattern (Direct DI)

```csharp
// Program.cs
services.AddScoped<IExecutionService, ExecutionService>();
services.AddScoped<IPortfolioService, PortfolioService>();
// ... all services registered

// Controller (direct method call, no HTTP/RPC)
var result = await _executionService.PlaceOrder(request);
```

---

## Phase 1 Detailed Requirements (Days 1-6)

### Day 1: Project Setup + Logging Infrastructure + DI Container

#### 1.1 Solution Structure

Create 13 .NET 10 projects with these specifications:

**Host Project:**
- `DHRUVA.Web`: ASP.NET Core 10 web application
  - Target: .NET 10
  - Language: C# 13
  - Nullable: Enable
  - Implicit usings: Enable
  - Output type: Exe (produces executable)

**Service Projects (9, all Class Libraries):**
```
DHRUVA.Execution.csproj
DHRUVA.Portfolio.csproj
DHRUVA.Strategy.csproj
DHRUVA.Scanner.csproj
DHRUVA.Data.csproj
DHRUVA.Broker.csproj
DHRUVA.Notification.csproj
DHRUVA.Reports.csproj
DHRUVA.Audit.csproj
```

**Shared Projects (4, all Class Libraries):**
```
DHRUVA.Core.csproj          (Models, Interfaces, Enums, Constants)
DHRUVA.Infrastructure.csproj (Logging, Caching, DB, Health Checks)
DHRUVA.Auth.csproj          (JWT, Token Management)
DHRUVA.Common.csproj        (Utilities, Extensions, Helpers)
```

**Project Dependencies:**
- All service projects → reference DHRUVA.Core, DHRUVA.Infrastructure, DHRUVA.Common
- DHRUVA.Web → references all 9 service projects + 4 shared projects
- Shared projects have minimal cross-dependencies (DHRUVA.Infrastructure → DHRUVA.Core)

#### 1.2 NuGet Packages (to install in relevant projects)

**DHRUVA.Web:**
```
Microsoft.AspNetCore.OpenApi
Microsoft.AspNetCore.SignalR
Serilog.AspNetCore
OpenTelemetry.Exporter.InMemory
OpenTelemetry.Exporter.Jaeger
```

**DHRUVA.Infrastructure:**
```
Serilog
Serilog.Sinks.PostgreSQL
Serilog.Formatting.Json
OpenTelemetry
OpenTelemetry.Exporter.Jaeger
StackExchange.Redis
```

**DHRUVA.Core + Others:**
```
(No external dependencies—use .NET only)
```

**All projects:**
```
(Target: .NET 10, no version-specific packages needed)
```

#### 1.3 Program.cs Setup (DHRUVA.Web)

```csharp
using Serilog;
using OpenTelemetry;
using OpenTelemetry.Trace;

var builder = WebApplicationBuilder.CreateBuilder(args);

// Logging: Serilog + OpenTelemetry
Log.Logger = new LoggerConfiguration()
    .MinimumLevel.Information()
    .WriteTo.Console(new CompactJsonFormatter())
    .WriteTo.PostgreSQL(
        builder.Configuration.GetConnectionString("DefaultConnection"),
        "logs",
        columnOptions: new Dictionary<string, ColumnWriterBase>
        {
            ["message_template"] = new MessageTemplateColumnWriter(),
            ["level"] = new LevelColumnWriter(),
            ["raise_date"] = new TimestampColumnWriter(),
            ["exception"] = new ExceptionColumnWriter(),
            ["log_event"] = new LogEventSerializerColumnWriter(),
            ["trace_id"] = new TraceIdColumnWriter()
        })
    .Enrich.FromLogContext()
    .Enrich.WithProperty("Service", "DHRUVA")
    .CreateLogger();

builder.Host.UseSerilog();

// Add services to container
builder.Services.AddControllers();
builder.Services.AddSignalR();

// Authentication (JWT)
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ValidateIssuerSigningKey = true,
            ValidIssuer = builder.Configuration["Jwt:Issuer"],
            ValidAudience = builder.Configuration["Jwt:Audience"],
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(builder.Configuration["Jwt:SecretKey"]))
        };
    });

builder.Services.AddAuthorization();

// Distributed Tracing: OpenTelemetry
builder.Services.AddOpenTelemetry()
    .WithTracing(tracerProviderBuilder =>
        tracerProviderBuilder
            .AddAspNetCoreInstrumentation()
            .AddHttpClientInstrumentation()
            .AddSqlClientInstrumentation()
            .AddRedisInstrumentation()
            .AddInMemoryExporter()
            .AddJaegerExporter(options =>
            {
                options.Endpoint = new Uri(builder.Configuration["Jaeger:Endpoint"] ?? "http://localhost:14268/api/traces");
            }));

// DI: Core Services
builder.Services.AddScoped<IExecutionService, ExecutionService>();
builder.Services.AddScoped<IPortfolioService, PortfolioService>();
builder.Services.AddScoped<IStrategyService, StrategyService>();
builder.Services.AddScoped<IScannerService, ScannerService>();
builder.Services.AddScoped<IDataService, DataService>();
builder.Services.AddScoped<IBrokerFactory, BrokerFactory>();
builder.Services.AddScoped<INotificationService, NotificationService>();
builder.Services.AddScoped<IReportService, ReportService>();
builder.Services.AddScoped<IAuditService, AuditService>();

// DI: Infrastructure
builder.Services.AddScoped<ICacheService, RedisCacheService>();
builder.Services.AddScoped<IAuthService, AuthService>();
builder.Services.AddScoped<ITokenService, TokenService>();
builder.Services.AddScoped<IPasswordService, PasswordService>();
builder.Services.AddScoped<IEncryptionService, EncryptionService>();

// Database
builder.Services.AddDbContext<DhruvaDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("DefaultConnection")));

// Redis Cache
builder.Services.AddStackExchangeRedisCache(options =>
{
    options.Configuration = builder.Configuration.GetConnectionString("Redis");
});

// Health Checks
builder.Services.AddHealthChecks()
    .AddDbContextCheck<DhruvaDbContext>()
    .AddRedis(builder.Configuration.GetConnectionString("Redis"));

var app = builder.Build();

// Middleware
app.UseRouting();
app.UseAuthentication();
app.UseAuthorization();

// Error handling middleware
app.UseExceptionHandler("/api/v1/errors");
app.UseStatusCodePages();

// Logging middleware
app.UseSerilogRequestLogging();

// Map endpoints
app.MapControllers();
app.MapHealthChecks("/health/live");
app.MapHealthChecks("/health/ready");
app.MapHub<TradingHub>("/hubs/trading");
// ... other hubs

// Serve Angular SPA
app.UseDefaultFiles();
app.UseStaticFiles();
app.MapFallbackToFile("index.html");

app.Run();
```

#### 1.4 Configuration: appsettings.json

```json
{
  "Logging": {
    "LogLevel": {
      "Default": "Information",
      "Microsoft": "Warning"
    }
  },
  "ConnectionStrings": {
    "DefaultConnection": "Host=localhost;Port=5432;Database=dhruva;Username=postgres;Password=postgres",
    "Redis": "localhost:6379"
  },
  "Jwt": {
    "Issuer": "dhruva.local",
    "Audience": "dhruva-users",
    "SecretKey": "your-secret-key-min-32-chars-long",
    "TokenExpiration": 900,
    "RefreshTokenExpiration": 604800
  },
  "Jaeger": {
    "Endpoint": "http://localhost:14268/api/traces"
  },
  "Features": {
    "TradingEnabled": true,
    "StrategyExecutionEnabled": true
  }
}
```

#### 1.5 docker-compose.yml (Local Development)

```yaml
version: '3.8'

services:
  postgres:
    image: timescale/timescaledb:latest-pg15
    container_name: dhruva-postgres
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: dhruva
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: dhruva-redis
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  rabbitmq:
    image: rabbitmq:3-management-alpine
    container_name: dhruva-rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: guest
      RABBITMQ_DEFAULT_PASS: guest
    ports:
      - "5672:5672"
      - "15672:15672"
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  jaeger:
    image: jaegertracing/all-in-one:latest
    container_name: dhruva-jaeger
    ports:
      - "16686:16686"
      - "14268:14268"
    environment:
      COLLECTOR_OTLP_ENABLED: "true"

volumes:
  postgres_data:

networks:
  default:
    name: dhruva-network
```

#### 1.6 Structured Logging Setup (DHRUVA.Infrastructure)

**File: `Services/LoggingService.cs`**

```csharp
using Serilog;
using Serilog.Formatting.Json;
using Serilog.Sinks.PostgreSQL;

namespace DHRUVA.Infrastructure.Services;

public interface ILoggingService
{
    void ConfigureLogging(IWebHostBuilder webHostBuilder);
}

public class LoggingService : ILoggingService
{
    public void ConfigureLogging(IWebHostBuilder webHostBuilder)
    {
        webHostBuilder.UseSerilog((context, services, config) =>
        {
            var connectionString = context.Configuration.GetConnectionString("DefaultConnection");
            
            config
                .MinimumLevel.Information()
                .WriteTo.Console(new CompactJsonFormatter())
                .WriteTo.PostgreSQL(
                    connectionString,
                    "logs",
                    columnOptions: new Dictionary<string, ColumnWriterBase>
                    {
                        ["message_template"] = new MessageTemplateColumnWriter(),
                        ["level"] = new LevelColumnWriter(),
                        ["raise_date"] = new TimestampColumnWriter(),
                        ["exception"] = new ExceptionColumnWriter(),
                        ["log_event"] = new LogEventSerializerColumnWriter(),
                        ["trace_id"] = new TraceIdColumnWriter(),
                        ["user_id"] = new CustomColumnWriter("user_id"),
                        ["account_id"] = new CustomColumnWriter("account_id"),
                        ["correlation_id"] = new CustomColumnWriter("correlation_id")
                    })
                .Enrich.FromLogContext()
                .Enrich.WithProperty("Service", "DHRUVA")
                .Enrich.When(logEvent => 
                    Activity.Current?.Id != null, 
                    (logEvent, lc) => lc.WithProperty("trace_id", Activity.Current.Id));
        });
    }
}
```

#### 1.7 Distributed Tracing Setup (DHRUVA.Infrastructure)

**File: `Services/TracingService.cs`**

```csharp
using OpenTelemetry;
using OpenTelemetry.Trace;

namespace DHRUVA.Infrastructure.Services;

public interface ITracingService
{
    IDisposable StartSpan(string spanName, Dictionary<string, object>? attributes = null);
    void RecordEvent(string eventName, Dictionary<string, object>? attributes = null);
    void AddAttribute(string key, object value);
}

public class TracingService : ITracingService
{
    private readonly ActivitySource _activitySource;

    public TracingService()
    {
        _activitySource = new ActivitySource("DHRUVA.Trading");
    }

    public IDisposable StartSpan(string spanName, Dictionary<string, object>? attributes = null)
    {
        var activity = _activitySource.StartActivity(spanName);
        if (activity != null && attributes != null)
        {
            foreach (var attr in attributes)
            {
                activity.SetTag(attr.Key, attr.Value);
            }
        }
        return activity ?? NullDisposable.Instance;
    }

    public void RecordEvent(string eventName, Dictionary<string, object>? attributes = null)
    {
        var activity = Activity.Current;
        if (activity != null)
        {
            activity.AddEvent(new ActivityEvent(eventName, tags: new ActivityTagsCollection(attributes ?? new())));
        }
    }

    public void AddAttribute(string key, object value)
    {
        var activity = Activity.Current;
        if (activity != null)
        {
            activity.SetTag(key, value);
        }
    }
}

internal class NullDisposable : IDisposable
{
    public static NullDisposable Instance { get; } = new();
    public void Dispose() { }
}
```

#### 1.8 Health Checks (DHRUVA.Infrastructure)

**File: `HealthChecks/PostgreSqlHealthCheck.cs`**

```csharp
using Microsoft.Extensions.Diagnostics.HealthChecks;

namespace DHRUVA.Infrastructure.HealthChecks;

public class PostgreSqlHealthCheck : IHealthCheck
{
    private readonly DhruvaDbContext _dbContext;

    public PostgreSqlHealthCheck(DhruvaDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken cancellationToken = default)
    {
        try
        {
            await _dbContext.Database.ExecuteSqlAsync(new FormattableStringFactory.Sql("SELECT 1"), cancellationToken);
            return HealthCheckResult.Healthy("PostgreSQL connection is healthy");
        }
        catch (Exception ex)
        {
            return HealthCheckResult.Unhealthy("PostgreSQL connection failed", ex);
        }
    }
}
```

---

### Day 2: Authentication + Cache Infrastructure + Redis Setup

#### 2.1 JWT Authentication (DHRUVA.Auth)

**File: `Services/AuthService.cs`**

```csharp
namespace DHRUVA.Auth.Services;

public interface IAuthService
{
    Task<LoginResponse> LoginAsync(string email, string password);
    Task<RefreshTokenResponse> RefreshTokenAsync(string refreshToken);
    Task LogoutAsync(string userId);
    Task<CurrentUserResponse> GetCurrentUserAsync(string userId);
}

public class AuthService : IAuthService
{
    private readonly ITokenService _tokenService;
    private readonly IPasswordService _passwordService;
    private readonly IUserRepository _userRepository;
    private readonly IRefreshTokenRepository _refreshTokenRepository;
    private readonly ILogger<AuthService> _logger;

    public AuthService(
        ITokenService tokenService,
        IPasswordService passwordService,
        IUserRepository userRepository,
        IRefreshTokenRepository refreshTokenRepository,
        ILogger<AuthService> logger)
    {
        _tokenService = tokenService;
        _passwordService = passwordService;
        _userRepository = userRepository;
        _refreshTokenRepository = refreshTokenRepository;
        _logger = logger;
    }

    public async Task<LoginResponse> LoginAsync(string email, string password)
    {
        var user = await _userRepository.GetByEmailAsync(email);
        if (user == null || !_passwordService.VerifyPassword(password, user.PasswordHash))
        {
            _logger.LogWarning("Login failed for email: {Email}", email);
            throw new UnauthorizedAccessException("Invalid credentials");
        }

        var (accessToken, refreshToken) = await _tokenService.GenerateTokensAsync(user.Id);
        
        // Store refresh token in DB
        var refreshTokenEntity = new RefreshToken
        {
            UserId = user.Id,
            Token = refreshToken,
            ExpiresAt = DateTime.UtcNow.AddDays(7),
            CreatedAt = DateTime.UtcNow,
            IsRevoked = false
        };
        
        await _refreshTokenRepository.AddAsync(refreshTokenEntity);

        _logger.LogInformation("User logged in: {UserId}", user.Id);

        return new LoginResponse
        {
            AccessToken = accessToken,
            RefreshToken = refreshToken,
            ExpiresIn = 900,
            TokenType = "Bearer"
        };
    }

    public async Task<RefreshTokenResponse> RefreshTokenAsync(string refreshToken)
    {
        var tokenEntity = await _refreshTokenRepository.GetByTokenAsync(refreshToken);
        if (tokenEntity == null || tokenEntity.IsRevoked || tokenEntity.ExpiresAt < DateTime.UtcNow)
        {
            _logger.LogWarning("Invalid refresh token");
            throw new UnauthorizedAccessException("Invalid refresh token");
        }

        var (newAccessToken, newRefreshToken) = await _tokenService.GenerateTokensAsync(tokenEntity.UserId);
        
        // Revoke old token and store new one
        tokenEntity.IsRevoked = true;
        await _refreshTokenRepository.UpdateAsync(tokenEntity);

        var newRefreshTokenEntity = new RefreshToken
        {
            UserId = tokenEntity.UserId,
            Token = newRefreshToken,
            ExpiresAt = DateTime.UtcNow.AddDays(7),
            CreatedAt = DateTime.UtcNow,
            IsRevoked = false
        };

        await _refreshTokenRepository.AddAsync(newRefreshTokenEntity);

        return new RefreshTokenResponse
        {
            AccessToken = newAccessToken,
            RefreshToken = newRefreshToken,
            ExpiresIn = 900,
            TokenType = "Bearer"
        };
    }

    public async Task LogoutAsync(string userId)
    {
        var tokens = await _refreshTokenRepository.GetByUserIdAsync(userId);
        foreach (var token in tokens)
        {
            token.IsRevoked = true;
            await _refreshTokenRepository.UpdateAsync(token);
        }
        
        _logger.LogInformation("User logged out: {UserId}", userId);
    }

    public async Task<CurrentUserResponse> GetCurrentUserAsync(string userId)
    {
        var user = await _userRepository.GetByIdAsync(userId);
        if (user == null)
        {
            throw new ArgumentException("User not found");
        }

        return new CurrentUserResponse
        {
            Id = user.Id,
            Email = user.Email,
            DisplayName = user.DisplayName,
            CreatedAt = user.CreatedAt
        };
    }
}
```

**File: `Services/TokenService.cs`**

```csharp
namespace DHRUVA.Auth.Services;

public interface ITokenService
{
    Task<(string AccessToken, string RefreshToken)> GenerateTokensAsync(string userId);
    string ValidateToken(string token);
}

public class TokenService : ITokenService
{
    private readonly IConfiguration _configuration;
    private readonly ILogger<TokenService> _logger;

    public TokenService(IConfiguration configuration, ILogger<TokenService> logger)
    {
        _configuration = configuration;
        _logger = logger;
    }

    public async Task<(string AccessToken, string RefreshToken)> GenerateTokensAsync(string userId)
    {
        var secretKey = _configuration["Jwt:SecretKey"];
        var issuer = _configuration["Jwt:Issuer"];
        var audience = _configuration["Jwt:Audience"];
        var tokenExpirationMinutes = int.Parse(_configuration["Jwt:TokenExpiration"] ?? "15");
        
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secretKey));
        var credentials = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

        // Access Token (15 minutes)
        var accessTokenDescriptor = new SecurityTokenDescriptor
        {
            Subject = new ClaimsIdentity(new[]
            {
                new Claim(ClaimTypes.NameIdentifier, userId),
                new Claim("sub", userId),
                new Claim("iss", issuer),
                new Claim("aud", audience)
            }),
            Expires = DateTime.UtcNow.AddMinutes(tokenExpirationMinutes),
            Issuer = issuer,
            Audience = audience,
            SigningCredentials = credentials
        };

        var tokenHandler = new JwtSecurityTokenHandler();
        var accessToken = tokenHandler.CreateToken(accessTokenDescriptor);
        var accessTokenString = tokenHandler.WriteToken(accessToken);

        // Refresh Token (7 days, just a random string)
        var refreshToken = Convert.ToBase64String(RandomNumberGenerator.GetBytes(64));

        _logger.LogInformation("Tokens generated for user: {UserId}", userId);

        return (accessTokenString, refreshToken);
    }

    public string ValidateToken(string token)
    {
        var secretKey = _configuration["Jwt:SecretKey"];
        var issuer = _configuration["Jwt:Issuer"];
        var audience = _configuration["Jwt:Audience"];

        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secretKey));
        var tokenHandler = new JwtSecurityTokenHandler();

        try
        {
            var principal = tokenHandler.ValidateToken(token, new TokenValidationParameters
            {
                ValidateIssuerSigningKey = true,
                IssuerSigningKey = key,
                ValidateIssuer = true,
                ValidIssuer = issuer,
                ValidateAudience = true,
                ValidAudience = audience,
                ValidateLifetime = true,
                ClockSkew = TimeSpan.Zero
            }, out SecurityToken validatedToken);

            var userId = principal.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            return userId ?? throw new SecurityTokenException("User ID not found in token");
        }
        catch (Exception ex)
        {
            _logger.LogWarning("Token validation failed: {Message}", ex.Message);
            throw new SecurityTokenException("Invalid token", ex);
        }
    }
}
```

**File: `Services/PasswordService.cs`**

```csharp
namespace DHRUVA.Auth.Services;

public interface IPasswordService
{
    string HashPassword(string password);
    bool VerifyPassword(string password, string hash);
}

public class PasswordService : IPasswordService
{
    public string HashPassword(string password)
    {
        return BCrypt.Net.BCrypt.HashPassword(password, workFactor: 12);
    }

    public bool VerifyPassword(string password, string hash)
    {
        try
        {
            return BCrypt.Net.BCrypt.Verify(password, hash);
        }
        catch
        {
            return false;
        }
    }
}
```

#### 2.2 Redis Cache Service (DHRUVA.Infrastructure)

**File: `Services/RedisCacheService.cs`**

```csharp
using StackExchange.Redis;
using System.Text.Json;

namespace DHRUVA.Infrastructure.Services;

public interface ICacheService
{
    Task<T?> GetAsync<T>(string key) where T : class;
    Task SetAsync<T>(string key, T value, TimeSpan? ttl = null) where T : class;
    Task DeleteAsync(string key);
    Task<T> GetOrSetAsync<T>(string key, Func<Task<T>> factory, TimeSpan? ttl = null) where T : class;
    Task InvalidateAsync(string pattern);
}

public class RedisCacheService : ICacheService
{
    private readonly IConnectionMultiplexer _redis;
    private readonly ILogger<RedisCacheService> _logger;

    public RedisCacheService(IConnectionMultiplexer redis, ILogger<RedisCacheService> logger)
    {
        _redis = redis;
        _logger = logger;
    }

    public async Task<T?> GetAsync<T>(string key) where T : class
    {
        try
        {
            var db = _redis.GetDatabase();
            var value = await db.StringGetAsync(key);
            
            if (value.IsNullOrEmpty)
            {
                _logger.LogDebug("Cache miss for key: {Key}", key);
                return null;
            }

            var deserialized = JsonSerializer.Deserialize<T>(value.ToString());
            _logger.LogDebug("Cache hit for key: {Key}", key);
            return deserialized;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Error retrieving cache key: {Key}", key);
            return null; // Graceful fallback
        }
    }

    public async Task SetAsync<T>(string key, T value, TimeSpan? ttl = null) where T : class
    {
        try
        {
            var db = _redis.GetDatabase();
            var serialized = JsonSerializer.Serialize(value);
            await db.StringSetAsync(key, serialized, ttl);
            _logger.LogDebug("Cache set for key: {Key} with TTL: {TTL}", key, ttl);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Error setting cache key: {Key}", key);
        }
    }

    public async Task DeleteAsync(string key)
    {
        try
        {
            var db = _redis.GetDatabase();
            await db.KeyDeleteAsync(key);
            _logger.LogDebug("Cache deleted for key: {Key}", key);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Error deleting cache key: {Key}", key);
        }
    }

    public async Task<T> GetOrSetAsync<T>(string key, Func<Task<T>> factory, TimeSpan? ttl = null) where T : class
    {
        var cached = await GetAsync<T>(key);
        if (cached != null)
        {
            return cached;
        }

        var value = await factory();
        await SetAsync(key, value, ttl);
        return value;
    }

    public async Task InvalidateAsync(string pattern)
    {
        try
        {
            var server = _redis.GetServer(_redis.GetEndPoints().FirstOrDefault() ?? throw new InvalidOperationException("No Redis endpoints"));
            var keys = server.Keys(pattern: pattern);
            var db = _redis.GetDatabase();
            
            foreach (var key in keys)
            {
                await db.KeyDeleteAsync(key);
            }
            
            _logger.LogInformation("Cache invalidated for pattern: {Pattern}, deleted {Count} keys", pattern, keys.Count());
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Error invalidating cache pattern: {Pattern}", pattern);
        }
    }
}
```

#### 2.3 Cache Keys Design

Define cache keys as constants in DHRUVA.Common:

**File: `Constants/CacheKeys.cs`**

```csharp
namespace DHRUVA.Common.Constants;

public static class CacheKeys
{
    // Format: service:entity:id:variation
    
    // Positions (1-sec TTL)
    public static string Position(string accountId, string symbol) => $"position:{accountId}:{symbol}";
    public static string PositionPattern(string accountId) => $"position:{accountId}:*";

    // Prices (5-sec TTL)
    public static string Price(string symbol) => $"price:{symbol}";
    public static string PricePattern() => $"price:*";

    // Holdings (1-min TTL)
    public static string Holdings(string accountId) => $"holdings:{accountId}";

    // Account Equity (30-sec TTL)
    public static string AccountEquity(string accountId) => $"equity:{accountId}";

    // Strategy Performance (5-min TTL)
    public static string StrategyPerformance(string strategyId) => $"strategy:perf:{strategyId}";

    // Analytics (5-min TTL)
    public static string Analytics(string accountId, string period, string metric) => 
        $"analytics:{accountId}:{period}:{metric}";

    // Risk Metrics (10-min TTL)
    public static string RiskMetrics(string accountId) => $"risk:{accountId}:metrics";
}
```

#### 2.4 Background Jobs (In-Process for MVP1)

**File: `DHRUVA.Infrastructure/BackgroundJobs/StrategyExecutionBackgroundService.cs`**

```csharp
namespace DHRUVA.Infrastructure.BackgroundJobs;

public class StrategyExecutionBackgroundService : BackgroundService
{
    private readonly ILogger<StrategyExecutionBackgroundService> _logger;
    private readonly IServiceProvider _serviceProvider;

    public StrategyExecutionBackgroundService(ILogger<StrategyExecutionBackgroundService> logger, IServiceProvider serviceProvider)
    {
        _logger = logger;
        _serviceProvider = serviceProvider;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("Strategy Execution Background Service started");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                // Calculate time until next minute boundary
                var now = DateTime.UtcNow;
                var nextMinute = now.AddMinutes(1).Date.AddMinutes(now.AddMinutes(1).Minute);
                var delay = nextMinute - now;

                _logger.LogDebug("Waiting {Seconds} seconds until next strategy execution", delay.TotalSeconds);
                await Task.Delay(delay, stoppingToken);

                // Execute strategies
                using (var scope = _serviceProvider.CreateScope())
                {
                    var strategyService = scope.ServiceProvider.GetRequiredService<IStrategyService>();
                    await strategyService.ExecuteEnabledStrategiesAsync();
                }
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error executing strategies");
            }
        }

        _logger.LogInformation("Strategy Execution Background Service stopped");
    }
}
```

Register in Program.cs:
```csharp
builder.Services.AddHostedService<StrategyExecutionBackgroundService>();
```

---

### Day 3: Database Design + EF Core + Event Sourcing

#### 3.1 EF Core DbContext (DHRUVA.Infrastructure)

**File: `Data/DhruvaDbContext.cs`**

```csharp
namespace DHRUVA.Infrastructure.Data;

public class DhruvaDbContext : DbContext
{
    public DhruvaDbContext(DbContextOptions<DhruvaDbContext> options) : base(options) { }

    // Tables
    public DbSet<User> Users { get; set; }
    public DbSet<Account> Accounts { get; set; }
    public DbSet<Strategy> Strategies { get; set; }
    public DbSet<Position> Positions { get; set; }
    public DbSet<Trade> Trades { get; set; }
    public DbSet<Order> Orders { get; set; }
    public DbSet<PortfolioSnapshot> PortfolioSnapshots { get; set; }
    public DbSet<RebalancePlan> RebalancePlans { get; set; }
    public DbSet<NotificationConfig> NotificationConfigs { get; set; }
    public DbSet<RiskAlert> RiskAlerts { get; set; }
    public DbSet<Report> Reports { get; set; }
    public DbSet<AuditLog> AuditLogs { get; set; }
    public DbSet<RefreshToken> RefreshTokens { get; set; }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        // User
        modelBuilder.Entity<User>(entity =>
        {
            entity.HasKey(e => e.Id);
            entity.Property(e => e.Email).IsRequired().HasMaxLength(255);
            entity.Property(e => e.PasswordHash).IsRequired();
            entity.Property(e => e.DisplayName).IsRequired().HasMaxLength(255);
            entity.Property(e => e.CreatedAt).IsRequired();
            entity.HasMany(e => e.Accounts).WithOne(a => a.User).HasForeignKey(a => a.UserId);
        });

        // Account
        modelBuilder.Entity<Account>(entity =>
        {
            entity.HasKey(e => e.Id);
            entity.Property(e => e.Name).IsRequired().HasMaxLength(255);
            entity.Property(e => e.BrokerId).IsRequired();
            entity.Property(e => e.BrokerAccountId).IsRequired().HasMaxLength(255);
            entity.Property(e => e.ApiKeyEncrypted).IsRequired();
            entity.Property(e => e.ApiSecretEncrypted).IsRequired();
            entity.Property(e => e.ConfigJson).HasColumnType("jsonb");
            entity.HasMany(e => e.Strategies).WithOne(s => s.Account).HasForeignKey(s => s.AccountId);
            entity.HasMany(e => e.Positions).WithOne(p => p.Account).HasForeignKey(p => p.AccountId);
            entity.HasMany(e => e.Trades).WithOne(t => t.Account).HasForeignKey(t => t.AccountId);
            entity.HasMany(e => e.Orders).WithOne(o => o.Account).HasForeignKey(o => o.AccountId);
        });

        // Strategy
        modelBuilder.Entity<Strategy>(entity =>
        {
            entity.HasKey(e => e.Id);
            entity.Property(e => e.Name).IsRequired().HasMaxLength(255);
            entity.Property(e => e.CodeOrTemplate).IsRequired();
            entity.Property(e => e.ParametersJson).HasColumnType("jsonb");
            entity.Property(e => e.CreatedAt).IsRequired();
            entity.HasMany(e => e.Trades).WithOne(t => t.Strategy).HasForeignKey(t => t.StrategyId);
        });

        // Position
        modelBuilder.Entity<Position>(entity =>
        {
            entity.HasKey(e => e.Id);
            entity.HasIndex(e => new { e.AccountId, e.Symbol }).IsUnique();
            entity.Property(e => e.Symbol).IsRequired().HasMaxLength(20);
            entity.Property(e => e.UpdatedAt).IsRequired();
        });

        // Trade
        modelBuilder.Entity<Trade>(entity =>
        {
            entity.HasKey(e => e.Id);
            entity.Property(e => e.Symbol).IsRequired().HasMaxLength(20);
            entity.Property(e => e.TradeDate).IsRequired();
        });

        // Order
        modelBuilder.Entity<Order>(entity =>
        {
            entity.HasKey(e => e.Id);
            entity.Property(e => e.Symbol).IsRequired().HasMaxLength(20);
            entity.Property(e => e.Status).IsRequired();
            entity.Property(e => e.OrderTime).IsRequired();
            entity.HasIndex(e => e.BrokerOrderId);
        });

        // AuditLog (immutable, append-only)
        modelBuilder.Entity<AuditLog>(entity =>
        {
            entity.HasKey(e => e.Id);
            entity.Property(e => e.Action).IsRequired();
            entity.Property(e => e.EntityType).IsRequired();
            entity.Property(e => e.CreatedAt).IsRequired();
            entity.Property(e => e.OldValueJson).HasColumnType("jsonb");
            entity.Property(e => e.NewValueJson).HasColumnType("jsonb");
        });

        // RefreshToken
        modelBuilder.Entity<RefreshToken>(entity =>
        {
            entity.HasKey(e => e.Id);
            entity.Property(e => e.Token).IsRequired();
            entity.Property(e => e.ExpiresAt).IsRequired();
            entity.Property(e => e.CreatedAt).IsRequired();
            entity.HasIndex(e => e.Token).IsUnique();
        });
    }
}
```

#### 3.2 Entity Models (DHRUVA.Core)

**File: `Models/User.cs`**

```csharp
namespace DHRUVA.Core.Models;

public class User
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string Email { get; set; }
    public string PasswordHash { get; set; }
    public string DisplayName { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    // Navigation
    public ICollection<Account> Accounts { get; set; } = new List<Account>();
}

public class Account
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string UserId { get; set; }
    public string Name { get; set; }
    public string BrokerId { get; set; } // Zerodha, Upstox, etc.
    public string BrokerAccountId { get; set; }
    public string ApiKeyEncrypted { get; set; }
    public string ApiSecretEncrypted { get; set; }
    public bool IsActive { get; set; } = true;
    public string? ConfigJson { get; set; } // Custom settings
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    // Navigation
    public User User { get; set; }
    public ICollection<Strategy> Strategies { get; set; } = new List<Strategy>();
    public ICollection<Position> Positions { get; set; } = new List<Position>();
    public ICollection<Trade> Trades { get; set; } = new List<Trade>();
    public ICollection<Order> Orders { get; set; } = new List<Order>();
}

public class Strategy
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string AccountId { get; set; }
    public string Name { get; set; }
    public string CodeOrTemplate { get; set; } // Strategy code or template name
    public bool IsEnabled { get; set; } = false;
    public string? ParametersJson { get; set; } // {"timeframe": "1M", "symbols": ["RELIANCE"], ...}
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    // Navigation
    public Account Account { get; set; }
    public ICollection<Trade> Trades { get; set; } = new List<Trade>();
}

public class Position
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string AccountId { get; set; }
    public string Symbol { get; set; }
    public decimal Quantity { get; set; }
    public decimal AvgCost { get; set; }
    public decimal CurrentPrice { get; set; }
    public decimal MarketValue { get; set; }
    public decimal UnrealizedPnL { get; set; }
    public string Sector { get; set; }
    public string InstrumentType { get; set; } // Equity, Derivatives, MutualFund
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;

    // Navigation
    public Account Account { get; set; }
}

public class Trade
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string AccountId { get; set; }
    public string? StrategyId { get; set; }
    public string Symbol { get; set; }
    public string TradeType { get; set; } // BUY, SELL
    public decimal Quantity { get; set; }
    public decimal Price { get; set; }
    public decimal Fees { get; set; }
    public decimal NetAmount { get; set; }
    public decimal PnL { get; set; }
    public DateTime TradeDate { get; set; }
    public bool IsSettled { get; set; } = false;
    public string? Notes { get; set; }

    // Navigation
    public Account Account { get; set; }
    public Strategy? Strategy { get; set; }
}

public class Order
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string AccountId { get; set; }
    public string Symbol { get; set; }
    public string Side { get; set; } // BUY, SELL
    public decimal Quantity { get; set; }
    public decimal Price { get; set; }
    public decimal? StopLoss { get; set; }
    public decimal? TakeProfit { get; set; }
    public string Status { get; set; } // PENDING, FILLED, REJECTED, CANCELLED
    public decimal FilledQuantity { get; set; } = 0;
    public decimal? FilledPrice { get; set; }
    public DateTime OrderTime { get; set; } = DateTime.UtcNow;
    public DateTime? FillTime { get; set; }
    public string? BrokerOrderId { get; set; }

    // Navigation
    public Account Account { get; set; }
}

public class PortfolioSnapshot
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string AccountId { get; set; }
    public DateTime SnapshotDate { get; set; }
    public decimal TotalValue { get; set; }
    public decimal Cash { get; set; }
    public decimal Invested { get; set; }
    public decimal DailyReturn { get; set; }
    public decimal CumulativeReturn { get; set; }
}

public class RebalancePlan
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string AccountId { get; set; }
    public string Name { get; set; }
    public string Status { get; set; } // Draft, Ready, Executing, Executed, Cancelled
    public string? TargetAllocationJson { get; set; } // {"RELIANCE": 0.15, "TCS": 0.10, ...}
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime? ExecutedAt { get; set; }
}

public class NotificationConfig
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string AccountId { get; set; }
    public string Email { get; set; }
    public string? EventsJson { get; set; } // Events to notify on
    public bool IsActive { get; set; } = true;
}

public class RiskAlert
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string AccountId { get; set; }
    public string AlertType { get; set; } // ConcentrationRisk, VaRExceeded, etc.
    public string Message { get; set; }
    public string Severity { get; set; } // Info, Warning, Error
    public bool IsRead { get; set; } = false;
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}

public class Report
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string UserId { get; set; }
    public string? AccountId { get; set; }
    public string? StrategyId { get; set; }
    public string ReportType { get; set; } // StrategyPerformance, Portfolio, Risk, Tax, etc.
    public string Period { get; set; } // 1D, 1M, 3M, 6M, YTD, 1Y
    public DateTime GeneratedAt { get; set; } = DateTime.UtcNow;
    public string FilePath { get; set; } // S3 path or local file path
    public string Format { get; set; } // PDF, Excel, CSV
}

public class AuditLog
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string? UserId { get; set; }
    public string Action { get; set; } // PlacedOrder, ExecutedTrade, etc.
    public string EntityType { get; set; } // Order, Trade, Account, etc.
    public string EntityId { get; set; }
    public string? OldValueJson { get; set; }
    public string? NewValueJson { get; set; }
    public string? IpAddress { get; set; }
    public string? UserAgent { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}

public class RefreshToken
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string UserId { get; set; }
    public string Token { get; set; }
    public DateTime ExpiresAt { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public bool IsRevoked { get; set; } = false;
}
```

#### 3.3 Event Sourcing (DHRUVA.Audit)

**File: `Models/DomainEvent.cs`**

```csharp
namespace DHRUVA.Audit.Models;

public abstract class DomainEvent
{
    public string Id { get; } = Guid.NewGuid().ToString();
    public DateTime Timestamp { get; } = DateTime.UtcNow;
    public string AggregateId { get; protected set; }
    public string AggregateType { get; protected set; }
}

public class OrderPlacedEvent : DomainEvent
{
    public OrderPlacedEvent(string orderId, string accountId, string symbol, decimal quantity, decimal price)
    {
        AggregateId = orderId;
        AggregateType = "Order";
        Symbol = symbol;
        Quantity = quantity;
        Price = price;
        AccountId = accountId;
    }

    public string AccountId { get; set; }
    public string Symbol { get; set; }
    public decimal Quantity { get; set; }
    public decimal Price { get; set; }
}

public class TradeExecutedEvent : DomainEvent
{
    public TradeExecutedEvent(string tradeId, string accountId, string symbol, decimal quantity, decimal price, decimal pnl)
    {
        AggregateId = tradeId;
        AggregateType = "Trade";
        Symbol = symbol;
        Quantity = quantity;
        Price = price;
        PnL = pnl;
        AccountId = accountId;
    }

    public string AccountId { get; set; }
    public string Symbol { get; set; }
    public decimal Quantity { get; set; }
    public decimal Price { get; set; }
    public decimal PnL { get; set; }
}

public class PositionUpdatedEvent : DomainEvent
{
    public PositionUpdatedEvent(string positionId, string symbol, decimal quantity, decimal unrealizedPnL)
    {
        AggregateId = positionId;
        AggregateType = "Position";
        Symbol = symbol;
        Quantity = quantity;
        UnrealizedPnL = unrealizedPnL;
    }

    public string Symbol { get; set; }
    public decimal Quantity { get; set; }
    public decimal UnrealizedPnL { get; set; }
}

public class StrategyExecutedEvent : DomainEvent
{
    public StrategyExecutedEvent(string strategyId, string symbol, string action, double confidence)
    {
        AggregateId = strategyId;
        AggregateType = "Strategy";
        Symbol = symbol;
        Action = action;
        Confidence = confidence;
    }

    public string Symbol { get; set; }
    public string Action { get; set; } // BUY, SELL, HOLD
    public double Confidence { get; set; }
}
```

**File: `Services/EventStore.cs`**

```csharp
namespace DHRUVA.Audit.Services;

public interface IEventStore
{
    Task AppendEventAsync(DomainEvent domainEvent);
    Task<IEnumerable<DomainEvent>> GetEventsByAggregateIdAsync(string aggregateId);
    Task<IEnumerable<DomainEvent>> GetEventsByTypeAsync(string eventType);
}

public class EventStore : IEventStore
{
    private readonly DhruvaDbContext _dbContext;
    private readonly ILogger<EventStore> _logger;

    public EventStore(DhruvaDbContext dbContext, ILogger<EventStore> logger)
    {
        _dbContext = dbContext;
        _logger = logger;
    }

    public async Task AppendEventAsync(DomainEvent domainEvent)
    {
        try
        {
            var eventJson = JsonSerializer.Serialize(domainEvent);
            
            var auditLog = new AuditLog
            {
                Id = Guid.NewGuid().ToString(),
                Action = domainEvent.GetType().Name,
                EntityType = domainEvent.AggregateType,
                EntityId = domainEvent.AggregateId,
                NewValueJson = eventJson,
                CreatedAt = domainEvent.Timestamp
            };

            _dbContext.AuditLogs.Add(auditLog);
            await _dbContext.SaveChangesAsync();

            _logger.LogInformation("Event appended: {EventType} for aggregate {AggregateId}", 
                domainEvent.GetType().Name, domainEvent.AggregateId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error appending event");
            throw;
        }
    }

    public async Task<IEnumerable<DomainEvent>> GetEventsByAggregateIdAsync(string aggregateId)
    {
        var auditLogs = await _dbContext.AuditLogs
            .Where(a => a.EntityId == aggregateId)
            .OrderBy(a => a.CreatedAt)
            .ToListAsync();

        var events = auditLogs.Select(a => 
            JsonSerializer.Deserialize<DomainEvent>(a.NewValueJson ?? "{}"))
            .Where(e => e != null)
            .ToList();

        return events;
    }

    public async Task<IEnumerable<DomainEvent>> GetEventsByTypeAsync(string eventType)
    {
        var auditLogs = await _dbContext.AuditLogs
            .Where(a => a.Action == eventType)
            .OrderBy(a => a.CreatedAt)
            .ToListAsync();

        var events = auditLogs.Select(a => 
            JsonSerializer.Deserialize<DomainEvent>(a.NewValueJson ?? "{}"))
            .Where(e => e != null)
            .ToList();

        return events;
    }
}
```

---

### Days 4-6: Execution, Broker, Strategy Services (Summary)

Due to length constraints, I'll provide the core interfaces and structure for these critical services:

#### **Day 4: Execution Service Interface (DHRUVA.Execution)**

```csharp
namespace DHRUVA.Execution.Services;

public interface IExecutionService
{
    Task<PlaceOrderResponse> PlaceOrderAsync(PlaceOrderRequest request);
    Task<CancelOrderResponse> CancelOrderAsync(string orderId);
    Task<GetPositionsResponse> GetPositionsAsync(string accountId);
    Task<GetOrderHistoryResponse> GetOrderHistoryAsync(string accountId);
}

public interface IRiskEngine
{
    Task<RiskCheckResult> ValidateOrderAsync(PlaceOrderRequest request);
    Task<bool> CheckMarginAsync(string accountId, decimal requiredMargin);
    Task<bool> CheckConcentrationAsync(string accountId, string symbol, decimal newQuantity);
    Task<bool> CheckMaxExposureAsync(string accountId, decimal exposure);
}

public interface IPositionTracker
{
    Task<Position> GetPositionAsync(string accountId, string symbol);
    Task UpdatePositionAsync(Position position);
    Task<List<Position>> GetAllPositionsAsync(string accountId);
}
```

#### **Day 5: Broker Adapter Interface (DHRUVA.Broker)**

```csharp
namespace DHRUVA.Broker.Adapters;

public interface IBrokerAdapter
{
    Task AuthenticateAsync(BrokerCredentials credentials);
    Task<PlaceOrderResponse> PlaceOrderAsync(OrderRequest order);
    Task<CancelOrderResponse> CancelOrderAsync(string orderId);
    Task<List<Position>> GetPositionsAsync();
    Task<List<Holding>> GetHoldingsAsync();
    Task<MarginDetails> GetMarginAsync();
    Task RefreshTokenAsync();
    Task<BrokerHealthStatus> GetHealthAsync();
}

public interface IBrokerFactory
{
    IBrokerAdapter CreateAdapter(BrokerType brokerType, BrokerCredentials credentials);
}

public interface IBrokerHealthMonitor
{
    Task MonitorBrokerHealthAsync();
}
```

#### **Day 6: Strategy Service Interface (DHRUVA.Strategy)**

```csharp
namespace DHRUVA.Strategy.Services;

public interface IStrategyService
{
    Task<CreateStrategyResponse> CreateStrategyAsync(CreateStrategyRequest request);
    Task<GetStrategyResponse> GetStrategyAsync(string strategyId);
    Task<List<GetStrategyResponse>> GetAllStrategiesAsync(string accountId);
    Task EnableStrategyAsync(string strategyId);
    Task DisableStrategyAsync(string strategyId);
    Task ExecuteEnabledStrategiesAsync();
}

public interface IStrategyExecutor
{
    Task<StrategySignal> ExecuteAsync(Strategy strategy, OHLCVCandle latestCandle);
}

public interface IBacktestEngine
{
    Task<BacktestResults> BacktestAsync(BacktestRequest request);
}

public interface IPaperTrader
{
    Task<PaperTradeResult> ExecutePaperTradeAsync(PaperTradingRequest request);
}
```

---

## Implementation Instructions

### Prerequisites

1. **Software:**
   - .NET 10 SDK installed
   - Visual Studio 2022 or VS Code with C# extension
   - PostgreSQL 15+ installed (or use Docker)
   - Redis 7+ installed (or use Docker)

2. **Environment:**
   - Clone repository
   - Create `appsettings.Development.json` (copy from appsettings.json, update connection strings)
   - `docker-compose up -d` to start databases locally

### Step 1: Create Solution & Projects

```bash
dotnet new sln -n DHRUVA
cd DHRUVA

# Host
dotnet new web -n DHRUVA.Web

# Services
dotnet new classlib -n DHRUVA.Execution
dotnet new classlib -n DHRUVA.Portfolio
dotnet new classlib -n DHRUVA.Strategy
dotnet new classlib -n DHRUVA.Scanner
dotnet new classlib -n DHRUVA.Data
dotnet new classlib -n DHRUVA.Broker
dotnet new classlib -n DHRUVA.Notification
dotnet new classlib -n DHRUVA.Reports
dotnet new classlib -n DHRUVA.Audit

# Shared
dotnet new classlib -n DHRUVA.Core
dotnet new classlib -n DHRUVA.Infrastructure
dotnet new classlib -n DHRUVA.Auth
dotnet new classlib -n DHRUVA.Common

# Add projects to solution
dotnet sln add DHRUVA.Web DHRUVA.Execution DHRUVA.Portfolio ... (all projects)
```

### Step 2: Add NuGet Packages

```bash
cd DHRUVA.Web
dotnet add package Serilog.AspNetCore
dotnet add package OpenTelemetry
dotnet add package OpenTelemetry.Exporter.Jaeger
dotnet add package StackExchange.Redis
```

### Step 3: Add Project References

```bash
dotnet add DHRUVA.Web reference DHRUVA.Execution DHRUVA.Portfolio ... (all services)
dotnet add DHRUVA.Execution reference DHRUVA.Core DHRUVA.Infrastructure
# ... similar for all service projects
```

### Step 4: Implement Files

Create the files listed above in each project according to the file paths specified.

### Step 5: Run Migrations

```bash
dotnet ef migrations add InitialCreate -p DHRUVA.Infrastructure -s DHRUVA.Web
dotnet ef database update -s DHRUVA.Web
```

### Step 6: Run Application

```bash
dotnet run --project DHRUVA.Web
```

Visit `https://localhost:5001/health/ready` to verify all services are healthy.

---

## Testing & Verification

### Health Checks
- `GET /health/live` → Should return 200
- `GET /health/ready` → Should return 200 with detailed status

### Authentication Flow
1. `POST /api/v1/auth/login` with email/password
2. Receive JWT access token + refresh token
3. Use access token in `Authorization: Bearer {token}` header

### Logging Verification
- Console output should show JSON logs
- Check PostgreSQL `logs` table for stored logs
- Filter by trace_id for order flow analysis

### Tracing
- Visit Jaeger dashboard: `http://localhost:16686`
- Search by service: DHRUVA.Trading
- View order flow with 9 spans

---

## Next Steps (After Phase 1)

1. **Phase 2 (Days 7-12):** Portfolio, Analytics, Risk Management
2. **Phase 3 (Days 13-15):** SignalR, Email Alerts, Monitoring
3. **Phase 4 (Days 16-18):** Angular Frontend with Dashboards
4. **Phase 5 (Days 19-22.5):** Testing, Security, Deployment

---

**Status**: Phase 1 Implementation Prompt Complete ✅  
**Scope**: Days 1-6 detailed (Projects, Auth, DB, Services structure)  
**Ready to**: Execute with provided code templates and architecture  

This prompt can be given to any AI or developer to implement Phase 1 of DHRUVA in one session.
