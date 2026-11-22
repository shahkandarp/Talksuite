# TalkSuite — AI-Powered NetSuite Assistant

**Team 12** | Manish, Rishabh, Kandarp, Nikunj, Teesha

---

## What is TalkSuite?

TalkSuite is a conversational AI assistant that lets business users interact with NetSuite using natural language. Instead of navigating complex ERP screens, users simply ask questions like "What invoices are pending for ABC Corp?" or "Show me sales from last quarter" — and TalkSuite handles the rest.

It connects to NetSuite's native MCP server, queries live data via SuiteQL, and returns answers with charts, tables, and follow-up suggestions — all in real-time via a streaming chat interface.

---

## Problem Statement

Business users spend significant time navigating NetSuite's complex UI to find information. Non-technical users (finance teams, managers, inventory staff) often depend on developers or consultants to pull reports. There's no simple way to "just ask" NetSuite a question.

---

## Solution

TalkSuite provides:
- A chat interface where users ask questions in plain English
- AI-powered routing that decides whether to query NetSuite (live data) or the Knowledge Base (documentation/policies)
- Role-based access control — finance users can only access finance tools, inventory users only inventory tools
- Real-time streaming responses with charts and follow-up suggestions
- Voice input via AWS Transcribe for hands-free operation

---

## Key Features

| Feature | Description |
|---------|-------------|
| Natural Language Queries | Ask NetSuite questions in plain English |
| Live Data via MCP | Connects to NetSuite's native MCP server (OAuth 2.0 PKCE) |
| Knowledge Base RAG | Searches internal documents via Bedrock Knowledge Base |
| Role-Based Guardrails | Users only see tools relevant to their role |
| Chart Visualization | Quantifiable responses rendered as Recharts bar/area charts |
| Voice Input | Speech-to-text via AWS Transcribe Streaming |
| SSE Streaming | Real-time token-by-token response streaming |
| Reasoning Transparency | Shows which tools were called and how the answer was derived |
| Follow-up Suggestions | AI generates clickable follow-up questions |
| Multi-Conversation | Persistent chat history with LLM-generated titles |
| Input Sanitization | Prompt injection detection and prevention |
| JWT Authentication | Secure login with role-based access |
| Soft Delete | Conversations are archived, not permanently removed |

---

## Architecture

```
React Frontend (Next.js + Recharts)
        │ HTTPS + SSE
        ▼
CloudFront (SSL termination)
        │
        ▼
Application Load Balancer
        │ Port 8000
        ▼
ECS Fargate (FastAPI + LangGraph + Python 3.11)
        │
        ├──► Amazon Bedrock (Claude Sonnet 4) — AI reasoning
        ├──► Bedrock Knowledge Base (RAG) — document search
        ├──► Amazon Transcribe — voice-to-text
        ├──► NetSuite MCP Server — live ERP data (JSON-RPC)
        └──► Amazon RDS (PostgreSQL 16) — conversations & users
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React, Next.js, TypeScript, Recharts, Tailwind CSS |
| Backend | Python 3.11, FastAPI, LangGraph, SQLAlchemy (async) |
| AI/LLM | Amazon Bedrock (Claude Sonnet 4), Bedrock Knowledge Base |
| ERP Integration | NetSuite Native MCP (OAuth 2.0 PKCE, JSON-RPC) |
| Voice | Amazon Transcribe Streaming |
| Database | Amazon RDS PostgreSQL 16 |
| Auth | JWT (PyJWT), role-based access control |
| Infrastructure | AWS ECS Fargate, ECR, ALB, CloudFront, Parameter Store, IAM |
| Streaming | Server-Sent Events (SSE) |

---

## AWS Services Used

- **ECS Fargate** — Serverless container hosting
- **ECR** — Docker image registry
- **Application Load Balancer** — Traffic routing + health checks
- **CloudFront** — HTTPS/SSL termination
- **RDS PostgreSQL** — Persistent storage
- **Amazon Bedrock** — LLM inference (Claude Sonnet 4)
- **Bedrock Knowledge Base** — RAG document retrieval
- **Amazon Transcribe** — Speech-to-text
- **Parameter Store** — Secrets management
- **IAM** — Role-based permissions for ECS tasks
- **CloudWatch** — Logging and monitoring

---

## How It Works

1. User sends a message (text or voice) from the React frontend
2. Backend authenticates via JWT and validates input (prompt injection guard)
3. **Role-based guardrail**: Based on the user's role (admin/finance/inventory), the system filters which MCP tools are available to Claude. A finance user will never see inventory tools and vice versa — Claude can only call tools permitted for that role.
4. LangGraph orchestrator invokes Claude with the filtered tool set
5. Claude decides: call NetSuite MCP (live data) or Knowledge Base (docs)
6. **Read-only guardrail**: Before any MCP tool is executed, the system validates that the tool is read-only (query/search operations only). Any tool that would create, update, or delete data in NetSuite is blocked — the AI can never modify ERP data, regardless of what Claude requests.
7. Tool results are fed back to Claude for final answer generation
8. Response streams back via SSE — text chunks, chart data, follow-ups
9. Frontend renders in real-time with Recharts visualizations

---

## Security & Guardrails

- **Read-only mode** — AI can only query NetSuite, never modify data
- **Role-based tool filtering** — each user role only sees permitted tools
- **Prompt injection detection** — pattern-based + structural sanitization
- **JWT authentication** — all endpoints protected (except /health and /auth/login)
- **Secrets in Parameter Store** — no credentials in code or env files
- **IAM Task Roles** — ECS tasks get minimal required AWS permissions

---

## Security & Guardrails
