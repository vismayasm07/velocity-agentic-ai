# Velocity CRM Agent - Progress

Last updated: 2026-08-08

## Continuous Integration

- Added a GitHub Actions workflow for pushes and pull requests targeting
  `main`, with concurrency cancellation for superseded runs.
- Backend CI uses PostgreSQL 17 with pgvector, applies the complete Alembic
  migration chain, and runs the full pytest suite with isolated CI settings.
- Frontend CI installs from the committed lockfile and runs ESLint followed by
  the Next.js production build.
- Render remains responsible for deployment; CI does not access the production
  database or production integration credentials.

## Operational Polish and Reliability Presentation

- Separated Zoho OAuth connection, synchronization permission, active adapter,
  and governed write readiness so a connected account is not presented as
  provider-execution ready. The page now explains local fallback explicitly and
  evaluates Deal reads, follow-up writes, and owner reassignment independently.
- Added a shared incident audit timeline with human-readable event names,
  source attribution, status, timestamps, and copyable correlation IDs.
- Completed presentation for every reassignment approval state and separated
  administrator authorization from provider execution. The approval inbox now
  includes approved items and state-specific empty messages.
- Made monitoring evidence clearer with latest-run duration and distinct
  first-run versus completed-clean-run messages. Monitoring settings now state
  that scheduler changes apply immediately and require no restart.
- Exposed existing idempotency behavior in follow-up and reassignment feedback:
  an existing active task or pending authorization is identified instead of
  appearing to be newly duplicated. Follow-up history uses readable execution
  source labels and distinguishes provider results from locally recorded work.

Validation completed:

- Full frontend ESLint and the Next.js 16.3 production build pass.
- VS Code reports no errors in the frontend source tree.
- Full backend regression suite passes: 119 passed, with one third-party Google
  GenAI deprecation warning under Python 3.14.
- Browser checks at desktop `1440x900` and mobile `390x844` found no horizontal
  overflow on the integration page. Mobile dashboard and monitoring checks found
  no viewport violations; all tested buttons are named and every monitoring
  input has an associated label.
- The dashboard rendered the completed-run duration and current monitoring
  evidence. The browser session reported Zoho as disconnected, so this pass did
  not initiate OAuth, synchronization, or any provider write. Earlier read-only
  connected-account evidence and user-confirmed gated write tests remain the
  live Zoho validation record.

## Final Security and AI Guardrail Audit

- Reviewed authentication and administrator dependencies, FastAPI route gates,
  PostgreSQL/pgvector access, Gemini prompt construction and structured output,
  proactive monitoring, notifications currently represented by governed CRM
  follow-up tasks, Zoho OAuth/read/write synchronization, approvals, outcomes,
  and audit events. The local environment file was not read; ignore/tracking
  behavior was checked without exposing secrets.
- Blocked manual follow-up execution when Gemini marks the recommendation as
  requiring human approval. Automatic and manual execution now enforce the
  same approval boundary.
- Restricted the configurable Zoho Accounts base URL to the canonical India
  HTTPS origin for authorization, token exchange/refresh, and revocation.
- Removed unused Zoho notification scopes from the default request, added
  baseline frontend CSP/frame/content-type/referrer/permissions headers, and
  upgraded vulnerable backend pins to `cryptography==50.0.0`, `PyJWT==2.13.0`,
  and `pytest==9.0.3`.
- Fixed active-incident deduplication after approved reassignment: escalated
  Deal incidents remain active for scan lookup and owner workload evidence, so
  a subsequent scan updates the original incident instead of creating another.
- Added regression coverage for approval-required follow-up refusal, malicious
  OAuth host configuration, JWT tampering and expiry, prompt-injection content
  isolation, and reassignment replay/deduplication.

Validation completed:

- Full backend suite: 119 passed, 1 third-party Google GenAI deprecation
  warning under Python 3.14.
- Backend `pip-audit -r requirements.txt`: no known vulnerabilities.
- Frontend ESLint and Next.js 16.3 production build pass.
- Production frontend `npm audit --omit=dev --audit-level=high`: 0
  vulnerabilities.
- VS Code reports no errors in the touched backend service and test files.

Remaining production requirements:

- Replace browser `localStorage` bearer tokens with short-lived secure,
  HttpOnly sessions plus rotation/revocation; add JWT issuer/audience/session
  controls and login/API rate limiting.
- Reject development database/admin/JWT defaults outside an explicit local
  mode, disable automatic demo seeding in production, and enforce HTTPS,
  trusted hosts, request-body limits, and stricter production CSP directives.
- Add organization/tenant ownership and object-level authorization. Current
  authenticated users share the same CRM object scope by design.
- Give Zoho token encryption a dedicated versioned key or KMS, and use a
  transactional outbox/idempotency reconciliation flow for remote writes.
- Move monitoring overlap control from process-local locks to distributed or
  database-backed coordination before horizontal scaling.
- Minimize/redact owner and Deal data sent to Gemini, strengthen evidence-ID
  grounding, normalize stored provider failure details, and make audit records
  append-only with complete actor/request correlation and an immutable sink.
- Add global abuse/load tests and webhook signature/replay tests when external
  notification or webhook ingestion is implemented. No inbound webhook exists
  in the current application.

## Owner Overload Detection

- Added deterministic owner workload scoring from current active Deal records,
  using configured limits for active deals, high-risk deals, overdue follow-ups,
  and optional pipeline value. Persisted owner capacity values identify owners
  and define limits but do not replace live Deal aggregation.
- Added owner-subject incidents with evidence, create/update/deduplicate/resolve
  lifecycle behavior, composite monitoring scans, and Alembic revision
  `20260807_16_add_owner_overload_detection`.
- Grounded Gemini RCA for owner incidents in the computed workload, affected
  Deals, team capacity, and governed actions. Deal-specific follow-up and
  reassignment actions reject owner incidents with HTTP 409.
- Extended API and frontend contracts for nullable Deal/owner subjects. The
  incident detail page has an owner-specific presentation, the dashboard lists
  owner subjects and calculates capacity from current active Deals, and the
  monitoring settings page exposes owner detection plus all four workload
  limits.
- Added focused coverage for scoring, lifecycle, API detail, RCA context,
  action guards, and exact test-data cleanup.

Validation completed:

- Applied Alembic revision `20260807_16`; the full backend regression suite
  passes: 114 passed, 1 warning.
- The Next.js 16.3 production build passes.
- A controlled isolated scenario created one `owner_overload` incident at risk
  score 35 from 2 active Deals against a limit of 1, then removed the incident,
  Deals, owner capacity, and restored settings exactly.
- Browser validation on the existing frontend confirmed the owner monitoring
  controls, owner-aware incident subjects, and live owner capacity. The mobile
  dashboard at `390x844` has no horizontal document overflow and retains the
  owner capacity section.
- The backend is healthy at `http://127.0.0.1:8000`. Port 8000 is fixed: stop a
  stale listener and restart the current backend there instead of using 8001.

