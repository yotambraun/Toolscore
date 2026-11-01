# Effect probes on the official MCP filesystem server

The [filesystem server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) only accepts paths inside the directories it was started with, and `read_text_file` takes `head` and `tail` to return the first or last N lines. Two things went wrong when Toolscore graded it before 1.11:

* every generated path was outside the sandbox, so correct refusals read as broken tools (grade F);
* `head: 0` returned the whole file with no error ([modelcontextprotocol/servers#4178](https://github.com/modelcontextprotocol/servers/issues/4178)), and nothing in the scorecard could tell.

Runs made on 2026-11-02 with Toolscore 1.11.0 against `@modelcontextprotocol/server-filesystem@2.1.0`, the current release, started on a sandbox directory holding a ten-line `ten.txt` (`line 1` ... `line 10`).

## 1. Give the server paths it accepts: `--arg`

| Run | Happy paths | Grade |
| --- | --- | --- |
| no `--arg` ([output](output-no-args.txt)) | 14% | F (48%) |
| `--arg TOOL:path=...` for the six read tools ([output](output-with-args.txt)) | 43% | D (66%) |

The write tools still get generated paths (outside the sandbox) and fail, and `read_text_file`'s generated happy paths send `head` and `tail` together, which the server rejects. Give those tools values too, or read their failures as "input the server does not accept".

## 2. The built-in bounds catch `head: 0` and `tail: 0`

With `--probes`, every read-only tool with a `head`, `tail` or `limit`-like integer parameter is called with small values and checked against the full result:

```
│ bound │ read_text_file │ warn   │ medium     │ tail=0 returned 10 lines (at most 0 expected)     │
│       │                │        │            │ (probe-bound-exceeded)                            │
│ bound │ read_text_file │ warn   │ medium     │ head=0 returned 10 lines (at most 0 expected)     │
│       │                │        │            │ (probe-bound-exceeded)                            │
```

(`read_file`, the deprecated alias, gets the same two rows.) Built-in relations infer their meaning from the parameter name, so they are medium confidence: warnings that do not change the grade.

## 3. Declare the relation to make it count

[`probes.json`](probes.json) declares the relations (edit the path to your sandbox file). Declared relations are high confidence:

```bash
toolscore mcp test "npx -y @modelcontextprotocol/server-filesystem@2.1.0 /tmp/sandbox" \
  --probe-config probes.json
```

Result on 2.1.0 (from the JSON report):

| Relation | Values | Result |
| --- | --- | --- |
| `head` (prefix) | 1, 3, 10, 20 | pass |
| `tail` (suffix) | 1, 3, 10, 20 | pass |
| `head-zero` (prefix) | 0 | **fail** `probe-bound-exceeded`: head=0 returned 10 lines |

So in 2.1.0, `head` and `tail` are right for N >= 1 (the earlier `tail` off-by-one, #4643, does not reproduce), and only 0 is wrong.
