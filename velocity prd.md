# Product Requirements Document (PRD): Velocity CRM Agent

**Version:** 1.0  
**Status:** Final / Jury-Ready  
**Product Name:** Velocity CRM Agent  
**Subtitle:** AI-Assisted CRM Operations with Governed Zoho Actions  

---

## 1. Executive Summary
Velocity CRM Agent is a production-grade system designed to observe synchronized CRM activity, detect operational bottlenecks, and provide AI-driven root-cause analysis grounded in company policy. The system empowers sales teams by automating routine tasks and providing governed, human-in-the-loop workflows for high-impact CRM actions, specifically within the Zoho CRM ecosystem.

## 2. Problem Statement
Sales organizations often suffer from "pipeline friction" caused by stalled deals and uneven lead distribution (owner overload). Manual monitoring of these bottlenecks is reactive and inconsistent. Furthermore, while AI can suggest fixes, autonomous agents often lack the governance and company-specific context (SOPs) required to make safe, policy-compliant changes to a production CRM.

## 3. Goals & Objectives
*   **Proactive Detection:** Identify stalled deals and overloaded owners using deterministic logic rather than speculative AI.
*   **Contextual Analysis:** Provide root-cause analysis grounded in actual company Standard Operating Procedures (SOPs).
*   **Governed Execution:** Execute CRM updates (tasks, reassignments) through a strict governance engine that requires human approval for high-stakes changes.
*   **Auditability:** Maintain a 100% transparent audit trail of all AI recommendations and system actions.

## 4. Target Users / Stakeholders
*   **Sales Representative:** Views pipeline dashboards and receives automated follow-up tasks.
*   **Sales Manager:** Monitors team bottlenecks and reviews AI-generated root-cause insights.
*   **Administrator:** Manages Zoho integration, configures monitoring settings, and approves/rejects high-impact actions like deal reassignment.

## 5. Functional Requirements

### 5.1 Synchronization & Monitoring
*   **Zoho Sync:** The system must perform idempotent, paginated synchronization of Zoho Deals into the local PostgreSQL database.
*   **Deterministic Detection:** A background scheduler must run at configurable intervals to detect:
    *   **Stalled Deals:** Deals with no activity for a defined threshold.
    *   **Owner Overload:** Users with a deal count exceeding capacity.
*   **Incident Management:** The system must deduplicate and track the lifecycle of "Bottleneck Incidents" (Open, Resolved, Analyzed).

### 5.2 AI Root-Cause Analysis (RAG)
*   **Knowledge Retrieval:** The system must use vector similarity search (pgvector) to retrieve relevant SOPs and policies based on the incident context.
*   **Structured Analysis:** The system must send sanitized evidence and retrieved context to Google Gemini to receive a structured analysis and recommendation.
*   **Grounding:** AI responses must be constrained by the provided policy context to prevent hallucinations.

### 5.3 Governed Action Engine
*   **Automated Tasks:** The system can automatically create follow-up tasks in Zoho CRM based on AI recommendations, subject to idempotency checks.
*   **Approval-Gated Reassignment:** Any change to Deal Ownership must be staged as a "Pending Approval" for an Administrator to review.
*   **Outcome Verification:** The system must track whether an intervention (e.g., a task or reassignment) successfully cleared the bottleneck.

### 5.4 User Interface
*   **Operations Console:** A web-based dashboard for viewing incidents, AI analysis, and audit timelines.
*   **Approval Workflow:** A dedicated interface for Administrators to approve or reject gated actions.

## 6. Non-Functional Requirements
*   **Performance:** The system must handle background synchronization without impacting the responsiveness of the frontend dashboard.
*   **Reliability:** Use of idempotency keys for all Zoho CRM write operations to prevent duplicate tasks or reassignments.
*   **Scalability:** Modular monolith architecture to allow for future service separation if load increases.
*   **Availability:** Hosted on Render Cloud Platform with managed PostgreSQL for high uptime.

