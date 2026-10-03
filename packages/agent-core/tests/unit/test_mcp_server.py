from __future__ import annotations

import asyncio
import inspect
import json
import threading

import pytest
from agent_core.mcp_server import (
    SKILLS_CATALOG_URI,
    ToolSpec,
    build_mcp_server,
    offload_to_thread,
    register_skills_surface,
    register_tools,
    render_review_prompt,
    skills_catalog,
    tool_annotations,
    transport_security,
)
from agent_core.settings import AgentServiceSettings

LAYER = {
    "version": "1",
    "flow": ["goal", "agent", "skill", "tool"],
    "business_goals": {
        "triage": {"description": "Triage risk", "default_agent": "triage_agent", "skills": ["lookup", "summarize"]},
    },
    "skills": {
        "lookup": {"description": "Look up context", "mcp_tools": ["context_get"]},
        "summarize": {"description": "Summarize risk", "mcp_tools": ["summary_generate"], "extra": 1},
    },
}


class _Tools:
    def __init__(self) -> None:
        self.threads: list[int] = []

    def context_get(self, subject_id: str, limit: int = 5) -> dict:
        """Return context for a subject."""
        self.threads.append(threading.get_ident())
        return {"subject_id": subject_id, "limit": limit}

    def summary_generate(self, question: str) -> dict:
        return {"question": question}


SPECS = (
    ToolSpec("context_get", "Get context", "read_only"),
    ToolSpec("summary_generate", "Generate summary", "generation", description="Summarize with the LLM."),
)


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> AgentServiceSettings:
    for key in (
        "MCP_INSTRUCTIONS",
        "MCP_STATELESS_HTTP",
        "MCP_JSON_RESPONSE",
        "MCP_DNS_REBINDING_PROTECTION",
        "MCP_ALLOWED_HOSTS",
        "MCP_ALLOWED_ORIGINS",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return AgentServiceSettings()


def test_tool_annotations_follow_kind() -> None:
    read_only = tool_annotations(SPECS[0])
    generation = tool_annotations(SPECS[1])
    export = tool_annotations(ToolSpec("x", "Export", "export"))
    assert read_only.title == "Get context"
    assert (read_only.readOnlyHint, read_only.idempotentHint, read_only.openWorldHint) == (True, True, False)
    assert (generation.idempotentHint, generation.openWorldHint) == (False, True)
    assert (export.idempotentHint, export.openWorldHint) == (False, False)
    assert not any(a.destructiveHint for a in (read_only, generation, export))


def test_transport_security_defaults_disable_rebinding_protection(monkeypatch: pytest.MonkeyPatch) -> None:
    security = transport_security(_settings(monkeypatch))
    assert security.enable_dns_rebinding_protection is False
    assert security.allowed_hosts == []


def test_transport_security_parses_csv_allow_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        monkeypatch,
        MCP_DNS_REBINDING_PROTECTION="true",
        MCP_ALLOWED_HOSTS="localhost:8000, agent-service:8000,",
        MCP_ALLOWED_ORIGINS="http://localhost:8088",
    )
    security = transport_security(settings)
    assert security.enable_dns_rebinding_protection is True
    assert security.allowed_hosts == ["localhost:8000", "agent-service:8000"]
    assert security.allowed_origins == ["http://localhost:8088"]


def test_build_mcp_server_instruction_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    assert build_mcp_server(_settings(monkeypatch), name="s", instructions="default").instructions == "default"
    overridden = _settings(monkeypatch, MCP_INSTRUCTIONS="from env", MCP_STATELESS_HTTP="true")
    mcp = build_mcp_server(overridden, name="s", instructions="default")
    assert mcp.instructions == "from env"
    assert mcp.settings.stateless_http is True


def test_offload_to_thread_preserves_signature_and_runs_off_loop() -> None:
    tools = _Tools()
    wrapped = offload_to_thread(tools.context_get)
    assert wrapped.__name__ == "context_get"
    assert list(inspect.signature(wrapped).parameters) == ["subject_id", "limit"]

    async def _call() -> tuple[dict, int]:
        return await wrapped(subject_id="p-1", limit=2), threading.get_ident()

    result, loop_thread = asyncio.run(_call())
    assert result == {"subject_id": "p-1", "limit": 2}
    assert tools.threads and tools.threads[0] != loop_thread


def test_register_tools_exposes_metadata_and_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = build_mcp_server(_settings(monkeypatch), name="s")
    tools = _Tools()
    register_tools(mcp, tools, SPECS)
    listed = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}

    context = listed["context_get"]
    assert context.title == "Get context"
    assert context.description == "Return context for a subject."
    assert context.annotations.readOnlyHint is True
    assert context.inputSchema["required"] == ["subject_id"]
    assert set(context.inputSchema["properties"]) == {"subject_id", "limit"}
    assert listed["summary_generate"].description == "Summarize with the LLM."

    result = asyncio.run(mcp.call_tool("context_get", {"subject_id": "p-9"}))
    assert json.loads(result[0].text) == {"subject_id": "p-9", "limit": 5}


def test_skills_catalog_summarizes_layer() -> None:
    catalog = skills_catalog(LAYER)
    assert catalog["business_goals"]["triage"]["skills"] == ["lookup", "summarize"]
    assert catalog["skills"][1] == {
        "id": "summarize",
        "description": "Summarize risk",
        "mcp_tools": ["summary_generate"],
        "uri": "skills://summarize",
    }


def test_render_review_prompt_lists_skills_and_subject() -> None:
    text = render_review_prompt(LAYER, business_goal="triage", subject_label="Patient", subject_id="p-1")
    assert "Patient: p-1" in text
    assert "- lookup: Look up context (tools: context_get)" in text
    with pytest.raises(ValueError, match="Unknown business_goal"):
        render_review_prompt(LAYER, business_goal="nope", subject_label="Patient")


def test_skills_surface_resources_and_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = build_mcp_server(_settings(monkeypatch), name="s")
    register_skills_surface(mcp, lambda: LAYER, prompt_name="review", prompt_title="Review", subject_label="Patient")

    assert SKILLS_CATALOG_URI in {str(r.uri) for r in asyncio.run(mcp.list_resources())}
    assert "skills://{skill_id}" in {t.uriTemplate for t in asyncio.run(mcp.list_resource_templates())}
    assert "review" in {p.name for p in asyncio.run(mcp.list_prompts())}

    catalog = json.loads(next(iter(asyncio.run(mcp.read_resource(SKILLS_CATALOG_URI)))).content)
    assert catalog["version"] == "1"
    skill = json.loads(next(iter(asyncio.run(mcp.read_resource("skills://summarize")))).content)
    assert skill["extra"] == 1
    with pytest.raises(Exception, match="Unknown skill"):
        asyncio.run(mcp.read_resource("skills://missing"))

    prompt = asyncio.run(mcp.get_prompt("review", {"business_goal": "triage", "subject_id": "p-2"}))
    assert "Patient: p-2" in prompt.messages[0].content.text