## Zoho Integration Route Reliability

- Investigated the integration-page `405 Method Not Allowed` against source,
  frontend requests, live OpenAPI, trailing-slash behavior, CORS, and Next.js
  configuration. The frontend correctly sent `POST
  /api/integrations/zoho/authorize`; the running non-reloading Uvicorn process
  exposed only the older GET route on that path. No rewrite, proxy, route
  conflict, trailing-slash redirect, or CORS failure changed the method.
- Restarted the backend from the current workspace so runtime route
  registration matches source. No OAuth method or provider flow was changed.
- Added a database-independent OpenAPI contract covering every Zoho
  integration route and method, including authorization, callback, status,
  connection test, Deal retrieval/sync, and disconnect.
- Integration action buttons now explicitly use `type="button"`. Backend
  failures surface a safe `HTTP {status}: {message}` in the existing alert,
  while browser navigation still occurs only after authorization startup
  succeeds.

Validation completed:

- Route contract and complete OAuth/Deal retrieval/synchronization endpoint
  slice passes: 28 tests.
- Frontend ESLint and the Next.js 16.3 production build pass.
- The pre-fix live reproduction returned 405 for POST authorization, 404 for
  test/sync/disconnect, and 401 for the registered GET status route. CORS
  preflight returned 200 and allowed POST; existing trailing-slash variants
  redirected with 307 only for registered routes.

## Zoho Integration Administration

- Added typed frontend clients for administrator-only Zoho status,
  authorization, connection testing, Deal synchronization, and disconnect
  endpoints.
- Added `/settings/integrations/zoho` with connection and adapter status,
  granted-scope inventory, synchronization facts and results, reconnect/test/
  sync controls, and confirmation-gated disconnect. OAuth continues in the
  provider browser flow; no provider credentials or tokens are accepted by the
  page.
- OAuth callback success and bounded error reasons are rendered from the URL.
  The route redirects missing local sessions to login and surfaces backend
  authorization failures inline.
- Added dashboard navigation to the integration page and removed the
  hard-coded Zoho synchronization age claim.

Validation completed:

- Full frontend ESLint passes.
- The Next.js 16.3 production build passes and statically prerenders the new
  route. The interactive query-parameter content is enclosed by the required
  Suspense boundary.
- Browser checks at desktop `1440x900` and mobile `390x844` found no document
  overflow; controls remain contained and destructive/sync controls are
  disabled while disconnected.
- No Zoho authorization, provider read, or provider write was initiated.
  Controlled live verification still requires account-owner sign-in and
  consent.

## Zoho Provider Adapter Hardening

- Active-user resolution now follows bounded Zoho user pagination instead of
  searching only the first 200 users. Owner names must still resolve to exactly
  one active provider user before a governed write proceeds.
- Approved Deal ownership updates now validate the single record-level Zoho
  result. An HTTP-success response containing a provider record error is
  rejected with a fixed, redacted HTTP 502 error instead of being reported as
  reassigned.
- Added adapter contracts for resolving an owner on a later page and rejecting
  record-level update failure without exposing provider response details.

Validation completed:

- Focused adapter contract tests pass: 6 passed.
- Complete OAuth, Deal retrieval, synchronization, and adapter suite passes:
  33 passed.
- Pylance reports no diagnostics in the provider adapter.
- Alembic reports the single expected `20260806_15 (head)` revision.
- The full backend run completed 106 tests successfully, then reported three
  RCA fixture setup errors because persisted `follow_up_tasks` rows still
  referenced an `agent_analyses` row the fixture attempted to delete. No test
  assertion failed, and this shared-database cleanup issue is outside the Zoho
  adapter changes.

## Zoho Deal Synchronization

- Added nullable unique `zoho_record_id`, `source` with a `local` server
  default, nullable `zoho_modified_at`, and nullable `last_synced_at` to the
  existing deals table through Alembic revision `20260806_15`. Existing demo
  and local deals are preserved and explicitly distinguished from Zoho rows.
- Added administrator-only `POST /api/integrations/zoho/sync/deals`. The
  service reuses validated Zoho fetching, creates or updates by provider record
  ID, skips records whose provider modified time has not advanced, isolates
  malformed records with savepoints, and returns bounded synchronization
  statistics and redacted error summaries.
- PostgreSQL uniqueness prevents duplicate local rows for one Zoho deal.
  Successful and unchanged Zoho rows are passed by local ID to the existing
  deterministic detector; local/demo deals are excluded from that post-sync
  scan.
- Synchronization start and terminal completion events are persisted in the
  existing audit log. Provider fetch failures and record-level failures use
  fixed, token-free summaries.
- The existing deals API now includes source and synchronization metadata so
  API/dashboard consumers can distinguish local and Zoho records.

Validation completed:

- Alembic reports `20260806_15 (head)`.
- Focused Zoho synchronization tests pass: 10 passed. Coverage includes create,
  update, idempotency, unchanged skipping, local preservation, malformed-row
  isolation, scoped detection, administrator authorization, redaction, and
  audit events.
- Full backend regression suite passes: 99 passed.
- VS Code diagnostics report no errors in all touched service, route, schema,
  model, migration, detector, and test files.
- The updated application reported `connected: false`; the safe pre-sync
  baseline was 16 local deals and zero Zoho deals. A controlled authenticated
  sync request returned the expected redacted HTTP 503 `Zoho CRM is not
  connected` and did not alter deal data.
- Real account synchronization, repeat-count verification, dashboard proof,
  and a live Zoho modification/update proof remain pending completion of the
  interactive Zoho sign-in and consent currently open in the shared browser.

## Read-Only Zoho Deal Fetching

- Added administrator-only `GET /api/integrations/zoho/deals` using the stored
  Zoho connection and its saved API domain.
- Access tokens are decrypted only for requests, refreshed before expiration,
  encrypted again before persistence, and refreshed once after a provider 401.
- The Zoho CRM V8 request selects only record ID, deal name, stage, amount,
  owner, closing date, created time, and modified time. Results are returned
  through a dedicated safe response contract and are not synchronized locally.
- Empty modules, missing Deals permission, rate limits, timeouts, malformed
  responses, and provider failures return bounded errors without provider
  payloads, tokens, or client credentials.

Validation completed:

- Focused mocked Zoho Deals tests pass: 7 passed. Coverage includes mapping,
  empty results, token refresh and encrypted persistence, permission/rate/
  provider failures, administrator authorization, and secret redaction.
- Full backend regression suite passes: 89 passed.
- VS Code diagnostics report no errors in the service, schema, route, or tests.
- A controlled authenticated request against the updated application reached
  the new endpoint and returned the expected safe HTTP 503 `Zoho CRM is not
  connected`. A live provider fetch still requires completion of the pending
  interactive Zoho consent callback so a real connection exists.

## Progress Tracking Rule

Every implementation, configuration, dependency, database, architecture, or
validation change made in this workspace must be recorded in this file during
the same work cycle. Update the relevant section, the validation status, and
the recommended next steps before considering a task complete.

