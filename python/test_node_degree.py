"""Test what node degree counts as an edge.

Run from the repo root::

    uv run python python/test_node_degree.py

An edge is any off-diagonal weight above zero. There used to be a hard-coded
cutoff of 0.0001, which left tiny edges out of ND while density and node
strength still counted them (GitHub issue #31).
"""

import numpy as np

from meanap.pipeline.network_metrics import density_und, find_node_deg_edge_weight


def test_any_positive_weight_is_an_edge():
    adj = np.zeros((3, 3))
    adj[0, 1] = adj[1, 0] = 1e-9
    nd, _ = find_node_deg_edge_weight(adj)
    assert nd.tolist() == [1, 1, 0]


def test_absent_negative_and_nan_weights_are_not_edges():
    adj = np.array([[0.0, 0.0, -0.3], [0.0, 0.0, np.nan], [-0.3, np.nan, 0.0]])
    nd, _ = find_node_deg_edge_weight(adj)
    assert nd.tolist() == [0, 0, 0]


def test_self_edges_are_not_counted():
    for diagonal in (0.0, 1.0):
        adj = np.array([[diagonal, 0.5], [0.5, diagonal]])
        nd, _ = find_node_deg_edge_weight(adj)
        assert nd.tolist() == [1, 1]


def test_degree_agrees_with_density():
    adj = np.array([[0.0, 1e-9, 0.5], [1e-9, 0.0, 0.0], [0.5, 0.0, 0.0]])
    nd, _ = find_node_deg_edge_weight(adj)
    n = adj.shape[0]
    assert nd.sum() / (n * (n - 1)) == density_und(adj)


if __name__ == "__main__":
    test_any_positive_weight_is_an_edge()
    test_absent_negative_and_nan_weights_are_not_edges()
    test_self_edges_are_not_counted()
    test_degree_agrees_with_density()
    print("All node degree tests passed")
