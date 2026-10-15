"""Planning every drone's route through space and time."""

import heapq
from dataclasses import dataclass, field

from models import Connection, Drone, Graph, Zone


class NoPathError(Exception):
    """The map is valid but the end zone cannot be reached."""


@dataclass(frozen=True)
class Move:
    """One movement of a drone from one zone to a neighbour.

    Attributes:
        turn: Turn on which the drone leaves its zone.
        connection: Connection it travels along.
        destination: Zone it arrives in.
    """

    turn: int
    connection: Connection
    destination: Zone

    @property
    def arrival(self) -> int:
        """Return the turn at the end of which the drone has arrived.

        A move into a restricted zone takes two turns: the drone spends
        the first one on the connection.
        """
        return self.turn + self.destination.cost - 1


@dataclass
class Plan:
    """The full route of one drone, waits included implicitly.

    Between two moves, the drone stays in the zone it reached.

    Attributes:
        drone: The drone following this plan.
        moves: Its moves, in order.
    """

    drone: Drone
    moves: list[Move] = field(default_factory=list)

    @property
    def arrival(self) -> int:
        """Return the turn on which the drone reaches the end zone."""
        if not self.moves:
            return 0
        return self.moves[-1].arrival


class ReservationTable:
    """What every already planned drone occupies, turn by turn.

    A zone counts the drones inside it at the end of a turn. A
    connection counts the drones that start crossing it during a turn;
    for a restricted destination the drone stays on the connection for
    that turn only, as the connection is freed on the turn it lands.
    """

    def __init__(self, graph: Graph) -> None:
        """Create an empty table.

        Args:
            graph: The network the drones fly in.
        """
        self._graph: Graph = graph
        self._zones: dict[tuple[str, int], int] = {}
        self._links: dict[tuple[str, int], int] = {}

    def zone_free(self, zone: Zone, turn: int) -> bool:
        """Return True if one more drone fits in the zone on that turn.

        Args:
            zone: The zone to check.
            turn: The turn to check.
        """
        if self._graph.is_unlimited(zone):
            return True
        return self._zones.get((zone.name, turn), 0) < zone.max_drones

    def link_free(self, connection: Connection, turn: int) -> bool:
        """Return True if one more drone may use the connection that turn.

        Args:
            connection: The connection to check.
            turn: The turn to check.
        """
        used = self._links.get((connection.name, turn), 0)
        return used < connection.max_link_capacity

    def reserve(self, plan: Plan) -> None:
        """Record everything a planned drone occupies.

        Args:
            plan: The plan of a drone that is now fixed.
        """
        for index, move in enumerate(plan.moves):
            link_key = (move.connection.name, move.turn)
            self._links[link_key] = self._links.get(link_key, 0) + 1
            if self._graph.is_unlimited(move.destination):
                continue
            leave = plan.moves[index + 1].turn
            for turn in range(move.arrival, leave):
                zone_key = (move.destination.name, turn)
                self._zones[zone_key] = self._zones.get(zone_key, 0) + 1


