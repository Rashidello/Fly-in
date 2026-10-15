"""Replaying the plans turn by turn and checking every rule."""

from dataclasses import dataclass, field

from models import Connection, Drone, Graph, Zone
from pathfinder import Move, Plan


class SimulationError(Exception):
    """A plan breaks a movement or capacity rule."""


@dataclass(frozen=True)
class Event:
    """What one drone did during one turn.

    Attributes:
        drone: The drone that moved.
        zone: Zone it arrived in, or the restricted zone it flies to.
        connection: Connection it is on, if it is still in flight.
    """

    drone: Drone
    zone: Zone
    connection: Connection | None = None

    @property
    def place(self) -> str:
        """Return the zone or connection name used in the output."""
        if self.connection is not None:
            return self.connection.name
        return self.zone.name

    def __str__(self) -> str:
        """Return the event in the output format, such as D1-roof1."""
        return f"{self.drone.name}-{self.place}"


@dataclass
class TurnState:
    """Everything that happened in one turn, and where drones ended up.

    Attributes:
        number: Turn number, starting at 1.
        events: Moves of this turn, ordered by drone number.
        zones: Drones inside each zone at the end of the turn.
        in_flight: Drones on each connection at the end of the turn.
        delivered: How many drones have reached the end so far.
    """

    number: int
    events: list[Event] = field(default_factory=list)
    zones: dict[str, list[Drone]] = field(default_factory=dict)
    in_flight: dict[str, list[Drone]] = field(default_factory=dict)
    delivered: int = 0

    @property
    def line(self) -> str:
        """Return the output line of this turn."""
        return " ".join(str(event) for event in self.events)


class Simulation:
    """Run the plans of all drones and verify they respect the rules.

    The pathfinder already avoids conflicts; this class checks it again
    from scratch, so a bug in planning cannot produce invalid output.
    """

    def __init__(self, graph: Graph, plans: list[Plan]) -> None:
        """Prepare a simulation.

        Args:
            graph: The network the drones fly in.
            plans: One plan per drone.
        """
        self._graph: Graph = graph
        self._plans: list[Plan] = sorted(
            plans, key=lambda plan: plan.drone.drone_id
        )

    def run(self) -> list[TurnState]:
        """Play every turn until all drones are delivered.

        Returns:
            The state after each turn, turn 1 first.

        Raises:
            SimulationError: If a plan breaks a rule.
        """
        for plan in self._plans:
            self._check_plan(plan)
        last = max((plan.arrival for plan in self._plans), default=0)
        position: dict[Drone, Zone] = {
            plan.drone: self._graph.start for plan in self._plans
        }
        delivered = 0
        turns: list[TurnState] = []
        for number in range(1, last + 1):
            state = TurnState(number)
            for plan in self._plans:
                delivered += self._play(plan, number, state, position)
            state.delivered = delivered
            self._check_capacities(state)
            turns.append(state)
        if delivered != len(self._plans):
            raise SimulationError("some drones never reach the end zone")
        return turns

    def _play(
        self,
        plan: Plan,
        number: int,
        state: TurnState,
        position: dict[Drone, Zone],
    ) -> int:
        """Apply one drone's activity for one turn.

        Args:
            plan: The drone's plan.
            number: The current turn.
            state: The turn being built, updated in place.
            position: Last zone of every drone, updated in place.

        Returns:
            1 if the drone reached the end zone this turn, else 0.
        """
        drone = plan.drone
        move = self._active_move(plan, number)
        if move is None:
            zone = position[drone]
            if zone != self._graph.end:
                state.zones.setdefault(zone.name, []).append(drone)
            return 0
        if move.arrival > number:
            state.events.append(
                Event(drone, move.destination, move.connection)
            )
            state.in_flight.setdefault(move.connection.name, []).append(drone)
            return 0
        state.events.append(Event(drone, move.destination))
        position[drone] = move.destination
        if move.destination == self._graph.end:
            return 1
        state.zones.setdefault(move.destination.name, []).append(drone)
        return 0

    def _active_move(self, plan: Plan, number: int) -> Move | None:
        """Return the move the drone is making on a turn, if any.

        Args:
            plan: The drone's plan.
            number: The turn to look at.
        """
        for move in plan.moves:
            if move.turn <= number <= move.arrival:
                return move
        return None

    def _check_plan(self, plan: Plan) -> None:
        """Check that a plan is a valid chain of moves to the end.

        Args:
            plan: The plan to check.

        Raises:
            SimulationError: If a move does not follow the rules.
        """
        here = self._graph.start
        free_from = 1
        for move in plan.moves:
            name = plan.drone.name
            if here not in (move.connection.zone_a, move.connection.zone_b):
                raise SimulationError(
                    f"{name} uses {move.connection.name} from {here.name}"
                )
            if move.connection.other(here) != move.destination:
                raise SimulationError(
                    f"{name} cannot reach {move.destination.name} "
                    f"through {move.connection.name}"
                )
            if move.destination.is_blocked:
                raise SimulationError(
                    f"{name} enters blocked zone {move.destination.name}"
                )
            if move.turn < free_from:
                raise SimulationError(
                    f"{name} starts a move on turn {move.turn} before "
                    "finishing the previous one"
                )
            here = move.destination
            free_from = move.arrival + 1
        if here != self._graph.end:
            raise SimulationError(f"{plan.drone.name} ends in {here.name}")

    def _check_capacities(self, state: TurnState) -> None:
        """Check zone and connection limits at the end of a turn.

        Args:
            state: The finished turn.

        Raises:
            SimulationError: If a zone or a connection is over capacity.
        """
        for name, drones in state.zones.items():
            zone = self._graph.zones[name]
            if self._graph.is_unlimited(zone):
                continue
            if len(drones) > zone.max_drones:
                raise SimulationError(
                    f"turn {state.number}: {len(drones)} drones in {name}, "
                    f"limit is {zone.max_drones}"
                )
        used: dict[Connection, int] = {}
        for event in state.events:
            move = self._active_move(self._plan_of(event.drone), state.number)
            if move is not None and move.turn == state.number:
                used[move.connection] = used.get(move.connection, 0) + 1
        for connection, count in used.items():
            if count > connection.max_link_capacity:
                raise SimulationError(
                    f"turn {state.number}: {count} drones on "
                    f"{connection.name}, limit is "
                    f"{connection.max_link_capacity}"
                )

    def _plan_of(self, drone: Drone) -> Plan:
        """Return the plan of a drone.

        Args:
            drone: The drone to look up.
        """
        return self._plans[drone.drone_id - 1]
