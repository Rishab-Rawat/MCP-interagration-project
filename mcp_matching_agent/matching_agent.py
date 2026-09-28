"""LangGraph recruitment matching agent using the filesystem MCP server as its tool provider."""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, TypedDict

from mcp import Client, StdioServerParameters
from langgraph.graph import END, START, StateGraph

ROOT = Path(__file__).resolve().parent
SERVER = ROOT / "filesystem_mcp_server.py"


class AgentState(TypedDict, total=False):
    job_description: str
    conversation_history: list[str]
    requirements: dict[str, Any]
    candidates: list[dict[str, Any]]
    shortlist: list[dict[str, Any]]
    reasoning: list[str]
    report: str
    feedback: str


class MCPFilesystemClient:
    """Small adapter around the official MCP v2 high-level Client."""

    def __init__(self) -> None:
        self.params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
        self._client = None

    async def __aenter__(self):
        self._client = Client(self.params)
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client:
            await self._client.__aexit__(exc_type, exc, tb)

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        result = await self._client.call_tool(name, arguments)
        if getattr(result, "is_error", False):
            raise RuntimeError(f"MCP tool '{name}' returned an error")
        structured = getattr(result, "structured_content", None)
        if structured is not None:
            return structured
        if result.content and hasattr(result.content[0], "text"):
            return json.loads(result.content[0].text)
        return result.content


def extract_requirements(jd: str) -> dict[str, Any]:
    """Deterministic requirement parser suitable for a no-API-key submission demo."""
    text = jd.lower()
    skills = [
        "python", "javascript", "typescript", "react", "node.js", "node", "java",
        "sql", "mongodb", "postgresql", "aws", "docker", "kubernetes", "langchain",
        "langgraph", "mcp", "git", "rest api", "fastapi", "machine learning",
    ]
    must = [s for s in skills if s in text]
    years = [int(x) for x in re.findall(r"(\d+)\+?\s*(?:years?|yrs?)", text)]
    min_years = max(years) if years else 0
    nice = []
    marker = re.search(r"nice[- ]to[- ]have[s]?:(.*?)(?:\n\n|$)", jd, re.I | re.S)
    if marker:
        nice = [x.strip().lower() for x in re.split(r",|;|\n", marker.group(1)) if x.strip()]
    return {"must_have": must, "nice_to_have": nice, "min_years": min_years}


def rank_documents(requirements: dict[str, Any], documents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    ranked, reasoning = [], []
    for doc in documents:
        text = doc["content"].lower()
        matched = [skill for skill in requirements["must_have"] if skill in text]
        years_found = [int(x) for x in re.findall(r"(\d+)\+?\s*(?:years?|yrs?)", text)]
        years = max(years_found) if years_found else 0
        year_score = min(years / requirements["min_years"], 1.0) if requirements["min_years"] else 1.0
        skill_score = len(matched) / max(len(requirements["must_have"]), 1)
        nice_matched = [x for x in requirements["nice_to_have"] if x in text]
        score = round(100 * (0.75 * skill_score + 0.25 * year_score) + min(5 * len(nice_matched), 10), 2)
        ranked.append({
            "candidate_id": Path(doc["filename"]).stem,
            "filename": doc["filename"],
            "score": min(score, 100),
            "matched_skills": matched,
            "nice_to_have_matches": nice_matched,
            "experience_years": years,
        })
    ranked.sort(key=lambda x: (-x["score"], x["candidate_id"]))
    for item in ranked:
        reasoning.append(
            f"{item['candidate_id']}: score {item['score']}%; matched {', '.join(item['matched_skills']) or 'none'}; "
            f"experience {item['experience_years']} years."
        )
    return ranked, reasoning


async def build_graph(mcp_client: MCPFilesystemClient):
    async def parse_jd(state: AgentState) -> AgentState:
        history = list(state.get("conversation_history", []))
        history.append("Parsed job description")
        return {"conversation_history": history}

    async def extract_node(state: AgentState) -> AgentState:
        req = extract_requirements(state["job_description"])
        return {"requirements": req, "conversation_history": state.get("conversation_history", []) + ["Extracted requirements"]}

    async def search_resumes(state: AgentState) -> AgentState:
        result = await mcp_client.call("batch_process", {"filenames": None})
        return {"candidates": result.get("documents", []), "conversation_history": state.get("conversation_history", []) + ["Searched resumes through MCP"]}

    async def rank_candidates(state: AgentState) -> AgentState:
        ranked, reasoning = rank_documents(state["requirements"], state["candidates"])
        return {"shortlist": ranked[:5], "reasoning": reasoning, "conversation_history": state.get("conversation_history", []) + ["Ranked candidates"]}

    async def generate_report(state: AgentState) -> AgentState:
        lines = ["RECRUITMENT MATCHING REPORT", "=" * 30, f"Requirements: {json.dumps(state['requirements'])}", ""]
        for i, c in enumerate(state.get("shortlist", []), 1):
            lines.append(f"{i}. {c['candidate_id']} — {c['score']}% match — {c['experience_years']} years")
            lines.append(f"   Skills: {', '.join(c['matched_skills']) or 'None'}")
        lines.append("\nReasoning:")
        lines.extend(f"- {r}" for r in state.get("reasoning", []))
        return {"report": "\n".join(lines), "conversation_history": state.get("conversation_history", []) + ["Generated report"]}

    async def human_feedback(state: AgentState) -> AgentState:
        feedback = state.get("feedback", "")
        return {"feedback": feedback, "conversation_history": state.get("conversation_history", []) + ["Human feedback checkpoint"]}

    graph = StateGraph(AgentState)
    graph.add_node("parse_jd", parse_jd)
    graph.add_node("extract_requirements", extract_node)
    graph.add_node("search_resumes", search_resumes)
    graph.add_node("rank_candidates", rank_candidates)
    graph.add_node("generate_report", generate_report)
    graph.add_node("human_feedback", human_feedback)
    graph.add_edge(START, "parse_jd")
    graph.add_edge("parse_jd", "extract_requirements")
    graph.add_edge("extract_requirements", "search_resumes")
    graph.add_edge("search_resumes", "rank_candidates")
    graph.add_edge("rank_candidates", "generate_report")
    graph.add_edge("generate_report", "human_feedback")
    graph.add_edge("human_feedback", END)
    return graph.compile()


async def run_agent(job_description: str, feedback: str = "") -> AgentState:
    async with MCPFilesystemClient() as client:
        graph = await build_graph(client)
        return await graph.ainvoke({
            "job_description": job_description,
            "conversation_history": [],
            "feedback": feedback,
        })


async def main() -> None:
    jd = " ".join(sys.argv[1:]).strip()
    if not jd:
        jd = input("Enter job description: ").strip()
    result = await run_agent(jd)
    print("\n" + result["report"])


if __name__ == "__main__":
    asyncio.run(main())
