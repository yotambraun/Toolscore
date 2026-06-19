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
  tagline: 'the instant health-check for LLM tool-calling',
  version: '1.7.1',
  license: 'Apache-2.0',
  author: 'Yotam Braun',
  description:
    'The instant, free, deterministic health-check for LLM tool-calling. Point Toolscore at an MCP server or an agent and get an A–F grade plus exactly what is broken — deterministically, offline, with zero API cost.',
  repo: 'https://github.com/yotambraun/Toolscore',
  pypi: 'https://pypi.org/project/tool-scorer/',
  pepy: 'https://pepy.tech/project/tool-scorer',
  docs: 'https://tool-scorer.readthedocs.io',
  action: 'https://github.com/marketplace/actions/toolscore',
  installPip: 'pip install tool-scorer',
  installUvx: 'uvx tool-scorer demo',
};

export const ogTitle = 'Toolscore — the instant health-check for LLM tool-calling';

// ---- navigation ----
export const nav = [
  { label: 'MCP servers', href: url('mcp') },
  { label: 'Agents', href: url('agents') },
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
      'Toolscore runs your server through generated happy-path and adversarial edge-case scenarios, lints the schemas, measures token cost, and grades whether an LLM can actually use it — before you publish.',
    cmd: 'toolscore mcp test "python my_server.py"',
    points: ['Happy-path + edge-case scenarios, auto-generated', 'Schema lint + token-cost signal', 'A–F grade with "Top issues to fix"'],
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
    points: ['Snapshot record / approve / replay', 'Fluent expect() API + matchers', 'Auto-detects 8 agent frameworks'],
    href: url('agents'),
    cta: 'Test your agent',
  },
] as const;

// "How it works" step flow.
export const steps = [
  {
    n: '01',
    title: 'Point it at a target',
    body: 'An MCP server launch command, or your agent’s tool calls. No glue code — raw OpenAI / Anthropic / Gemini / framework responses are auto-detected.',
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
    code: 'Grade B (87%)  ·  Top issues to fix →',
  },
];

// Feature grid (home).
export const features = [
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
    body: '--fail-under B exits non-zero below the bar; --ci writes the verdict straight to your GitHub Actions job summary and fails on blocking issues.',
    icon: 'shield',
  },
  {
    title: 'Framework auto-detect',
    body: 'Pass raw responses from OpenAI, Anthropic, Gemini, LangGraph, Pydantic AI, OpenAI Agents SDK, Claude Agent SDK, or CrewAI. Toolscore detects the format.',
    icon: 'plug',
  },
  {
    title: 'Snapshot record / replay',
    body: 'Record your agent’s tool calls once, approve them as the baseline, and replay forever. Drift fails the build with a full expected-vs-actual diff.',
    icon: 'camera',
  },
];

// ====================================================================
// THE ANIMATED SCORECARD DEMO (centerpiece data)
// ====================================================================

