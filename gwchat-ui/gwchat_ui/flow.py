"""Turns one agent reply into (a) a step-by-step hop table and (b) a Graphviz diagram, so a presenter can show
GWChat UI → Agent → Gateway → MCP tool → on-prem API for the turn that was just answered."""
from __future__ import annotations

from .client import AgentReply

GREEN, RED, GOLD, BLUE, GREY = "#D6F0DD", "#F8D7DA", "#FFF0C2", "#E3EEFA", "#EEF1F4"


def _onprem_by_tool(reply: AgentReply) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for c in (reply.data.get("_demo") or {}).get("onprem_calls", []):
        out.setdefault(c["tool"], []).append(c)
    return out


def build_steps(reply: AgentReply) -> list[dict]:
    d, onprem = reply.data, _onprem_by_tool(reply)
    trace = d.get("tool_trace", [])
    steps: list[dict] = [{"#": 1, "Hop": "GWChat UI → Agent", "Component": "AgentCore Runtime (HTTP)",
                          "What happened": "POST /invocations with prompt, UI context and the user's bearer token", "ms": reply.http_ms}]
    n = 2
    if trace:
        steps.append({"#": n, "Hop": "Agent (Strands + LLM)", "Component": "Intent + tool selection",
                      "What happened": f"Validated the request, offered only allow-listed tools, model chose {len(trace)} tool call(s). Intent: {d.get('intent')}", "ms": None})
    else:
        steps.append({"#": n, "Hop": "Agent (Strands + LLM)", "Component": "Intent",
                      "What happened": "No tool needed or allowed (clarification, out-of-scope, or capability answer). Nothing was looked up or inferred.", "ms": None})
    n += 1
    for t in trace:
        tool, oc = t["tool"], t["outcome"]
        if oc == "queued_for_confirmation":
            steps.append({"#": n, "Hop": "Agent guardrail", "Component": "Write interception", "ms": None,
                          "What happened": f"{tool} is a WRITE: the call was cancelled and a signed confirmation ticket was issued. Nothing was sent to the Gateway."})
        elif oc == "blocked":
            steps.append({"#": n, "Hop": "Agent guardrail", "Component": "Policy hook", "ms": None,
                          "What happened": f"{tool} was blocked ({t.get('error_code')})."})
        else:
            route = onprem.get(tool)
            tail = (" → on-prem " + ", ".join(f"{r['method']} {r['route']}" for r in route[:2])) if route else ""
            steps.append({"#": n, "Hop": "Agent → Gateway → FastMCP", "Component": f"tools/call {tool}", "ms": t.get("latency_ms"),
                          "What happened": ("OK" if t["ok"] else f"FAILED ({t.get('error_code')})") + tail})
        n += 1
    status, blocks, gaps = d.get("status"), d.get("blocks", []), d.get("data_gaps", [])
    steps.append({"#": n, "Hop": "Agent → GWChat UI", "Component": "Deterministic assembly", "ms": None,
                  "What happened": f"status={status}; {len(blocks)} block(s) built verbatim from tool data; {len(gaps)} data gap(s); narrative grounding-checked."})
    return steps


def _label(s: str) -> str:
    return s.replace('"', "'")


def build_dot(reply: AgentReply) -> str:
    d, onprem = reply.data, _onprem_by_tool(reply)
    trace = d.get("tool_trace", [])
    many = len([t for t in trace if t['outcome'] not in ('queued_for_confirmation', 'blocked')]) > 4
    lines = [
        "digraph G {", "rankdir=TB; bgcolor=transparent; nodesep=0.3; ranksep=0.45;",
        'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, color="#8CA0B3"];',
        'edge [fontname="Helvetica", fontsize=9, color="#5B6B7B"];',
        f'UI [label="GWChat UI\\n(Streamlit)", fillcolor="{BLUE}"];',
        f'AG [label="Agent\\nAgentCore Runtime\\nStrands + LLM", fillcolor="{BLUE}"];',
        f'GW [label="AgentCore Gateway\\nauthn/z + tool routing", fillcolor="{GREY}"];',
        f'ONP [label="On-prem TRC API\\nCareNavi · ADT/HIE · Vista\\nEIP · Claims · MRAT", fillcolor="{GREY}"];',
        f'UI -> AG [label="1  prompt + JWT\\n{reply.http_ms} ms total"];',
    ]
    called = [t for t in trace if t["outcome"] not in ("queued_for_confirmation", "blocked")]
    if called:
        lines.append(f'AG -> GW [label="2  MCP tools/call x{len(called)}"];')
        if many:
            # big fan-out: one compact node listing every tool (a 13-node column is unreadable)
            body = "".join(f"{_label(t['tool'])}  {t['latency_ms'] if t.get('latency_ms') is not None else '-'} ms  {'ok' if t['ok'] else 'FAILED'}\\l" for t in called)
            allok = all(t["ok"] for t in called)
            lines.append(f'T [shape=box, style="rounded,filled", fillcolor="{GREEN if allok else RED}", fontname="Courier", fontsize=9, '
                         f'label="FastMCP server: {len(called)} typed tools (run in parallel)\\n\\n{body}"];')
            lines.append("GW -> T; T -> ONP;")
        else:
            lines.append('subgraph cluster_mcp { label="FastMCP server (typed tools)"; fontname="Helvetica"; fontsize=10; color="#8CA0B3"; style="rounded,dashed";')
            for i, t in enumerate(called):
                lat = f"\\n{t['latency_ms']} ms" if t.get("latency_ms") is not None else ""
                mark = "ok" if t["ok"] else "FAILED"
                lines.append(f'T{i} [label="{_label(t["tool"])}{lat}\\n{mark}", fillcolor="{GREEN if t["ok"] else RED}"];')
            lines.append("}")
            for i, t in enumerate(called):
                lines.append(f"GW -> T{i};")
                r = onprem.get(t["tool"])
                lab = "" if not r else f' [label="{r[0]["method"]} {_label(r[0]["route"])[:38]}"]'
                lines.append(f"T{i} -> ONP{lab};")
    for i, t in enumerate(x for x in trace if x["outcome"] == "queued_for_confirmation"):
        lines.append(f'Q{i} [label="{_label(t["tool"])}\\nWRITE queued\\nawaiting approval", fillcolor="{GOLD}"];')
        lines.append(f'AG -> Q{i} [style=dashed, label="intercepted"];')
        lines.append(f'Q{i} -> UI [style=dashed, label="Approve / Reject", constraint=false];')
    for i, t in enumerate(x for x in trace if x["outcome"] == "blocked"):
        lines.append(f'B{i} [label="{_label(t["tool"])}\\nblocked", fillcolor="{RED}"]; AG -> B{i} [style=dashed];')
    lines.append(f'AG -> UI [label="{len(d.get("blocks", []))} blocks + narrative\\n{d.get("status")}", constraint=false, color="#0A6EBD"];')
    lines.append("}")
    return "\n".join(lines)
