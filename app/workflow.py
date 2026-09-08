import logging
from typing import Any, TypedDict
from .storage import ObjectStorage, parse_csv

log = logging.getLogger("flowops.workflow")

try:
    from langgraph.graph import StateGraph, END
except ImportError:  # pragma: no cover
    StateGraph = None
    END = "__end__"


class State(TypedDict, total=False):
    source: str
    text: str
    raw: str
    rows: list[dict[str, Any]]
    transformed: list[dict[str, Any]]
    validation: dict[str, Any]
    evaluation: dict[str, Any]


def ingest(s: State) -> State:
    s["raw"] = s.get("text") or ObjectStorage().read(s["source"])
    s["rows"] = parse_csv(s["raw"])
    return s


def transform(s: State) -> State:
    rows = []
    for row in s.get("rows", []):
        out = dict(row)
        for k, v in list(out.items()):
            try: out[k] = float(v) if "." in v else int(v)
            except (ValueError, TypeError): pass
        rows.append(out)
    s["transformed"] = rows
    return s


def validate(s: State) -> State:
    rows = s.get("transformed", [])
    s["validation"] = {"valid": bool(rows), "row_count": len(rows), "errors": [] if rows else ["empty dataset"]}
    return s


def evaluate(s: State) -> State:
    s["evaluation"] = {"score": 1.0 if s["validation"]["valid"] else 0.0, "quality": "good" if s["validation"]["valid"] else "poor"}
    return s


def build_workflow(on_stage=None):
    if StateGraph is None:
        return None
    graph = StateGraph(State)
    nodes = (("ingestion", ingest), ("transformation", transform),
             ("validation", validate), ("evaluation", evaluate))
    for stage, node in nodes:
        if on_stage:
            async def wrapped(state, _node=node, _stage=stage):
                result = _node(state)
                await on_stage(_stage, result)
                return result
            graph.add_node(stage, wrapped)
        else:
            graph.add_node(stage, node)
    graph.set_entry_point("ingestion")
    graph.add_edge("ingestion", "transformation"); graph.add_edge("transformation", "validation")
    graph.add_edge("validation", "evaluation"); graph.add_edge("evaluation", END)
    return graph.compile()


async def execute(source: str, text: str | None = None, on_stage=None) -> dict[str, Any]:
    initial: State = {"source": source, "text": text or ""}
    workflow = build_workflow(on_stage)
    if workflow:
        result = await workflow.ainvoke(initial)
    else:
        # Compatibility path for environments where optional LangGraph import fails.
        result = initial
        for stage, node in (("ingestion", ingest), ("transformation", transform),
                            ("validation", validate), ("evaluation", evaluate)):
            result = node(result)
            if on_stage:
                await on_stage(stage, result)
    return {"validation": result["validation"], "evaluation": result["evaluation"], "rows": result["transformed"]}
