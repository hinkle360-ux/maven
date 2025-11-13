"""
Basic unit tests for the cognitive graph engine and episodic memory.

These tests verify that the graph engine can register nodes, connect
them and propagate events, and that episodic memory operations work
as expected.  They do not rely on external dependencies and
operate entirely within the standard library.
"""

from brains.cognitive.graph_engine import GraphEngine, GraphNode
from brains.memory.episodic_memory import store_episode, get_episodes, summarize_episodes


def test_graph_engine_propagation():
    engine = GraphEngine()
    # Define two simple nodes: one that appends to payload and one that echoes
    def node_a(ctx, payload):
        if payload is None:
            return None
        return f"A:{payload}"
    def node_b(ctx, payload):
        if payload is None:
            return None
        return f"B:{payload}"
    engine.register_node(GraphNode("A", node_a, inputs=["test"], outputs=["a"]))
    engine.register_node(GraphNode("B", node_b, inputs=["a"], outputs=[]))
    engine.connect("A", "B")
    result = engine.emit("test", "x", {})
    # The final result should be from node B
    assert result == "B:A:x"


def test_episodic_memory_store_and_retrieve(tmp_path, monkeypatch):
    # Patch the episode path to use a temporary directory
    from brains.memory import episodic_memory as em
    monkeypatch.setattr(em, "EPISODE_PATH", tmp_path / "episodes.jsonl", raising=False)
    info = {"question": "Q?", "answer": "A", "confidence": 0.9, "tags": ["test"]}
    store_episode(info, ttl=10)
    episodes = get_episodes()
    assert len(episodes) >= 1
    # The most recent episode should match the stored info
    ep = episodes[0]
    assert ep["question"] == "Q?"
    assert ep["answer"] == "A"
    summary = summarize_episodes(1)
    assert summary["count"] >= 1
    assert summary["recent"][0]["question"] == "Q?"