## Project Goal

Build a proactive CRM operations agent for detecting and resolving bottlenecks
before they affect customers. Initial target scenarios are stalled deals,
overloaded sales owners, and Zoho synchronization failures.

The project artifacts reviewed so far are:

- `Product-Requirements-Document-PRD-Velocity-CRM-Agent.md`
- `architecture-a2-1785909290675.pdf`
- `velocity_crm_agent_single_agent.pdf`

## Architecture Decisions

- Use deterministic rules/statistical services for monitoring, bottleneck
  detection, and risk forecasting.
- Use Gemini for evidence-based root-cause analysis, recommendations,
  explanations, and controlled tool selection.
- Use one LangGraph Operations Super-Agent with a bounded flow:
  `Perceive -> Reason -> Plan -> Validate -> Approve/Act -> Verify -> Explain`.
- Require structured Gemini output and evidence references. Do not allow the
  model to execute arbitrary SQL or Zoho API calls.
- Keep write operations behind typed tools, authorization, entity limits,
  idempotency, audit logging, and human approval for high-impact actions.
- Use PostgreSQL as the operational source of truth. BigQuery, Redis, pgvector,
  and advanced ML can be added after the core end-to-end demo works.
- Primary hackathon demo: detect owner overload before SLA impact, propose a
  small lead reassignment, obtain manager approval, execute it, and verify the
  risk reduction.
- Proactive monitoring reuses the deterministic stalled-deal detector, records
  one database-backed run per cycle, prevents overlapping cycles, and never
  invokes Gemini inside detection. Optional automatic RCA is dispatched only
  after the deterministic cycle and its candidates have been persisted.

## Proactive Bottleneck Monitoring

- Added validated environment settings for enablement and interval control.
- Added the `monitoring_runs` persistence model, API response contracts, and
  Alembic revision `20260806_07`.
- Monitoring audit events can now reference a cycle without requiring an
  incident.
- Refactored stalled-deal scanning to return cycle statistics internally while
  preserving the manual scan endpoint contract.
- Each deal is isolated in a database savepoint so one malformed deal does not
  abort successful detections in the same cycle.
- Added a single-task proactive scheduler with immediate startup scanning,
  interval waits, overlap prevention, clean shutdown, and persisted cycle audit
  records.
- FastAPI starts monitoring after seed completion, stops it before database
  disposal, and exposes authenticated status and run-history endpoints.
- Added backend coverage for authenticated monitoring APIs, enabled/disabled
  startup, scheduled invocation, overlap refusal, cycle statistics/auditing,
  and clean shutdown.
- Added typed frontend monitoring clients and a dashboard operational status
  strip with 15-second status/incident polling; manual scans remain available
  as a secondary control.

Validation completed:

- VS Code diagnostics report no errors in the monitoring settings, models,
  schemas, or migration.
- Alembic revision `20260806_07` was applied and is the current schema head.
- Existing deterministic detector and manual endpoint tests pass: 9 passed.
- Focused monitoring service, API, overlap, shutdown, persistence, and per-deal
  isolation tests pass: 6 passed.
- Full backend regression suite passes: 45 passed.
- Frontend ESLint and production Next.js build pass.
- Desktop `1440x900` and mobile `390x844` dashboard checks found no document,
  text, or control overflow; screenshots are stored in `.local/`.
- Live automatic proof succeeded with a 3-second runtime interval: healthy deal
  `AUTO-MONITOR-LIVE-PROOF-84d421a0` initially had no incident, then became
  stale through CRM timestamp updates. Without calling the manual scan route,
  monitoring run `87d27d44-17f8-4ff5-a754-f0f9e647b564` completed and created
  incident `80c73810-3b90-4486-b23a-337935c5df73` at risk score 100.
- Gemini remained outside monitoring: `agent_analyses` stayed at 47 before and
  after the live automatic detection.

The backend is currently running at `http://127.0.0.1:8000` with the persisted
5-second monitoring interval. The frontend remains available at
`http://localhost:3000`.

## Admin-Managed Monitoring Settings

- Added a singleton `MonitoringSettings` persistence model and Alembic revision
  `20260806_08` with administrator attribution and timestamps.
- Added validated settings contracts: scan intervals are limited to 5-3600
  seconds and stage/inactivity thresholds to 1-8760 hours.
- Added idempotent default seeding that preserves current behavior: monitoring
  enabled, 60-second scans, 168-hour stage SLA, 120-hour inactivity threshold,
  and overdue follow-up detection enabled.
- Added admin-only settings GET/PUT APIs. Successful updates persist the editor,
  write an audit event containing old/new values, wake the live scheduler, and
  are reflected by the monitoring status API without restarting the backend.
- Detector scoring now accepts hour-based rules and can disable overdue
  follow-up scoring while retaining legacy defaults for direct callers.
- The scheduler remains dormant when monitoring is disabled so an administrator
  can re-enable it at runtime; API status still represents disabled monitoring
  as inactive.
- Added the admin monitoring settings page with numeric bounds, binary controls,
  loading/saving/success/error states, and dashboard navigation.
- Applied migration `20260806_08` and validated 48 backend tests, frontend lint,
  and the Next.js production build including `/settings/monitoring`.
- Live no-restart proof: changed inactivity threshold from 120 to 24 hours in
  the UI at 06:15:15Z; the running scheduler applied `threshold_hours: 24` to
  incident evidence at 06:15:17Z. A following completed run scanned 8 deals
  with zero errors.
- Monitoring cycles are serialized across service instances in the same event
  loop, preventing concurrent scheduler/manual-service mutations while keeping
  same-service overlap rejection. Final validation: 48 backend tests passed.
- Automatic RCA milestone in progress: added safe persisted defaults (disabled,
  minimum risk 80), incident analysis states/fingerprints, and a unique active
  analysis claim to prevent concurrent Gemini work for one incident.

## Automatic Agentic Root-Cause Analysis

- Added Alembic revision `20260806_09` for administrator-controlled automatic
  RCA settings, incident analysis state/fingerprints, analysis trigger/input
  fingerprints, and a partial unique index allowing only one `RUNNING`
  analysis per incident.
- Safe defaults keep automatic RCA disabled with a minimum risk score of 80;
  API validation limits the score to 0-100.
- Deterministic detection emits analysis candidates only for newly created or
  materially changed open incidents. Gemini remains outside the detector and
  cannot prevent monitoring run persistence.
- Monitoring dispatches eligible candidates after cycle persistence, limits
  automatic Gemini work to three concurrent analyses, isolates per-incident
  failures, records low-risk skips, and links start/completion/failure audits
  to the originating monitoring run.
- Transactional database claims, incident fingerprints, and the active-analysis
  uniqueness constraint prevent duplicate work across repeated cycles and
  concurrent service instances. Materially changed evidence can be analyzed
  again.
- Incidents expose `PENDING_ANALYSIS`, `ANALYZING`, `ANALYZED`, and
  `ANALYSIS_FAILED`. Manual Analyze remains available for retries and uses the
  same claim and audit workflow.
