"""
LangGraph Workflow -- wires the four nodes into a state machine with
conditional routing (the retry loop).

Think of it like a flowchart:

    [Analyze] -> [Matrix CSV] -> [Generate] -> [Verify] --pass--> [Deploy]
                     ^                  |
                     |___fail & retries_|
                              |
                        (no retries left -> STOP)

LangGraph takes this flowchart definition and turns it into a runnable
object that manages state transitions automatically.

Usage:
    graph = build_graph(container)
    final_state = graph.invoke({"ticket": my_ticket, "max_retries": 3})
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from autotest_agent.agents.nodes import NodeContainer
from autotest_agent.domain.models import GraphState


def _should_retry_or_deploy(state: GraphState) -> str:
    """
    Routing function called after the Verify node.
    Decides whether to loop back to Generate (retry) or move to Deploy.
    """
    verification = state.get("verification")
    if verification and verification.passed:
        return "deploy"

    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    if retry_count < max_retries:
        return "generate"

    return "deploy"


def build_graph(container: NodeContainer) -> StateGraph:
    """
    Construct the LangGraph state machine and return the compiled graph.

    The `container` holds all the infrastructure services; its methods
    become the node functions.
    """
    graph = StateGraph(GraphState)

    graph.add_node("analyze", container.analyze)
    graph.add_node("matrix_csv", container.matrix_csv)
    graph.add_node("generate", container.generate)
    graph.add_node("verify", container.verify)
    graph.add_node("deploy", container.deploy)

    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "matrix_csv")
    graph.add_edge("matrix_csv", "generate")
    graph.add_edge("generate", "verify")
    graph.add_conditional_edges(
        "verify",
        _should_retry_or_deploy,
        {"deploy": "deploy", "generate": "generate"},
    )
    graph.add_edge("deploy", END)

    return graph.compile()
