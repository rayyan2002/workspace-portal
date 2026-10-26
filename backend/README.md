# Backend — Spring Boot API and the GenAI service

The setup runbook that used to live here is now in the
**[repository root README](../README.md)**, alongside the architecture overview, so a
reader arriving at this project gets the whole system in one file rather than half of it
in each.

Paths in that runbook are relative to **this directory** — §0 says so and tells you to
`cd backend` first — so everything still works as written.

| | |
|---|---|
| `src/main/java/com/knowledgeassistant/` | the Spring Boot API |
| `src/main/resources/db/migration/` | Flyway migrations, `V1`–`V25`, forward-only |
| `genai-service/` | the FastAPI retrieval and generation service |
| `genai-service/benchmarks/` | the measurements the defaults are set from |
| `INTEGRATION_CONTRACT.md` | the Spring ↔ Python boundary, specified rather than observed |
