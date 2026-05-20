"""
main.py — ClawOps Agent · DataVita SRE Automation
===================================================
Industrial-grade autonomous operations loop built with the Google Generative AI
native SDK (google-genai).  Implements a full Sense → Think → Act closed-loop
using Gemini's Function Calling without any third-party agent framework.

Architecture
------------
  Perception  : utils/log_generator.get_latest_server_logs()
  Cognition   : Gemini 2.5 Flash via google.genai (multi-turn function-call loop)
  Action      : tools/ops_tools.{reboot_server, send_compliance_email}
  Resilience  : Hard-coded SMS fallback on any unrecoverable exception
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
import traceback
from typing import Any

# ── Env & path setup ─────────────────────────────────────────────────────────
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass  # python-dotenv is optional; export GEMINI_API_KEY manually if absent

# ── Project imports ───────────────────────────────────────────────────────────
from utils.log_generator import get_latest_server_logs
from tools.ops_tools import reboot_server, send_compliance_email

# ── Google GenAI SDK ──────────────────────────────────────────────────────────
try:
    from google import genai
    from google.genai import types
except ImportError as exc:
    sys.exit(
        f"[FATAL] google-genai package not found. "
        f"Run: pip install google-genai python-dotenv\nOriginal error: {exc}"
    )

# ── Constants ─────────────────────────────────────────────────────────────────
MODEL_ID       = "gemini-2.5-flash"
MAX_TOOL_TURNS = 10   # Safety cap: prevent infinite tool-call loops

# ── Colour helpers for terminal output ───────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    GREY   = "\033[90m"
    BLUE   = "\033[94m"

def banner(title: str, colour: str = C.CYAN) -> None:
    width = 70
    print(f"\n{colour}{C.BOLD}{'═' * width}")
    print(f"  {title}")
    print(f"{'═' * width}{C.RESET}")

def section(label: str, colour: str = C.BLUE) -> None:
    print(f"\n{colour}{C.BOLD}── {label} ──{C.RESET}")

def log(msg: str, colour: str = C.GREY) -> None:
    print(f"{colour}{msg}{C.RESET}")


# ═════════════════════════════════════════════════════════════════════════════
# Tool registry
# Maps Gemini tool-call names → (callable, argument_schema)
# ═════════════════════════════════════════════════════════════════════════════

def _build_tool_declarations() -> list[types.Tool]:
    """
    Constructs native google.genai Tool objects from the ops_tools docstrings.
    Keeping schema definitions co-located here makes diffs readable and avoids
    schema/implementation drift.
    """
    reboot_fn = types.FunctionDeclaration(
        name="reboot_server",
        description=(
            "Initiates an immediate hard reboot of a physical server via IPMI power-cycle. "
            "Use this tool ONLY when a server is confirmed CRITICAL in the log snapshot. "
            "Verify server_id against the incident log before calling."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "server_id": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "Unique DataVita CMDB identifier of the target server, "
                        "e.g. 'srv-dc1-001'.  Must match the server_id field in the log."
                    ),
                )
            },
            required=["server_id"],
        ),
    )

    email_fn = types.FunctionDeclaration(
        name="send_compliance_email",
        description=(
            "Dispatches a formal incident or compliance report via the DataVita internal SMTP relay "
            "to the on-call distribution list and the regulatory audit mailbox.  "
            "The report_content MUST contain the three required section headers: "
            "[INCIDENT OVERVIEW], [ROOT CAUSE ANALYSIS], [RESOLUTION DETAILS].  "
            "Call this tool only after a reboot attempt has been made and the report is fully drafted."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "report_content": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "Full plain-text body of the incident report in formal English.  "
                        "Include all three mandatory sections."
                    ),
                )
            },
            required=["report_content"],
        ),
    )

    return [types.Tool(function_declarations=[reboot_fn, email_fn])]


# ── Local tool dispatcher ─────────────────────────────────────────────────────

TOOL_MAP: dict[str, Any] = {
    "reboot_server":        reboot_server,
    "send_compliance_email": send_compliance_email,
}

def dispatch_tool(name: str, args: dict) -> str:
    """Execute the named tool locally and return its string result."""
    fn = TOOL_MAP.get(name)
    if fn is None:
        return f"ERROR: Unknown tool '{name}'. No action taken."
    try:
        return fn(**args)
    except Exception as exc:  # noqa: BLE001
        return f"TOOL_EXCEPTION | tool={name} | error={exc}"


# ═════════════════════════════════════════════════════════════════════════════
# Core Agent loop
# ═════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = textwrap.dedent("""
    You are ClawOps Agent, an elite autonomous Site Reliability Engineer (SRE)
    AI operating inside the DataVita production data centre.

    Your mission is to monitor server health logs and resolve incidents with
    zero human intervention.  You have two tools at your disposal:

      • reboot_server          — Hard-reboot a CRITICAL server via IPMI.
      • send_compliance_email  — Dispatch a formal incident report.

    === OPERATING RULES ===

    SCENARIO A — CRITICAL server detected:
      1. Identify every server whose "status" is "CRITICAL".
      2. For EACH critical server, call reboot_server with the correct server_id.
      3. After ALL reboots are attempted, draft a single consolidated
         Incident Report in formal English.  The report MUST contain exactly
         these three section headers (verbatim):
           [INCIDENT OVERVIEW]
           [ROOT CAUSE ANALYSIS]
           [RESOLUTION DETAILS]
         Be thorough: include server IDs, error codes, error messages, reboot
         outcomes, timestamps, and recommended preventive actions.
      4. Call send_compliance_email with the full report as report_content.
      5. After the email is confirmed delivered, output a concise human-readable
         summary of what happened and what you did.

    SCENARIO B — All servers ONLINE:
      • Do NOT call any tools.
      • Output a brief, professional routine patrol summary covering cluster
        health metrics (CPU, memory, disk averages), uptime, and a green-light
        confirmation.

    === GUARDRAILS ===
    • Never fabricate server IDs.  Use only the IDs present in the log data.
    • Never call reboot_server on an ONLINE server.
    • Never call send_compliance_email unless a reboot was performed.
    • Be concise in tool arguments; be thorough in the incident report body.
