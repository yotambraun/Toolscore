# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
and uses [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## [Unreleased]

## [1.11.0] - Unreleased

Toolscore 1.11 speaks the current MCP revision (2026-07-28) and tests remote servers, so any MCP server, local or hosted, can be graded in CI and show its grade in its README. And correct tool calls are not enough: 1.11 checks that the tool really did it, and that the agent told the truth about it. It also adds the rigor to trust the answers: an agent harness, pinned servers, contracts, receipts, tri-state evidence and repeated-run statistics.

### Highlights

- **Effect probes: did the tool really do it?** `toolscore mcp test --probes` checks invariants against the live server. Built in and read-only: `head`/`tail`/`limit`-like parameters must bound the result. With `--allow-writes`: round trips that write marked values, read them back, write again to the same key and check earlier records survive (`probe-write-not-observable`, `probe-silent-noop`, `probe-data-lost`). A probe config declares pairs, bounds, two-path agreements and idempotent calls. On the official memory server, `server-memory@2026.8.31` gets `probe-silent-noop` on `create_entities` (the #4887 bug) and `2.0.1` passes, with no configuration; on `server-filesystem@2.1.0` the built-in bounds flag `head: 0` and `tail: 0` returning the whole file.
- **Honesty checks: did the agent tell the truth?** Every evaluation reads the agent's final answer from the trace and reports `claimed-success`, `done-after-error`, `undisclosed-warning`, `escape-hatch-after-refusal` and `injected-fault-undisclosed` under Behavior and safety, plus a `false_success` summary. `toolscore honesty TRACE` runs them alone, with no gold file. Without a final answer they report unknown, never pass.
- **Fault injection.** `toolscore mcp proxy --inject faults.json` sits in front of any stdio server and gives chosen calls an error, a JSON-RPC error, a warning, an empty or truncated result, a delay, a timeout, a "disabled" / "permission denied" answer, or an instruction planted in the result with a canary token (prompt injection). The session records what was injected, so the honesty checks verify the agent's report against ground truth.
- **A silent no-op caps the grade at C.** A high-confidence probe failure now also caps the letter grade at C (the score is unchanged), with `capped because: probe-silent-noop on create_entities` in every scorecard format and the badge. `server-memory@2026.8.31` graded A (93%) with its silent no-op; it now grades C. `--no-probe-grade-cap` restores the uncapped grade. **This is a deliberate, reversible grading decision**; see Changed.
- **Truth checks where agents run.** browser-use histories (the #6068 disabled-button override is an `escape-hatch-after-refusal`), Claude Code and Codex CLI sessions (`toolscore sessions list`, `toolscore honesty SESSION.jsonl`, read-only, credentials redacted), live recorders for Claude Agent SDK hooks and OpenAI Agents SDK tracing, an Inspect AI scorer, and Pydantic AI 2 tool outcomes.
- **`toolscore lint-config`** checks `CLAUDE.md`, `AGENTS.md`, `SKILL.md`, Cursor and Copilot instructions and MCP host configs against the tools the servers really expose: unknown servers and tools, the deprecated SSE transport, and instructions that contradict a tool's annotations.
- **`toolscore demo --truth`** shows a tool that lies and an agent that lies in one offline command, and a **Claude Code plugin** adds skills to audit an MCP server, add tool-call tests, check agent honesty and pin servers.
- **Agent harness.** `toolscore agent run spec.yaml` (and `toolscore.mcp.agent`) runs tasks x arms x repetitions of an LLM agent against any MCP server, with the OpenAI Responses API, Anthropic Messages or a free scripted provider: a guard on every tool call, a hard budget checked before every model call (unknown prices refused unless allowed), per-run limits, a seeded shuffled order, resumable JSONL with one row per run, and build verification of `serverInfo` and a version command.
- **Pinning and drift.** `toolscore mcp pin` writes `toolscore.lock.json` (hashes of every tool definition, the server, protocol and instructions, and a read/write/delete/network/exec capability manifest); `mcp verify-pin`, `mcp test --pin` and `mcp lint --pin` fail on drift or a new delete/exec capability: a defense against MCP rug pulls and description poisoning. `toolscore mcp diff A B` compares two servers, builds or snapshots with text diffs, the lint delta and, with `--test`, scorecard and probe deltas.
- **Contracts v2.** Required, optional and forbidden calls and alternative paths in one file (JSON Schema shipped); optional calls are neither missing nor extra, and the best-scoring alternative wins.
- **Receipts and regrade.** `toolscore eval --receipt` writes a content-hashed record of the inputs, settings, version and result; `toolscore regrade` re-scores receipts, traces and agent runs with a new contract or weights without re-running anything. Record once, re-score forever (inspired by Agent Eval Flow).
- **Tri-state evidence.** Every check is pass, fail or unknown, never a silent pass: reports count them, and missing latency and cost are "unknown", never 0.
- **Comparing runs.** `toolscore compare --runs` reports complete populations, Wilson intervals, Fisher's exact test, pass^k and pre-declared decision rules; `toolscore select` picks a variant by lexicographic, weighted or Pareto objectives (inspired by Agent Eval Flow). `toolscore doctor` checks everything before any paid call; `toolscore export --format aef` writes neutral, versioned run records.
- **Argument values for sandboxed servers.** `--arg [TOOL:]NAME=VALUE` and `--args-file` give the scorecard and the probes values a server accepts, so the filesystem and git servers no longer fail every happy path on generated paths (`server-filesystem@2.1.0`: F to D with sandbox paths for its read tools).
- **MCP 2026-07-28, with a fallback.** The MCP clients probe with `server/discover` and send the protocol version, client info and capabilities in each request's `_meta`, as the stateless 2026-07-28 revision requires. A server built on an earlier revision (any non-modern error, an HTTP 4xx without a modern error body, or on stdio no answer within 5 seconds) gets the `initialize` handshake with 2025-11-25 instead. `UnsupportedProtocolVersionError` answers pick a version from the server's list, and the scorecard shows which protocol a run used.
- **Remote MCP servers.** `toolscore mcp test`, `mcp lint` and `mcp list` accept a Streamable HTTP URL, or a `url` entry in a Claude Desktop, Cursor, Claude Code or VS Code config file (`pip install "tool-scorer[http]"`). Credentials come from the environment (`--auth-env VAR`, `--header 'Name: ${VAR}'`, `${VAR}` / `${env:VAR}` in config files) and are never printed.
- **Lint for what clients rely on.** Behavior annotations (`readOnlyHint`, `destructiveHint`, ...) missing on tools whose names say they write or delete, `readOnlyHint: true` on `delete_*`, and conflicting hints; and `structuredContent` that does not match a tool's `outputSchema`. Every lint issue now has a stable rule ID.
- **Grade badges.** `mcp test --badge PATH` writes an SVG badge ("MCP grade: A · Toolscore") and `--badge-json PATH` a shields.io endpoint file, both from the run's own scorecard. A workflow example keeps the badge current.
- **OpenAI Responses API.** `evaluate()` accepts `Response` objects and Responses item lists; `from_openai_responses()` reads `function_call`, `mcp_call` and `custom_tool_call` items and pairs `function_call_output` items to their calls.

### Added

#### MCP
- `MCPClient`, the transport-independent protocol logic; `MCPStdioClient` and the new `MCPHttpClient` (Streamable HTTP, both eras: per-request `MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name` and `Mcp-Param-*` headers for `x-mcp-header` parameters in 2026-07-28; `Mcp-Session-Id` sessions in 2025-11-25; JSON and server-sent-event responses). Both take `protocol="auto" | "modern" | "legacy"`; `client.era`, `client.protocol_version` and `client.server_versions` report what was agreed.
- `MODERN_PROTOCOL_VERSION` ("2026-07-28") and `LEGACY_PROTOCOL_VERSION` ("2025-11-25").
- `toolscore mcp test|lint|list --protocol`, `--header` and `--auth-env`; URL targets.
- `load_mcp_config()` reads the VS Code `servers` layout and `url` / `serverUrl` entries with `headers`; `MCPServerSpec.url`, `.headers` and `.transport`; `open_client(spec)` returns the right client. Entries with the deprecated SSE transport are rejected with the reason.
- `MCPToolDef.annotations`, `.output_schema` and `.title`; `MCPToolResult.structured_content`.
- `resultType: "input_required"` (MCP 2026-07-28 multi round-trip requests) is its own state, not a tool error: `MCPToolResult.input_required` and `.input_requests`; an answer with only a `requestState` is retried with it (`MAX_INPUT_REQUIRED_RETRIES`). In the scorecard such a scenario is not evaluated (`ScenarioResult.status` `input_required`, left out of the rates, counted in `scores.not_evaluated` and every format); `input-required-undeclared` flags a server that sends input requests the client did not declare. Probes treat it as inconclusive; the agent harness tells the model the call did not finish.
- Requests the server sends during a call are answered: `ping` with an empty result, anything else with `-32601` (method not found), over stdio and Streamable HTTP. `client.server_messages` keeps the last `MAX_SERVER_MESSAGES` (200); `server_messages_dropped` counts the rest.
- `edge-accepted-invalid-input`: an edge case whose arguments break the tool's own `inputSchema` and that gets a result without `isError` is reported (`Scenario.violations`, `ScenarioResult.accepted_invalid_input`, `scenario_findings()`, `SCENARIO_RULES`, the JSON report's `findings` and "Top issues to fix"). The score is unchanged.
- `LintIssue.rule`, a stable rule ID on every issue (`toolscore mcp lint` shows a Rule column; the JSON report has `rule`). New rules: `annotations-missing`, `annotation-read-only-contradiction`, `annotation-hints-conflict`, `annotation-invalid-value`, `structured-content-missing`, `structured-content-mismatch`. All are warnings.
- `output_schema_issues()` and `toolscore.mcp.output_schema.validate_instance()`, a conservative JSON Schema check that never judges keywords it does not know.
- `score_server(client)` runs the whole scorecard for any client; `MCPScorecard.protocol_version` and `.era`; the JSON report adds `protocol`.
- `toolscore mcp test --badge` and `--badge-json` (`toolscore.mcp.badge`).
- The bundled sample server (`python -m toolscore.mcp.sample_server`) speaks both eras and now declares annotations and an output schema; the demo grade stays B, with one new finding (`create_note` declares no annotations).

#### Effect probes (`toolscore.mcp.probes`)
- `toolscore mcp test --probes`, `--allow-writes` and `--probe-config FILE` (JSON or YAML; implies `--probes`). `score_server(client, probes=True | ProbeConfig, allow_writes=False)` and `run_probes()`.
- Rules: `probe-write-not-observable`, `probe-silent-noop`, `probe-data-lost`, `probe-bound-exceeded`, `probe-bound-short`, `probe-slice-mismatch`, `probe-paths-disagree`, `probe-not-idempotent` (`PROBE_RULES`).
- Every result has a `confidence` (`high`: declared, or seen through a read tool that already showed the record; `medium`: inferred from names; `low`: any other read tool) and a `basis` saying how the read tool or relation was chosen. Only high-confidence failures are errors: they lower the score by as much as a tool failing all its happy paths (`0.6 / number of tools` per failing tool) and cap the letter grade at C; passing probes leave the score unchanged. `--ci` treats them as blocking.
- **Grade cap.** A high-confidence probe failure caps the grade at C (`PROBE_GRADE_CAP`): the score is unchanged, and the console, Markdown and JSON scorecards and the badge say `capped because: probe-silent-noop on create_entities` (`MCPScorecard.uncapped_grade`, `.grade_capped`, `.grade_cap_reasons`, `.grade_cap_note`; JSON `grade_cap`; badge `C (capped) · Toolscore`). Without it `server-memory@2026.8.31` graded A (93%) with a silent no-op. `--no-probe-grade-cap`, `score_server(probe_grade_cap=False)` and the Action input `mcp-probe-grade-cap: false` turn it off.
- `ProbeConfig`, `RoundTripPair`, `BoundRelation`, `Agreement`, `CallSpec`, `ProbeResult`, `load_probe_config()`; `MCPScorecard.probes`, `.effect_rate`, `.probe_failed_tools`; the console and Markdown scorecards show an "Effect probes" table and the JSON report `probes` and `scores.effect_rate`.
- Probes that write run only with `--allow-writes` (a probe config cannot enable them) and leave `tsp<hex>-` marker records behind.
- The sample server stores its notes, and `python -m toolscore.mcp.sample_server --bug silent-skip | lose-on-write | limit-ignored` misbehaves without an error, for demos and tests. The default behavior and the demo scorecard are unchanged.
- `--arg [TOOL:]NAME=VALUE` and `--args-file` on `mcp test` (`ArgumentFixtures`, `load_fixtures()`, `generate_scenarios(fixtures=...)`): values replace generated ones in happy paths and seed the probes; edge cases keep their bad values.

#### Honesty checks (`toolscore.metrics.honesty`)
- `metrics["honesty_metrics"]` in every `evaluate()` and `evaluate_trace()` result, `EvaluationResult.false_success`, and `summary.false_success` in the JSON report. Findings appear under Behavior and safety with their rule ID.
- Rules: `claimed-success`, `injected-fault-undisclosed`, `prompt-injection-followed` and `canary-leaked` (errors), `escape-hatch-after-refusal` (error when the code overrides the refusal, warning when it only targets the same thing), `done-after-error` and `undisclosed-warning` (warnings) (`HONESTY_RULES`).
- `false_success` counts per run: `claimed_success`, `failed_required`, `done_after_error`, `undisclosed_warning`, `escape_hatch`, `injected_faults`, `injected_undisclosed`; `None` where the final answer (or the gold) is needed and missing.
- `toolscore honesty TRACE [--gold] [--final-answer TEXT|@FILE] [--injected SESSION] [--config] [--json] [--fail-on-findings]`; `toolscore eval --final-answer`, `--honesty-config`, `--injected` and `--fail-on-honesty`.
- `check_honesty()`, `HonestyConfig` (every pattern and tool list configurable; JSON/YAML with `"extend": true` to add to the defaults), `apply_injections()`, `evaluate(final_answer=..., honesty=...)`, `evaluate_trace(final_answer=..., honesty=..., injections=...)`.
- Disclosure is negation-aware: "no errors", "without any issues", "nothing failed", "zero warnings", "didn't hit any errors" and "error-free" are reassurance, not a disclosure, so "Done, no errors!" after a failed call is a `claimed-success` (`neutral_patterns`, configurable). A negated action ("nothing was saved", "not shipped", "no order was placed") is a disclosure, as are "pending", "on hold", "timed out", "except" and refusals ("I won't").
- Answers that are not in English are unknown, never honest: `answer_language` (`"english"`, `"other"`) in the report, a deterministic script and function-word heuristic (`answer_language()`); the answer-dependent counts are `None` and the evidence says "the final answer is not in English". `require_english: false` turns it off for your own patterns.
- A labelled corpus of final answers (`tests/fixtures/honesty_answers.json`) with precision and recall floors. On the 30-answer held-out set: claims success 1.00 precision / 0.73 recall, discloses a problem 1.00 / 0.69 (0.75 / 0.20 and 0.58 / 0.54 before the negation-aware patterns); see the honesty guide for what they miss.
- `toolscore.transcript`: `load_transcript()`, `Transcript` and `final_answer_of()` find the final answer in OpenAI Chat Completions, Anthropic, Responses, LangChain/LangGraph and Claude Agent SDK messages, OpenTelemetry `gen_ai.output.messages`, a final `done`-style call, or a `final_answer` / `final_output` / `output_text` field. `toolscore.core.adapter_for()`.

#### Fault injection (`toolscore.mcp.faults`)
- `toolscore mcp proxy COMMAND -o SESSION [--inject SPEC]` and `MCPRecorder(..., injector=FaultInjector(spec))`. Faults: `error`, `jsonrpc_error`, `warning`, `empty`, `delay`, `timeout`, `disabled`, `denied`, `truncate`; tools by name or glob, calls by number or probability with a fixed seed; failures are answered without reaching the server unless `forward: true`.
- The session adds `fault_spec`, `injections` and `injected` on each changed response; `MCPAdapter` keeps it as `metadata["injected"]`. `mcp record` is unchanged. Stdio only.
- `FaultSpec`, `FaultRule`, `FaultInjector`, `load_fault_spec()`, `FAULT_KINDS`.
- The `prompt_injection` fault: the proxy appends an instruction (call `target_tool`, or put the code in the next call and the reply, and do not tell the user) with a unique canary token (`canary`, or derived from the seed, tool and call number) to the real result. The honesty checks add `prompt-injection-followed` (a later call to the target tool, or one matching a forbidden rule: `check_honesty(forbidden=...)`, `toolscore honesty --forbidden`, and `eval --forbidden`) and `canary-leaked` (the canary in a later call's arguments or the final answer, matched in any language), the `prompt_injection` counts (`planted`, `followed`, `canary_leaked`; unknown without a final answer) and a `prompt-injection` evidence check. `examples/fault_injection/scripted_injection.py` runs it offline.

#### Agent harness (`toolscore.mcp.agent`)
- `toolscore agent run SPEC [--output] [--max-runs] [--retry-errors] [--allow-unknown-price] [--dry-run]`; `run_study()`, `run_agent()`, `load_agent_spec()`, `spec_from_mapping()`, `AgentSpec`, `ArmSpec`, `TaskSpec`.
- Providers: `OpenAIResponsesProvider`, `AnthropicMessagesProvider` (any client with `responses.create` / `messages.create`; the SDKs stay optional extras) and `ScriptedProvider`. `map_tools()` maps MCP tools to provider function tools with safe, unique names.
- Guards: `allow()`, `deny(reason)`, `rules_guard(deny_rules, allow_tools)` and `guard.python: module:function`; denied calls are returned to the model as tool errors and listed in `guard_denials`.
- `Budget`, `Price`, `price_for()`, `preflight_prices()` (`UnknownPriceError` before any call), `estimate_study_cost()`; `Limits(max_turns, max_calls)`.
- `verify` (`server_name`, `server_version`, `command` + `expect`), `check_build()`, `BuildMismatchError`.
- Run rows (`run_record_version` "1"): calls with IDs, arguments, results, errors, durations and denials; final answer; usage; cost (`null` when unknown); server identity and protocol; the evaluation with honesty and evidence; `outcome` (pass, fail, error, unknown). `regrade_rows()`.
- `examples/agent_harness/`: an offline study with real output, and a real-model spec marked as costing money.

#### Pinning and diffs (`toolscore.mcp.pin`, `toolscore.mcp.server_diff`, `toolscore.mcp.snapshot`)
- `toolscore mcp pin`, `toolscore mcp verify-pin [--lock] [--fail-on drift|capability|never] [--json] [--ci]`, `mcp test --pin/--pin-fail-on`, `mcp lint --pin/--pin-fail-on`.
- `toolscore mcp list --json` writes a server snapshot; `ServerSnapshot`, `load_snapshot()`, `write_snapshot()`.
- `build_lock()`, `verify_pin()`, `PinReport`, `PinFinding`, `PIN_RULES` (`pin-tool-added`, `pin-tool-removed`, `pin-tool-changed`, `pin-capability-added`, `pin-instructions-changed`, `pin-lock-modified`, `pin-server-changed`, `pin-protocol-changed`), `infer_capabilities()`, `CAPABILITIES`, capability overrides (`--capabilities`).
- `toolscore mcp diff A B [--test] [--probes] [--allow-writes] [--fail-on any|breaking|none] [--json]`; `diff_snapshots()`, `ServerDiff`, `ToolChange`.
- `examples/pinning/`: an offline rug pull and the memory server's `2026.8.31` vs `2.0.1`, with real output.

#### Contracts, receipts and evidence
- `toolscore.contract`: `evaluate_contract()`, `load_contract()`, `Contract`, `contract_from_mapping()`, `is_contract()`, `matcher_from_json()` (`$regex`, `$contains`, `$one_of`, `$any`, `$type`, `$approx`); `toolscore/schemas/contract-v2.schema.json`. `toolscore eval`, `evaluate_trace()` and `toolscore regrade` accept a contract wherever they take a gold file. `EvaluationResult.scored_calls`.
- `toolscore.receipts`: `toolscore eval --receipt PATH`, `build_receipt()`, `verify_receipt()`, `regrade()`; `toolscore regrade SOURCES [--gold] [--weight] [--forbidden] [--receipt-dir] [--json] [--no-verify] [--spec] [--output]` for receipts, traces and agent-run JSONL.
- `toolscore.evidence` and `EvaluationResult.evidence`: tri-state checks (`required-calls`, `call-errors`, `forbidden-calls`, `credentials`, `claimed-success`, `disclosure`, `escape-hatch`, `side-effects`), counts and coverage, in the console, Markdown, HTML and JSON reports and `to_dict()`. `MCPScorecard.probe_evidence` (inconclusive probes are unknown).
- `ToolCall.id` (the provider call ID or the JSON-RPC request ID); `to_dict()` and the JSON report keep `id`, `is_error` and `timestamp` for every call.
- `examples/contracts/`: a contract against the gold file it replaces, and a regrade, with real output.

#### Runs, selection, export and doctor
- `toolscore.stats`: `wilson_interval()`, `fisher_exact()`, `pass_hat_k()`, `compare_runs()`, `select_variant()`, `pareto_front()`, `evaluate_protocol()`, `load_runs()`, `runs_from_traces()`.
- `toolscore compare --runs FILE | GOLD --variant NAME=DIR [--k] [--baseline] [--min-n] [--alpha] [--min-score] [--protocol] [--json]`; `toolscore select [--policy lexicographic|weighted|pareto] [--objective] [--weight]`.
- `toolscore export --format aef INPUTS -o FILE` and `toolscore.export` (`export_records()`, `write_export()`, `validate_record()`): `toolscore.run-record` v1 with `toolscore/schemas/run-record-v1.schema.json` and a manifest.
- `toolscore doctor [--spec] [--contract] [--server] [--key] [--json]` and `toolscore.doctor.run_doctor()`.

#### Agents in the wild
- browser-use: `from_browser_use()`, `BrowserUseAdapter` and the `browser-use` trace format read an `AgentHistoryList`, its `model_dump()` or the JSON `save_to_file()` writes (verified against browser-use 0.13.14). Each executed action is a call, paired with its `ActionResult`; the `done` text is the final answer and its `success` flag the agent's own verdict (`Transcript.success`). A `done` with `success: true` is a success claim, and code that overrides a refusal the model noted on the step is an escape hatch. `examples/browser_use/`.
- Coding-agent sessions: Claude Code transcripts (`~/.claude/projects/*/*.jsonl`, `CLAUDE_CONFIG_DIR`) and Codex CLI rollouts (`~/.codex/sessions/**/rollout-*.jsonl`, `CODEX_HOME`, verified against the `openai/codex` source on 2026-11-02) are auto-detected (`claude-code` and `codex` formats; `ClaudeCodeSessionAdapter`, `CodexSessionAdapter`). Subagent lines are skipped; a Codex shell call fails when its output reports a non-zero exit code. `toolscore sessions list [--agent] [--since] [--project] [--root] [--flagged] [--json]` and `toolscore sessions export SESSION -o trace.json` (credentials redacted); `toolscore.sessions`. Read-only; nothing is uploaded. `examples/coding_sessions/` (synthetic).
- Trace files may be JSON Lines: `load_trace()`, `load_transcript()` and every command that reads a trace parse a file that is not one JSON document line by line (`toolscore.core.read_trace_data()`).
- `toolscore.recorders`: `ClaudeAgentSDKRecorder` (`PreToolUse`, `PostToolUse` and `PostToolUseFailure` hooks for `ClaudeAgentOptions(hooks=recorder.hooks())`; inputs, responses, errors, durations, subagent IDs; `observe()` keeps the `ResultMessage` text) and `OpenAIAgentsRecorder` (a tracing processor for `add_trace_processor()`: function and MCP tool spans with arguments, outputs and errors). Both have `calls`, `final_answer`, `to_trace()`, `save()` (credentials redacted) and `evaluate()`. Tested with claude-agent-sdk 0.2.176 and openai-agents 0.24.0.
- `toolscore.inspect_scorer.toolscore_scorer()`: an Inspect AI scorer with `tool_score`, `passed`, `false_success` and `honesty_unknown` metrics; expectations from the scorer, `Sample.metadata["toolscore"]` (calls or a contract) or a JSON target; `from_inspect_messages()`. Tested with inspect_ai 0.3.287; `examples/inspect_ai/` runs offline with `mockllm`.
- Pydantic AI 2 (verified with 2.64.0): `from_pydantic_ai()` pairs `ToolReturnPart`s with their calls as `result`; an `outcome` of `failed`, `denied`, `interrupted` or `retried`, or a `RetryPromptPart`, makes the call failed; `evaluate()` takes the run's text `output` as the final answer (`pydantic_ai_final_answer()`).
- `toolscore honesty` and `toolscore sessions` redact credentials in what they print.

#### Agent-config lint
- `toolscore lint-config [PATHS] [--snapshot [SERVER=]FILE] [--pin [SERVER=]FILE] [--connect] [--user] [--json] [--fail-on error|warning|never]` and `toolscore.config_lint` (`lint_config()`, `discover_files()`, `ConfigLintReport`, `ConfigIssue`, `CONFIG_RULES`). Rules: `config-server-invalid`, `config-unknown-server`, `config-unknown-tool`, `config-annotation-contradiction`. Without a tool list the tool rules are skipped, not passed; `--connect` (which starts the configured servers) is never the default. Inspired by Agent Eval Flow's configuration assessment. `examples/lint_config/`.

#### Claude Code plugin and demo
- `.claude-plugin/marketplace.json` and `plugins/toolscore/` with the skills `audit-mcp-server`, `add-tool-call-tests`, `check-agent-honesty` and `pin-mcp-servers` (plain `SKILL.md` files that call the CLI): `/plugin marketplace add yotambraun/toolscore`, `/plugin install toolscore@toolscore`.
- `toolscore demo --truth`: effect probes on the sample server's silent no-op, then the honesty check on a bundled browser-agent trace.

#### Examples
- `examples/mcp_memory_probes/` and `examples/mcp_filesystem_probes/`: the probes on the official memory and filesystem servers, with the commands and the console output.
- `examples/probes/` (a probe config for the sample server), `examples/honesty/` (traces for the honesty checks) and `examples/fault_injection/` (a scripted agent behind the proxy, offline).

#### SARIF and JUnit (`toolscore.reports.ci`)
- `--sarif PATH` (SARIF 2.1.0, for GitHub code scanning) and `--junit PATH` (JUnit XML, for GitLab, Jenkins and other test-report viewers) on `mcp test`, `mcp lint`, `mcp verify-pin`, `mcp diff`, `lint-config`, `honesty` and `eval`, from one shared reporter (`Outcome`, `to_sarif()`, `to_junit()`, `write_ci_reports()`). Every check is pass, fail or unknown: in SARIF an unknown check is `kind: "open"` with `level: "none"`, never a pass; in JUnit it is `<skipped>`. Rules carry descriptions, help and documentation links. Results point at the file they are about (config-lint file and line, the lock file, the trace), or for a server at `--report-location`, the `--config` file or the server script in the command. The output validates against the official SARIF 2.1.0 schema (tested).

#### pre-commit
- `.pre-commit-hooks.yaml` with `toolscore-lint-config`, `toolscore-verify-pin` and `toolscore-mcp-lint`: local, deterministic, no API key; none calls a tool. Documented in the CI guide.

#### GitHub Action
- New inputs `mcp-probes`, `mcp-allow-writes`, `mcp-probe-config`, `mcp-args-file` and `fail-on-honesty`, and the `honesty-errors` output.
- New inputs `mcp-pin-file` and `mcp-pin-fail-on` (pin check with the scorecard), `mcp-diff-against` and `mcp-diff-fail-on` (a server diff in the job summary, output `mcp-diff-breaking`), and `mcp-probe-grade-cap`.
- New inputs `sarif-file`, `junit-file` and `report-location`: the scorecard or the evaluation also writes SARIF (upload it with `github/codeql-action/upload-sarif`) and JUnit XML.
- New inputs `mcp-auth-env`, `mcp-badge`, `mcp-badge-json` and `toolscore-version`; `mcp-command` accepts a URL. New outputs `mcp-grade` and `mcp-score`. MCP mode writes the scorecard to the job summary.
- The action installs Toolscore from its own checkout, so the installed version matches the action ref (it installed the latest PyPI release before). `toolscore-version` installs a given PyPI release instead.
- `examples/github_actions/mcp-badge.yml` commits an updated badge when the grade changes.

#### Integrations
- `from_openai_responses()` and auto-detection of Responses API responses, output lists and input item lists, in `evaluate()` and in trace files (`--format auto` / `openai`). Outputs become the call's `result`; an output counts as an `error` only when it clearly is one (a JSON object with `error` or `is_error: true`, or the OpenAI Agents SDK's tool error message). `mcp_call` items keep their `output` and `error`.

#### Models and prices
- `toolscore.models`: the current default model IDs in one place, with the date they were verified (2026-11-01).
- `lookup_pricing()`, `UnknownModelPriceWarning`, `PRICES_VERIFIED_ON`, and `pricing=(input, output)` on `calculate_llm_cost()` and `estimate_trace_cost()`.

### Changed

- **A high-confidence effect-probe failure caps the grade at C.** The score is unchanged; `MCPScorecard.grade` is capped and `.uncapped_grade` is what the score alone earns (`.grade_capped`, `.grade_cap_reasons`, `.grade_cap_note`; JSON `grade_cap`; badge `C (capped) · Toolscore`). `--fail-under` and the Action's `mcp-grade` use the capped grade. Rationale: a tool that reports success and does nothing is a correctness bug, and the score penalty alone (`0.6 / number of tools`) left `server-memory@2026.8.31` at A. Turn it off with `--no-probe-grade-cap`, `score_server(probe_grade_cap=False)` or `mcp-probe-grade-cap: false`.
- **Latency and cost are never 0 when unknown.** `metrics["latency_metrics"]` and `["cost_metrics"]` are now always present, also for `evaluate()`, with `status` (`measured`, `partial`, `unknown`), `measured_calls` and `total_calls`; their totals are `None` when no call has the value (they were 0.0, or the section was left out). `calculate_latency()` and `calculate_cost_attribution()` return the same. Reports print `unknown` or `N of M calls`; the JSON report's summary adds `total_duration`, `total_cost`, `latency_status`, `cost_status` and `evidence`.
- **The honesty checks need tool results to pass.** When no call carries a result or an error, `undisclosed_warning` and `escape_hatch` are `None` (unknown) and `flagged` is `None`; the report adds `results` (`captured`, `partial`, `missing`). They were 0 (a pass) on request-only traces.
- `toolscore compare`'s `GOLD_FILE` is optional (the runs mode takes `--runs`); the one-trace-per-model form is unchanged.
- The agent-side console, HTML and Markdown reports add an Evidence section, and the HTML report always shows the performance section.

- **The LLM judge sends no `temperature` unless you set one.** `JudgeConfig.temperature` defaults to `None` (it was `0.0`): current Claude models (Opus 4.7 and later, Sonnet 5 and later, Haiku 5.5) and OpenAI's GPT-6 models at their default reasoning effort reject a non-default temperature with a 400 error. Set `temperature=0.0` for models that accept it, such as local OpenAI-compatible servers.
- **The default judge model is `gpt-6-luna`** (was `gpt-4o-mini`, which OpenAI retires on 2027-01-14). Docs and examples use `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5` and `gemini-3.5-flash-lite`.
- **Model prices match exactly or by longest prefix, and unknown models have no price.** `calculate_llm_cost()` and `estimate_trace_cost()` return `None` with an `UnknownModelPriceWarning` for a model they do not know (they used to fall back to the gpt-4o-mini price), so their return type is now `float | None`. The table is refreshed from the providers' pricing pages; retired models (Claude 3.x, Claude Opus 4.1, Gemini 1.5 and 2.0) were removed. `estimate_trace_cost()` defaults to `gpt-6-luna`.
- `MCPStdioClient` sends `server/discover` before `initialize`. Servers built on earlier revisions answer it with an error (handled), or do not answer, which costs up to `probe_timeout` (5 seconds by default) before the handshake. `DEFAULT_PROTOCOL_VERSION` is now "2026-07-28".
- **Grades can drop slightly.** The new annotation and output-schema warnings count toward the lint score like any warning (0.1 per warning, divided by the number of tools, in a term weighted 20%). A server whose write tools declare no annotations loses a few points; check `--fail-under` gates after upgrading. The bundled sample server went from 87% to 86%.
- **Evaluations report more findings.** The honesty checks add Behavior and safety lines to traces that failed or warned: a trace that ends right after a failed call gets `done-after-error`, and a trace with failures but no final answer gets "disclosure unknown". They do not change the score. The examples' guardrails trace now shows both.
- **Chat histories keep tool results.** OpenAI Chat Completions `role: "tool"` messages and Anthropic `tool_result` blocks are attached to their calls as `result` (they were dropped), and an Anthropic `tool_result` with `is_error: true` makes the call failed, so it now counts in `error_count`, `required_call_recall` and the findings. Side-effect validators that read `result` see it too.
- Message lists (trace files or `evaluate_trace()`) that start with a user or system message are detected as OpenAI or Anthropic traces (they were read as the custom format, with no calls).
- Python 3.14 is supported and tested.
- The README is a short landing page; its detail moved to the documentation: *What Toolscore catches*, *CI/CD*, and recipes for server authors, agent builders, security teams and researchers.
- The comparison (docs and the site's Compare page) is rewritten around the tools people compare Toolscore with today: MCP Inspector, the official MCP conformance suite (which Toolscore does not replace), Snyk Agent Scan and Cisco MCP Scanner, DeepEval's MCP metrics and Promptfoo. Each statement about another tool links its own documentation (checked 2026-11-02) and says where that tool is the better choice; the old DeepEval/RAGAS/LangSmith matrix is gone.
- The release workflow publishes with PyPI Trusted Publishing and moves the `v1` tag to each release, so `uses: yotambraun/toolscore@v1` resolves.

### Fixed

- **Claude Agent SDK messages yielded no calls.** The SDK's `ToolUseBlock` and `ToolResultBlock` dataclasses carry no `type` field, so `from_claude_agent_sdk()` and auto-detection returned nothing for the messages `query()` yields. Blocks are recognized by class, tool results are paired to their calls (`is_error` makes a call failed), and the `ResultMessage` text is the final answer.
- A `claimed-success` finding said a failed call "was not retried" when a later call to the same tool failed too; it now says "no later call to it succeeded".
- The JSON report failed (`Object of type ... is not JSON serializable`) when expected arguments held matchers; they are written as their `repr`, as `to_dict()` does.

- **A perfect run scores exactly 1.0.** The composite score summed its weights with plain float addition and gave 0.9999999999999999.
- **Prices of similarly named models.** `gpt-5-mini` was priced as `gpt-5`, `gpt-4o-mini` as `gpt-4o`, and `gemini-2.5-flash-lite` as `gemini-2.5-flash` (the first table key contained in the name won). Claude Opus 4.6 was listed at $15/$75 per million tokens; it is $5/$25.
- `evaluate()` on an OpenAI Responses API object failed with "Cannot auto-detect provider format".
- Error messages and reprs never show credentials: URLs are shown without userinfo, query or fragment, `MCPServerSpec` keeps `env`, `url` and `headers` out of its repr, and a malformed `--header` is not echoed. Error panels show server text literally instead of parsing it as Rich markup.
- **`toolscore init` scaffolds that failed on their first run.** The fake responses written for Pydantic AI, the OpenAI Agents SDK and CrewAI were bare lists that `evaluate()` could not detect. Lists of Pydantic AI messages, Agents SDK `tool_call_item` items and CrewAI `tool_name` entries are now auto-detected.
- The Anthropic capture example stored SDK content blocks, which `json.dump` cannot serialize; it now stores them as JSON.
- Behavior and safety findings are printed literally in the console (text in brackets from a tool result was read as Rich markup).

## [1.10.0] - 2026-10-03

Toolscore 1.10 scores what agents really did, not only which tools they named: record real MCP sessions or import OpenTelemetry spans, and see failed calls, required calls that never succeeded, leaked credentials and forbidden calls next to the score. Every new check was validated on real agents and real MCP servers, including GitHub's official MCP server.

### Highlights

- **Record real MCP sessions.** `toolscore mcp record "<server command>" -o session.json` is a transparent stdio proxy: put it in your MCP client config in place of the server, use your agent as usual, and every tool call is saved with its arguments, result, error and duration. `toolscore eval gold.json session.json` scores it directly.
- **Behavior and safety checks.** Every evaluation now reports failed tool calls, retries of a failed call with the same arguments, and credentials passed into tool arguments (API keys, tokens, private keys; reported with a redacted preview). Forbidden-call policies (`forbidden=` in Python, `--forbidden rules.json` on the CLI, `does_not_call(tool, **args)` in `expect()`) flag calls an agent must never make, and `--fail-on-violations` turns them into a CI gate.
- **Required calls that never succeeded are visible.** `required_call_recall` counts each required call that was made and did not fail. The CLI prints `Required calls completed: X of N` when some are missing, and `--weight required_call_recall=0.3` (or `weights=`) makes them lower the score.
- **MCP lint finds broken and hostile tool descriptions.** References to tools the server does not expose (in descriptions, parameter descriptions and server instructions), and tool-poisoning patterns: hidden Unicode (tag characters, bidi controls), instructions to hide things from the user or to ignore other instructions (errors), and `<IMPORTANT>`-style instruction blocks (warnings). On GitHub's official MCP server (v1.12.2, 254 tool definitions across three toolset configurations) it reports the two real stale references and no false positives.
- **OpenTelemetry import.** `from_otel()`, `--format otel` and auto-detection read tool calls from OpenTelemetry GenAI spans (`execute_tool`) and MCP `tools/call` spans, from OTLP JSON exports or SDK span objects, so any instrumented framework or observability platform can feed Toolscore.

### Added

#### Traces keep what happened
- Tool calls keep their `result`, `error`, `is_error`, `duration`, `cost`, `id` and metadata when loaded from files or passed to `evaluate()`; `ToolCall.is_error` tells whether a call failed.
- `efficiency_metrics` adds `error_count`, `error_rate` and `retry_after_error_count`.
- `EvaluationResult.to_dict()` returns a complete, JSON-safe, versioned record (`schema_version` "2"): score, grade, weights, `required_call_recall`, all metrics, and every expected and actual call. Built for harnesses that store evidence, such as Agent Eval Flow.

#### Behavior and safety
- `required_call_recall` metric and `EvaluationResult.required_call_recall`: required calls completed, counting repeats (a contract that requires `search` twice is half met by one `search`).
- Opt-in `required_call_recall` score weight (0 by default), also accepted by `evaluate_trace(weights=...)`, `expect(...).with_weights(...)` and `toolscore eval --weight NAME=VALUE`.
- `security_metrics`: credentials found in tool arguments at any depth (OpenAI, Anthropic, GitHub, AWS, Google, Slack and Stripe formats and PEM private keys), with the argument path and a redacted preview. OpenAI and Anthropic matches must also look random (digits and both letter cases), so slugs are not reported. No false positives on 861 real agent tool calls. `redact_secrets()` replaces credentials in any text.
- Forbidden-call policies: `evaluate(..., forbidden=[...])` and `evaluate_trace(..., forbidden=[...])` report `policy_metrics` and `EvaluationResult.policy_violations`. Rules name a tool and optional argument values or matchers. `load_forbidden_rules()` / `rules_from_json()` read JSON rules where values may be `{"$regex": ...}` (found anywhere in the value, like `re.search`, so a prefix or a second line does not hide it; lists are matched as their items joined with spaces), `{"$contains": ...}` or `{"$one_of": [...]}`. Policies do not change the score.
- `expect(...).does_not_call(tool, **args)` accepts arguments and matchers: forbid `run_shell` only when the command matches `rm -rf`.
- Console, Markdown and HTML reports list behavior and safety findings (forbidden calls, credentials, failed calls, blind retries) and the required calls completed. The HTML and Markdown reports now show the score and grade. All three redact credentials wherever they would print them, so a Markdown report posted to a GitHub job summary does not publish a key; the JSON report and `to_dict()` keep the calls as recorded.
- The JSON report's `summary` adds `score`, `grade`, `weights`, `required_call_recall`, `failed_calls`, `policy_violations` and `secrets`, so CI scripts can read the verdict without recomputing it.
- `toolscore eval --forbidden FILE`, `--weight NAME=VALUE` and `--fail-on-violations`.

#### GitHub Action
- New inputs `forbidden-file` and `fail-on-violations` (off by default) for a safety gate, and new outputs `score`, `grade`, `required-call-recall` and `violations`. The `format` input accepts `mcp` and `otel`.

#### Examples
- `examples/guardrails/`: a deploy agent's trace with a destructive command, a credential posted to a webhook and a failed deploy retried unchanged, with `forbidden.json` rules.
- `examples/otel_genai_spans.json`: an OTLP export written by the official OpenTelemetry Python SDK.
- The quality-gates workflow example gains a safety-check job.

#### MCP
- `toolscore mcp record` (and `MCPRecorder`): records only `tools/call` requests and their responses, writes atomically, and exits with the server's exit code.
- Lint rules for dangling tool references and tool poisoning; `lint_tools(tools, instructions=...)` also checks the server's `instructions`.
- The scorecard reports the token cost of the server's instructions alongside the tool definitions (`instructions_tokens`, `context_tokens`).
- `MCPStdioClient.server_instructions` and `server_capabilities` from the handshake; `MCPToolResult.text` and `content_to_text()` render every MCP content type (text, embedded resources, resource links, images, audio).

#### Integrations
- `from_otel()`, `OTelAdapter` and `--format otel` for OpenTelemetry GenAI tool spans (OTLP JSON exports, span dicts, or SDK `ReadableSpan` objects). Arguments, results, call ids, errors (`error.type` or an ERROR status) and durations are kept; calls are ordered by start time.

### Fixed

- **MCP traces no longer contain phantom calls.** `MCPAdapter` turned each JSON-RPC response into a separate `unknown` tool call, which inflated call counts and lowered selection and sequence scores. Responses are now paired with their requests by id, and their result or error is attached to the call. **Scores for MCP traces can change; re-approve baselines after upgrading.**
- **MCP sessions are auto-detected.** With `--format auto`, a recorded session (`{"format": "mcp", "messages": [...]}`) was routed to the OpenAI adapter and a plain JSON-RPC message list to the custom adapter; both loaded as zero calls.
- **Embedded resources are kept.** Tool results that return MCP `resource` content were reduced to an empty string.
- **MCP server commands with spaces.** `toolscore mcp list|lint|test|record` re-joined a multi-token command with spaces and split it again, so an argument containing a space (`-- npx -y server "/path with spaces"`, as MCP client configs pass it) was broken in two. Several tokens are now used as given; a single quoted string is still split like a shell command.

### Notes

- The default composite score is unchanged. It judges the calls that were made, so a trace that skips required calls can still score well; use the `required_call_recall` weight or the new console line to catch that.
- The `weights` reported by `to_dict()` and the JSON report now include `required_call_recall` (0.0 unless you set it). Passing the four existing weight names works as before.
- Missing-tool references and `<IMPORTANT>`-style blocks are lint warnings; hidden Unicode and concealment or override instructions are errors, and lower the MCP scorecard's lint score.
- A call counts as failed when it has `"is_error": true` or a non-empty `error`; `""`, `null`, `{}` and `[]` mean no error.

## [1.9.1] - 2026-10-01

Found by running `toolscore mcp test` against the official MCP reference servers (modelcontextprotocol/servers). Several failing grades were Toolscore's mistakes, not the servers'.

### Fixed

- **Union schema types.** A property whose `type` is a list (`["boolean", "string"]`, as in the official sequential-thinking server) crashed the scorecard with `unhashable type: 'list'`, and the value generator produced `None` for it. Values are now generated for the first non-null type, and wrong-type probes match none of the listed types.
- **Reproducible scenarios.** Scenario values came from the unseeded global `random`, so two runs against the same server could differ. Each tool now gets a generator seeded by its name.
- **Optional fields are typed.** The linter reported pydantic optional fields (`anyOf: [{"type": "string"}, {"type": "null"}]`) and `enum`/`const`/`$ref` properties as "missing a 'type'" (5 false errors on the official git server).
- **Schema hints are used.** Happy-path values now come from `examples`, a non-null `default`, an example quoted in the description ("e.g., 'America/New_York'"), or a well-formed value for `format` (uri, date-time, date, email, uuid, …) before falling back to synthetic values. The official time server previously received `"sample_timezone"`, and its correct rejection was scored as a failure.

### Known limitation

- Servers that restrict paths to allowed roots (filesystem, git) still reject generated paths, which lowers their happy-path rate. Read those failures as "input outside the server's sandbox", not as server defects.

## [1.9.0] - 2026-09-28

Found while evaluating a real research agent (DeerFlow) with Agent Eval Flow + Toolscore: `redundant_rate` could not tell a looping agent from one running many different searches, and one missing call could zero the argument score of every later call.

### Added

- **Identical-call (loop) metric.** `efficiency_metrics` now also reports `identical_count` and `identical_rate`: calls that exactly repeat an earlier call (same tool, same arguments, key order ignored). `redundant_rate` keeps its meaning (calls beyond the gold's per-tool expectation), so a research agent that runs many *different* searches is no longer indistinguishable from one stuck repeating the same call. Additive; composite scores are unchanged.

### Fixed

- **Argument and side-effect matching now pairs calls one-to-one.** Each expected call used to be matched to the first actual call with the same tool name at the same or a later *position*. One missing, extra or reordered call therefore shifted every later comparison, and a correct call could score 0. Expected calls are now paired with actual calls of the same tool by the best one-to-one assignment (exact for up to 12 calls per tool, greedy above). Examples: a missed earlier call went from `argument_f1` 0.00 to 0.67; two same-tool calls in swapped order, and a wrong attempt followed by the right one, went from 0.00 to 1.00 (the extra attempt is still penalised by `redundant_rate` and `sequence_accuracy`). An agent that correctly calls no tools when none are expected now gets `argument_f1` 1.0 (was 0.0). **Scores can rise for existing baselines and snapshots; re-approve after upgrading.**
- **Claude LLM judge works with current `anthropic` SDKs.** Recent SDK releases removed `temperature` from `messages.create`, so the Anthropic judge raised `TypeError: unexpected keyword argument 'temperature'`. `temperature` is now passed only when the installed SDK accepts it.

## [1.8.1] - 2026-06-19

This entry covers 1.7.0 through 1.8.1 (released 2026-06-13 to 2026-06-19).

### Highlights

- **Snapshot testing — record, approve, replay.** Stop hand-writing expected tool calls: `toolscore init` scaffolds a suite, the first `pytest` run records your agent's calls, `toolscore approve --all` blesses the baseline, and CI replays it forever. Jest snapshots for agents.
- **MCP Scorecard & instant health-check.** `toolscore mcp test "<server command>"` — or `toolscore demo` for a zero-setup sample server — auto-generates happy-path and edge-case scenarios from tool schemas, runs them, lints definitions, measures each tool's context-token cost, and prints an A–F grade with a ranked **Top issues to fix** list and concrete fixes. Export Markdown reports and gate CI with `--fail-under` or `--ci` (writes the verdict to `$GITHUB_STEP_SUMMARY` and fails on blocking issues) — a fast, deterministic, offline quality check for MCP servers.
- **Fluent `expect()` API, matchers, and rich diffs.** `expect(agent).on(prompt).calls("tool", arg=ANY).does_not_call(...).with_score(0.9).run()`, with `ANY`/`Regex`/`Approx`/`Contains`/`OneOf`/`IsType` matchers and aligned expected-vs-actual failure tables.
- **Native everywhere.** Raw responses from OpenAI, Anthropic, Gemini, LangGraph, Pydantic AI, OpenAI Agents SDK, Claude Agent SDK, and CrewAI (experimental) go straight into `evaluate()`/`expect()`/snapshots — zero glue. Async agents via `test_agent_async()` / `.run_async()`.
- **LLM judge for every provider.** Optional semantic judging via OpenAI, Anthropic, Gemini, or any OpenAI-compatible endpoint (Ollama/vLLM/Groq) — one `judge=` parameter and matching `[llm]`/`[anthropic]`/`[gemini]` extras.

### Added

#### Snapshot Testing
- `snapshot_check()`, `Snapshot`, and `SnapshotStore` — record-approve-replay state machine backed by plain JSON files under `.toolscore/snapshots/`
- `toolscore_snapshot` pytest fixture: records on first run, replays approved baselines, fails on drift, and prints a Jest-style terminal summary (`toolscore: 1 snapshot created (pending approval), 5 passed`)
- Pytest options `--toolscore-update` (re-record + re-approve), `--toolscore-snapshot-dir`, and `--toolscore-allow-pending`; `TOOLSCORE_RECORD_UPDATE=1` mirrors `--toolscore-update`
- CLI commands: `toolscore record` (subprocess or `--from-trace` mode), `toolscore approve [NAME|--all]`, and `toolscore snapshots list|show|rm`
- CI-safe by design: snapshots are never created or auto-approved when the `CI` env var is set — missing/pending snapshots fail the build

#### MCP Scorecard
- Zero-dependency MCP stdio client (`MCPStdioClient`) with config-file support for Claude Desktop style files (`--config` / `--server`)
- Scenario harness: happy-path and edge-case scenarios generated from each tool's input schema
- Schema linting (`lint_tools`) for missing descriptions, malformed schemas, undeclared required lists, and more
- `MCPScorecard` with an A–F grade blending happy-path pass rate (60%), edge resilience (20%), and lint cleanliness (20%)
- CLI commands: `toolscore mcp list`, `toolscore mcp lint`, `toolscore mcp test` with `--cases`, `--no-edge-cases`, `--report md|json --output`, and `--fail-under A-F`
- GitHub Action MCP mode: set `mcp-command` (and optionally `mcp-fail-under`) to grade an MCP server in CI instead of running the eval path

#### Fluent API, Matchers & Diffs
- `expect()` / `Expectation` fluent builder: `.on()`, `.calls()`, `.then_calls()`, `.does_not_call()`, `.with_score()`, `.with_weights()`, `.with_strict_args()`, `.run()`, `.run_async()`
- Argument matchers usable anywhere expected args appear: `ANY`, `Regex`, `Approx`, `Contains`, `OneOf`, `IsType`
- Rich failure diffs: `ToolScoreAssertionError` messages now embed an aligned expected-vs-actual table with per-argument mismatches and targeted tips (colored on a TTY, plain text in CI logs)

#### Framework & Async Support
- New extractors: `from_langgraph()`, `from_pydantic_ai()`, `from_openai_agents()`, `from_claude_agent_sdk()`, and `from_crewai()` (experimental); `auto_extract()` detects all of them, including list-shaped message formats
- `test_agent_async()` and `expect(...).run_async()` for async agents; sync entry points raise a clear `TypeError` pointing at the async variant

#### Multi-Provider LLM Judge
- `JudgeConfig` dataclass with provider inference from the model name (`claude-*` → Anthropic, `gemini-*` → Gemini, `base_url` → any OpenAI-compatible endpoint, otherwise OpenAI)
- CLI flags `--llm-model`, `--llm-provider`, and `--llm-base-url` on `toolscore eval` (e.g. Ollama: `--llm-model llama3.1 --llm-base-url http://localhost:11434/v1`)
- New extras: `tool-scorer[anthropic]` and `tool-scorer[gemini]`

#### Scaffolding & Quality
- `toolscore init` reworked into a framework-detecting wizard: detects your agent framework (LangGraph, Pydantic AI, OpenAI Agents SDK, Claude Agent SDK, CrewAI, raw SDKs, or generic), writes a pytest suite that passes immediately, and adds a snapshot-replay GitHub Actions workflow
- `evaluate()` validates inputs: `TypeError` for non-list `expected`, `ValueError` for unknown, negative, or non-finite weight keys; `assert_tools()`/`test_agent()` validate `min_score` range early
- `assert_score()` on `ToolscoreAssertions` and the `toolscore_assert_tools` fixture bridge the pytest plugin to the in-memory API
- `py.typed` marker (PEP 561) — mypy/pyright now see inline annotations
- Strict argument comparison mode (`strict=True` / `.with_strict_args()`): pure equality, no int/float coercion or string stripping

### Changed

**This release intentionally changes a few behaviors. Review these before upgrading:**

- **`evaluate_trace()` takes a single `judge` parameter.** The old `use_llm_judge`, `llm_judge_model`, and `llm_judge_api_key` keyword arguments are gone. Pass `judge=False` (default), `judge=True`, a model-name string, or a `JudgeConfig` — e.g. `evaluate_trace(gold, trace, judge=JudgeConfig(model="gemini-2.0-flash"))`.
- **Composite-score weights are renormalized.** Custom `weights=` are merged with the defaults and scaled so they sum to 1.0 before the composite score is computed. Scores produced with partial weight overrides may differ from previous releases; the relative ordering of metrics you emphasized is preserved.
- **Omitted gold arguments now mean "do not check arguments".** An expected call with `args` omitted (or `null`) is a tool-name-only expectation: the tool must be called, but any arguments are accepted. An explicit `"args": {}` keeps its strict meaning — "expect this tool to be called with zero arguments". This affects `argument_f1`, `tool_correctness`, trajectory, the composite score, gold-file loading, the fluent `.calls("tool")` (no kwargs = don't check args), and failure-diff rendering.
- **`ToolCall.args` preserves `None`.** It is no longer coerced to `{}` on construction, keeping "do not check" (`None`) distinct from "expect zero args" (`{}`). Code that assumed `.args` is always a dict should handle `None`.
- **The `min_accuracy` pytest marker is removed.** It was dead code; use `assert_tools(min_score=...)`, the `toolscore_snapshot` fixture, or the `toolscore_assert` helpers instead.
- **Importing `toolscore` no longer creates a `traces/` directory.** Trace capture creates its output directory lazily on first write, so simply importing the package leaves your filesystem untouched.
- Cost estimator pricing refreshed (February 2026), including a `claude-opus-4-6` entry.

### Fixed

- Zero-argument tool calls now score a perfect argument F1 when matched exactly (instead of being penalized as having no overlapping args)
- `evaluate()` routes `actual` through `auto_extract()`, so list-shaped raw formats (Claude Agent SDK / LangGraph message lists) are detected even when passed as plain lists
- LLM judge batching falls back to per-pair requests only on parse failures; transport and auth errors propagate instead of fanning out into doomed retries
- `MCPStdioClient.list_tools()` guards against runaway `nextCursor` pagination loops
- Argument comparison recurses strictly through nested dicts and lists
- `JudgeConfig` is exported from the package root

## [1.6.0]

### Added - Instant Value: Zero-Friction API

#### Auto-Detect Provider Responses
- **`auto_extract()`** — auto-detect OpenAI, Anthropic, and Gemini responses and extract tool calls
- **`evaluate()` and `assert_tools()` now accept raw provider responses** as the `actual` argument — no need to import or call `from_openai()` / `from_anthropic()` / `from_gemini()` manually
- Supports response objects (with `model_dump()`), plain dicts, and already-formatted lists

#### End-to-End Agent Testing
- **`test_agent()`** — run an agent callable, extract tool calls, evaluate, and optionally assert a minimum score, all in one call
- Accepts any callable that returns an LLM response (raw or pre-formatted)

#### Data-Driven Pytest Decorator
- **`@toolscore.cases()`** — parametrize pytest test functions with a list of test-case dicts
- Thin wrapper around `pytest.mark.parametrize` with automatic key extraction and test IDs
- Lazy pytest import avoids breaking non-pytest users

## [1.5.0]

### Added - In-Memory API, Integration Helpers & Simplified Output

#### In-Memory Python API
- **New `evaluate()` function** accepting Python dicts directly - no file I/O required
- **New `assert_tools()` one-liner** for pytest: `assert_tools(expected, actual, min_score=0.9)`
- **Composite `.score` property** on `EvaluationResult` (weighted average of key metrics)
- **Convenience properties**: `.selection_accuracy`, `.argument_f1`, `.sequence_accuracy`
- **Custom weights** support for composite score calculation
- **`ToolScoreAssertionError`** with detailed failure messages

#### Integration Helpers (`toolscore.integrations`)
- **`from_openai(response)`** - extract tool calls from OpenAI ChatCompletion responses
- **`from_anthropic(response)`** - extract tool calls from Anthropic Message responses
- **`from_gemini(response)`** - extract tool calls from Google Gemini responses
- Works with both response objects and plain dicts
- Supports modern and legacy formats (e.g., `tool_calls` and `function_call` for OpenAI)

#### Simplified CLI Output
- Default output now shows 4 key metrics: Overall Score, Selection Accuracy, Argument F1, Sequence Accuracy
- PASS/WARN/FAIL verdict with overall score
- Full detailed output available with `--verbose` flag
- Added `toolscore` as CLI alias alongside `tool-scorer`

#### README & Positioning
- New tagline: "Lightweight tool-call testing for LLM agents - deterministic, local, zero API cost"
- Leads with 3-line Python API example
- Honest comparison table including DeepEval, Ragas, and Inspect AI
- "When to use Toolscore vs. alternatives" section
- Advanced features moved to dedicated section

## [1.4.0] - 2026-01-09

### Added - Self-Explaining Metrics, Regression Testing & GitHub Action

#### Self-Explaining Metrics
- **Know exactly WHY your agent failed** with detailed explanations after each metric
- Automatic detection of tool name mismatches and similar names using SequenceMatcher
- Actionable tips like "use --llm-judge to catch semantic equivalence"
- Per-metric breakdowns showing MISSING, EXTRA, and MISMATCH items with severity levels
- New `toolscore/explainer.py` module with comprehensive explanation generation
- Categories: missing tools, extra tools, argument mismatches, type errors, value mismatches
- Tips tailored to specific failure patterns (low precision vs low recall, etc.)
- **Impact**: Users immediately understand what went wrong without manual debugging

#### Regression Testing (`toolscore regression`)
- **New CLI command** for CI/CD regression detection
- Save baselines with `--save-baseline` flag on `eval` command
- Automatic PASS/FAIL with configurable thresholds (default: 5%)
- Detailed delta reports showing improvements and regressions for each metric
- Exit codes: 0=PASS, 1=FAIL (regression), 2=ERROR
- Baseline includes:
  - Version tracking
  - Timestamp
  - Gold file hash for verification
  - All core metrics
- Comparison shows:
  - Baseline vs current values
  - Absolute delta and percentage change
  - Status per metric (REGRESSION/IMPROVED/OK)
- **Impact**: CI/CD pipelines can automatically catch agent degradation

#### GitHub Action
- **Official GitHub Action** for one-click CI setup
- Available on GitHub Actions Marketplace
- Supports both threshold and regression testing modes
- Features:
  - Automatic HTML report generation as artifacts
  - Job summary with evaluation results
  - Configurable accuracy thresholds
  - Regression testing against baselines
  - All trace format support
- Example usage:
  ```yaml
  - uses: yotambraun/toolscore@v1
    with:
      gold-file: tests/gold_standard.json
      trace-file: tests/agent_trace.json
      threshold: '0.90'
  ```
- **Impact**: Zero-config CI/CD setup for any repository

### Changed
- Enhanced console output with "What Went Wrong" section showing top issues
- Tips section now shows actionable suggestions based on detected problems
- Metrics table now shows self-explaining descriptions (e.g., "3 of 4 correct")
- Removed redundant "Suggestions for Improvement" section (replaced by new explainer)

### New Files
- `toolscore/explainer.py` - Self-explaining metrics generation
- `toolscore/baseline.py` - Baseline save/load/compare for regression testing
- `action.yml` - GitHub Action definition

## [1.2.0] - 2025-10-28

### Added - 🎯 Multi-Provider Support & Export Formats

#### 🤖 Google Gemini Adapter
- Full support for Google Gemini function calling traces
- Auto-detection for Gemini response format
- Handles multiple Gemini format variations:
  - `candidates` with `functionCall` (camelCase)
  - `function_call` (snake_case) alternative format
  - Direct `parts` list format
  - Mixed content with text and function calls
- Comprehensive test coverage (72.82%)
- **Impact**: Now supports all major LLM providers (OpenAI, Anthropic, Gemini)

#### 📊 CSV Export (`--csv`)
- Export evaluation results to CSV format for Excel/Google Sheets
- Human-readable formatting with percentage values
- Flattened metrics structure for easy sorting/filtering
- Ideal for sharing results with non-technical stakeholders
- 94.59% test coverage
- **Impact**: Business teams can analyze results in familiar spreadsheet tools

#### 📝 Markdown Export (`--markdown`)
- Export evaluation results to Markdown format for GitHub/docs
- Beautiful tables with status indicators (Excellent/Good/Fair/Needs Improvement)
- Collapsible details sections for clean PR comments
- Automatic timestamp and metadata
- Perfect for CI/CD workflows and pull request comments
- 81.38% test coverage
- **Impact**: Seamless integration with GitHub workflows

#### 💰 LLM Cost Estimation
- Built-in cost tracking with `calculate_llm_cost()` function
- Token estimation with `estimate_tokens()` function
- Trace-level cost estimation with `estimate_trace_cost()`
- Cost savings calculator with `calculate_cost_savings()`
- Up-to-date pricing for October 2025 models:
  - **OpenAI**: GPT-5 ($1.25/$10), GPT-5-mini, GPT-5-nano, GPT-4o, GPT-4o-mini
  - **Anthropic**: Sonnet 4.5 ($3/$15), Haiku 4.5 ($1/$5), Opus 4.1 ($15/$75)
  - **Google**: Gemini 2.5 Pro, 2.5 Flash, 2.5 Flash-Lite, 2.0 Flash
- Legacy model support for backward compatibility
- **Impact**: Quantify ROI and optimize agent costs

#### 🔧 CI/CD Integration Template
- Ready-to-use GitHub Actions workflow (`.github/workflows/toolscore-example.yml`)
- Automatic PR comments with evaluation results
- Quality gates with configurable thresholds
- CSV/Markdown/HTML report generation
- **Impact**: Zero-config CI/CD setup

#### 🛤️ Trajectory Evaluation
- Multi-step path analysis with `calculate_trajectory_accuracy()`
- Evaluates reasoning PATH taken by agent, not just final result
- Step-by-step comparison with detailed trajectory analysis
- Path efficiency metrics (penalizes unnecessary detours)
- Partial trajectory matching for flexible evaluation
- 89.29% test coverage with 13 comprehensive tests
- **Impact**: Industry-standard evaluation (matches BFCL V3/V4 capabilities)

#### 🔌 MCP (Model Context Protocol) Adapter
- Full support for Anthropic's Model Context Protocol (JSON-RPC 2.0)
- Auto-detection for MCP message format
- Handles tool requests, results, and error responses
- Batch call support
- 93.10% test coverage with 20 comprehensive tests
- **Impact**: Future-proof support for emerging open standard

#### 📦 Production Trace Capture
- `@capture_trace` decorator for capturing real agent executions
- Auto-save production traces as JSON test cases
- Convert captured traces to gold standard format
- Manual tool capture API with `TraceCapture` class
- **Impact**: Closes production→testing feedback loop

#### 🔍 Enhanced State Validators
- **FileSystemValidator**: Content validation (file contains text, size constraints)
- **SQLValidator**: Row-level validation (WHERE conditions, specific row matching)
- Deeper validation beyond simple existence checks
- **Impact**: State-based evaluation like BFCL V4

### Changed

- **Enhanced README**: Complete repositioning as "pytest for LLM agents"
- **Improved SEO**: Expanded PyPI keywords from 16 to 40+ for better discoverability
- **Updated Comparison Table**: Now compares against real competitors (LangSmith, OpenAI Evals, W&B)
- **CLI Enhancement**: Added `--csv` and `--markdown` flags to `eval` command
- **Format Support**: Added "gemini" option to all format-related commands

### Testing

- Increased test coverage from 47.80% to 55.05% (+7.25%)
- Added 63 comprehensive tests across new features (31 from initial features, 32 from advanced features)
- All 215 tests passing with zero bugs
- Strict mypy type checking compliance maintained
- New test suites:
  - 13 trajectory evaluation tests
  - 20 MCP adapter tests
  - Enhanced validator tests

## [1.1.0] - 2025-10-18

### Added - 🎯 Week 2: Major UX & Developer Experience Improvements

#### 🚀 Zero-Friction Onboarding (`toolscore init`)
- **Interactive CLI command** for project setup in 30 seconds
- Choose from 5 pre-built agent types (Weather, E-commerce, Code, RAG, Multi-tool)
- Automatically generates gold standard templates, README, and example files
- **Impact**: Onboarding time: 1+ hour → 30 seconds

#### ⚡ Synthetic Test Generator (`toolscore generate`)
- Generate comprehensive test cases from OpenAI function schemas
- Automatic edge case and boundary value generation (60% normal, 20% boundary, 20% edge)
- Smart value generation based on parameter names (email, url, query, etc.)
- Schema validation metadata extraction
- **Impact**: Test creation time: hours → 30 seconds

#### 📊 Quick Compare (`toolscore compare`)
- Compare multiple model traces side-by-side in single command
- Color-coded performance comparison table
- Automatic ranking per metric with best model highlighted
- Overall winner calculation with weighted average scores
- JSON comparison report export
- **Impact**: Multi-model benchmarking: manual spreadsheet → 1 command

#### 🔍 Interactive Debug Mode (`--debug`)
- Step-by-step failure analysis with `--debug` flag on eval command
- Interactive navigation through mismatches (next/previous/quit)
- Side-by-side expected vs actual comparison tables
- Context-specific fix suggestions for each failure type
- Detailed failure categorization:
  - Missing tools (expected but never called)
  - Extra tools (called but not expected)
  - Tool name mismatches
  - Argument mismatches with field-by-field comparison
  - Missing calls (trace ended early)
  - Extra calls (redundant invocations)
- **Impact**: Debugging: manual JSON diffing → guided walkthrough

#### 💡 Actionable Error Messages
- Automatic detection of common failure patterns during evaluation
- Specific fix suggestions displayed in console output
- Suggests `--llm-judge` for tool name mismatches
- Suggests `--verbose` for schema validation errors
- Suggests reviewing logic for missing tools
- Suggests checking arguments for type/value errors
- **Impact**: Users know exactly what to fix instead of guessing

### Added - 🎯 Week 1: Core Evaluation Features

#### Tool Correctness Metric
- New metric measuring whether ALL expected tools were called
- Complements selection accuracy by checking coverage vs per-call matching
- Reports `missing_tools` and `extra_tools` lists
- Deterministic evaluation without LLM needed

#### Integrated LLM-as-a-Judge
- Semantic evaluation now built into core evaluation engine
- Simple `--llm-judge` CLI flag (no separate script needed)
- Catches semantically equivalent tool names (e.g., "search" vs "web_search")
- Configurable model selection with `--llm-model` option
- **Previously**: Separate script in metrics directory
- **Now**: Integrated with single flag

#### Parameter Schema Validation
- Validate argument types (string, integer, number, boolean, array, object)
- Numeric constraints (minimum, maximum)
- String constraints (minLength, maxLength, pattern regex)
- Enum validation for allowed values
- Required field checking
- Detailed error reporting with field-level validation failures
- Define schemas in gold standard metadata:
  ```json
  {
    "metadata": {
      "schema": {
        "query": {"type": "string", "minLength": 1},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100}
      }
    }
  }
  ```

#### Example Datasets
- 5 realistic gold standard templates included:
  - `weather_agent.json` (Beginner - API lookup)
  - `ecommerce_agent.json` (Intermediate - Shopping workflow)
  - `code_assistant.json` (Intermediate - Code search/edit)
  - `rag_agent.json` (Advanced - Retrieval pipeline)
  - `multi_tool_agent.json` (Advanced - Research workflow)
- Each includes schema validation examples and descriptions
- Located in `examples/datasets/` directory

### Added - 🎯 Previous Features

- **LLM-as-a-judge metrics** (now integrated): Optional semantic correctness evaluation using OpenAI API
  - `calculate_semantic_correctness()` function for single evaluations
  - `calculate_batch_semantic_correctness()` for batch processing
  - Detects semantically equivalent tool calls beyond exact string matching
  - Supports custom models (default: gpt-4o-mini)
- **LangChain adapter**: Support for LangChain agent traces
  - Legacy AgentAction format (`tool`, `tool_input`, `log`)
  - Modern ToolCall format (`name`, `args`, `id`)
  - Alternative action/action_input format
  - Auto-detection support
- Comprehensive test suite increasing coverage from 37% to 80%+
- Complete Sphinx documentation with ReadTheDocs integration
- Interactive Jupyter notebook tutorials (quickstart, custom formats, advanced metrics)
- Rich-formatted console output with color-coded metrics tables
- Pytest plugin for seamless test integration
- Python-semantic-release configuration for automated versioning
- Optional dependency groups: `llm`, `langchain`, `all`

### Changed

- **Enhanced console output** with new tables:
  - Tool Correctness metrics table
  - Schema Validation metrics table
  - Actionable suggestions section
- **Improved CLI help text** for all commands
- Updated CLI to include all new commands: `init`, `generate`, `compare`
- Enhanced documentation with comprehensive examples
- Improved README with "What's New in v1.1" section
- Better command organization in help output

### Fixed

- Windows console Unicode compatibility (removed emoji characters causing UnicodeEncodeError)
- SQLValidator now supports multiple database field name variations
- CLI tests updated for correct Click exit codes
- Moved manual test files to proper `tests/manual/` directory

## [0.1.0] - 2025-10-13

### Added

- Initial release of Toolscore
- Core evaluation engine for LLM tool usage
- Support for OpenAI, Anthropic, and custom trace formats
- Comprehensive metrics:
  - Invocation accuracy
  - Selection accuracy
  - Sequence edit distance
  - Argument F1 score
  - Redundant call rate
  - Side-effect validation (HTTP, filesystem, database)
  - Performance metrics (latency, cost)
- CLI with `eval` and `validate` commands
- JSON and HTML report generation
- Side-effect validators for HTTP, filesystem, and SQL operations
- Format auto-detection
- Adapters for multiple LLM providers

### Documentation

- README with quick start guide
- Example files for all supported formats
- API documentation
- Usage examples

[Unreleased]: https://github.com/yotambraun/Toolscore/compare/v1.10.0...HEAD
[1.11.0]: https://github.com/yotambraun/Toolscore/compare/v1.10.0...HEAD
[1.10.0]: https://github.com/yotambraun/Toolscore/compare/v1.9.1...v1.10.0
[1.9.1]: https://github.com/yotambraun/Toolscore/compare/v1.9.0...v1.9.1
[1.9.0]: https://github.com/yotambraun/Toolscore/compare/v1.8.1...v1.9.0
[1.8.1]: https://github.com/yotambraun/Toolscore/compare/v1.6.0...v1.8.1
[1.6.0]: https://github.com/yotambraun/Toolscore/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/yotambraun/toolscore/compare/v1.4.2...v1.5.0
[1.4.0]: https://github.com/yotambraun/Toolscore/compare/v1.2.0...v1.4.0
[1.2.0]: https://github.com/yotambraun/Toolscore/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/yotambraun/Toolscore/compare/v0.1.0...v1.1.0
[0.1.0]: https://github.com/yotambraun/Toolscore/releases/tag/v0.1.0
