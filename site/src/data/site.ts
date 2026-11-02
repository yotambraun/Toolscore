// Central constants for the Toolscore site. Change copy/links/numbers here once.

// ---- base-path helper (the #1 gotcha for GitHub project pages) ----
// BASE_URL may be "/Toolscore" or "/Toolscore/" depending on Astro version, so
// we normalize to exactly one slash between base and path. Route every internal
// link/asset through url() so nothing 404s under the project base.
const BASE = import.meta.env.BASE_URL.replace(/\/$/, ''); // -> "/Toolscore"
export const url = (p = ''): string => {
  const clean = p.replace(/^\//, '');
  return clean ? `${BASE}/${clean}` : `${BASE}/`;
};
export const asset = (name: string): string => url(name.replace(/^\//, ''));

export const site = {
  name: 'Toolscore',
  pkg: 'tool-scorer',
  tagline: 'MCP server and agent tool-call testing',
  version: '1.11.0',
  license: 'Apache-2.0',
  author: 'Yotam Braun',
  description:
    'Test MCP servers and the tool calls your agents make. Toolscore grades any MCP server A–F (local or remote, MCP 2026-07-28) and checks agent tool calls against the ones you expect, with exactly what is broken — deterministically, offline, with zero API cost.',
  repo: 'https://github.com/yotambraun/Toolscore',
  pypi: 'https://pypi.org/project/tool-scorer/',
  pepy: 'https://pepy.tech/project/tool-scorer',
  docs: 'https://yotambraun.github.io/Toolscore/docs/',
  action: 'https://github.com/marketplace/actions/toolscore',
  aef: 'https://github.com/guybass/agent-eval-flow',
  installPip: 'pip install tool-scorer',
  installUvx: 'uvx tool-scorer demo',
};

export const ogTitle = 'Toolscore — MCP server and agent tool-call testing';

// ---- navigation ----
export const nav = [
  { label: 'MCP servers', href: url('mcp') },
  { label: 'Agents', href: url('agents') },
  { label: 'Use cases', href: url('use-cases') },
  { label: 'Compare', href: url('compare') },
  { label: 'Quickstart', href: url('quickstart') },
];

// ====================================================================
// HOME
// ====================================================================

// The two audiences ("two sides of one handshake").
export const audiences = [
  {
    key: 'mcp',
    eyebrow: 'You ship an MCP server',
    title: 'Grade your MCP server',
    blurb:
      'Toolscore runs your server, local or remote, through generated happy-path and adversarial edge-case scenarios, lints the definitions, checks output schemas, measures token cost, and grades whether an LLM can actually use it — before you publish.',
    cmd: 'toolscore mcp test "python my_server.py"',
    points: [
      'stdio or Streamable HTTP, MCP 2026-07-28 and earlier',
      'Lint for annotations, output schemas, missing tools and tool poisoning',
      'A–F grade with "Top issues to fix", and a README badge',
    ],
    href: url('mcp'),
    cta: 'Test your MCP server',
  },
  {
    key: 'agents',
    eyebrow: 'You build an agent',
    title: 'Test your agent',
    blurb:
      'Snapshot your agent’s tool calls and fail CI the instant a prompt or model change makes it call the wrong tool, with the wrong arguments, in the wrong order. Jest snapshots, for agents.',
    cmd: 'toolscore init   #  record -> approve -> replay',
    points: [
      'Snapshot record / approve / replay',
      'Failed calls, leaked credentials and forbidden calls, flagged',
      'Auto-detects the major SDKs, browser-use, MCP sessions and OpenTelemetry',
    ],
    href: url('agents'),
    cta: 'Test your agent',
  },
  {
    key: 'security',
    eyebrow: 'You run the platform',
    title: 'Gate what agents can touch',
    blurb:
      'Pin every MCP server your agents use and fail CI when a description, schema or capability changes under you. Block destructive calls and leaked keys, lint the instruction files that name the tools, and review what coding agents did on developer machines.',
    cmd: 'toolscore mcp verify-pin "uvx my-server" --lock toolscore.lock.json',
    points: [
      'Lock files with a read/write/delete/network/exec manifest',
      'lint-config for CLAUDE.md, AGENTS.md, skills and MCP configs',
      'Claude Code and Codex sessions, read-only, credentials redacted',
    ],
    href: url('use-cases#security'),
    cta: 'Secure your agents',
  },
  {
    key: 'research',
    eyebrow: 'You study agents',
    title: 'Run repeatable agent studies',
    blurb:
      'Run tasks x arms x repetitions of an LLM agent against any MCP server with a guard and a hard budget, compare variants with Wilson intervals, Fisher’s exact test and pass^k, and re-score every run later without re-running it.',
    cmd: 'toolscore compare --runs runs.jsonl --k 2',
    points: [
      'Preflight with toolscore doctor before any paid call',
      'Honesty and false-success counts next to pass rates',
      'An Inspect AI scorer and neutral run records for study tools',
    ],
    href: url('use-cases#research'),
    cta: 'Study agents',
  },
] as const;

// "How it works" step flow.
export const steps = [
  {
    n: '01',
    title: 'Point it at a target',
    body: 'An MCP server launch command or URL, or your agent’s tool calls. No glue code — raw OpenAI (Chat Completions or Responses) / Anthropic / Gemini / framework responses are auto-detected.',
    code: 'toolscore mcp test "python my_server.py"',
  },
  {
    n: '02',
    title: 'It generates scenarios',
    body: 'From each tool’s JSON schema, Toolscore builds happy-path and adversarial edge-case inputs, then lints the definitions and estimates token cost.',
    code: '6 scenarios / tool  ·  happy + edge  ·  schema lint',
  },
  {
    n: '03',
    title: 'It runs everything offline',
    body: 'Deterministic, local, zero API cost. No LLM judge by default, no cloud, no per-test bill. The same input always yields the same grade.',
    code: 'offline  ·  $0 per run  ·  deterministic',
  },
  {
    n: '04',
    title: 'You get a graded verdict',
    body: 'An A–F scorecard, a per-tool table, and a ranked "Top issues to fix" list with concrete suggestions. Gate CI with --fail-under or --ci.',
    code: 'Grade B (86%)  ·  Top issues to fix →',
  },
];

// Feature grid (home).
export const features = [
  {
    title: 'Did the tool really do it?',
    body: 'Effect probes write marked values, read them back and write again: a tool that reports success and changes nothing, or loses earlier data, fails. On the official memory server they catch the #4887 bug in the release before the fix.',
    icon: 'scan',
  },
  {
    title: 'Did the agent tell the truth?',
    body: 'Honesty checks compare tool results with the agent’s final answer: success claimed after a failure, warnings left out, a JavaScript escape hatch after a disabled button. Unknown, never pass, when the answer is missing.',
    icon: 'alert',
  },
  {
    title: 'Fault injection',
    body: 'toolscore mcp proxy --inject makes chosen calls fail in front of any stdio server: errors, warnings, timeouts, "permission denied", or an instruction planted in the result with a canary. The session records the ground truth: the honesty checks flag a hidden failure, a followed instruction and a leaked canary.',
    icon: 'record',
  },
  {
    title: 'What did my coding agent do?',
    body: 'toolscore sessions list reads Claude Code and Codex CLI sessions on your machine, read-only, and flags the ones where the agent reported success after a failing test or command. Credentials are redacted in everything it prints or exports.',
    icon: 'scan',
  },
  {
    title: 'Lint the instructions too',
    body: 'toolscore lint-config checks CLAUDE.md, AGENTS.md, skills, Cursor and Copilot rules and MCP configs against the tools that really exist: unknown tools and servers, deleting with a read-only tool, SSE configs.',
    icon: 'list',
  },
  {
    title: 'Top issues to fix',
    body: 'Not just a number — a ranked, plain-English list of what is broken and how to fix it, from broken handlers to untyped schemas to thin descriptions.',
    icon: 'list',
  },
  {
    title: 'Token-cost signal',
    body: 'Every tool definition costs context. Toolscore estimates per-tool definition tokens so you can trim bloat before it taxes every single request.',
    icon: 'coins',
  },
  {
    title: 'Zero LLM cost, deterministic',
    body: 'All core metrics run offline with no LLM judge. The same inputs always produce the same grade — so it belongs in CI, not a billing dashboard.',
    icon: 'lock',
  },
  {
    title: 'CI gate built in',
    body: '--fail-under B exits non-zero below the bar; --ci writes the verdict straight to your GitHub Actions job summary and fails on blocking issues. --sarif feeds GitHub code scanning, --junit GitLab and Jenkins test reports.',
    icon: 'shield',
  },
  {
    title: 'Framework auto-detect',
    body: 'Pass raw responses from OpenAI (Chat Completions or Responses API), Anthropic, Gemini, LangGraph, Pydantic AI, OpenAI Agents SDK, Claude Agent SDK, CrewAI or browser-use. Toolscore detects the format; live recorders plug into the Claude Agent SDK hooks and OpenAI Agents SDK tracing.',
    icon: 'plug',
  },
  {
    title: 'Snapshot record / replay',
    body: 'Record your agent’s tool calls once, approve them as the baseline, and replay forever. Drift fails the build with a full expected-vs-actual diff.',
    icon: 'camera',
  },
  {
    title: 'Behavior and safety checks',
    body: 'See what the score hides: failed calls, blind retries, required calls that never succeeded, credentials passed into tools, and calls your agent must never make.',
    icon: 'alert',
  },
  {
    title: 'Real sessions, real traces',
    body: 'Record what an agent really did against an MCP server with toolscore mcp record, or import the OpenTelemetry spans you already collect.',
    icon: 'record',
  },
  {
    title: 'Lint for tool poisoning',
    body: 'Catch descriptions that point models at tools that do not exist, hidden Unicode, and <IMPORTANT>-style instructions smuggled into tool metadata.',
    icon: 'scan',
  },
  {
    title: 'Lint what clients rely on',
    body: 'A delete_* tool without destructiveHint, readOnlyHint: true on a tool that writes, or structuredContent that breaks its own outputSchema: each gets a warning with a rule ID and a fix.',
    icon: 'shield',
  },
  {
    title: 'Remote servers, current protocol',
    body: 'Test a server by URL over Streamable HTTP with the token read from an environment variable. Speaks MCP 2026-07-28 and falls back to the initialize handshake of earlier revisions.',
    icon: 'plug',
  },
  {
    title: 'A grade badge for your README',
    body: '--badge writes an SVG ("MCP grade: A · Toolscore") from the run’s own scorecard, and a workflow keeps it current. No way to set a grade by hand.',
    icon: 'list',
  },
  {
    title: 'Pin tools, catch rug pulls',
    body: 'toolscore mcp pin hashes every tool definition into a lock file; verify-pin fails CI when a description, schema or annotation changes or a delete/exec tool appears. mcp diff compares two builds.',
    icon: 'lock',
  },
  {
    title: 'Agent experiments, light statistics',
    body: 'toolscore agent run runs tasks x arms x repetitions against any MCP server, with a guard and a hard budget. compare gives Wilson intervals and Fisher’s exact test; select picks a variant.',
    icon: 'scan',
  },
  {
    title: 'Record once, re-score forever',
    body: 'A receipt pins the evaluated trace by hash; toolscore regrade re-scores it with a new contract or weights, running nothing. Contracts allow alternatives; every check is pass, fail or unknown.',
    icon: 'record',
  },
];

// ====================================================================
// PROOF: bugs found with Toolscore and fixed upstream (verified 2026-11-01)
// ====================================================================

export const foundWith = {
  heading: 'Found with Toolscore',
  intro:
    'Two bugs in the official MCP memory server, found with Agent Eval Flow and Toolscore, and fixed upstream. Both fixes port @yotambraun’s contributions with authorship kept; maintainer cliffhall merged them on 2026-10-05.',
  items: [
    {
      pr: '#5035',
      prUrl: 'https://github.com/modelcontextprotocol/servers/pull/5035',
      title: 'fix(memory): keep unreadable lines when saving the graph',
      issue: '#4885',
      issueUrl: 'https://github.com/modelcontextprotocol/servers/issues/4885',
      what: 'Unreadable lines in the memory file were deleted by the next write.',
    },
    {
      pr: '#5008',
      prUrl: 'https://github.com/modelcontextprotocol/servers/pull/5008',
      title: 'fix(memory): report entities that create_entities skipped',
      issue: '#4887',
      issueUrl: 'https://github.com/modelcontextprotocol/servers/issues/4887',
      what: 'create_entities silently dropped observations for entities that already existed.',
    },
  ],
  caseStudy: 'https://github.com/guybass/agent-eval-flow/tree/main/examples/data/mcp-memory',
  agentEvalFlow: 'https://github.com/guybass/agent-eval-flow',
};

// ====================================================================
// THE ANIMATED SCORECARD DEMO (centerpiece data)
// ====================================================================

// Real output of `toolscore demo` (the bundled sample server), Toolscore 1.11.0.
export const scorecard = {
  command: 'uvx tool-scorer demo',
  server: 'notes-server',
  serverVersion: '1.1.0',
  grade: 'B',
  score: 86,
  protocol: 'MCP 2026-07-28 (stateless)',
  dims: [
    { label: 'happy', value: 80 },
    { label: 'edge', value: 100 },
    { label: 'lint', value: 91 },
  ],
  tools: [
    { name: 'create_note', scenarios: '6/6', pass: true, latency: '0.6 ms', tokens: 80 },
    { name: 'list_notes', scenarios: '6/6', pass: true, latency: '0.5 ms', tokens: 59 },
    { name: 'search_notes', scenarios: '6/6', pass: true, latency: '0.5 ms', tokens: 48 },
    { name: 'delete_note', scenarios: '6/6', pass: true, latency: '0.5 ms', tokens: 52 },
    { name: 'export_notes', scenarios: '3/6', pass: false, latency: '0.5 ms', tokens: 64 },
  ],
  tokenNote: 'Tool definitions cost ~303 estimated tokens of context across 5 tool(s).',
  issues: [
    {
      n: 1,
      tool: 'export_notes',
      problem: 'fails on valid input (export failed: storage backend not configured)',
      fix: 'The tool errors on well-formed arguments - check the handler and that the input schema matches what the tool actually accepts.',
    },
    {
      n: 2,
      tool: 'delete_note',
      problem: "property 'note_id' is missing a 'type'",
      fix: 'Give the property a JSON-schema type (and an enum where the values are fixed) so the model does not have to guess.',
    },
    {
      n: 3,
      tool: 'create_note',
      problem: 'changes state but declares no readOnlyHint/destructiveHint annotations',
      fix: 'Declare annotations {"readOnlyHint": false, "destructiveHint": false} (or true if it can overwrite or delete), so clients know what it changes.',
    },
    {
      n: 4,
      tool: 'search_notes',
      problem: 'description is very short (< 10 chars)',
      fix: 'Describe what the tool does and when to use it - models choose tools by their description.',
    },
  ],
};

// ====================================================================
// MCP page
// ====================================================================

export const mcpDimensions = [
  {
    label: 'Happy path',
    weight: '60%',
    grade: 'A',
    body: 'For each tool, Toolscore synthesizes well-formed arguments from the schema and checks the call succeeds. The single biggest signal that a tool actually works.',
  },
  {
    label: 'Edge-case resilience',
    weight: '20%',
    grade: 'B',
    body: 'Adversarial inputs — missing required fields, wrong types, empty values, boundaries — probe whether the server fails gracefully instead of crashing. Invalid input answered as a success is flagged as a finding; a call that needs client input (input_required) is not evaluated, never a fail.',
  },
  {
    label: 'Lint',
    weight: '20%',
    grade: 'C',
    body: 'Static checks on the tool definitions and server instructions: missing types and descriptions, behavior annotations, results that break the declared output schema, references to tools the server does not expose, and tool-poisoning patterns such as hidden Unicode. Every issue has a rule ID.',
  },
  {
    label: 'Token cost',
    weight: 'signal',
    grade: 'D',
    body: 'Every tool definition is part of the prompt on every request. Toolscore estimates the per-tool token footprint so you can spot context bloat early.',
  },
];

export const mcpCommands = [
  { cmd: 'toolscore demo', note: 'Grade a bundled sample MCP server — zero setup, no API key.' },
  { cmd: 'toolscore mcp test "python my_server.py"', note: 'Grade your own server by launch command.' },
  {
    cmd: 'toolscore mcp test https://mcp.example.com/mcp --auth-env MCP_TOKEN',
    note: 'Grade a remote server over Streamable HTTP (needs tool-scorer[http]); the token is never printed.',
  },
  {
    cmd: 'uvx tool-scorer mcp test --config claude_desktop_config.json --server my-server',
    note: 'Straight from a Claude Desktop, Cursor, Claude Code or VS Code config, zero install.',
  },
  { cmd: 'toolscore mcp list "python my_server.py"', note: 'Show the advertised tools.' },
  { cmd: 'toolscore mcp lint "python my_server.py"', note: 'Lint only: schemas, annotations, missing tools, tool poisoning, with rule IDs (exit 1 on errors).' },
  { cmd: 'toolscore mcp test "python my_server.py" --probes', note: 'Effect probes, read-only: head/tail/limit-like parameters must bound the result.' },
  { cmd: 'toolscore mcp test "python my_server.py" --probes --allow-writes', note: 'Plus round trips: a write must be visible, a same-key write must change it or say why not, earlier records must survive. Use a disposable server.' },
  { cmd: 'toolscore mcp test "python my_server.py" --probe-config probes.yaml', note: 'Declared pairs, bounds and agreements: high confidence, they count in the grade.' },
  { cmd: 'toolscore mcp test "npx -y @modelcontextprotocol/server-filesystem /sandbox" --arg path=/sandbox/a.txt', note: 'Give a sandboxed server values it accepts (TOOL:NAME=VALUE for one tool, --args-file for many).' },
  { cmd: 'toolscore mcp record -o session.json -- python my_server.py', note: 'Record a real client session, then score it with toolscore eval.' },
  { cmd: 'toolscore mcp proxy --inject faults.json -o session.json -- python my_server.py', note: 'Record a session and make chosen calls fail; then toolscore honesty session.json checks what the agent said.' },
  { cmd: 'toolscore mcp pin "python my_server.py" -o toolscore.lock.json', note: 'Pin every tool definition, the server info and each tool’s capabilities. Commit the lock file.' },
  { cmd: 'toolscore mcp verify-pin "python my_server.py" --lock toolscore.lock.json', note: 'Exit 1 on drift (--fail-on capability: only a new delete/exec tool). Also mcp test --pin and mcp lint --pin.' },
  { cmd: 'toolscore mcp diff "python old_server.py" "python new_server.py" --fail-on breaking', note: 'Tools added or removed, changed descriptions, schemas and annotations, lint delta; --test adds the scorecard.' },
  { cmd: 'toolscore mcp test "python my_server.py" --report md --output SCORECARD.md', note: 'Export a Markdown report for a PR or README.' },
  { cmd: 'toolscore mcp test "python my_server.py" --fail-under B', note: 'CI gate: exit 1 below a B.' },
  { cmd: 'toolscore mcp test "python my_server.py" --ci', note: 'Write the verdict to $GITHUB_STEP_SUMMARY, fail on blocking issues.' },
  { cmd: 'toolscore mcp test "python my_server.py" --badge mcp-grade.svg', note: 'Write an SVG grade badge from this run (--badge-json for shields.io).' },
  { cmd: 'toolscore mcp test "python my_server.py" --protocol legacy', note: 'Force the pre-2026 initialize handshake (auto detects the era).' },
];

// ====================================================================
// AGENTS page
// ====================================================================

export const snapshotSteps = [
  {
    n: '1',
    title: 'Record',
    body: 'The first pytest run captures your agent’s tool calls into pending snapshots and passes with a warning. No hand-written expected calls, no YAML.',
    code: 'pytest   #  toolscore: 1 snapshot created (pending approval)',
  },
  {
    n: '2',
    title: 'Approve',
    body: 'Review the recorded calls, then bless them as the baseline. Snapshots are plain JSON under .toolscore/snapshots/ — they review cleanly in PRs.',
    code: 'toolscore approve --all',
  },
  {
    n: '3',
    title: 'Replay',
    body: 'Every run after that replays against the baseline. Drift fails the test with a full expected-vs-actual diff. Re-record on purpose with --toolscore-update.',
    code: 'pytest   #  fails the build on drift',
  },
];

export const matchers = [
  { name: 'ANY', matches: 'anything', example: 'calls("search", q=ANY)' },
  { name: 'Regex(pattern)', matches: 'full string match', example: 'Regex(r"FL-\\d+")' },
  { name: 'Approx(value, rel, abs)', matches: 'numbers within tolerance', example: 'Approx(40.71, rel=1e-2)' },
  { name: 'Contains(item)', matches: 'membership in str/list/dict', example: 'Contains("metric")' },
  { name: 'OneOf(*values)', matches: 'any of the candidates', example: 'OneOf("NYC", "New York")' },
  { name: 'IsType(*types)', matches: 'isinstance check (bool-safe)', example: 'IsType(int)' },
];

export const frameworks = [
  { name: 'OpenAI', detail: 'Chat Completions + Responses API' },
  { name: 'Anthropic', detail: 'tool_use blocks' },
  { name: 'Google Gemini', detail: 'functionCall parts' },
  { name: 'LangGraph', detail: 'state / message lists' },
  { name: 'Pydantic AI', detail: 'run results' },
  { name: 'OpenAI Agents SDK', detail: 'run results' },
  { name: 'Claude Agent SDK', detail: 'message lists' },
  { name: 'CrewAI', detail: 'experimental' },
  { name: 'MCP sessions', detail: 'toolscore mcp record' },
  { name: 'OpenTelemetry', detail: 'GenAI + MCP spans' },
];

// ====================================================================
// COMPARE page — which tool for which job (verified 2026-11-02, see docs/comparison.rst)
// ====================================================================

export const compareCheckedOn = '2026-11-02';

export const compareJobs: { job: string; reach: string; toolscore: string; self?: boolean }[] = [
  {
    job: 'Explore a server by hand, debug OAuth, review an MCP App',
    reach: 'MCP Inspector (web UI, TUI, CLI)',
    toolscore: 'Nothing comparable: no UI. toolscore mcp list prints the tools.',
  },
  {
    job: 'Script a smoke test in CI: connect, list, call, assert',
    reach: 'MCP Inspector CLI (JSON output, exit codes, assertions you write with jq)',
    toolscore: 'mcp test generates the calls from the tool schemas and grades the server, with no assertions to write.',
  },
  {
    job: 'Check that a server or client conforms to the MCP specification',
    reach: 'The official MCP conformance suite',
    toolscore: 'Does not replace it. Toolscore tests what the tools do, not every rule of the protocol.',
  },
  {
    job: 'Scan installed agents, MCP servers and skills for prompt injection, tool poisoning, toxic flows or malware',
    reach: 'Snyk Agent Scan or Cisco MCP Scanner',
    toolscore: 'A lighter, offline check: lint rules for hidden instructions, and mcp pin / verify-pin to fail CI when a tool definition changes.',
  },
  {
    job: 'Judge with a model whether an agent used its MCP tools well',
    reach: 'DeepEval (MCP Use, Multi-Turn MCP Use, MCP Task Completion)',
    toolscore: 'Deterministic checks instead: required and forbidden calls, arguments, contracts. An LLM judge is optional.',
  },
  {
    job: 'Red-team an agent or an MCP server with generated attacks',
    reach: 'Promptfoo (MCP provider, MCP red-team plugin)',
    toolscore: 'Fault injection with fixed, reproducible faults (mcp proxy --inject), including one planted instruction with a canary, not attack generation.',
  },
  {
    job: 'Check that a write really happened (write, then read back)',
    reach: 'Toolscore effect probes',
    toolscore: 'probe-silent-noop, probe-data-lost, bounds and agreement checks.',
    self: true,
  },
  {
    job: 'Check that the agent’s final answer matches what its tools returned',
    reach: 'Toolscore honesty checks',
    toolscore: 'claimed-success, undisclosed-warning, escape-hatch-after-refusal, injected faults the answer hides.',
    self: true,
  },
];

export const compareTools = [
  {
    name: 'MCP Inspector',
    href: 'https://github.com/modelcontextprotocol/inspector',
    best: 'The MCP project’s developer tool: a web UI, a TUI and a CLI for automation and CI. Best for looking at a server, trying calls by hand, debugging OAuth and writing precise assertions about specific calls.',
  },
  {
    name: 'MCP conformance suite',
    href: 'https://github.com/modelcontextprotocol/conformance',
    best: 'Tests MCP clients and servers against the specification, validates every message on the wire against the spec’s JSON schema, and runs what one revision requires. Toolscore does not replace it.',
  },
  {
    name: 'Snyk Agent Scan',
    href: 'https://github.com/snyk/agent-scan',
    best: 'Formerly mcp-scan. Discovers the agents, MCP servers and skills on a machine and scans them for prompt injection, tool poisoning, tool shadowing and toxic flows, through the Agent Scan API.',
  },
  {
    name: 'Cisco MCP Scanner',
    href: 'https://github.com/cisco-ai-defense/mcp-scanner',
    best: 'Scans tools, prompts, resources and instructions with YARA rules (no key needed), an LLM analyzer, the Cisco AI Defense API and behavioral analysis of the server’s source code.',
  },
  {
    name: 'DeepEval',
    href: 'https://deepeval.com/docs/metrics-mcp-use',
    best: 'LLM-as-a-judge metrics for how an application uses MCP servers, plus a deterministic Tool Correctness metric and broad answer-quality and RAG metrics.',
  },
  {
    name: 'Promptfoo',
    href: 'https://www.promptfoo.dev/docs/providers/mcp/',
    best: 'Calls MCP tools directly to test or red-team a server, generates MCP attacks, and compares prompts and models with deterministic and model-assisted assertions.',
  },
];

// ====================================================================
// QUICKSTART page
// ====================================================================

export const entryPoints = [
  {
    title: 'See it in 10 seconds',
    cmd: 'uvx tool-scorer demo',
    body: 'Grade a bundled sample MCP server — no install, no API key, no setup. The fastest way to see the scorecard.',
  },
  {
    title: 'Grade your MCP server',
    cmd: 'toolscore mcp test "python my_server.py"',
    body: 'Point it at your own server, or its URL. Add --fail-under B to gate CI, --report md to export a Markdown scorecard, or --badge for a README badge.',
  },
  {
    title: 'Evaluate a trace',
    cmd: 'toolscore eval gold.json trace.json',
    body: 'Score a captured trace, a recorded MCP session or an OpenTelemetry export against a gold standard. Get an A–F grade, "Top issues to fix" and behavior and safety findings.',
  },
];

export const ciSnippet = `name: toolscore
on: [push, pull_request]

jobs:
  scorecard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - run: pip install tool-scorer
      # Grade the MCP server on every PR; fail the build below a B
      - run: toolscore mcp test "python my_server.py" --fail-under B --ci`;
