from supply_chain_agent.orchestration import graph


def test_compiled_graph_is_cached_per_tracing_config(monkeypatch):
    graph.clear_graph_cache()
    monkeypatch.setattr(graph, "mlflow_enabled", lambda: False)
    first = graph.get_compiled_graph()
    assert graph.get_compiled_graph() is first

    monkeypatch.setattr(graph, "mlflow_enabled", lambda: True)
    traced = graph.get_compiled_graph()
    assert traced is not first

    graph.clear_graph_cache()
    monkeypatch.setattr(graph, "mlflow_enabled", lambda: False)
    assert graph.get_compiled_graph() is not first
    graph.clear_graph_cache()