- The monitoring settings page now controls automatic analysis and its minimum
  risk score. Dashboard incidents show exact analysis labels, and incident
  details poll while analysis is pending/running so completed recommendations
  appear without a manual reload or Analyze click.
- Corrective actions remain separately governed and are never executed by the
  automatic RCA workflow.

Validation completed:

- Alembic current revision and repository head both report `20260806_09`.
- Full backend regression suite passes: 52 passed. Coverage includes high-risk
  dispatch, low-risk skip, disabled runtime behavior, unchanged-input
  deduplication, material-change reanalysis, success/failure state transitions,
  audit linkage, bounded failure isolation, manual retries, and score bounds.
- Frontend ESLint passes and the Next.js production build completes with all
  routes and TypeScript checks.
- VS Code diagnostics report no errors in the four touched frontend files.
- The sole test warning is an upstream Google GenAI deprecation warning for
  `_UnionGenericAlias` on Python 3.14.

## Safe Corrective Action: Create Follow-Up Task

- Added Alembic revisions `20260806_10` and `20260806_11` for safe-action
  settings, analysis provenance, structured execution results, nullable
  automatic-action attribution, completion timestamps, and active-only task
  uniqueness. Historical completed/cancelled/failed tasks are retained while
  only one `PENDING` or `IN_PROGRESS` task may exist per incident.
- Added a typed CRM adapter boundary with a deterministic local adapter. The
  service locks the incident, validates a completed `CREATE_FOLLOW_UP`
  recommendation, claims the task before the external side effect, applies the
  configured due window, records before/after audit state, and transitions the
  incident to `OBSERVING` only after success.
- Manual execution is authenticated and idempotent. Incident details and the
  dedicated action-history endpoint expose execution source, result, assignee,
  deadline, status, analysis provenance, and the audit timeline.
- Automatic execution is disabled independently by default and is strictly
  gated by enabled automatic RCA, enabled safe actions, a completed analysis,
  exact `CREATE_FOLLOW_UP` action type, no approval requirement, and the saved
  confidence threshold. No other action type can execute automatically.
- Adapter failures roll back the task claim, emit `AUTOMATIC_ACTION_FAILED` for
  automatic attempts, and do not fail the completed monitoring cycle.
- Added administrator controls for automatic safe actions and the 1-720 hour
  follow-up window. Incident details continuously poll for automatic changes
  and display action history plus the linked audit timeline.

Validation completed:

- Alembic reports `20260806_11 (head)`.
- Full backend regression suite passes: 60 passed. Focused follow-up coverage:
  9 passed; focused monitoring and automatic-action coverage: 17 passed.
- Frontend TypeScript, ESLint, and the production Next.js build pass.
- Authenticated `curl.exe` validation created an idempotent manual task, moved
  incident `42237aa1-6060-40e2-9f3c-bf4288db2816` to `OBSERVING`, returned CRM
  result `CREATED`, and exposed matching action history and timeline records.
- Deterministic live proof used a local structured provider, never Gemini:
  monitoring run `e796e98e-d9fd-4069-b9a0-a44828e4b2ba` detected a risk-100
  stale deal, completed RCA with `CREATE_FOLLOW_UP` and no approval, created
  automatic task `be02261d-3d5d-4339-8c12-3d928728e1e2`, applied the saved
  36-hour due window, and moved incident
  `f9e7c54c-456b-4db4-b4db-4d59c1a8c48e` to `OBSERVING`.
- The proof audit chain contains `AUTOMATIC_ANALYSIS_STARTED`,
  `AUTOMATIC_ANALYSIS_COMPLETED`, and `CREATE_FOLLOW_UP`. The temporary
  automatic-RCA prerequisite was restored to its original disabled value.
- The restarted backend returned readiness HTTP 200 and exposed the automatic
  result through authenticated APIs. Desktop and mobile browser checks found
  no horizontal overflow or control overlap on incident and monitoring settings
  pages; automatic source/result, owner, safe-action toggle, and the 36-hour
  due window rendered correctly.

## Approval-Controlled Deal Owner Reassignment

- Added Alembic revision `20260806_12`, persisted owner capacities, approval
  requests, a pending-only uniqueness constraint, and an emergency high-impact
  action disable control.
- Reassignment requests require a current completed `REQUEST_REASSIGNMENT`
  recommendation marked for approval. Gemini remains advisory; only an
  administrator can approve or reject execution.
- Approval execution locks and revalidates the approval, incident, deal,
  settings, current owner, proposed owner activity, and available capacity
  immediately before using the typed CRM adapter.
- Successful execution records reviewer attribution and before/after audit
  snapshots, updates both owner capacities, and moves the incident to canonical
  lowercase `observing`. Repeated approval is idempotent.
- CRM exceptions and explicit non-success statuses persist
  `EXECUTION_FAILED` without changing local deal ownership.
- Overdue requests are transactionally moved from `PENDING` to `EXPIRED` during
  request and read paths, emit an expiration audit event, and no longer block a
  replacement request.
- Detection treats `open`, `observing`, and legacy `OBSERVING` incidents as the
  same active incident, normalizes the legacy value, and does not create a
  duplicate while post-action verification is underway.
- Added the incident reassignment controls, Approval Inbox, administrator review
  detail, capacity evidence, terminal-state filters, and monitoring settings
  kill switch. Malformed stored user data no longer crashes the review page.

Validation completed:

- Alembic revision `20260806_12` was applied.
- Focused reassignment coverage passes: 11 tests. Combined reassignment and
  follow-up lifecycle coverage passes: 20 tests, including a detector scan after
  execution that confirms only one incident remains.
- Full backend regression suite passes: 71 tests.
- Frontend TypeScript, ESLint, and the production Next.js build pass, including
  `/approvals`, `/approvals/[approvalId]`, and incident/settings integration.
- The sole test warning remains the upstream Google GenAI `_UnionGenericAlias`
  deprecation warning on Python 3.14.

## Outcome Verification and Automatic Incident Resolution

- Added Alembic revision `20260806_13` and the `IncidentOutcome` model for
  action-linked schedules, baseline/current risk, fresh CRM evidence,
  deterministic outcomes, retry timing, and verification history. A partial
  unique index permits only one pending/running check per incident.
- Added administrator settings for outcome enablement, initial/retry delay,
  maximum checks, and the deterministic resolution risk threshold. Defaults
  are enabled, 60 minutes, three checks, and risk 20.
- Extended the typed CRM adapter with fresh deal snapshots. Successful
  follow-up and reassignment actions now start observation and schedule an
  outcome check in the same transaction.
- Added a deterministic outcome service that reuses stalled-deal detection,
  compares activity, follow-up, stage, owner, action status, and risk changes,
  and returns `SUCCESSFUL`, `PARTIALLY_SUCCESSFUL`, `FAILED`,
  `AWAITING_EVIDENCE`, or `RECURRED`. Gemini is never called by verification.