""").strip()


def run_agent() -> None:
    """
    Main entry point.  Runs one full Sense → Think → Act cycle.
    Raises on unrecoverable errors so the caller can trigger the SMS fallback.
    """
    # ── 1. Sense: Fetch logs ──────────────────────────────────────────────────
    section("PHASE 1 — SENSE: Ingesting cluster telemetry", C.CYAN)
    raw_logs = get_latest_server_logs()
    log_data = json.loads(raw_logs)

    critical_servers = [s for s in log_data["servers"] if s["status"] == "CRITICAL"]
    healthy_count    = log_data["total_servers"] - len(critical_servers)

    log(f"  Cluster      : {log_data['cluster']}", C.GREY)
    log(f"  Snapshot time: {log_data['snapshot_time']}", C.GREY)
    log(f"  Total servers: {log_data['total_servers']}", C.GREY)

    if critical_servers:
        for s in critical_servers:
            print(
                f"  {C.RED}{C.BOLD}⚠  CRITICAL{C.RESET}  "
                f"{s['server_id']} | {s['error_code']} | {s['error_msg'][:80]}…"
            )
    else:
        log(f"  Status       : {C.GREEN}ALL {healthy_count} SERVERS ONLINE{C.RESET}", "")

    # ── 2. Initialise Gemini client ───────────────────────────────────────────
    section("PHASE 2 — THINK: Engaging Gemini reasoning engine", C.YELLOW)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY not set.  Add it to .env or export it as an environment variable."
        )

    client  = genai.Client(api_key=api_key)
    tools   = _build_tool_declarations()

    # Compose the initial user turn: system context + log payload
    initial_user_message = (
        f"Here is the latest cluster health snapshot from DataVita production:\n\n"
        f"```json\n{raw_logs}\n```\n\n"
        f"Analyse the data and take all necessary actions per your operating rules."
    )

    # Conversation history (list of Content objects)
    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=initial_user_message)])
    ]

    log(f"  Model  : {MODEL_ID}", C.GREY)
    log(f"  Tools  : {[t.function_declarations[0].name for t in tools[0:1]] + [tools[0].function_declarations[1].name]}", C.GREY)  # noqa

    # ── 3. Act: Multi-turn function-calling loop ──────────────────────────────
    section("PHASE 3 — ACT: Autonomous tool-calling loop", C.GREEN)

    tool_turns = 0

    while tool_turns < MAX_TOOL_TURNS:
        # ── Call Gemini ───────────────────────────────────────────────────────
        response = client.models.generate_content(
            model    = MODEL_ID,
            contents = contents,
            config   = types.GenerateContentConfig(
                system_instruction = SYSTEM_PROMPT,
                tools              = tools,
                temperature        = 0.1,   # Low temperature for deterministic ops decisions
            ),
        )

        candidate = response.candidates[0]
        model_content = candidate.content          # types.Content(role='model', parts=[...])

        # Append model turn to conversation history
        contents.append(model_content)

        # ── Inspect parts ─────────────────────────────────────────────────────
        has_tool_call = False
        tool_results  = []

        for part in model_content.parts:
            # Text output from model
            if part.text:
                print(f"\n{C.BLUE}[GEMINI]{C.RESET} {part.text.strip()}")

            # Function call requested by model
            if part.function_call:
                has_tool_call = True
                fc_name = part.function_call.name
                fc_args = dict(part.function_call.args)

                print(
                    f"\n{C.YELLOW}[TOOL CALL]{C.RESET}  {C.BOLD}{fc_name}{C.RESET}"
                    f"({json.dumps(fc_args, ensure_ascii=False)})"
                )

                # ── Dispatch tool locally ─────────────────────────────────────
                result_str = dispatch_tool(fc_name, fc_args)

                print(
                    f"{C.GREEN}[TOOL RESULT]{C.RESET} {result_str[:200]}"
                    f"{'…' if len(result_str) > 200 else ''}"
                )

                tool_results.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name     = fc_name,
                            response = {"result": result_str},
                        )
                    )
                )

        # ── If there were tool calls, feed results back and continue ──────────
        if has_tool_call:
            tool_turns += 1
            contents.append(
                types.Content(role="user", parts=tool_results)
            )
            continue

        # ── No tool calls → model is done ────────────────────────────────────
        log(f"\n  Agent reached terminal state after {tool_turns} tool turn(s).", C.GREY)
        break

    else:
        log(
            f"\n[WARNING] Reached MAX_TOOL_TURNS ({MAX_TOOL_TURNS}) safety cap.  "
            "Possible reasoning loop detected.  Review conversation history.",
            C.YELLOW,
        )


# ═════════════════════════════════════════════════════════════════════════════
# Resilience wrapper — SMS hard-coded fallback
# ═════════════════════════════════════════════════════════════════════════════

def _sms_fallback(exc: Exception) -> None:
    """
    Hard-coded degraded-mode fallback.
    In production this would invoke an SNS/Twilio endpoint.
    Here it emits the audit trail to stdout so the on-call pager picks it up.
    """
    banner("⚠  CLAWOPS AGENT — DEGRADED MODE FALLBACK", C.RED)
    print(
        f"{C.RED}{C.BOLD}"
        "  已绕过 AI，直接向苏格兰高级值班工程师手机发送短信阻断告警\n"
        "  [BYPASSED AI] — Escalating directly to Scotland on-call SRE via SMS\n"
        f"{C.RESET}"
        f"  Reason  : {type(exc).__name__}: {exc}\n"
        f"  SMS To  : +44-7XXX-XXXXXX  (Lead SRE, Edinburgh NOC)\n"
        f"  Message : [CLAWOPS CRITICAL] Autonomous agent failed. "
        f"Manual intervention required for DataVita cluster. "
        f"Check Grafana dashboard immediately.\n"
    )
    print(f"{C.GREY}  — Stack trace for post-mortem —")
    traceback.print_exc()
    print(C.RESET)


# ═════════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    banner("ClawOps Agent  ·  DataVita SRE Automation  ·  v1.0", C.CYAN)
    log("  Initialising autonomous operations cycle …\n", C.GREY)

    try:
        run_agent()
        banner("✓  Cycle complete — all tasks resolved", C.GREEN)

    # ── Specific, actionable exceptions ──────────────────────────────────────
    except EnvironmentError as exc:
        banner("CONFIG ERROR", C.RED)
        log(f"  {exc}", C.RED)
        log("  Fix: ensure GEMINI_API_KEY is present in .env or environment.", C.YELLOW)
        _sms_fallback(exc)
        sys.exit(1)

    except Exception as exc:  # noqa: BLE001  — intentional broad catch for resilience
        # Covers: network timeouts, API rate-limits, context-window overflow,
        #         transient 5xx errors, JSON parse failures, etc.
        _sms_fallback(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
