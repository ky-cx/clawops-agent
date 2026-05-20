"""
tools/ops_tools.py
Action Layer — Physical effectors available to the ClawOps Agent.

Each function's docstring is the authoritative contract fed to Gemini's
Function Calling schema.  Keep them precise, complete, and in English.
"""

import time
import random
from datetime import datetime, timezone


# ── Tool 1: Hardware reboot ───────────────────────────────────────────────────

def reboot_server(server_id: str) -> str:
    """
    Initiates an immediate hard reboot of the specified physical server in the
    DataVita data-centre fleet.

    This function sends an IPMI power-cycle command to the target server's
    baseboard management controller (BMC), waits for the POST sequence to
    complete, and verifies that the OS heartbeat is restored.  It is the
    canonical remediation action for CRITICAL hardware or kernel-level faults.

    Args:
        server_id: The unique identifier of the server to reboot, e.g.
                   "srv-dc1-001".  Must match a registered asset in the
                   DataVita CMDB.  Rebooting the wrong server causes outage,
                   so verify the ID against the incident log before calling.

    Returns:
        A plain-text status string describing the outcome, including:
        - Confirmation that the IPMI command was accepted.
        - Observed POST duration in seconds.
        - Final OS health-check result (PASS / FAIL).
        - Timestamp of service restoration in ISO-8601 UTC format.

    Raises:
        Does not raise; all errors are encoded in the return string so the
        calling agent can decide on follow-up actions without exception
        handling overhead.
    """
    print(f"    [TOOL] reboot_server called → target: {server_id}")
    time.sleep(1)  # simulate IPMI round-trip latency

    post_seconds = random.randint(28, 47)
    restored_at  = datetime.now(timezone.utc).isoformat()

    # Simulate a 5 % chance of POST failure for realism
    if random.random() < 0.05:
        return (
            f"REBOOT_RESULT | server_id={server_id} | status=FAIL | "
            f"reason=POST_TIMEOUT after {post_seconds}s | "
            f"action_required=ESCALATE_TO_ON_SITE_ENGINEER | timestamp={restored_at}"
        )

    return (
        f"REBOOT_RESULT | server_id={server_id} | status=SUCCESS | "
        f"ipmi_cmd=ACCEPTED | post_duration={post_seconds}s | "
        f"os_heartbeat=RESTORED | health_check=PASS | "
        f"service_restored_at={restored_at}"
    )


# ── Tool 2: Compliance e-mail dispatch ───────────────────────────────────────

def send_compliance_email(report_content: str) -> str:
    """
    Delivers a structured incident or compliance report to the DataVita
    on-call distribution list and the regulatory audit mailbox.

    The function serialises the report body, attaches a UTC timestamp and a
    unique message-ID, and dispatches it via the internal SMTP relay
    (compliance-relay.datavita.internal:587 / TLS).  A copy is
    simultaneously archived to the immutable audit log bucket
    (s3://datavita-audit-logs/emails/).

    Args:
        report_content: The full plain-text body of the report to be sent.
                        Must be written in formal English and must contain the
                        following three sections, each prefixed by its header:
                          [INCIDENT OVERVIEW]
                          [ROOT CAUSE ANALYSIS]
                          [RESOLUTION DETAILS]
                        Reports missing any section are rejected by the
                        compliance gateway with a 422 error.

    Returns:
        A plain-text delivery receipt string containing:
        - Unique message-ID assigned by the SMTP relay.
        - Recipient addresses (masked for PII compliance).
        - Delivery status (QUEUED / DELIVERED / REJECTED).
        - Archive S3 URI of the stored copy.
        - Dispatch timestamp in ISO-8601 UTC format.

    Raises:
        Does not raise; SMTP or archival errors are encoded in the return
        string so the calling agent can log and retry without crashing.
    """
    print(f"    [TOOL] send_compliance_email called → report length: {len(report_content)} chars")
    time.sleep(0.5)  # simulate SMTP relay latency

    import uuid
    msg_id       = f"CLAWOPS-{uuid.uuid4().hex[:12].upper()}"
    dispatched_at = datetime.now(timezone.utc).isoformat()
    archive_uri  = f"s3://datavita-audit-logs/emails/{msg_id}.txt"

    # Validate required sections
    required_sections = ["[INCIDENT OVERVIEW]", "[ROOT CAUSE ANALYSIS]", "[RESOLUTION DETAILS]"]
    missing = [s for s in required_sections if s not in report_content]
    if missing:
        return (
            f"EMAIL_RESULT | message_id={msg_id} | status=REJECTED | "
            f"reason=MISSING_SECTIONS:{','.join(missing)} | timestamp={dispatched_at}"
        )

    return (
        f"EMAIL_RESULT | message_id={msg_id} | status=DELIVERED | "
        f"recipients=[oncall-dl@datavita.io, audit@datavita.io] | "
        f"archive={archive_uri} | dispatched_at={dispatched_at}"
    )
