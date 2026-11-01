# Effect probes on the official MCP memory server

`create_entities` in the official [memory server](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) used to skip entities whose name already existed and still answer with success ([modelcontextprotocol/servers#4887](https://github.com/modelcontextprotocol/servers/issues/4887), fixed by [#5008](https://github.com/modelcontextprotocol/servers/pull/5008), merged 2026-10-05). The scorecard alone grades that server A: every call answers, nothing errors. The effect probes write, read back and write again, and catch it.

Both runs below were made on 2026-11-02 with Toolscore 1.11.0 and no probe config: the write tools, the read tools and the key field (`name`) were all found by the heuristics.

| Package version (npm) | Published | Contains the #4887 fix | `create_entities` round trip |
| --- | --- | --- | --- |
| `@modelcontextprotocol/server-memory@2026.8.31` | 2026-08-31 | no | **FAIL** `probe-silent-noop`, high confidence |
| `@modelcontextprotocol/server-memory@2.0.1` | 2026-10-28 | yes | pass: "a same-key write was reported as skipped" |

## Commands

Each run gets a fresh, empty memory file, so the probes never touch real data (they leave marker entities such as `tspd11f8d-name` behind):

```bash
MEMORY_FILE_PATH=$(mktemp) toolscore mcp test \
  "npx -y @modelcontextprotocol/server-memory@2026.8.31" --probes --allow-writes

MEMORY_FILE_PATH=$(mktemp) toolscore mcp test \
  "npx -y @modelcontextprotocol/server-memory@2.0.1" --probes --allow-writes
```

Full console output: [`output-2026.8.31.txt`](output-2026.8.31.txt) and [`output-2.0.1.txt`](output-2.0.1.txt). Marker names are random per run.

## What the probe did

1. `create_entities` with one entity whose `name`, `entityType` and observation carry a fresh marker.
2. `read_graph`, `search_nodes` and `open_nodes` (the server's read-only tools) all showed it, so they count as confirmed readers.
3. `create_entities` again with the **same `name`** and new markers in `entityType` and the observation.
   - 2026.8.31 answered `[]` with success, and no reader showed the new values: *reported success, state unchanged* (`probe-silent-noop`).
   - 2.0.1 answered "Skipped 1 entity that already exists: … Its observations were not added; use add_observations for existing entities." The skip is reported, so the probe passes.
4. A third entity with a different name, then the first one is read again (`probe-data-lost` fires if it is gone). The probe stops at its first failure, so this step ran only for 2.0.1, which kept the entity.

`add_observations` (both versions) and `create_relations` (2.0.1) were **inconclusive**: they need an entity that already exists, and the probe's generated names do not. Declare values with `--arg` or a probe config to cover them.

The grade: 2026.8.31 scores 93% (A) with the failing probe, from 100% without probes. A tool with a high-confidence probe failure costs as much as a tool that fails all of its happy paths (0.6 divided by the 9 tools). `toolscore mcp test --ci` fails the run on it.

`#4885` (unreadable lines in the graph file deleted by the next write) needs a corrupted file before the write, which a probe cannot create through the server's tools, so it is not covered here.
