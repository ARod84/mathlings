"""The prerequisite graph, held in memory. Standard library only, no database.

About 700 topics and 1,500 edges, so plain dicts are plenty. The graph is
filled by `reload`, which service.reload_graph calls with rows from the
database: at API startup, at the end of an import, and whenever the API sees
that the database has been re-imported.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

Strength = Literal["hard", "soft"]

_STRENGTH_RANK = {"hard": 0, "soft": 1}


@dataclass(frozen=True)
class Edge:
    """topic_id depends on prerequisite_id."""

    topic_id: str
    prerequisite_id: str
    strength: str
    reason: str


@dataclass(frozen=True)
class Link:
    """One topic reached from a starting topic, and the edge it was reached by."""

    topic_id: str
    strength: str
    reason: str
    # 1 = direct.
    distance: int
    # The other end of the edge: the topic that needs `topic_id` (for
    # prerequisites), or the prerequisite it builds on (for unlocks).
    via: str


class PrerequisiteGraph:
    def __init__(
        self,
        edges: Iterable[Edge] = (),
        centrality: Mapping[str, float | None] | None = None,
    ) -> None:
        self.prereqs_of: dict[str, list[Edge]] = {}
        self.unlocks_of: dict[str, list[Edge]] = {}
        self.centrality: dict[str, float | None] = {}
        # Whatever the loader wants to remember about where the data came
        # from; used to notice that the database has changed since.
        self.version: object = None
        self.loaded = False
        self.reload(edges, centrality or {})
        self.loaded = bool(self.centrality)

    def reload(
        self,
        edges: Iterable[Edge],
        centrality: Mapping[str, float | None],
        version: object = None,
    ) -> None:
        """Replace the whole graph. `centrality` has one entry per topic, edges or not."""
        prereqs_of: dict[str, list[Edge]] = {topic_id: [] for topic_id in centrality}
        unlocks_of: dict[str, list[Edge]] = {topic_id: [] for topic_id in centrality}
        for edge in edges:
            prereqs_of.setdefault(edge.topic_id, []).append(edge)
            unlocks_of.setdefault(edge.prerequisite_id, []).append(edge)
            prereqs_of.setdefault(edge.prerequisite_id, [])
            unlocks_of.setdefault(edge.topic_id, [])

        def order(edge: Edge) -> tuple[int, str, str]:
            return (_STRENGTH_RANK.get(edge.strength, 9), edge.prerequisite_id, edge.topic_id)

        for edge_list in (*prereqs_of.values(), *unlocks_of.values()):
            edge_list.sort(key=order)

        # Swapped in together, so a reader never sees half of a reload.
        self.prereqs_of, self.unlocks_of = prereqs_of, unlocks_of
        self.centrality = {**{topic_id: None for topic_id in prereqs_of}, **centrality}
        self.version = version
        self.loaded = True

    def __contains__(self, topic_id: object) -> bool:
        return topic_id in self.prereqs_of

    @property
    def topic_count(self) -> int:
        return len(self.prereqs_of)

    @property
    def edge_count(self) -> int:
        return sum(len(edges) for edges in self.prereqs_of.values())

    def direct_prerequisites(self, topic_id: str, strength: Strength | None = None) -> list[Link]:
        """What the topic needs first: hard prerequisites, then soft ones."""
        return [
            Link(edge.prerequisite_id, edge.strength, edge.reason, 1, topic_id)
            for edge in self.prereqs_of.get(topic_id, ())
            if strength is None or edge.strength == strength
        ]

    def all_prerequisites(self, topic_id: str, strength: Strength | None = None) -> list[Link]:
        """Everything the topic needs, however far back, nearest first.

        Breadth-first, so `distance` is the shortest path and each topic
        appears once even when several paths lead to it. With `strength`,
        only edges of that strength are followed. When a topic can be reached
        at the same distance by a hard and a soft edge, the hard one is shown.
        """
        seen = {topic_id}
        found: list[Link] = []
        frontier = [topic_id]
        distance = 0
        while frontier:
            distance += 1
            level: dict[str, Link] = {}
            for current in frontier:
                for edge in self.prereqs_of.get(current, ()):
                    if strength is not None and edge.strength != strength:
                        continue
                    target = edge.prerequisite_id
                    if target in seen:
                        continue
                    known = level.get(target)
                    if known is None or self._rank(edge.strength) < self._rank(known.strength):
                        level[target] = Link(target, edge.strength, edge.reason, distance, current)
            seen.update(level)
            found.extend(level[target] for target in sorted(level))
            frontier = sorted(level)
        return found

    def direct_unlocks(self, topic_id: str) -> list[Link]:
        """The topics that directly depend on this one."""
        return [
            Link(edge.topic_id, edge.strength, edge.reason, 1, topic_id)
            for edge in self.unlocks_of.get(topic_id, ())
        ]

    def step_back_candidates(self, topic_id: str) -> list[Link]:
        """Where to step back to when a child is stuck on this topic, best first.

        Nearest first. At the same distance, hard prerequisites come before
        soft ones, then the more central topic (the one more of the graph
        rests on) comes first. So the list opens with the direct hard
        prerequisites, then the direct soft ones, then those further back.
        """

        def order(link: Link) -> tuple[int, int, float, str]:
            centrality = self.centrality.get(link.topic_id)
            return (
                link.distance,
                self._rank(link.strength),
                -centrality if centrality is not None else float("inf"),
                link.topic_id,
            )

        return sorted(self.all_prerequisites(topic_id), key=order)

    @staticmethod
    def _rank(strength: str) -> int:
        return _STRENGTH_RANK.get(strength, 9)


# The graph the API and the importer share within one process.
taxonomy_graph = PrerequisiteGraph()
