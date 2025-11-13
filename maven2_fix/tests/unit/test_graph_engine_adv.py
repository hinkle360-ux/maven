"""
Advanced tests for the upgraded cognitive graph engine.

These tests ensure that the GraphEngine handles duplicate node
registrations, duplicate edges, propagation ordering and the maximum
steps limit correctly.  They also verify that a trace file is
written after emissions when visits occur.
"""

from brains.cognitive.graph_engine import GraphEngine, GraphNode


def test_register_and_connect_duplicate_edges(monkeypatch, tmp_path):
    # Patch the trace path to a temporary location to avoid polluting reports
    import brains.cognitive.graph_engine as ge_module
    monkeypatch.setattr(ge_module, "TRACE_PATH", str(tmp_path / "trace_graph.jsonl"), raising=False)
    engine = GraphEngine()
    # Define simple nodes that operate on integers
    def add_one(ctx, payload):
        return payload + 1 if isinstance(payload, int) else None
    # Register a node and attempt to re‑register with the same name
    engine.register_node(GraphNode("A", add_one, inputs=["n"], outputs=["m"]))
    engine.register_node(GraphNode("A", lambda c, p: None, inputs=["x"], outputs=[]))
    # Only one entry should exist for "A"
    assert list(engine.nodes.keys()).count("A") == 1
    # Register additional nodes and connect
    engine.register_node(GraphNode("B", add_one, inputs=["m"], outputs=[]))
    engine.connect("A", "B")
    # Duplicate connections should be ignored
    engine.connect("A", "B")
    assert engine.edges["A"].count("B") == 1
    # Emitting an event should process A then B
    result = engine.emit("n", 0, {})
    # 0 → A:1 → B:2
    assert result == 2
    # A trace file should have been created with at least one record
    with open(ge_module.TRACE_PATH, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    assert len(lines) >= 1


def test_max_steps_limits_propagation(monkeypatch, tmp_path):
    # Patch the trace path to temporary location
    import brains.cognitive.graph_engine as ge_module
    monkeypatch.setattr(ge_module, "TRACE_PATH", str(tmp_path / "trace_graph2.jsonl"), raising=False)
    # Build a chain of four nodes that each add one to the payload
    def inc(ctx, payload):
        return payload + 1 if isinstance(payload, int) else None
    engine = GraphEngine(max_steps=2)
    engine.register_node(GraphNode("n1", inc, inputs=["x"], outputs=[]))
    engine.register_node(GraphNode("n2", inc, inputs=[], outputs=[]))
    engine.register_node(GraphNode("n3", inc, inputs=[], outputs=[]))
    engine.register_node(GraphNode("n4", inc, inputs=[], outputs=[]))
    engine.connect("n1", "n2")
    engine.connect("n2", "n3")
    engine.connect("n3", "n4")
    # Emit an event; only two nodes should execute due to max_steps
    result = engine.emit("x", 0, {})
    # n1: returns 1, n2: returns 2, n3/n4 skipped
    assert result == 2
    # The trace should record exactly two visits
    with open(ge_module.TRACE_PATH, "r", encoding="utf-8") as fh:
        import ast
        # Use ast.literal_eval instead of eval for safety when parsing Python literals
        rec = [ast.literal_eval(line) for line in fh]
    visits = rec[0]["visits"]
    assert len(visits) == 2