- Observing incidents are resolved only when the configured risk threshold and
  original bottleneck conditions clear. Unchanged/partial evidence schedules
  another check; exhausted checks or failed actions escalate the incident.
  Genuine recurrence reopens the same incident as `open` and resets analysis.
- Monitoring runs process due checks after deterministic scanning with isolated
  error auditing. Added authenticated outcome history, administrator-only
  manual verification, outcomes in incident detail, and complete transition
  audit events.
- Added monitoring controls plus an incident outcome panel showing risk delta,
  deterministic reason, evidence indicators, next check, history, and an
  administrator-only `Verify Outcome Now` command.

Validation completed:

- Migration `20260806_13` was applied successfully.
- Focused outcome coverage passes: 5 tests for scheduling/deduplication,
  authorization, deterministic resolution without analysis, retry/escalation,
  and recurrence.
- Full backend regression suite passes: 76 tests. The sole warning remains the
  upstream Google GenAI `_UnionGenericAlias` deprecation on Python 3.14.
- Frontend ESLint and the Next.js production build pass, including TypeScript
  validation and all static/dynamic routes.
- Backend readiness and frontend login both return HTTP 200 on ports 8000 and
  3000. The live settings page renders persisted outcome defaults and bounds
  without horizontal overflow; legacy uppercase `OBSERVING` incidents now
  render the observation panel consistently.
- Live administrator verification on incident
  `f9e7c54c-456b-4db4-b4db-4d59c1a8c48e` collected fresh local CRM evidence,
  persisted an unchanged `100 -> 100` risk result as `AWAITING_EVIDENCE`, kept
  the incident observing, emitted outcome audit events, and scheduled the next
  check. Desktop and `390x844` mobile checks show the settings controls,
  evidence badges, risk delta, and verification history without overflow.

## Zoho CRM OAuth Development Connection

- Added settings-backed Zoho client ID, client secret, India accounts URL,
  exact callback URI, and read-only Deals scopes without adding synchronization
  or frontend behavior.
- Added Alembic revision `20260806_14` for temporary OAuth states and encrypted
  Zoho connection credentials. Only SHA-256 state hashes are stored; states
  expire after ten minutes and are consumed before token exchange so failures
  cannot be replayed.
- Added administrator-only authorization and status endpoints plus the public
  provider callback. Authorization requests offline access and explicit consent
  from `accounts.zoho.in`; status exposes only connection state, API domain,
  authorized scopes, and connection time.
- Access and refresh tokens are Fernet-encrypted before persistence. Callback
  and error responses never return provider credentials, tokens, or exchange
  response payloads.

Validation completed:

- Migration `20260806_14` was applied and Alembic reports it as the current
  head.
- Focused OAuth coverage passes for URL generation, hashed state persistence,
  valid callback and encrypted storage, invalid/expired/reused states, exchange
  failure consumption, administrator protection, and secret redaction: 6 tests.
- Full backend regression suite passes: 82 tests. The existing Google GenAI
  deprecation warning remains.
- Live authorization returned HTTP 307 to `accounts.zoho.in/oauth/v2/auth` with
  the exact registered `localhost:8000` callback and reached Zoho sign-in. The
  provider-authenticated consent and real callback remain pending interactive
  sign-in in the open browser.

## Completed Backend Setup

The `backend/` FastAPI project has been created with:

- Dedicated virtual environment: `backend/.venv`
- FastAPI and Uvicorn
- Async SQLAlchemy and asyncpg
- Pydantic settings loaded from `backend/.env`
- Application package under `backend/app/`
- Root endpoint: `GET /`
- Liveness endpoint: `GET /health/live`
- Database readiness endpoint: `GET /health/ready`
- Dependency pins in `backend/requirements.txt`
- Setup documentation in `backend/README.md`

Validation completed:

- Python compile check passed.
- VS Code reported no errors in `backend/`.
- `GET /health/live` returned HTTP 200 with `{"status":"ok"}`.
- `GET /health/ready` returned HTTP 200 with
  `{"status":"ok","database":"velocity"}`.

## Admin User and Schema

Alembic migration support and the first versioned schema migration were added.
Revision `20260805_01` creates the `users` table with:

- UUID primary key
- Unique, indexed email address
- Argon2 password hash (plaintext passwords are never stored)
- `is_admin` and `is_active` flags
- `created_at` and `updated_at` timestamp metadata

Application startup atomically seeds one local admin with PostgreSQL
`ON CONFLICT DO NOTHING`, making repeated or concurrent startup safe.

Local development admin credentials are configured in the ignored
`backend/.env` file:

- Email: `admin@velocitycrm.com`
- Password: `VelocityAdmin@2026`

The password must be changed for any shared, staged, or production deployment.
Validation confirmed that exactly one active admin exists, its stored value is
an Argon2 hash, timestamps are populated, and the configured password verifies
against that hash. The focused concurrent seed test passed.

## PostgreSQL Setup

PostgreSQL was not installed on the machine. PostgreSQL 17.10 was downloaded
from the official EDB Windows binary distribution and installed as a local,
non-admin project runtime.

- Runtime directory: `.local/postgresql-dist/pgsql`
- Data directory: `.local/pgdata`
- Host: `localhost`
- Port: `5432`
- Database: `velocity`
- Application role: `velocity_app`
- Local development password: `velocity_dev`
- Connection URL is stored in the ignored file `backend/.env`.

The local cluster uses loopback development trust authentication. It is for
local hackathon development only and must not be reused as a production
configuration. The application still connects through the dedicated
`velocity_app` role.

Database lifecycle commands, run from `backend/`:

```powershell
& .\scripts\start-postgres.ps1
& .\scripts\stop-postgres.ps1
```

Both `.local/` and environment files are excluded from source control.

The project-local PostgreSQL 17 runtime now includes pgvector `0.8.6`. The
verified PG17 x64 release archive had SHA-256
`420388e9e9f05d92f06d6967ce8772483629b27a66ca9255925fa0fdd445438e`.
The `vector` extension was enabled once by the cluster owner; the routine
`velocity_app` role remains a non-superuser.

## Running the Backend

From the workspace root:

```powershell
& .\backend\scripts\start-postgres.ps1
Set-Location backend
& .\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Development URLs:

- API: `http://127.0.0.1:8000`
- OpenAPI docs: `http://127.0.0.1:8000/docs`
- Liveness: `http://127.0.0.1:8000/health/live`
- Database readiness: `http://127.0.0.1:8000/health/ready`

Runtime status verified on 2026-08-05:

- Project-local PostgreSQL is running on port `5432`.
- Uvicorn is running on `http://127.0.0.1:8000` with reload enabled.
- `/health/live` returned `{"status":"ok"}`.
- `/health/ready` returned `{"status":"ok","database":"velocity"}`.

Runtime state should always be checked when starting a new session.

## Frontend Setup and Experience

The `frontend/` application has been created with:

