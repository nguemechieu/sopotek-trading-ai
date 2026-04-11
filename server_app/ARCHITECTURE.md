# Sopotek Trading AI Platform Architecture

## Overview

Sopotek Trading AI is structured as a shared backend with multiple operator surfaces:

- `backend/`: FastAPI control plane, auth, terminal commands, portfolio, strategy, risk, orders, licensing, and websocket fanout
- `frontend/`: Next.js web control center with authentication, dashboard, integrated terminal, and operator pages
- `src/`: PySide6 desktop workstation and trading runtime

The web and desktop clients are intended to share the same backend domain model and command/event semantics.

## Core Design

- Authentication is the entry point.
- After successful authentication the user is redirected into the control center.
- The control center is the operational dashboard.
- The integrated terminal is a guided command surface on top of the same backend services.
- State is event-driven and microservices-ready:
  - PostgreSQL for durable records
  - Redis-ready realtime cache layer
  - Kafka-ready command and event transport
  - in-process `PlatformStateStore` fallback for local and single-node runtime

## Folder Layout

```text
server_app/
  backend/
    app/
      api/
        routes/
          auth.py
          control.py
          orders.py
          portfolio.py
          positions.py
          risk.py
          strategies.py
          terminal.py
          workspace.py
      core/
        config.py
        dependencies.py
        security.py
      db/
        base.py
        session.py
      models/
        user.py
        portfolio.py
        trade.py
        strategy.py
        log.py
        workspace_config.py
      schemas/
        auth.py
        orders.py
        portfolio.py
        risk.py
        strategies.py
        terminal.py
      services/
        auth_rate_limiter.py
        bootstrap.py
        command_service.py
        core_bridge.py
        kafka_gateway.py
        state_store.py
        terminal_service.py
      ws/
        router.py
    tests/
  frontend/
    app/
      dashboard/
      terminal/
      login/
      register/
      forgot-password/
      reset-password/
    components/
      auth/
      control-panel/
      layout/
      panels/
      terminal/
    lib/
      api.ts
      auth.ts
      auth-shared.ts
      server-session.ts
      terminal.ts
      workspace-config.ts
```

## Authentication Flow

Backend auth capabilities:

- bcrypt-aware password hashing with PBKDF2 fallback
- JWT access tokens
- JWT refresh tokens
- remember-me token extension
- in-memory auth rate limiting
- email verification token flow
- optional TOTP 2FA bootstrap and confirm endpoints

Primary endpoints:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`
- `POST /auth/verify-email`
- `POST /auth/resend-verification`
- `POST /auth/2fa/setup`
- `POST /auth/2fa/confirm`
- `POST /auth/2fa/disable`
- `GET /auth/me`

Frontend auth pages:

- `/login`
- `/register`
- `/forgot-password`
- `/reset-password`

## Control Center

The dashboard is the post-login landing surface and contains:

- portfolio overview
- total equity
- daily, weekly, and monthly PnL
- active positions
- market watchlist
- AI signals panel
- notifications
- workspace settings mirroring the desktop dashboard launch parameters

## Integrated Terminal

The web terminal is a guided command interface built on the backend terminal service.

Supported commands:

- `/help`
- `/markets`
- `/trade SYMBOL long|short QUANTITY`
- `/positions`
- `/risk`
- `/strategy start|pause CODE`
- `/backtest SYMBOL HORIZON`
- `/agents status`

Terminal APIs:

- `GET /terminal/manifest`
- `GET /terminal/history`
- `POST /terminal/execute`

The terminal does not bypass the platform. It calls the same control services used by order, strategy, and risk pages.

## Core Engines

Shared runtime responsibilities across desktop and web:

- Market data engine: stream and normalize market state
- Strategy engine: maintain strategy inventory and assignments
- Risk engine: track exposure, drawdown, limits, and alerts
- Execution engine: accept validated order requests
- Portfolio engine: equity, PnL, and position state
- Agent mesh: signal, risk, execution, and monitoring agents

## Event Flow

```text
Market stream / broker adapter
  -> Kafka or internal gateway
  -> TradingCoreBridge
  -> PlatformStateStore
  -> REST snapshots + WebSocket push
  -> Dashboard / Terminal / Desktop UI

Operator command
  -> REST route
  -> TradingControlService / TerminalService
  -> DB write + log
  -> Kafka command topic
  -> trading core / execution services
```

## Deployment

### Local

1. Start PostgreSQL.
2. Start the backend:
   - `uvicorn app.main:app --reload`
3. Start the frontend:
   - `npm run dev`
4. Optional:
   - connect Kafka
   - connect Redis
   - point the desktop app to the same backend domain

### Docker

- Build backend and frontend images with their existing Dockerfiles.
- Run Postgres as a separate service.
- Mount environment variables for secrets and broker configuration.
- Expose:
  - backend `8000`
  - frontend `3000`

### AWS-Ready Topology

- Frontend: Vercel, CloudFront/S3, or ECS/Fargate
- Backend: ECS/Fargate or EKS
- PostgreSQL: Amazon RDS for PostgreSQL
- Redis: ElastiCache
- Kafka: Amazon MSK
- Secrets: AWS Secrets Manager
- Email delivery: Amazon SES
- Observability:
  - CloudWatch logs
  - OpenTelemetry or Application Insights compatible tracing

## Security Checklist

- store JWT secret and broker secrets outside source control
- terminate TLS at the edge and between services where required
- prefer HttpOnly cookies if the web platform moves to server-managed session refresh
- enforce verified email for production desks when onboarding policies require it
- enable TOTP 2FA for privileged roles
- apply rate limiting on auth and terminal write commands

## Extension Path

- move terminal command execution onto a durable job bus
- replace in-memory auth limiter and state store with Redis-backed implementations
- add server-managed refresh rotation
- add broker connectivity health tiles and live agent telemetry streams
- unify desktop and web command grammars around a shared contract package
