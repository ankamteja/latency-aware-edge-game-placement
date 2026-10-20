"""python -m pytest placement/"""
from placement.algorithms import closest, compositions, greedy, optimal, score
from placement.models import Analytical, Queueing

NODES = [
    {"name": "near", "cores": 0.5, "rtt_ms": 5.0},
    {"name": "far", "cores": 4.0, "rtt_ms": 40.0},
]


def test_compositions_cover_every_split_once():
    got = sorted(map(tuple, compositions(3, 3)))
    assert len(got) == len(set(got)) == 10
    assert all(sum(c) == 3 for c in got)


def test_load_blind_model_fills_the_nearest_node_first():
    assert closest(NODES, 5, 10, Analytical()) == [5, 0]
    assert optimal(NODES, 5, 10, Analytical()) == [5, 0]


def test_max_players_is_a_hard_limit():
    assert closest(NODES, 12, 10, Analytical()) == [10, 2]
    assert greedy(NODES, 12, 10, Analytical())[0] <= 10


def test_queueing_model_moves_load_off_a_saturating_node():
    q = Queueing(s_ms=5.0)
    # 50 players saturate the 0.5-core node (u = 1), so some must go far
    placement = optimal(NODES, 5, 10, q)
    assert placement[1] > 0
    assert score(placement, NODES, q, 10)[0] < q.CAP_MS


def test_greedy_never_beats_optimal_on_its_own_model():
    q = Queueing(s_ms=5.0)
    for k in range(1, 9):
        g = score(greedy(NODES, k, 10, q), NODES, q, 10)
        o = score(optimal(NODES, k, 10, q), NODES, q, 10)
        assert o <= g