- Node.js 24.19.0 and npm 11.17.0
- Next.js 16.3.0 with the App Router, React 19, and TypeScript
- Tailwind CSS v4
- shadcn UI using the Radix Nova style and Lucide icons
- Geist Sans and Geist Mono through `next/font`
- A warm light theme with a cherry-red primary accent
- shadcn Button, Input, Label, Checkbox, and Separator primitives

The public landing page at `/` includes a full-bleed Unsplash hero, responsive
navigation, product positioning, a pipeline-risk preview, outcome sections,
security messaging, and calls to action that lead to `/login`.

The login page at `/login` includes:

- A full-height Unsplash collaboration image on desktop
- A focused, single-column form on mobile
- Work email and password fields
- A functional password visibility toggle
- Remember-me, password-recovery, and administrator-contact affordances
- Responsive layouts without horizontal overflow

External Unsplash images use direct loading because the local Next.js image
optimizer returned HTTP 500 while proxying the remote assets. Both direct image
sources were confirmed to decode successfully in the browser.

## Authentication and Operations Dashboard

The frontend is now wired to FastAPI through a typed client in
`frontend/src/lib/api.ts`. The login form submits the seeded administrator
credentials to `POST /auth/login`, stores the returned bearer token in browser
local storage, displays backend authentication errors, and routes successful
sessions to `/dashboard`.

The backend authentication and dashboard contract includes:

- `POST /auth/login` with email/password validation against PostgreSQL
- Argon2 password verification with safe invalid-password handling
- HS256 signed access tokens with an eight-hour local development lifetime
- Active-user validation through a bearer-token FastAPI dependency
- CORS for the local Next.js development origins
- `GET /dashboard/summary`, protected by bearer authentication
- Typed Pydantic schemas for metrics, pipeline stages, risk items, activities,
  and owner workload

`PyJWT==2.10.1` was added to `backend/requirements.txt` and installed in the
backend service virtual environment. The JWT secret has a local development
default and must be replaced through `backend/.env` before shared deployment.

The authenticated `/dashboard` experience includes:

- A persistent desktop sidebar and responsive shadcn Sheet navigation on mobile
- A sticky header with search, notifications, profile menu, and sign out
- Four shadcn KPI cards driven by the protected backend response
- Pipeline momentum visualization and owner-capacity Progress components
- A horizontally contained risk table ranked by exposure and urgency
- Live agent/system activity and operational health state
- Loading skeletons, API error feedback, refresh, and unauthenticated redirect

The current dashboard values are an initial backend-provided operational
snapshot. Replace them with database aggregates after the CRM event, lead,
incident, action, and owner tables are implemented; the frontend response shape
can remain stable during that transition.

Authentication/dashboard validation completed on 2026-08-05:

- Backend Pylance syntax and editor diagnostic checks passed.
- Live administrator login returned an active admin and an eight-hour token.
- The protected summary returned four metrics, four risks, and four owner loads.
- Frontend ESLint and the Next.js production build passed.
- `/dashboard` was statically generated and loaded protected API data after
  login.
- Desktop validation at `1440x900` rendered eight dashboard cards with no
  document-level horizontal overflow.
- Mobile validation at `390x844` rendered without document-level horizontal
  overflow and the sidebar opened with all navigation items visible.
- The mobile navigation trigger has an explicit accessible label.

Frontend validation completed on 2026-08-05:

- ESLint passed.
- The production build compiled successfully with TypeScript checks.
- `/` and `/login` were statically prerendered.
- Landing page checks passed at `1440x900` and `390x844`.
- Login page checks passed at `1440x900` and `390x844`.
- Both Unsplash images decoded successfully at their source dimensions.
- No horizontal overflow was detected on either inspected viewport.
- The landing page preserves a visible hint of the next section in the first
  viewport on desktop and mobile.
- Navigation from `/` to `/login` and the password show/hide interaction were
  exercised successfully.

## Deal Management Milestone

The backend now includes a persisted `Deal` entity with UUID identity, precise
decimal value, stage and owner metadata, timezone-aware activity timestamps,
an optional next follow-up, status, and creation timestamp. Alembic revision
`20260805_02` creates the `deals` table and indexes its common filtering fields.

Startup seeding idempotently creates five realistic records representing a
healthy active deal, an inactive deal, an overdue follow-up, a high-value deal,
and a newly created deal. The authenticated `GET /api/deals` endpoint returns
these records newest first through the ORM-backed `DealResponse` schema.

Deal milestone validation completed on 2026-08-05:

- Alembic upgrade completed and the database reports `20260805_02 (head)`.
- Deal creation and persistence, authenticated listing, and response structure
  tests all passed (`3 passed`).
- The live endpoint returned exactly five seeded deals.
- An unauthenticated request to `/api/deals` returned HTTP 401.
- Backend editor diagnostics reported no errors.

The operations dashboard now consumes the protected Deal endpoint through the
existing authenticated frontend client. It derives total deals, active deals,
pipeline value, and attention count from live Deal records, and displays all
deals with stage, owner, value, activity, follow-up, and status fields. Currency
and dates use locale-aware formatting; overdue follow-ups are emphasized, and
loading, empty, and API-error states follow the established dashboard styling.

Live Deal dashboard validation completed on 2026-08-05:

- Authenticated API access returned five deals totaling `$750,500`.
- The browser rendered `5` total, `4` active, `$750,500` pipeline value, and
  `2` deals needing attention.
- All seven requested table columns and all five seeded Deal rows rendered.
- ESLint, TypeScript checks, and the Next.js production build passed.
- Desktop `1440x900` and mobile `390x844` checks found no document-level
  horizontal overflow; the wide Deal table remains contained in its scroller.
- Frontend editor diagnostics reported no errors.

## Stalled-Deal Detection Milestone

The backend now provides deterministic stalled-deal monitoring. Each scan
scores every Deal from three explainable signals: days in the current stage,
days since the last activity, and days that the next follow-up is overdue. The
score is clamped to `0-100`, maps to low/medium/high/critical severity, and
opens an incident at score `40` or higher.

Alembic revision `20260805_03` adds persisted `bottleneck_incidents` with
structured JSON evidence, risk and severity fields, lifecycle timestamps, and
a Deal foreign key. A PostgreSQL partial unique index and update-in-place scan
logic allow only one open `stalled_deal` incident per Deal. Subsequent scans
refresh its evidence and score; recovered Deals have their open incident
resolved.

The authenticated detection API includes:

- `POST /api/detection/scan` to evaluate Deals and return detected incidents.
- `GET /api/incidents` to list persisted incidents by descending risk score.

Stalled-deal validation completed on 2026-08-05:

- Alembic upgrade completed and the database reports `20260805_03 (head)`.
- Six focused tests cover healthy and inactive Deals, overdue follow-up risk,
  score bounds, repeated-scan deduplication, and authenticated listing.
- The full backend suite passed (`9 passed`).
- Two live seeded incidents were detected with scores `80` (critical) and `50`
  (medium); repeated scans preserved both incident IDs.
