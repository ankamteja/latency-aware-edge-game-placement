"""Unit tests for the live controller's decisions and log reading.

The policies are built around a stub model with a known knee, so every
expected move can be worked out by hand; nothing here touches the testbed.
"""
import math

import pytest

from live import policy as lp
from live.controller import Match
from live.testbed import Tail
from placement.models import Analytical

NODES = [
    {"name": "edge1", "cores": 0.5, "rtt_ms": 5.0},
    {"name": "edge2", "cores": 1.0, "rtt_ms": 15.0},
    {"name": "edge3", "cores": 2.0, "rtt_ms": 30.0},
    {"name": "cloud", "cores": 4.0, "rtt_ms": 40.0},
]


class Knee:
    """p95 = rtt + 2 ms, plus 5 ms per player beyond 40 players per core."""

    def predict(self, node, players):
        return node["rtt_ms"] + 2.0 + 5.0 * max(0.0, players - 40 * node["cores"])


def make(cls=lp.Policy, model=None, gains=None):
    p = cls.__new__(cls)
    p.name = "stub"
    p.nodes = {n["name"]: n for n in NODES}
    p.order = sorted(p.nodes, key=lambda n: p.nodes[n]["rtt_ms"])
    p.model = model or Knee()
    p.gains = gains or lp.Gains()
    if cls is lp.LivePolicy:
        p.log_c = {n: 0.0 for n in p.nodes}
        p.broke = {}
    return p


# place

def test_place_empty_system_goes_to_nearest():
    assert make().place({}, 10) == "edge1"


def test_place_avoids_node_past_its_knee():
    # edge1 at 20 players is at its knee: 30 would predict 57 ms, edge2 17 ms
    assert make().place({"edge1": 20}, 10) == "edge2"


def test_place_respects_capacity():
    load = {"edge1": 95, "edge2": 95, "edge3": 95, "cloud": 95}
    assert make().place(load, 10) is None


# rebalance

def crowded():
    load = {"edge1": 30}
    matches = {m: ("edge1", 0.0) for m in (1, 2, 3)}
    return load, matches


def test_rebalance_moves_one_match_off_crowded_node():
    load, matches = crowded()
    mv = make().rebalance(load, matches, now=1000.0, size=10)
    assert mv["src"] == "edge1" and mv["dst"] == "edge2"
    assert mv["predicted_worst_before"] == pytest.approx(57.0)
    assert mv["predicted_worst_after"] == pytest.approx(17.0)


def test_rebalance_cooldown_blocks_recent_moves():
    load, _ = crowded()
    matches = {m: ("edge1", 990.0) for m in (1, 2, 3)}
    assert make().rebalance(load, matches, now=1000.0, size=10) is None


def test_rebalance_hysteresis_ignores_small_gains():
    # edge2 -> edge1 lowers the worst from 17 to 7 ms: taken at the default
    # 10 ms threshold, refused when the threshold is 20 ms
    load = {"edge1": 10, "edge2": 10}
    matches = {1: ("edge1", 0.0), 2: ("edge2", 0.0)}
    assert make().rebalance(load, matches, 1000.0, 10)["dst"] == "edge1"
    strict = lp.Gains(worst_ms=20.0, mean_ms=100.0)
    assert make(gains=strict).rebalance(load, matches, 1000.0, 10) is None


def test_rebalance_skips_full_destination():
    load = {"edge1": 30, "edge2": 95, "edge3": 95, "cloud": 95}
    matches = {m: ("edge1", 0.0) for m in (1, 2, 3)}
    assert make().rebalance(load, matches, 1000.0, 10) is None


def test_analytical_never_moves_off_crowded_node():
    load, matches = crowded()
    assert make(model=Analytical()).rebalance(load, matches, 1000.0, 10) is None


def test_balanced_system_stays_put():
    # two matches on edge1, still flat at 20 players: nothing to gain
    mv = make().rebalance({"edge1": 20}, {1: ("edge1", 0.0), 2: ("edge1", 0.0)}, 1000.0, 10)
    assert mv is None


# LivePolicy

def test_live_policy_learns_slower_node():
    # edge1 now behaves as if each player cost twice as much: at 20 players
    # it measures what the grid saw at 40
    p = make(lp.LivePolicy)
    slow = Knee().predict(p.nodes["edge1"], 40)
    for _ in range(8):
        p.observe("edge1", 20, slow)
    assert p.capacity_factor("edge1") == pytest.approx(2.0, rel=0.1)
    assert p.predict("edge1", 20) == pytest.approx(slow, rel=0.15)
    assert p.capacity_factor("edge2") == 1.0


