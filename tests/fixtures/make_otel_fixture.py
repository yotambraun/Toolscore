"""Regenerate otel_genai_tool_spans.json: a real OTLP JSON export of GenAI tool spans with the official OpenTelemetry SDK.

Spans follow the GenAI semantic conventions (execute_tool spans) and the MCP conventions
(tools/call). Exported through the SDK's own OTLP encoder, then protobuf -> JSON, exactly as
an OTLP/JSON exporter or collector file exporter writes it.

Requires: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-common
"""

import json
import time

from google.protobuf.json_format import MessageToDict
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

exporter = InMemorySpanExporter()
provider = TracerProvider(resource=Resource.create({"service.name": "demo-agent"}))
provider.add_span_processor(SimpleSpanProcessor(exporter))
tracer = provider.get_tracer("demo.agent")

with tracer.start_as_current_span(
    "invoke_agent support-bot", attributes={"gen_ai.operation.name": "invoke_agent"}
):
    with tracer.start_as_current_span(
        "chat gpt-4.1-mini",
        attributes={"gen_ai.operation.name": "chat", "gen_ai.request.model": "gpt-4.1-mini"},
    ):
        pass
    with tracer.start_as_current_span(
        "execute_tool search_orders",
        attributes={
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "search_orders",
            "gen_ai.tool.call.id": "call_1",
            "gen_ai.tool.type": "function",
            "gen_ai.tool.call.arguments": json.dumps(
                {"customer": "ada@example.com", "status": "open"}
            ),
            "gen_ai.tool.call.result": json.dumps({"orders": [{"id": "A-17", "total": 42.5}]}),
        },
    ):
        time.sleep(0.02)
    with tracer.start_as_current_span(
        "tools/call issue_refund",
        attributes={
            "mcp.method.name": "tools/call",
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "issue_refund",
            "jsonrpc.request.id": "7",
            "gen_ai.tool.call.arguments": json.dumps({"order_id": "A-17", "amount": 42.5}),
            "error.type": "tool_error",
        },
    ) as span:
        span.set_status(Status(StatusCode.ERROR, "Refund window has closed"))
        time.sleep(0.01)
    with tracer.start_as_current_span(
        "execute_tool send_email",
        attributes={
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "send_email",
            "gen_ai.tool.call.id": "call_3",
            "gen_ai.tool.call.arguments": json.dumps(
                {"to": "ada@example.com", "subject": "Your refund"}
            ),
        },
    ):
        pass

export = MessageToDict(encode_spans(exporter.get_finished_spans()))
print(json.dumps(export, indent=2))  # python make_otel_fixture.py > otel_genai_tool_spans.json
