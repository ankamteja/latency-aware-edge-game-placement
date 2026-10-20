"""Placement algorithms: assign a batch of matches to nodes.

A batch is K matches of `match_size` players each. A placement is the number of
matches on each node. Every node also has a hard player limit (the server's
max-players), which every algorithm respects.

The quality of a placement is the latency its WORST-OFF player sees: the
highest predicted p95 over the nodes that host anyone. That is the number that
decides whether some players have an unplayable match, which a mean hides.

  closest   every match goes to the nearest node that still has room. What a
            distance-ranked placement does, and what any latency model with no
            load term reduces to.
  greedy    matches are placed one at a time, each on the node with the lowest
            predicted latency given what is already placed there.
  optimal   exhaustive search over every way to split the K matches across the
            nodes, minimising the worst predicted p95 (ties: lower mean).
"""
from itertools import combinations


def score(placement, nodes, model, match_size):
    """(worst p95, player-weighted mean p95) under `model`."""
    worst, total, players = 0.0, 0.0, 0
    for node, k in zip(nodes, placement):
        if k == 0:
            continue
        p = k * match_size
        lat = model.predict(node, p)
        worst = max(worst, lat)
        total += lat * p
        players += p
    return worst, total / players if players else 0.0


def fits(placement, match_size, max_players):
    return all(k * match_size <= max_players for k in placement)


def closest(nodes, k, match_size, model, max_players=100):
    order = sorted(range(len(nodes)), key=lambda i: nodes[i]["rtt_ms"])
    placement = [0] * len(nodes)
    for _ in range(k):
        for i in order:
            if (placement[i] + 1) * match_size <= max_players:
                placement[i] += 1
                break
        else:
            raise ValueError("batch does not fit")
    return placement


def greedy(nodes, k, match_size, model, max_players=100):
    placement = [0] * len(nodes)
    for _ in range(k):
        best, best_lat = None, None
        for i, node in enumerate(nodes):
            if (placement[i] + 1) * match_size > max_players:
                continue
            lat = model.predict(node, (placement[i] + 1) * match_size)
            if best_lat is None or lat < best_lat:
                best, best_lat = i, lat
        if best is None:
            raise ValueError("batch does not fit")
        placement[best] += 1
    return placement


def compositions(k, parts):
    """Every way to write k as an ordered sum of `parts` non-negative ints."""
    for bars in combinations(range(k + parts - 1), parts - 1):
        prev, out = -1, []
        for b in bars:
            out.append(b - prev - 1)
            prev = b
        out.append(k + parts - 2 - prev)
        yield out


def optimal(nodes, k, match_size, model, max_players=100):
    best, best_score = None, None
    for placement in compositions(k, len(nodes)):
        if not fits(placement, match_size, max_players):
            continue
        s = score(placement, nodes, model, match_size)
        if best_score is None or s < best_score:
            best, best_score = placement, s
    if best is None:
        raise ValueError("batch does not fit")
    return best


ALGORITHMS = {"closest": closest, "greedy": greedy, "optimal": optimal}
