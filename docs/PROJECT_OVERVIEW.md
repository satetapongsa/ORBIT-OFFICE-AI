# AURA OFFICE AI — Project Overview

**AURA OFFICE AI** is an AI-powered internal office management platform for a
medium-sized private company. It centralises office information, tasks,
documents, IT support, HR information and analytics in one web application, and
adds an AI assistant that answers questions **only from company data the
signed-in user is authorised to see**.

## Goals

1. Reduce repetitive employee workload (searching documents, writing drafts,
   status reporting, ticket triage).
2. Give every employee one place to find authorised company information.
3. Give managers real-time visibility of team workload and overdue work.
4. Give administrators full control over users, roles, permissions, document
   access and AI configuration.
5. Do all of this with production-grade security: backend-enforced RBAC,
   document-level ACLs, audit logging and permission-filtered AI retrieval.

## Users and roles

| Role         | Primary needs                                                                   |
| ------------ | ------------------------------------------------------------------------------- |
| `EMPLOYEE`   | Own tasks, authorised documents, AI assistant, IT tickets, notifications        |
| `MANAGER`    | Everything an employee has + team workload, task assignment, team reports       |
| `HR`         | Employee records (incl. sensitive HR fields), company policies                  |
| `IT_SUPPORT` | Helpdesk queue: assign, respond, change status, close tickets                   |
| `ADMIN`      | Users, departments, roles, permissions, document ACLs, system & AI settings, audit logs |

Roles are data, not code: each role is a set of permissions stored in the
database. New roles can be created without code changes (see `SECURITY.md`).

## Modules

| # | Module               | Thai label (UI)          | Delivered in |
| - | -------------------- | ------------------------ | ------------ |
| 1 | Dashboard            | แดชบอร์ด                  | Phase 3      |
| 2 | AI Assistant         | ผู้ช่วย AI                 | Phase 6–7    |
| 3 | Document Center      | ศูนย์เอกสาร                | Phase 4 ✅ (RAG: 7) |
| 4 | Task Management      | จัดการงาน                 | Phase 5      |
| 5 | Employee Center      | ศูนย์พนักงาน               | Phase 5      |
| 6 | IT Helpdesk          | แจ้งปัญหาไอที              | Phase 8      |
| 7 | Analytics & Reports  | รายงานและการวิเคราะห์       | Phase 8      |
| 8 | Notifications        | การแจ้งเตือน               | Phase 3 (inbox), 8 |
| 9 | Settings             | ตั้งค่า                    | Phase 2+     |

## Non-negotiable product rules

- Every metric, list and search result comes from real backend APIs and the
  database. No hardcoded production data, no fake buttons.
- The AI never invents internal company information. It answers from retrieved,
  authorised evidence, cites sources, and says so when evidence is missing.
- Unauthorised document content is never sent to an LLM — permission filtering
  happens in the database query, before retrieval results leave the backend.
- AI actions that change records always require explicit user confirmation.
- The primary UI language is Thai; code, API fields and database identifiers are
  English.

## Where to read next

- `ARCHITECTURE.md` — system architecture and layering
- `DATABASE_DESIGN.md` — schema plan
- `API_CONVENTIONS.md` — REST conventions
- `SECURITY.md` — authentication, authorisation, ACL and AI security
- `DEVELOPMENT_PHASES.md` — Phase 0–9 plan with acceptance criteria
- `PROJECT_STATUS.md` — the real current state
- `DECISIONS.md` — architecture decision records
- `RUNBOOK.md` — setup, run, test and troubleshooting commands
