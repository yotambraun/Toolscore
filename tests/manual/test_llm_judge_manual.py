"""Quick test script for LLM judge metrics."""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from toolscore.adapters.base import ToolCall
from toolscore.metrics.llm_judge import calculate_semantic_correctness

# Load API key from .env
from dotenv import load_dotenv
load_dotenv()

print("Testing LLM Judge Metrics...")
print("=" * 60)

# Test 1: Identical calls (should get ~1.0)
print("\n1. Testing identical calls:")
gold1 = [ToolCall(tool="search", args={"query": "Python programming"})]
trace1 = [ToolCall(tool="search", args={"query": "Python programming"})]

result1 = calculate_semantic_correctness(gold1, trace1)
print(f"   Score: {result1['semantic_score']:.2f}")
print(f"   Explanation: {result1['explanations'][0]}")

# Test 2: Similar but different naming (should get ~0.8-1.0)
print("\n2. Testing similar calls with different naming:")
gold2 = [ToolCall(tool="search_web", args={"query": "Python"})]
trace2 = [ToolCall(tool="web_search", args={"q": "Python"})]

result2 = calculate_semantic_correctness(gold2, trace2)
print(f"   Score: {result2['semantic_score']:.2f}")
print(f"   Explanation: {result2['explanations'][0]}")

# Test 3: Different intent (should get low score)
print("\n3. Testing completely different calls:")
gold3 = [ToolCall(tool="search", args={"query": "Python"})]
trace3 = [ToolCall(tool="delete_file", args={"filename": "test.txt"})]

result3 = calculate_semantic_correctness(gold3, trace3)
print(f"   Score: {result3['semantic_score']:.2f}")
print(f"   Explanation: {result3['explanations'][0]}")

print("\n" + "=" * 60)
print("✓ LLM Judge tests completed successfully!")
print(f"  Model used: {result1['model_used']}")
