from dataclasses import dataclass


@dataclass(frozen=True)
class OperationalPolicy:
    title: str
    document_type: str
    version: str
    content: str


OPERATIONAL_POLICIES = (
    OperationalPolicy(
        title="Deal Stage SLA Rules",
        document_type="deal_stage_sla",
        version="1.0",
        content="""## Stage time limits
Qualified deals should progress within 5 days, Discovery within 7 days, Proposal within 10 days, and Negotiation within 7 days. A deal beyond its stage SLA requires owner review.

## SLA breach response
When a stage limit is exceeded, verify the latest customer activity and next follow-up. Record the reason for delay, schedule a recovery action, and escalate high-value blocked deals to the sales manager.""",
    ),
    OperationalPolicy(
        title="Stalled-Deal Handling",
        document_type="stalled_deal",
        version="1.0",
        content="""## Identification
A deal is stalled when it exceeds its stage SLA, has no recent customer activity, or has an overdue follow-up. Multiple signals increase urgency and should be handled as one incident.

## Recovery procedure
The owner must review the evidence, contact the customer, set a dated next step, and update the CRM within one business day. Critical incidents require manager visibility and a documented recovery plan.""",
    ),
    OperationalPolicy(
        title="Sales Follow-Up Procedure",
        document_type="sales_follow_up",
        version="1.0",
        content="""## Follow-up cadence
Every active deal must have a dated next follow-up. Customer interactions and outcomes must be logged on the same business day, with the next action assigned before the current task is closed.

## Overdue follow-up
An overdue follow-up must be completed or rescheduled immediately with a reason. If both customer activity and follow-up are overdue, notify the owner and flag the deal for stalled-deal review.""",
    ),
    OperationalPolicy(
        title="Approval Escalation",
        document_type="approval_escalation",
        version="1.0",
        content="""## Escalation thresholds
Pricing, legal, or security approvals blocked for more than two business days must be escalated to the responsible manager. Five-day blocks on high-value deals are critical.

## Escalation record
The request must identify the approver, decision needed, business impact, deadline, and prior follow-ups. Escalations remain open until a decision and CRM update are verified.""",
    ),
    OperationalPolicy(
        title="Deal-Owner Reassignment",
        document_type="deal_owner_reassignment",
        version="1.0",
        content="""## Reassignment criteria
Reassignment is permitted when the owner is unavailable, materially over capacity, or unable to complete a time-sensitive recovery action. Customer continuity and account expertise must be considered.

## Approval and handoff
A manager must approve reassignment. The handoff must include deal context, open commitments, customer contacts, next action, and due date. Notify both owners and verify the new owner in the CRM.""",
    ),
)