export const scorecard = {
  command: 'uvx tool-scorer mcp test "python my_server.py"',
  server: 'notes-server',
  serverVersion: '1.0.0',
  grade: 'B',
  score: 87,
  dims: [
    { label: 'happy', value: 80 },
    { label: 'edge', value: 100 },
    { label: 'lint', value: 93 },
  ],
  tools: [
    { name: 'create_note', scenarios: '6/6', pass: true, latency: '0.1 ms', tokens: 80 },
    { name: 'list_notes', scenarios: '6/6', pass: true, latency: '0.1 ms', tokens: 59 },
    { name: 'search_notes', scenarios: '6/6', pass: true, latency: '0.1 ms', tokens: 48 },
    { name: 'delete_note', scenarios: '6/6', pass: true, latency: '0.1 ms', tokens: 52 },
    { name: 'export_notes', scenarios: '3/6', pass: false, latency: '0.1 ms', tokens: 64 },
  ],
  tokenNote: 'Tool definitions cost ~303 estimated tokens of context across 5 tool(s).',
  issues: [
    {
      n: 1,
      tool: 'export_notes',
      problem: 'fails on valid input (export failed: storage backend not configured)',
      fix: 'The tool errors on well-formed arguments — check the handler and the input schema.',
    },
    {
      n: 2,
      tool: 'delete_note',
      problem: "property 'note_id' is missing a 'type'",
      fix: 'Give the property a JSON-schema type (and an enum where values are fixed).',
    },
    {
      n: 3,
      tool: 'search_notes',
      problem: 'description is very short (< 10 chars)',
      fix: 'Describe what the tool does and when to use it.',
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
    body: 'Adversarial inputs — missing required fields, wrong types, empty values, boundaries — probe whether the server fails gracefully instead of crashing or returning garbage.',
  },
  {
    label: 'Schema lint',
    weight: '20%',
    grade: 'C',
    body: 'Static checks on the tool definitions themselves: missing types, absent descriptions, no enums on fixed-value fields — the things that make a model guess.',
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
    cmd: 'uvx tool-scorer mcp test --config claude_desktop_config.json --server my-server',
    note: 'Straight from a Claude Desktop config, zero install.',
  },
  { cmd: 'toolscore mcp list "python my_server.py"', note: 'Show the advertised tools.' },
  { cmd: 'toolscore mcp lint "python my_server.py"', note: 'Schema lint only (exit 1 on errors).' },
  { cmd: 'toolscore mcp test "python my_server.py" --report md --output SCORECARD.md', note: 'Export a Markdown report for a PR or README.' },
  { cmd: 'toolscore mcp test "python my_server.py" --fail-under B', note: 'CI gate: exit 1 below a B.' },
  { cmd: 'toolscore mcp test "python my_server.py" --ci', note: 'Write the verdict to $GITHUB_STEP_SUMMARY, fail on blocking issues.' },
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
  { name: 'OpenAI', detail: 'Chat Completions + legacy function_call' },
  { name: 'Anthropic', detail: 'tool_use blocks' },
  { name: 'Google Gemini', detail: 'functionCall parts' },
  { name: 'LangGraph', detail: 'state / message lists' },
  { name: 'Pydantic AI', detail: 'run results' },
  { name: 'OpenAI Agents SDK', detail: 'run results' },
  { name: 'Claude Agent SDK', detail: 'message lists' },
  { name: 'CrewAI', detail: 'experimental' },
];

// ====================================================================
// COMPARE page — confident positioning matrix
// ====================================================================

export const compareTools = ['Toolscore', 'DeepEval', 'LangChain agentevals', 'EvalView', 'mcp-eval'];

// value: true (yes) | false (no) | 'partial'
export const compareRows: { label: string; values: (boolean | 'partial')[] }[] = [
  { label: 'Deterministic — no LLM judge required', values: [true, 'partial', true, 'partial', 'partial'] },
  { label: 'Runs fully offline ($0 per run)', values: [true, false, true, false, false] },
  { label: 'Snapshot record / approve / replay', values: [true, false, false, false, false] },
  { label: 'MCP-server scorecard (A–F + lint + token cost)', values: [true, false, false, false, 'partial'] },
  { label: 'Ranked "Top issues to fix" verdict', values: [true, false, false, 'partial', false] },
  { label: 'pytest-native (drop-in fixture + assertions)', values: [true, 'partial', false, false, false] },
  { label: 'Framework auto-detect (8 SDKs)', values: [true, 'partial', 'partial', false, false] },
  { label: 'CI gate built in (--fail-under / --ci)', values: [true, 'partial', false, false, 'partial'] },
];

export const compareBestAt = [
  {
    name: 'Toolscore',
    best: 'The deterministic, in-CI health-check for tool-calling. It verifies your agent calls the right tools, with the right arguments, in the right order — and grades whether an MCP server can be used at all — for free, in your test suite.',
    self: true,
  },
  {
    name: 'DeepEval',
    best: 'A broad LLM-eval framework — best for scoring production outputs across many quality dimensions (hallucination, toxicity, RAG faithfulness), often with an LLM judge.',
    self: false,
  },
  {
    name: 'LangChain agentevals',
    best: 'Trajectory and tool-call evaluators living inside the LangChain ecosystem — a natural fit when your stack is already LangChain / LangGraph end to end.',
    self: false,
  },
  {
    name: 'EvalView',
    best: 'Visual review and dashboards for agent runs — best when the goal is human inspection and reporting of traces rather than a hard CI gate.',
    self: false,
  },
  {
    name: 'mcp-eval',
    best: 'Task-driven MCP evaluation that exercises servers through an LLM — best for end-to-end, model-in-the-loop checks of MCP behavior.',
    self: false,
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
    body: 'Point it at your own server. Add --fail-under B to gate CI, or --report md to export a Markdown scorecard.',
  },
  {
    title: 'Evaluate a trace',
    cmd: 'toolscore eval gold.json trace.json',
    body: 'Score a captured agent trace against a gold standard. Get an A–F grade and the same "Top issues to fix" verdict.',
  },
];

export const ciSnippet = `name: toolscore
on: [push, pull_request]

jobs:
  scorecard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install tool-scorer
      # Grade the MCP server on every PR; fail the build below a B
      - run: toolscore mcp test "python my_server.py" --fail-under B --ci`;