- Unauthenticated incident listing returned HTTP 401.
- Backend editor diagnostics reported no errors.

## Proactive Incident Dashboard Milestone

The frontend API client now models the complete `BottleneckIncident` response
and provides authenticated functions for `GET /api/incidents` and
`POST /api/detection/scan`. The operations dashboard loads incidents alongside
Deals and the dashboard summary, and includes a `Scan for Bottlenecks` action.

A scan disables conflicting controls, runs detection, then refreshes the
incident list, Deal data, and dashboard summary. The interface preserves
existing data during scan failures and presents explicit loading, scanning,
success, API-error, and empty states.

The dashboard now derives four live incident metrics:

- Active bottlenecks from open incidents.
- Critical incidents from open critical-severity incidents.
- High-risk incidents from open high-severity incidents.
- Pipeline value at risk from unique Deals with open incidents.

The responsive incidents table displays title, affected Deal, normalized
incident type, risk score, severity, status, and detection time. Low, medium,
high, and critical severities use distinct semantic badges, while unresolved
Deal references fall back to their UUID.

Proactive incident dashboard validation completed on 2026-08-05:

- Frontend ESLint passed.
- Next.js production build and TypeScript checks passed.
- Frontend editor diagnostics reported no errors.
- The live dashboard displayed two active incidents, one critical incident,
  zero high-severity incidents, and `$161,500` in unique Deal value at risk.
- The browser scan issued `POST /api/detection/scan`, received HTTP 200,
  refreshed dashboard data, restored the scan control, and announced
  `Scan complete. 2 active bottlenecks detected.`
- Desktop `1440x900` and mobile `390x844` checks found no document-level
  horizontal overflow; the incidents table remains contained in its scroller.

## Incident Details Milestone

The backend now exposes authenticated `GET /api/incidents/{incident_id}` with
the incident identity, type, title, status, severity, risk score, detection and
update timestamps, complete structured evidence, and a nested affected Deal.
Unknown incident UUIDs return HTTP 404, while missing or invalid credentials
remain protected by the shared bearer-token dependency.

Dashboard incident rows now open `/incidents/[incidentId]` and support mouse,
Enter, and Space activation. The details view includes:

- Risk score, severity, and lifecycle status summary.
- Affected Deal stage, value, owner, stage-entry, last-activity, and follow-up
  timestamps.
- Human-readable stage-duration, inactivity, and overdue-follow-up factors.
- Complete structured detector evidence.
- A timeline combining incident and Deal activity events.
- Loading, not-found, API-error with retry, and unauthenticated redirect states.

Incident details validation completed on 2026-08-05:

- Three endpoint tests cover required authentication, valid nested retrieval,
  and unknown incident handling; the full backend suite passed (`12 passed`).
- Frontend ESLint, TypeScript checks, and the Next.js production build passed.
- Next.js recognized `/incidents/[incidentId]` as a dynamic application route.
- Editor diagnostics reported no errors in the changed backend and frontend
  files.
- The live API returned HTTP 200 with matching nested Deal and evidence data,
  HTTP 404 for an unknown UUID, and HTTP 401 without authentication.
- Browser validation confirmed dashboard row navigation, all requested detail
  sections, the dedicated not-found state, and missing-token login redirect.
- Desktop `1440x900` and mobile `390x844` checks found no document-level
  horizontal overflow.

## Operational Policy Knowledge Base Milestone

Alembic revision `20260805_04` adds `knowledge_documents` and
`knowledge_chunks`, with versioned document uniqueness, ordered chunks,
structured metadata, 768-dimensional pgvector embeddings, and an HNSW cosine
index. Startup idempotently seeds five versioned policies for Deal stage SLAs,
stalled-Deal handling, sales follow-up, approval escalation, and Deal-owner
reassignment. The database contains five documents and ten section chunks.

Embedding generation uses a configurable service interface. Local development
and tests use a deterministic local embedder; `EMBEDDING_PROVIDER=google`
selects Google's `gemini-embedding-001` model when `GOOGLE_API_KEY` is set.
Both providers preserve the schema's 768-dimensional contract.

The authenticated knowledge API includes:

- `GET /api/knowledge/documents` to list versioned policies.
- `POST /api/knowledge/search` for pgvector cosine search by query, optional
  incident type, and a validated result limit.

Knowledge-base validation completed on 2026-08-05:

- Migration `20260805_04` applied successfully as non-superuser
  `velocity_app`; pgvector reports version `0.8.6` and the HNSW index uses
  `vector_cosine_ops`.
- Six focused tests cover document persistence, chunk storage, embeddings,
  semantic relevance, result limiting, and authentication (`6 passed`).
- The complete backend regression suite passed (`18 passed`).
- The query `deal inactive beyond stage SLA with overdue follow-up` ranked
  `Sales Follow-Up Procedure` first and `Stalled-Deal Handling` second.
- Both knowledge endpoints return HTTP 401 without bearer authentication.
- Application import and route-registration checks passed.

## Gemini Root Cause Analysis Milestone

Alembic revision `20260806_05` adds persisted `agent_analyses` and
`agent_audit_events`. Analysis rows retain structured completed output or a
sanitized failed state for retry. Audit rows record model name, latency, token
usage, policy count, success/failure status, and normalized error codes without
API keys or raw provider payloads.

The official `google-genai==1.62.0` SDK is wrapped by a reusable asynchronous
provider service configured through `GEMINI_API_KEY`, `GEMINI_MODEL`, and
`GEMINI_TEMPERATURE` (default `0.2`). Requests require JSON output validated by
a strict Pydantic schema, use bounded timeouts, and normalize missing
configuration, timeout, rate-limit, malformed-response, and provider errors.

The single-agent read-only workflow now:

- Loads the incident and affected Deal but excludes Deal/customer names and
  owner identity from the prompt.
- Retrieves five relevant policy chunks through the existing pgvector search.
- Separates trusted instructions from untrusted CRM and policy reference data.
- Restricts recommendations to four controlled action types and never executes
  CRM writes.
- Rejects policy citations that were not retrieved and forces human review,
  approval, and confidence below `0.5` when triggered evidence is absent.
- Persists every success or failure with a corresponding audit event; a latest
  `FAILED` row can be retried.

Authenticated RCA endpoints are:

- `POST /api/incidents/{incident_id}/analyze` to create or retry analysis.
- `GET /api/incidents/{incident_id}/analysis` to return the latest completed or
  failed state.

The incident detail page loads prior analysis and provides Analyze with AI,
analyzing, failure, and retry states. Completed results display summary, root
cause, supporting evidence, risk, recommendation, controlled action type,
confidence, approval requirement, policy references, and expected outcome.

RCA validation completed on 2026-08-06:

- Migration `20260806_05` applied successfully; Alembic reports it as head.
- Fourteen mocked tests cover grounded success, incident/Deal context,
  pgvector retrieval invocation, structured validation, invalid action type,
  invalid confidence, unsupported citations, insufficient-evidence fallback,
  unknown incidents, missing configuration, timeout/rate limiting, retry,
  authentication, and audit creation (`14 passed`).
