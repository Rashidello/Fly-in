"""Coloured terminal rendering of the simulation."""

from models import Graph, Zone
from simulation import Event, TurnState


class Palette:
    """Translate map color names into ANSI terminal escape codes.

    Codes use the 256-color mode: ESC[38;5;<n>m sets the text color to
    color number n, and ESC[0m resets every style.
    """

    RESET: str = "\033[0m"
    BOLD: str = "\033[1m"
    DIM: str = "\033[2m"
    CODES: dict[str, int] = {
        "black": 244,
        "white": 255,
        "red": 196,
        "darkred": 124,
        "maroon": 88,
        "crimson": 161,
        "green": 46,
        "lime": 118,
        "blue": 33,
        "cyan": 51,
        "yellow": 226,
        "gold": 220,
        "orange": 208,
        "brown": 130,
        "purple": 129,
        "violet": 177,
        "magenta": 201,
        "pink": 213,
        "gray": 245,
        "grey": 245,
    }
    RAINBOW: tuple[int, ...] = (196, 208, 226, 46, 33, 129)

    def __init__(self, enabled: bool) -> None:
        """Create a palette.

        Args:
            enabled: False to produce plain text with no escape codes.
        """
        self.enabled: bool = enabled

    def paint(self, text: str, color: str | None) -> str:
        """Return the text in the given color.

        Unknown color names leave the text unchanged, since maps may use
        any single word as a color.

        Args:
            text: The text to color.
            color: A color name from the map, or None.
        """
        if not self.enabled or color is None:
            return text
        name = color.lower()
        if name == "rainbow":
            return "".join(
                self._code(self.RAINBOW[index % len(self.RAINBOW)]) + char
                for index, char in enumerate(text)
            ) + self.RESET
        if name not in self.CODES:
            return text
        return self._code(self.CODES[name]) + text + self.RESET

    def style(self, text: str, code: str) -> str:
        """Return the text with a style such as BOLD or DIM.

        Args:
            text: The text to style.
            code: One of the style constants of this class.
        """
        if not self.enabled:
            return text
        return code + text + self.RESET

    def _code(self, number: int) -> str:
        """Return the escape code selecting a 256-color number."""
        return f"\033[38;5;{number}m"


class Display:
    """Render turns as output lines, with an optional state panel."""

    BAR_WIDTH: int = 10

    def __init__(self, graph: Graph, palette: Palette) -> None:
        """Create a display.

        Args:
            graph: The network being simulated.
            palette: Colors to use, possibly disabled.
        """
        self._graph: Graph = graph
        self._palette: Palette = palette
        self._width: int = max(len(name) for name in graph.zones)

    def line(self, state: TurnState) -> str:
        """Return the output line of a turn, colored when enabled.

        Without colors this is exactly the required D<ID>-<zone> format.

        Args:
            state: The turn to render.
        """
        return " ".join(self._event(event) for event in state.events)

    def panel(self, state: TurnState) -> str:
        """Return a block describing every zone after a turn.

        Args:
            state: The turn to describe.
        """
        paint = self._palette.paint
        title = f"== Turn {state.number} "
        lines = [self._palette.style(title.ljust(50, "="), Palette.BOLD)]
        lines.append(self.line(state) or "(every drone waits)")
        for zone in self._graph.zones.values():
            drones = state.zones.get(zone.name, [])
            if zone == self._graph.end:
                count = state.delivered
            elif zone == self._graph.start:
                count = len(drones)
            elif not drones:
                continue
            else:
                count = len(drones)
            name = paint(zone.name.ljust(self._width), zone.color)
            names = " ".join(drone.name for drone in drones)
            lines.append(f"  {name}  {self._gauge(zone, count)}  {names}")
        for connection, drones in state.in_flight.items():
            names = " ".join(drone.name for drone in drones)
            label = self._palette.style(f"~ {connection}", Palette.DIM)
            lines.append(f"  {label}  {names}")
        return "\n".join(lines)

    def summary(self, turns: list[TurnState]) -> str:
        """Return the closing line with the total turn count.

        Args:
            turns: Every turn of the simulation.
        """
        delivered = turns[-1].delivered if turns else 0
        text = f"{delivered} drones delivered in {len(turns)} turns"
        return self._palette.style(text, Palette.BOLD)

    def _event(self, event: Event) -> str:
        """Return one event, the destination in its zone color."""
        place = self._palette.paint(event.place, event.zone.color)
        if event.connection is not None:
            place = self._palette.style(place, Palette.DIM)
        return f"{event.drone.name}-{place}"

    def _gauge(self, zone: Zone, count: int) -> str:
        """Return a bar showing how full a zone is.

        Args:
            zone: The zone to measure.
            count: Drones in it, or delivered for the end zone.
        """
        if self._graph.is_unlimited(zone):
            return f"[{count} drones]".ljust(self.BAR_WIDTH + 8)
        filled = round(self.BAR_WIDTH * count / zone.max_drones)
        bar = "#" * filled + "." * (self.BAR_WIDTH - filled)
        return f"[{bar}] {count}/{zone.max_drones}".ljust(self.BAR_WIDTH + 8)