## 7. System Architecture Overview
The system follows a **Modular Monolith** pattern hosted on the **Render Cloud Platform**.
*   **Frontend:** Next.js application handling the presentation layer and user interactions.
*   **Backend:** FastAPI service containing the detection engine, AI logic, and Zoho integration.
*   **Database:** PostgreSQL 17 with `pgvector` for both relational data and vector embeddings.
*   **External Integration:** Synchronous and scheduled flows to Zoho CRM API and Google Gemini API.

## 8. Tech Stack
*   **Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS, Radix UI.
*   **Backend:** Python, FastAPI, SQLAlchemy Async, Pydantic, Alembic, Uvicorn.
*   **Database:** PostgreSQL 17, pgvector.
*   **AI/LLM:** Google Gemini API.
*   **Integration:** Zoho CRM API (OAuth 2.0).
*   **Hosting:** Render Cloud Platform.

## 9. Data Requirements
The **Velocity Operational Database** must store:
*   **Core Entities:** Users, Roles, and Synchronized Deals.
*   **Operational Data:** Bottleneck Incidents, Monitoring Settings, and Monitoring Run logs.
*   **AI/Knowledge:** SOP Documents, Vector Embeddings, and AI Analysis results.
*   **Action Logs:** Follow-up Tasks, Reassignment Approvals, and Incident Outcomes.
*   **Security:** Encrypted Zoho OAuth tokens and a comprehensive Audit Event log.

## 10. API Specifications
*   **Internal API:** RESTful endpoints between Next.js and FastAPI using JWT Bearer authentication.
*   **Zoho CRM API:** 
    *   `READ` Deals and Active Users.
    *   `CREATE` Tasks.
    *   `UPDATE` Deal Ownership (Gated).
*   **Google Gemini API:** Structured inference for root-cause analysis using sanitized incident data.

## 11. Security Requirements
*   **Authentication:** JWT-based authentication for all web users.
*   **Authorization:** Role-Based Access Control (RBAC) specifically for Administrator-only approval actions.
*   **Data Protection:** 
    *   Encryption of Zoho OAuth tokens at rest.
    *   Sanitization of data sent to external AI APIs (PII stripping).
*   **Governance:** Mandatory human-in-the-loop for high-impact CRM writes.
*   **Audit Trail:** Every action must include Actor ID, Source, Timestamp, and Correlation ID.

## 12. Deployment & Infrastructure
*   **Platform:** Render (Web Services for Frontend/Backend, Managed PostgreSQL).
*   **CI/CD:** Automated deployments via Render's GitHub integration.
*   **Migrations:** Database schema changes managed via Alembic.

## 13. Success Metrics
*   **Bottleneck Resolution Time:** Average time from incident detection to resolution.
*   **AI Accuracy:** Percentage of AI recommendations accepted by Administrators.
*   **Sync Reliability:** Zero duplicate records in Zoho CRM due to idempotency failures.
*   **User Adoption:** Frequency of Sales Manager logins to the Operations Console.

## 14. Timeline & Milestones
*   **Phase 1: Foundation:** Zoho OAuth integration, Deal synchronization, and basic dashboard.
*   **Phase 2: Detection:** Implementation of the Deterministic Detection Engine and Incident tracking.
*   **Phase 3: Intelligence:** Integration of pgvector, SOP ingestion, and Gemini AI Analysis.
*   **Phase 4: Governance:** Implementation of the Governed Action Engine and Admin Approval workflows.

## 15. Open Questions & Risks
*   **API Rate Limits:** Zoho and Gemini have strict rate limits; the system may require a "leaky bucket" implementation in the Action Engine.
*   **Process Contention:** Running the scheduler inside the FastAPI process may cause latency; may require moving to a Render Background Worker in Phase 2.
*   **LLM Latency:** Gemini response times may exceed standard HTTP timeouts, requiring optimized frontend loading states or asynchronous polling.
*   **Database Load:** High-frequency audit logging and vector searches may impact PostgreSQL performance as the dataset grows.