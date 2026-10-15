*This project has been created as part of the 42 curriculum by rarayano.*

# Fly-in

## Description

Fly-in moves a group of drones from a start zone to an end zone through a network of connected zones, in as few turns as possible.

The program reads a map file, plans a route for every drone, checks that no rule is broken, and prints the moves turn by turn in the `D<ID>-<zone>` format.

Main rules:

- A zone holds at most `max_drones` drones (default 1). The start and end zones have no limit.
- A connection lets at most `max_link_capacity` drones cross it in the same turn (default 1).
- `restricted` zones take 2 turns to enter, `blocked` zones can't be entered, and `priority` zones should be preferred.
- All drones move at the same time.

No graph library is used. The code is object-oriented and passes `flake8` and `mypy`.

## Instructions

You need Python 3.10 or later. `flake8` and `mypy` are only used for linting.

```sh
make install                 # install the dependencies
python3 main.py <map_file>   # run a map
```

Options:

- `-v`, `--visual`: show the state of every zone after each turn
- `--no-color`: disable colours

Makefile rules:

- `make run`: run a map (`make run MAP=path/to/map.txt`)
- `make debug`: run with `pdb`
- `make clean`: remove cache files
- `make lint`: run `flake8` and `mypy`
- `make lint-strict`: run `flake8` and `mypy --strict`

## Example

Input:

```
nb_drones: 4

start_hub: start 0 0 [color=green]
hub: junction 1 0 [color=yellow max_drones=2]
hub: path_a 2 1 [color=blue]
hub: path_b 2 -1 [color=blue]
end_hub: goal 3 0 [color=red]

connection: start-junction [max_link_capacity=2]
connection: junction-path_a
connection: junction-path_b
connection: path_a-goal
connection: path_b-goal
```

Output:

```
D1-junction D2-junction
D1-path_a D2-path_b D3-junction D4-junction
D1-goal D2-goal D3-path_a D4-path_b
D3-goal D4-goal
```

When a drone is flying to a restricted zone, the line shows the connection name instead:

```
D1-base-roof
D1-roof D2-base-roof
D1-goal D2-roof
D2-goal
```

If the map is invalid, the program stops with a clear message:

```
Error: invalid map: line 4: invalid zone type 'lava', expected one of: normal, blocked, restricted, priority
Error: unsolvable map: no path joins 'a' to 'b'
```

## Algorithm

The program is split into a few parts:

- `map_parser.py` reads and checks the map file, and stops at the first error with its line number.
- `models.py` holds the zones, connections, drones and the graph.
- `pathfinder.py` plans the routes.
- `simulation.py` replays the routes and checks every rule.
- `display.py` handles colours and the visual mode.

### How the routes are planned

1. **Distance to the end.** A Dijkstra search, run backwards from the end zone, gives each zone its shortest distance to the end in turns. It runs only once. If the start has no distance, the map is unsolvable.

2. **One drone at a time.** Drones are planned in order. When a drone's route is chosen, every zone and connection it uses is saved in a reservation table, per turn. The next drones can only use what is still free, so drones never collide.

3. **A\* in space and time.** Each drone searches over (zone, turn) pairs. At each turn it can either wait or move to a neighbour, if there is room. The Dijkstra distances are used as the A\* heuristic. Because time is part of the search, drones automatically spread over different paths or wait when a path is full.

4. **Priority zones.** When two routes arrive at the same turn, the one going through more priority zones wins.

5. **Always finishes.** A drone can always wait until all earlier drones have landed and then take its shortest path. That gives a maximum arrival turn, and the search never looks past it, so it can't loop forever.

6. **Double check.** The simulation replays every route and checks capacities and moves again. If something is wrong, it reports an error instead of printing a wrong result.

### Complexity

With `V` zones, `E` connections, `D` drones and `H` the maximum number of turns:

- Dijkstra: `O(E log V)`, done once
- A\* per drone: `O(E·H·log(V·H))`
- Total: `O(D·E·H·log(V·H))`

The reservation table only stores what drones actually use, and each drone's search data is thrown away once its route is chosen.

Planning drones one by one is not always perfect, because an early drone can take a spot a later drone needed. But since every drone takes the earliest route still free, the result is usually optimal or very close to it.

## Visual representation

- **Colours:** each move is printed in the colour of the zone it goes to, so you can see which path each drone takes. Drones still flying to a restricted zone are dimmed.
- **Visual mode (`-v`):** after each turn, it shows every occupied zone with a fill bar and the drones inside, then the total number of turns at the end:

```
== Turn 2 ========================================
D1-path_a D2-path_b D3-junction D4-junction
  start     [0 drones]
  junction  [##########] 2/2    D3 D4
  path_a    [##########] 1/1    D1
  path_b    [##########] 1/1    D2
  goal      [0 drones]
```

This makes it easy to see where drones wait and which zones are full.

## Resources

- [A* search algorithm](https://en.wikipedia.org/wiki/A*_search_algorithm)
- [Dijkstra's algorithm](https://en.wikipedia.org/wiki/Dijkstra%27s_algorithm)
- [Red Blob Games: Introduction to A*](https://www.redblobgames.com/pathfinding/a-star/introduction.html)
- David Silver, *Cooperative Pathfinding* (2005)
- [Python `heapq`](https://docs.python.org/3/library/heapq.html)
- [mypy](https://mypy.readthedocs.io/) and [flake8](https://flake8.pycqa.org/)
- [ANSI escape codes](https://en.wikipedia.org/wiki/ANSI_escape_code)

### Use of AI

I used Claude (Anthropic) to:

- understand the subject and compare pathfinding approaches,
- help write parts of the code (pathfinding, simulation and display), which I reviewed and made sure I understand,
- write docstrings and fix `flake8` / `mypy` warnings,
- write this README.