class PathFinder:
    """Plan all drones one after another, earliest arrival first.

    Each drone runs an A* search on states (zone, turn). From a state
    it may wait one turn or move to a neighbour, as long as the
    reservation table shows room. Once its plan is found it is
    reserved, and the next drone plans around it. This is called
    prioritized planning: drones never collide because a later drone
    only uses what earlier ones left free.
    """

    def __init__(self, graph: Graph) -> None:
        """Prepare the search for a graph.

        Args:
            graph: The network to plan in.
        """
        self._graph: Graph = graph
        self._distance: dict[str, int] = self._distances_to_end()

    @property
    def is_solvable(self) -> bool:
        """Return True if the end zone can be reached from the start."""
        return self._graph.start.name in self._distance

    def plan_all(self) -> list[Plan]:
        """Plan the route of every drone.

        Returns:
            One plan per drone, drone 1 first.

        Raises:
            NoPathError: If no route joins the start to the end.
        """
        if not self.is_solvable:
            raise NoPathError(
                f"no path joins '{self._graph.start.name}' "
                f"to '{self._graph.end.name}'"
            )
        table = ReservationTable(self._graph)
        plans: list[Plan] = []
        latest = 0
        for drone_id in range(1, self._graph.nb_drones + 1):
            plan = self._plan_drone(Drone(drone_id), table, latest)
            table.reserve(plan)
            plans.append(plan)
            latest = max(latest, plan.arrival)
        return plans

    def _distances_to_end(self) -> dict[str, int]:
        """Compute, for every zone, the fewest turns to reach the end.

        This is Dijkstra run backwards from the end, ignoring other
        drones. It serves to detect unsolvable maps and as the A*
        heuristic: no drone can ever do better than this distance.

        Returns:
            Distance by zone name, for zones that can reach the end.
        """
        end = self._graph.end
        distance: dict[str, int] = {end.name: 0}
        queue: list[tuple[int, str]] = [(0, end.name)]
        while queue:
            current, name = heapq.heappop(queue)
            if current > distance[name]:
                continue
            zone = self._graph.zones[name]
            if zone.is_blocked:
                continue
            for neighbour, _ in self._graph.neighbours(zone):
                if neighbour.is_blocked and neighbour != self._graph.start:
                    continue
                candidate = current + zone.cost
                if candidate < distance.get(neighbour.name, candidate + 1):
                    distance[neighbour.name] = candidate
                    heapq.heappush(queue, (candidate, neighbour.name))
        return distance

    def _plan_drone(
        self, drone: Drone, table: ReservationTable, latest: int
    ) -> Plan:
        """Find the earliest-arriving route of one drone.

        Args:
            drone: The drone to plan.
            table: What earlier drones already occupy.
            latest: Last arrival turn among earlier drones.

        Returns:
            The drone's plan.

        Raises:
            RuntimeError: If no route exists, which the horizon below
                makes impossible on a solvable map.
        """
        start = self._graph.start
        end = self._graph.end
        # After every earlier drone has landed the network is empty,
        # so waiting until then and taking the shortest path always
        # works. No search needs to look further than that.
        horizon = latest + self._distance[start.name]
        Key = tuple[str, int]
        came_from: dict[Key, tuple[Key, Move | None]] = {}
        best: dict[Key, int] = {(start.name, 0): 0}
        counter = 0
        queue: list[tuple[int, int, int, int, str]] = [
            (self._distance[start.name], 0, 0, counter, start.name)
        ]
        while queue:
            _, minus_priority, turn, _, name = heapq.heappop(queue)
            key = (name, turn)
            if best.get(key, 1) < minus_priority:
                continue
            if name == end.name:
                return self._build_plan(drone, key, came_from)
            zone = self._graph.zones[name]
            options: list[tuple[Zone, Move | None]] = [(zone, None)]
            for neighbour, connection in self._graph.neighbours(zone):
                if neighbour.is_blocked:
                    continue
                if neighbour.name not in self._distance:
                    continue
                options.append(
                    (neighbour, Move(turn + 1, connection, neighbour))
                )
            for target, move in options:
                if move is None:
                    arrival = turn + 1
                else:
                    arrival = move.arrival
                    if not table.link_free(move.connection, move.turn):
                        continue
                estimate = arrival + self._distance[target.name]
                if estimate > horizon:
                    continue
                if not table.zone_free(target, arrival):
                    continue
                next_priority = minus_priority
                if move is not None and target.is_priority:
                    next_priority -= 1
                next_key = (target.name, arrival)
                if next_priority >= best.get(next_key, 1):
                    continue
                best[next_key] = next_priority
                came_from[next_key] = (key, move)
                counter += 1
                heapq.heappush(
                    queue,
                    (estimate, next_priority, arrival, counter, target.name),
                )
        raise RuntimeError(f"no route found for {drone.name}")

    def _build_plan(
        self,
        drone: Drone,
        goal: tuple[str, int],
        came_from: dict[tuple[str, int], tuple[tuple[str, int], Move | None]],
    ) -> Plan:
        """Walk the search tree back from the goal to rebuild the moves.

        Args:
            drone: The drone the plan is for.
            goal: State (zone name, turn) where the end was reached.
            came_from: Parent state and move of every reached state.

        Returns:
            The plan, moves in chronological order.
        """
        moves: list[Move] = []
        key = goal
        while key in came_from:
            key, move = came_from[key]
            if move is not None:
                moves.append(move)
        moves.reverse()
        return Plan(drone, moves)
