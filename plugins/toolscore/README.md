# Toolscore plugin for Claude Code

Skills that drive the [Toolscore](https://github.com/yotambraun/toolscore) CLI
(`pip install tool-scorer`, or `uvx tool-scorer` with nothing installed).
Toolscore is deterministic and local: the skills call no model and send nothing
anywhere.

| Skill | What it does |
| --- | --- |
| `audit-mcp-server` | Lint an MCP server, run the A-F scorecard, run effect probes (asks before write probes), and explain each fix |
| `add-tool-call-tests` | Capture a trace, write a contract of required, optional and forbidden calls, and add a pytest test |
| `check-agent-honesty` | Check a trace or a coding-agent session for false success, hidden warnings and refusal overrides, and explain the findings |
| `pin-mcp-servers` | Pin MCP servers in `toolscore.lock.json` and verify the pin in CI against drift and new capabilities |

Install:

```
/plugin marketplace add yotambraun/toolscore
/plugin install toolscore@toolscore
```

The skills are plain `SKILL.md` files, so other agents that read skills can use
them too: copy `skills/<name>/` into the agent's skills folder.
