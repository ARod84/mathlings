from app.taxonomy.graph import Edge, PrerequisiteGraph


def edge(topic: str, prerequisite: str, strength: str = "hard") -> Edge:
    return Edge(topic, prerequisite, strength, f"{topic} needs {prerequisite}")


def ids(links) -> list[str]:
    return [link.topic_id for link in links]


#        top
#       /   \         (hard)        top also needs "side" (soft)
#    left   right
#       \   /
#       base
#         |
#       root
DIAMOND = [
    edge("top", "left"),
    edge("top", "right"),
    edge("top", "side", "soft"),
    edge("left", "base"),
    edge("right", "base"),
    edge("base", "root"),
]


def diamond(centrality=None) -> PrerequisiteGraph:
    return PrerequisiteGraph(DIAMOND, centrality or {})


def test_direct_prerequisites_put_hard_before_soft_and_carry_the_edge():
    links = diamond().direct_prerequisites("top")

    assert ids(links) == ["left", "right", "side"]
    assert [link.strength for link in links] == ["hard", "hard", "soft"]
    assert all(link.distance == 1 and link.via == "top" for link in links)
    assert links[0].reason == "top needs left"


def test_direct_prerequisites_strength_filter():
    graph = diamond()
    assert ids(graph.direct_prerequisites("top", "hard")) == ["left", "right"]
    assert ids(graph.direct_prerequisites("top", "soft")) == ["side"]
    assert graph.direct_prerequisites("root") == []


def test_all_prerequisites_counts_each_topic_once_in_a_diamond():
    links = diamond().all_prerequisites("top")

    # "base" is reachable through left and through right, but appears once.
    assert ids(links) == ["left", "right", "side", "base", "root"]
    assert len(set(ids(links))) == len(links)
    assert {link.topic_id: link.distance for link in links} == {
        "left": 1,
        "right": 1,
        "side": 1,
        "base": 2,
        "root": 3,
    }
    by_id = {link.topic_id: link for link in links}
    assert by_id["base"].via == "left"
    assert by_id["root"].via == "base"
    assert by_id["root"].reason == "base needs root"


def test_distance_is_the_shortest_path():
    # far is two steps away through mid, but also a direct prerequisite.
    graph = PrerequisiteGraph([edge("a", "mid"), edge("mid", "far"), edge("a", "far", "soft")])

    links = {link.topic_id: link for link in graph.all_prerequisites("a")}
    assert links["far"].distance == 1
    assert links["far"].strength == "soft"


def test_a_hard_edge_wins_over_a_soft_one_at_the_same_distance():
    graph = PrerequisiteGraph(
        [edge("a", "x", "soft"), edge("a", "y"), edge("x", "shared", "soft"), edge("y", "shared")]
    )

    shared = next(link for link in graph.all_prerequisites("a") if link.topic_id == "shared")
    assert (shared.distance, shared.strength, shared.via) == (2, "hard", "y")


def test_all_prerequisites_strength_filter_follows_only_that_strength():
    graph = PrerequisiteGraph(
        [edge("a", "b"), edge("b", "c", "soft"), edge("c", "d"), edge("a", "e", "soft")]
    )

    assert ids(graph.all_prerequisites("a", "hard")) == ["b"]
    assert ids(graph.all_prerequisites("a", "soft")) == ["e"]
    assert ids(graph.all_prerequisites("a")) == ["b", "e", "c", "d"]


def test_direct_unlocks():
    graph = diamond()

    links = graph.direct_unlocks("base")
    assert ids(links) == ["left", "right"]
    assert all(link.via == "base" and link.distance == 1 for link in links)
    assert graph.direct_unlocks("top") == []


def test_step_back_orders_by_distance_then_strength_then_centrality():
    graph = diamond({"left": 0.2, "right": 0.9, "side": 0.99, "base": 0.5, "root": 0.1})

    candidates = graph.step_back_candidates("top")

    # Direct hard ones first (more central first), then the direct soft one
    # even though it is the most central, then further back.
    assert ids(candidates) == ["right", "left", "side", "base", "root"]
    assert [c.distance for c in candidates] == [1, 1, 1, 2, 3]


def test_step_back_puts_unknown_centrality_last_and_breaks_ties_by_id():
    graph = PrerequisiteGraph(
        [edge("a", "p"), edge("a", "q"), edge("a", "r"), edge("a", "s")],
        {"p": None, "q": 0.5, "r": 0.5, "s": 0.7},
    )

    assert ids(graph.step_back_candidates("a")) == ["s", "q", "r", "p"]


def test_unknown_topic_is_empty_everywhere_and_not_contained():
    graph = diamond()

    assert "nope" not in graph
    assert "top" in graph
    assert graph.direct_prerequisites("nope") == []
    assert graph.all_prerequisites("nope") == []
    assert graph.direct_unlocks("nope") == []
    assert graph.step_back_candidates("nope") == []


def test_topics_without_edges_are_part_of_the_graph():
    graph = PrerequisiteGraph([edge("a", "b")], {"a": 0.1, "b": 0.2, "lonely": 0.3})

    assert "lonely" in graph
    assert graph.topic_count == 3
    assert graph.edge_count == 1
    assert graph.all_prerequisites("lonely") == []


def test_a_cycle_does_not_loop_forever():
    # The importer rejects cycles; the graph still has to stay safe.
    graph = PrerequisiteGraph([edge("a", "b"), edge("b", "c"), edge("c", "a")])

    assert ids(graph.all_prerequisites("a")) == ["b", "c"]


def test_reload_replaces_everything():
    graph = PrerequisiteGraph()
    assert not graph.loaded
    assert graph.topic_count == 0

    graph.reload(DIAMOND, {"top": 0.5}, version="v1")
    assert graph.loaded
    assert graph.version == "v1"
    assert ids(graph.direct_prerequisites("top")) == ["left", "right", "side"]

    graph.reload([edge("x", "y")], {"x": 0.1, "y": 0.2}, version="v2")
    assert graph.version == "v2"
    assert "top" not in graph
    assert graph.direct_prerequisites("top") == []
    assert ids(graph.direct_prerequisites("x")) == ["y"]
    assert graph.topic_count == 2
