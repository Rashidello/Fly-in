"""Reading a Fly-in map file into a Graph."""

import re

from models import Connection, Graph, Zone, ZoneType


class ParseError(Exception):
    """A map file that does not follow the expected format."""

    def __init__(self, line_number: int, message: str) -> None:
        """Create the error.

        Args:
            line_number: Line of the file where the problem is, or 0
                when it concerns the whole file.
            message: What is wrong.
        """
        self.line_number: int = line_number
        self.message: str = message
        if line_number > 0:
            super().__init__(f"line {line_number}: {message}")
        else:
            super().__init__(message)


class MapParser:
    """Turn the text of a map file into a Graph.

    Each line is checked as soon as it is read, so the first error
    stops parsing and reports its line number.
    """

    ZONE_PREFIXES: dict[str, tuple[bool, bool]] = {
        "start_hub": (True, False),
        "end_hub": (False, True),
        "hub": (False, False),
    }
    ZONE_KEYS: frozenset[str] = frozenset({"zone", "color", "max_drones"})
    CONNECTION_KEYS: frozenset[str] = frozenset({"max_link_capacity"})

    _ZONE_RE = re.compile(
        r"^(?P<name>[^\s\[\]-]+)\s+(?P<x>[+-]?\d+)\s+(?P<y>[+-]?\d+)"
        r"\s*(?:\[(?P<meta>[^\[\]]*)\])?$"
    )
    _CONNECTION_RE = re.compile(
        r"^(?P<a>[^\s\[\]-]+)-(?P<b>[^\s\[\]-]+)"
        r"\s*(?:\[(?P<meta>[^\[\]]*)\])?$"
    )
    _POSITIVE_RE = re.compile(r"^\+?\d+$")

    def __init__(self) -> None:
        """Create a parser with no graph yet."""
        self._graph: Graph | None = None

    def parse_file(self, path: str) -> Graph:
        """Read and parse a map file.

        Args:
            path: Path of the map file.

        Returns:
            The graph described by the file.

        Raises:
            OSError: If the file cannot be read.
            ParseError: If the content is invalid.
        """
        try:
            with open(path, encoding="utf-8") as file:
                text = file.read()
        except UnicodeDecodeError as error:
            raise ParseError(0, f"the file is not valid text: {error}")
        return self.parse_text(text)

    def parse_text(self, text: str) -> Graph:
        """Parse the full content of a map file.

        Args:
            text: Content of the file.

        Returns:
            The graph described by the text.

        Raises:
            ParseError: If the content is invalid.
        """
        self._graph = None
        for number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.split("#", 1)[0].strip()
            if line:
                self._parse_line(number, line)
        graph = self._graph
        if graph is None:
            raise ParseError(0, "the file is empty")
        if not graph.has_start:
            raise ParseError(0, "missing start_hub zone")
        if not graph.has_end:
            raise ParseError(0, "missing end_hub zone")
        return graph

    def _parse_line(self, number: int, line: str) -> None:
        """Parse one meaningful line and add its content to the graph.

        Args:
            number: Line number, for error messages.
            line: The line without comment or surrounding spaces.

        Raises:
            ParseError: If the line is invalid.
        """
        prefix, separator, rest = line.partition(":")
        prefix = prefix.strip()
        rest = rest.strip()
        if not separator:
            raise ParseError(number, f"expected '<type>: ...', got '{line}'")
        if self._graph is None:
            if prefix != "nb_drones":
                raise ParseError(
                    number, "the first line must be 'nb_drones: <number>'"
                )
            self._graph = Graph(self._positive(number, "nb_drones", rest))
            return
        try:
            if prefix in self.ZONE_PREFIXES:
                is_start, is_end = self.ZONE_PREFIXES[prefix]
                zone = self._parse_zone(number, rest, is_start or is_end)
                self._graph.add_zone(zone, is_start, is_end)
            elif prefix == "connection":
                self._graph.add_connection(
                    self._parse_connection(number, rest)
                )
            elif prefix == "nb_drones":
                raise ParseError(number, "nb_drones is defined twice")
            else:
                raise ParseError(number, f"unknown line type '{prefix}'")
        except ValueError as error:
            raise ParseError(number, str(error))

    def _parse_zone(self, number: int, rest: str, unlimited: bool) -> Zone:
        """Parse '<name> <x> <y> [metadata]'.

        Args:
            number: Line number, for error messages.
            rest: Text after the prefix.
            unlimited: True for the start and end zones, whose
                max_drones value is ignored.

        Returns:
            The zone described by the text.

        Raises:
            ParseError: If the text is invalid.
        """
        match = self._ZONE_RE.match(rest)
        if match is None:
            raise ParseError(
                number,
                "expected '<name> <x> <y> [metadata]' with integer "
                f"coordinates and no dash in the name, got '{rest}'",
            )
        meta = self._parse_metadata(number, match["meta"], self.ZONE_KEYS)
        zone_type = ZoneType.NORMAL
        if "zone" in meta:
            try:
                zone_type = ZoneType(meta["zone"])
            except ValueError:
                raise ParseError(
                    number,
                    f"invalid zone type '{meta['zone']}', expected one of: "
                    + ", ".join(kind.value for kind in ZoneType),
                )
        max_drones = 1
        if "max_drones" in meta and not unlimited:
            max_drones = self._positive(
                number, "max_drones", meta["max_drones"]
            )
        return Zone(
            name=match["name"],
            x=int(match["x"]),
            y=int(match["y"]),
            zone_type=zone_type,
            color=meta.get("color"),
            max_drones=max_drones,
        )

    def _parse_connection(self, number: int, rest: str) -> Connection:
        """Parse '<zone1>-<zone2> [metadata]'.

        Args:
            number: Line number, for error messages.
            rest: Text after the prefix.

        Returns:
            The connection described by the text.

        Raises:
            ParseError: If the text is invalid or a zone is unknown.
        """
        match = self._CONNECTION_RE.match(rest)
        if match is None:
            raise ParseError(
                number, f"expected '<zone1>-<zone2> [metadata]', got '{rest}'"
            )
        assert self._graph is not None
        for name in (match["a"], match["b"]):
            if name not in self._graph.zones:
                raise ParseError(number, f"unknown zone '{name}'")
        meta = self._parse_metadata(
            number, match["meta"], self.CONNECTION_KEYS
        )
        capacity = 1
        if "max_link_capacity" in meta:
            capacity = self._positive(
                number, "max_link_capacity", meta["max_link_capacity"]
            )
        return Connection(
            zone_a=self._graph.zones[match["a"]],
            zone_b=self._graph.zones[match["b"]],
            max_link_capacity=capacity,
        )

    def _parse_metadata(
        self, number: int, block: str | None, allowed: frozenset[str]
    ) -> dict[str, str]:
        """Parse the inside of a '[key=value ...]' block.

        Args:
            number: Line number, for error messages.
            block: Text between the brackets, or None if there were none.
            allowed: Keys accepted on this kind of line.

        Returns:
            The keys and values, in any order.

        Raises:
            ParseError: If a tag is malformed, unknown or repeated.
        """
        result: dict[str, str] = {}
        if block is None:
            return result
        for tag in block.split():
            key, separator, value = tag.partition("=")
            if not separator or not key or not value:
                raise ParseError(
                    number, f"invalid metadata '{tag}', expected key=value"
                )
            if key not in allowed:
                raise ParseError(
                    number,
                    f"unknown metadata '{key}', expected one of: "
                    + ", ".join(sorted(allowed)),
                )
            if key in result:
                raise ParseError(number, f"metadata '{key}' is repeated")
            result[key] = value
        return result

    def _positive(self, number: int, field: str, value: str) -> int:
        """Convert a text to a positive integer.

        Args:
            number: Line number, for error messages.
            field: Name of the value, for error messages.
            value: Text to convert.

        Returns:
            The integer, at least 1.

        Raises:
            ParseError: If the text is not a positive integer.
        """
        if self._POSITIVE_RE.match(value) is None or int(value) < 1:
            raise ParseError(
                number, f"{field} must be a positive integer, got '{value}'"
            )
        return int(value)