- Backend-wide editor diagnostics and frontend RCA diagnostics reported no
  errors; frontend ESLint passed.
- An earlier blank-key check confirmed the sanitized local configuration error
  path before a credential was added; the current ignored local environment is
  now configured and verified without logging the key value.
- Browser validation loaded a persisted completed analysis for a real incident
  and rendered every RCA output field, controlled action, confidence, approval
  requirement, policy reference, model, and generation timestamp.
- An authenticated analysis request without a key returned the sanitized HTTP
  503 configuration error, persisted a failed attempt, and rendered the
  failure and Retry state after reload.
- The incident/RCA page had no document-level horizontal overflow at desktop
  (`842/842`) or mobile (`375/375` at a `390x844` viewport); the RCA heading,
  failed state, and Retry control remained visible on mobile.
- `backend/.env` remains ignored by Git. A fresh backend settings process
  confirmed that its local `GEMINI_API_KEY` is configured and that the selected
  model is `gemini-3-flash-preview`; no credential value was logged.
- A minimal live Google AI Studio request completed successfully on 2026-08-06
  using the official SDK and the backend virtual environment. The configured
  `gemini-3-flash-preview` model returned the requested `OK` response, verifying
  that the API key, model access, and provider connection are working.
- A full rerun on 2026-08-06 restored project-local PostgreSQL, confirmed
  Alembic revision `20260806_05 (head)`, passed all `32` backend tests, passed
  frontend ESLint, and completed the Next.js production build with the login,
  dashboard, and dynamic incident-detail routes.
- Clean backend and frontend processes passed API live/readiness checks and
  served the login page. The first full live RCA call recorded a retryable
  `GEMINI_PROVIDER_ERROR`; a minimal structured-output probe succeeded, and the
  endpoint retry then completed the same analysis row successfully.
- Live analysis `67d85a82-3e8b-460f-8d02-9755bb157f86` completed with model
  `gemini-3-flash-preview`, controlled action `SEND_MANAGER_ALERT`, required
  human approval, four supporting evidence items, and three validated policy
  references. The saved-result endpoint returned the completed analysis.
- The completed audit event recorded `27,648 ms` latency, five retrieved policy
  chunks, and token telemetry (`784` prompt, `324` output, `2,090` total), while
  preserving the preceding failed event as the retry audit trail.

## Create Follow-Up Corrective Action

Implementation is in progress for the first human-triggered corrective action.
The backend now defines a persisted `FollowUpTask` result with a database unique
constraint on `incident_id`, owner assignment, due date, status, authenticated
creator, and timestamps. Alembic revision `20260806_06` creates the table and
its foreign keys and indexes.

The authenticated create-follow-up action validates the latest saved analysis,
permits execution only for `CREATE_FOLLOW_UP`, derives the task from the affected
deal and validated recommendation, and performs task creation, incident status
transition to `OBSERVING`, and audit creation in one transaction. Repeated calls
return the existing task. An authenticated GET route exposes the persisted task
for incident-page reloads. Focused tests cover successful execution, invalid
recommendations, duplicate execution, unknown incidents, authentication,
incident status updates, and audit creation.

The incident details UI now loads persisted task state, presents an Execute
Follow-Up command only for a saved `CREATE_FOLLOW_UP` recommendation, refreshes
the incident to `OBSERVING` after execution, and displays the task title,
description, assignee, due date, pending task status, and completed execution
status. Migration `20260806_06` was applied and all seven focused backend tests
passed. Frontend lint/build, full regression tests, and live UI validation remain
pending.

Frontend lint and the production build passed. The first full backend regression
run identified uppercase severity in corrective-action test fixtures that leaked
into the shared development database; the fixture now uses the API's lowercase
severity contract and removes all generated deals and cascading records during
module teardown. The leaked test rows were removed and revalidation completed:

- Alembic reports `20260806_06 (head)`.
- The focused corrective-action suite passed all seven tests.
- The complete backend suite passed all 39 tests; the only warning is an
  upstream `google-genai` Python 3.17 deprecation notice.
- Frontend ESLint and the Next.js production build passed.
- Live UI verification used incident
  `af5f4462-5a3b-40a8-876f-8ad0cb388c93`, whose saved analysis recommends
  `CREATE_FOLLOW_UP`.
- The visible Execute Follow-Up control returned HTTP 200 and created task
  `d4584337-fb9f-4e2b-a96d-30c64dd94dcb`, assigned to Jordan Lee with a
  24-hour due date and `PENDING` task status.
- The page immediately displayed `OBSERVING`, task details, due date, assignee,
  and completed execution status. Reload preserved the result and removed the
  execute control.
- A repeated POST returned the same task ID and timestamps. PostgreSQL confirmed
  exactly one follow-up task, one `CREATE_FOLLOW_UP` audit event, and final
  incident status `OBSERVING`.
- Mobile validation at `390x844` displayed the persisted result without
  horizontal overflow.

## Running the Frontend

From the workspace root:

```powershell
Set-Location frontend
npm run dev
```

Development URL: `http://localhost:3000`

Runtime status verified on 2026-08-05: the Next.js development server is
running at `http://127.0.0.1:3000`, FastAPI is running at
`http://127.0.0.1:8000`, and project-local PostgreSQL is running on port `5432`.
All three services were fully stopped and restarted on 2026-08-05. Post-restart
checks returned HTTP 200 from the frontend, `ok` from both FastAPI health
endpoints, and `velocity` from a direct PostgreSQL database query.

## Recommended Next Steps

1. Move bearer storage from local storage to secure HTTP-only cookies before
  shared or production deployment and add refresh/revocation behavior.
2. Define initial tables: `crm_events`, `owners`, `leads`, `pipeline_stages`,
   `incident_candidates`, `agent_runs`, `agent_actions`, and
   `action_approvals`.
3. Build a synthetic Zoho event generator before integrating real credentials.
4. Add a canonical CRM event ingestion endpoint with duplicate-event handling.
5. Add deterministic owner-overload and synchronization-failure detectors.
6. Add incident recovery and resolution workflows to the operations dashboard.
7. Extend the read-only RCA workflow into the bounded LangGraph flow.
8. Add one human-approved write action for lead reassignment.
9. Replace the remaining dashboard snapshot with PostgreSQL aggregates and add
  detail views for risks, agent runs, approvals, and recovery verification.
10. Configure a Google AI Studio key and supported model, then complete the
  controlled live RCA smoke test.

## Scope Guardrails

- Do not begin with a multi-agent architecture.
- Do not use Gemini as the primary anomaly detector.
- Do not add BigQuery or Redis until the PostgreSQL workflow is demonstrated
  end to end; pgvector is limited to the operational policy retrieval layer.
- Do not expose unrestricted database or CRM tools to the model.
- Keep the demo focused on proactive detection, evidence, guarded action, and
  measurable recovery.