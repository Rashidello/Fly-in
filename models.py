"""Data model of a Fly-in map: zones, connections, graph and drones."""

from dataclasses import dataclass
from enum import Enum


class ZoneType(Enum):
    """Kind of a zone, which decides how drones may enter it."""

    NORMAL = "normal"
    BLOCKED = "blocked"
    RESTRICTED = "restricted"
    PRIORITY = "priority"

    @property
    def cost(self) -> int:
        """Return the number of turns needed to move into this type."""
        if self is ZoneType.RESTRICTED:
            return 2
        return 1


@dataclass(frozen=True)
class Zone:
    """A node of the network.

    Attributes:
        name: Unique name of the zone.
        x: Horizontal coordinate, used only for display.
        y: Vertical coordinate, used only for display.
        zone_type: Kind of the zone.
        color: Display color, or None when the map gives none.
        max_drones: How many drones may be in the zone at once.
    """

    name: str
    x: int
    y: int
    zone_type: ZoneType = ZoneType.NORMAL
    color: str | None = None
    max_drones: int = 1

    @property
    def cost(self) -> int:
        """Return the number of turns needed to move into this zone."""
        return self.zone_type.cost

    @property
    def is_blocked(self) -> bool:
        """Return True if no drone may ever enter this zone."""
        return self.zone_type is ZoneType.BLOCKED

    @property
    def is_priority(self) -> bool:
        """Return True if pathfinding should prefer this zone."""
        return self.zone_type is ZoneType.PRIORITY


@dataclass(frozen=True)
class Connection:
    """A bidirectional edge between two zones.

    Attributes:
        zone_a: First zone, as written in the map file.
        zone_b: Second zone, as written in the map file.
        max_link_capacity: How many drones may use it in the same turn.
    """

    zone_a: Zone
    zone_b: Zone
    max_link_capacity: int = 1

    @property
    def name(self) -> str:
        """Return the connection name as written in the map file."""
        return f"{self.zone_a.name}-{self.zone_b.name}"

    def other(self, zone: Zone) -> Zone:
        """Return the zone at the opposite end from the given one.

        Args:
            zone: One end of this connection.

        Returns:
            The other end.

        Raises:
            ValueError: If the zone is not an end of this connection.
        """
        if zone == self.zone_a:
            return self.zone_b
        if zone == self.zone_b:
            return self.zone_a
        raise ValueError(f"{zone.name} is not part of {self.name}")


@dataclass(frozen=True)
class Drone:
    """A drone, identified by its number.

    Attributes:
        drone_id: Number of the drone, starting at 1.
    """

    drone_id: int

    @property
    def name(self) -> str:
        """Return the identifier used in the output, such as D1."""
        return f"D{self.drone_id}"


class Graph:
    """The whole network, stored as an adjacency list."""

    def __init__(self, nb_drones: int) -> None:
        """Create an empty graph for the given number of drones.

        Args:
            nb_drones: Number of drones waiting in the start zone.
        """
        self.nb_drones: int = nb_drones
        self.zones: dict[str, Zone] = {}
        self.connections: list[Connection] = []
        self._start: Zone | None = None
        self._end: Zone | None = None
        self._adjacency: dict[str, list[Connection]] = {}
        self._pairs: set[frozenset[str]] = set()

    @property
    def start(self) -> Zone:
        """Return the start zone.

        Raises:
            ValueError: If no start zone was added.
        """
        if self._start is None:
            raise ValueError("the map has no start zone")
        return self._start

    @property
    def end(self) -> Zone:
        """Return the end zone.

        Raises:
            ValueError: If no end zone was added.
        """
        if self._end is None:
            raise ValueError("the map has no end zone")
        return self._end

    @property
    def has_start(self) -> bool:
        """Return True once a start zone was added."""
        return self._start is not None

    @property
    def has_end(self) -> bool:
        """Return True once an end zone was added."""
        return self._end is not None

    def add_zone(
        self, zone: Zone, is_start: bool = False, is_end: bool = False
    ) -> None:
        """Add a zone to the graph.

        Args:
            zone: The zone to add.
            is_start: True if this is the start zone.
            is_end: True if this is the end zone.

        Raises:
            ValueError: If the name is taken, or a second start or end
                zone is given.
        """
        if zone.name in self.zones:
            raise ValueError(f"duplicate zone name: {zone.name}")
        if is_start and self._start is not None:
            raise ValueError("a start zone is already defined")
        if is_end and self._end is not None:
            raise ValueError("an end zone is already defined")
        self.zones[zone.name] = zone
        self._adjacency[zone.name] = []
        if is_start:
            self._start = zone
        if is_end:
            self._end = zone

    def add_connection(self, connection: Connection) -> None:
        """Add a connection between two zones already in the graph.

        Args:
            connection: The connection to add.

        Raises:
            ValueError: If a zone is unknown, both ends are the same
                zone, or the connection already exists.
        """
        pair = frozenset((connection.zone_a.name, connection.zone_b.name))
        if len(pair) == 1:
            raise ValueError(
                f"a zone cannot connect to itself: {connection.name}"
            )
        for name in pair:
            if name not in self.zones:
                raise ValueError(f"unknown zone: {name}")
        if pair in self._pairs:
            raise ValueError(f"duplicate connection: {connection.name}")
        self._pairs.add(pair)
        self.connections.append(connection)
        for name in pair:
            self._adjacency[name].append(connection)

    def neighbours(self, zone: Zone) -> list[tuple[Zone, Connection]]:
        """Return each zone one move away, with the connection used.

        Args:
            zone: The zone to look around.

        Returns:
            Pairs of (neighbour zone, connection leading to it).
        """
        links = self._adjacency[zone.name]
        return [(link.other(zone), link) for link in links]

    def is_unlimited(self, zone: Zone) -> bool:
        """Return True if the zone has no capacity limit.

        The start and end zones accept any number of drones, whatever
        their max_drones metadata says.

        Args:
            zone: The zone to check.
        """
        return zone == self._start or zone == self._end
