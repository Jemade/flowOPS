"""Workflow engine using LangGraph to orchestrate pipeline stages.

The pipeline executes a directed acyclic graph (DAG) composed of four stages:
1. Ingestion: Reads raw CSV data from the specified source.
2. Transformation: Converts string numbers into integers and floats.
3. Validation: Checks row presence and verifies dataset integrity.
4. Evaluation: Calculates quality metrics and grading scores.
"""

import logging
from typing import Any, TypedDict
from .storage import ObjectStorage, parse_csv

log = logging.getLogger("flowops.workflow")

# Attempt to import LangGraph components. If not installed, execute()
# falls back to a simple sequential execution loop.
try:
    from langgraph.graph import StateGraph, END
except ImportError:
    StateGraph = None
    END = "__end__"


class State(TypedDict, total=False):
    """Shared state dictionary passed across pipeline graph nodes."""
    source: str
    text: str
    raw: str
    rows: list[dict[str, Any]]
    transformed: list[dict[str, Any]]
    validation: dict[str, Any]
    evaluation: dict[str, Any]


def ingest(s: State) -> State:
    """Stage 1: Load raw data from inline text or external storage."""
    s["raw"] = s.get("text") or ObjectStorage().read(s["source"])
    s["rows"] = parse_csv(s["raw"])
    return s


def transform(s: State) -> State:
    """Stage 2: Parse and type-cast numeric column values.

    Tries converting values to float if a decimal point is present,
    otherwise integer. Keeps original text if conversion fails.
    """
    rows = []
    for row in s.get("rows", []):
        out = dict(row)
        for k, v in list(out.items()):
            try:
                out[k] = float(v) if "." in v else int(v)
            except (ValueError, TypeError):
                pass
        rows.append(out)
    s["transformed"] = rows
    return s


def validate(s: State) -> State:
    """Stage 3: Validate row count and collect dataset errors."""
    rows = s.get("transformed", [])
    has_rows = bool(rows)
    s["validation"] = {
        "valid": has_rows,
        "row_count": len(rows),
        "errors": [] if has_rows else ["empty dataset"],
    }
    return s


def evaluate(s: State) -> State:
    """Stage 4: Score the overall dataset quality based on validation results."""
    is_valid = s["validation"]["valid"]
    s["evaluation"] = {
        "score": 1.0 if is_valid else 0.0,
        "quality": "good" if is_valid else "poor",
    }
    return s


def build_workflow(on_stage=None):
    """Constructs and compiles the LangGraph StateGraph.

    Args:
        on_stage: Optional asynchronous callback invoked after each stage
            node completes. Useful for broadcasting progress updates.

    Returns:
        A compiled LangGraph runnable instance, or None if LangGraph is unavailable.
    """
    if StateGraph is None:
        return None

    graph = StateGraph(State)
    nodes = (
        ("ingestion", ingest),
        ("transformation", transform),
        ("validation", validate),
        ("evaluation", evaluate),
    )

    for stage, node in nodes:
        if on_stage:
            # Wrap the stage function so we can notify listeners of progress
            async def wrapped(state, _node=node, _stage=stage):
                result = _node(state)
                await on_stage(_stage, result)
                return result
            graph.add_node(stage, wrapped)
        else:
            graph.add_node(stage, node)

    # Wire up the execution edges in linear order
    graph.set_entry_point("ingestion")
    graph.add_edge("ingestion", "transformation")
    graph.add_edge("transformation", "validation")
    graph.add_edge("validation", "evaluation")
    graph.add_edge("evaluation", END)

    return graph.compile()


async def execute(source: str, text: str | None = None, on_stage=None) -> dict[str, Any]:
    """Runs the full pipeline end-to-end and returns the aggregated output.

    Args:
        source: Source identifier ('demo', 'inline', file path, or S3 URI).
        text: Optional inline CSV string.
        on_stage: Optional asynchronous callback for stage progress events.

    Returns:
        Dictionary containing validation results, evaluation scores, and rows.
    """
    initial: State = {"source": source, "text": text or ""}
    workflow = build_workflow(on_stage)

    if workflow:
        result = await workflow.ainvoke(initial)
    else:
        # Fallback path for environments where LangGraph is not present
        result = initial
        for stage, node in (
            ("ingestion", ingest),
            ("transformation", transform),
            ("validation", validate),
            ("evaluation", evaluate),
        ):
            result = node(result)
            if on_stage:
                await on_stage(stage, result)

    return {
        "validation": result["validation"],
        "evaluation": result["evaluation"],
        "rows": result["transformed"],
    }