def test_live_policy_flat_region_keeps_factor_one():
    p = make(lp.LivePolicy)
    for _ in range(8):
        p.observe("edge1", 10, Knee().predict(p.nodes["edge1"], 10))
    assert p.capacity_factor("edge1") == pytest.approx(1.0)


def test_live_policy_ignores_empty_or_missing_windows():
    p = make(lp.LivePolicy)
    for players, p95 in ((0, 50.0), (20, None), (20, 0.0), (20, -1.0)):
        p.observe("edge1", players, p95)
    assert p.capacity_factor("edge1") == 1.0


def test_live_policy_moves_match_after_slowdown():
    p = make(lp.LivePolicy)
    load = {"edge1": 20}
    matches = {1: ("edge1", 0.0), 2: ("edge1", 0.0)}
    assert p.rebalance(load, matches, 1000.0, 10) is None
    for _ in range(8):
        p.observe("edge1", 20, Knee().predict(p.nodes["edge1"], 40))
    assert p.rebalance(load, matches, 1000.0, 10)["dst"] == "edge2"


# Tail

def test_tail_keeps_partial_line(tmp_path):
    f = tmp_path / "seg.csv"
    f.write_text("1000,bot0,rtt,12.5\n1001,bot1,rtt,1")
    t = Tail(f)
    assert t.read() == [(1000, "bot0", 12.5)]
    with f.open("a") as w:
        w.write("3.0\n")
    assert t.read() == [(1001, "bot1", 13.0)]
    assert t.read() == []


def test_tail_drops_malformed_lines(tmp_path):
    f = tmp_path / "seg.csv"
    f.write_text("\n".join([
        "epoch,bot,kind,value",
        "1000,bot0,join,0",
        "1001,bot0,rtt",
        "x1002,bot0,rtt,5",
        "1003,bot0,rtt,abc",
        "1004,bot0,rtt,nan",
        "1005,bot0,rtt,inf",
        "1006,bot0,rtt,7.5",
    ]) + "\n")
    assert Tail(f).read() == [(1006, "bot0", 7.5)]


def test_tail_missing_file(tmp_path):
    assert Tail(tmp_path / "none.csv").read() == []


# Match.close_gap

def test_close_gap_uses_last_player_back():
    m = Match(1, "edge2", 0, since=100.0, tail=None, moved_at=100.0)
    m.back = {"bot0": 103.0, "bot1": 107.5}
    m.close_gap(now=200.0)
    assert m.gaps == [pytest.approx(7.5)]
    assert m.moved_at is None and m.back == {}


def test_close_gap_nobody_back_uses_now():
    m = Match(1, "edge2", 0, since=100.0, tail=None, moved_at=100.0)
    m.close_gap(now=130.0)
    assert m.gaps == [pytest.approx(30.0)]


def test_close_gap_without_move_is_noop():
    m = Match(1, "edge1", 0, since=0.0, tail=None)
    m.close_gap(now=10.0)
    assert m.gaps == []


def test_live_policy_keeps_factor_through_quiet_windows():
    # edge1 learned to be twice as slow; then it carries a light load that is
    # flat for every c. Those windows say nothing about c and must not undo it.
    p = make(lp.LivePolicy)
    for _ in range(8):
        p.observe("edge1", 20, Knee().predict(p.nodes["edge1"], 40))
    learned = p.capacity_factor("edge1")
    for _ in range(20):
        p.observe("edge1", 5, Knee().predict(p.nodes["edge1"], 5))
    assert p.capacity_factor("edge1") == pytest.approx(learned)


def test_live_policy_remembers_a_measured_violation(monkeypatch):
    p = make(lp.LivePolicy)
    clock = [1000.0]
    monkeypatch.setattr(lp.time, "time", lambda: clock[0])
    p.observe("edge1", 30, 900.0)              # edge1 broke at 30 players
    assert p.predict("edge1", 30) >= 900.0
    assert p.predict("edge1", 40) >= 900.0
    assert p.predict("edge1", 20) < 900.0      # lighter loads are not pinned to it
    # the controller will not move a match back onto it ...
    load = {"edge1": 20, "edge2": 10}
    mv = p.rebalance(load, {1: ("edge1", 0.0), 2: ("edge1", 0.0), 3: ("edge2", 0.0)},
                     clock[0], 10)
    assert mv is None or mv["dst"] != "edge1"
    clock[0] += lp.LivePolicy.HOLD_S + 1       # ... until the memory expires
    assert p.predict("edge1", 30) < 900.0
