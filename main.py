"""Entry point of the Fly-in drone routing simulation."""

import argparse
import sys

from display import Display, Palette
from map_parser import MapParser, ParseError
from pathfinder import NoPathError, PathFinder
from simulation import Simulation, SimulationError


class FlyIn:
    """Tie the parser, pathfinder, simulation and display together."""

    def __init__(self, map_path: str, visual: bool, color: bool) -> None:
        """Store the run options.

        Args:
            map_path: Path of the map file to solve.
            visual: True to print a panel with every zone after each turn.
            color: True to color the output.
        """
        self.map_path: str = map_path
        self.visual: bool = visual
        self.color: bool = color

    def run(self) -> int:
        """Solve the map and print the simulation.

        Returns:
            The exit status: 0 on success, 1 on any error.
        """
        try:
            graph = MapParser().parse_file(self.map_path)
            plans = PathFinder(graph).plan_all()
            turns = Simulation(graph, plans).run()
        except OSError as error:
            return self._fail(f"cannot read '{self.map_path}': {error}")
        except ParseError as error:
            return self._fail(f"invalid map: {error}")
        except NoPathError as error:
            return self._fail(f"unsolvable map: {error}")
        except SimulationError as error:
            return self._fail(f"invalid simulation: {error}")
        display = Display(graph, Palette(self.color))
        for state in turns:
            if self.visual:
                print(display.panel(state))
            else:
                print(display.line(state))
        if self.visual:
            print(display.summary(turns))
        return 0

    def _fail(self, message: str) -> int:
        """Print an error on the error stream.

        Args:
            message: What went wrong.

        Returns:
            The exit status for an error.
        """
        print(f"Error: {message}", file=sys.stderr)
        return 1


def main() -> int:
    """Read the command line and run the simulation.

    Returns:
        The exit status of the program.
    """
    parser = argparse.ArgumentParser(
        description="Route a fleet of drones from start to end."
    )
    parser.add_argument("map", help="path of the map file")
    parser.add_argument(
        "-v",
        "--visual",
        action="store_true",
        help="show every zone's occupancy after each turn",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="disable colored output"
    )
    args = parser.parse_args()
    color = not args.no_color and sys.stdout.isatty()
    try:
        return FlyIn(args.map, args.visual, color).run()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
