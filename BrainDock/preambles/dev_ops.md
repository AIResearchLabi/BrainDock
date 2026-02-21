# Development Operations Context

## Architecture Principles
- Prefer simplicity over abstraction. Solve the immediate problem.
- Use established, well-maintained dependencies. Avoid bleeding-edge unless justified.
- Design for readability first, performance second (optimize only proven bottlenecks).
- Follow the principle of least surprise — code should do what it looks like it does.
- Separate concerns clearly: data, logic, presentation, and infrastructure.

## Code Standards
- Every module should have a single clear responsibility.
- Public APIs should be small, typed, and documented at boundaries.
- Error handling: fail fast internally, handle gracefully at system boundaries.
- Tests: unit tests for logic, integration tests for boundaries. No test theater.
- Naming: descriptive > short. Code is read far more than it is written.

## Tech Preferences
- Language/framework preferences: (customize per project)
- Deployment target: (customize — cloud, edge, local, etc.)
- Database philosophy: start simple (SQLite/Postgres), scale when data demands it.
- API design: REST for CRUD, WebSockets for real-time, gRPC for internal services.

## Project Structure
- Keep a flat, navigable directory structure. Deep nesting hides complexity.
- Configuration separate from code. Environment-specific values in env vars or config files.
- Dependencies pinned to specific versions. Lock files committed.

## What I Know About This Domain
(Add your technical context here — existing systems, constraints, team skills,
infrastructure, deployment environment, CI/CD setup, tech debt, etc.)
