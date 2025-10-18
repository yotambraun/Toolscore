# Example Datasets

This directory contains realistic gold standard examples for different types of LLM agents. Use these as templates for creating your own evaluation datasets.

## Available Datasets

### 1. Weather Agent (`weather_agent.json`)
**Use Case:** Simple weather lookup service
**Tools:** `get_current_weather`, `get_forecast`
**Complexity:** ⭐ Beginner
**Features:**
- Basic parameter validation
- Optional arguments
- Enum constraints for units

**Example Usage:**
```bash
toolscore eval examples/datasets/weather_agent.json your_trace.json
```

### 2. E-Commerce Agent (`ecommerce_agent.json`)
**Use Case:** Online shopping workflow
**Tools:** `search_products`, `get_product_details`, `add_to_cart`, `get_cart_total`, `checkout`
**Complexity:** ⭐⭐ Intermediate
**Features:**
- Multi-step workflow
- Number/price validation
- String length constraints
- Enum payment methods

**Example Usage:**
```bash
toolscore eval examples/datasets/ecommerce_agent.json your_trace.json --verbose
```

### 3. Code Assistant (`code_assistant.json`)
**Use Case:** Code search and editing
**Tools:** `search_code`, `read_file`, `edit_file`, `run_tests`
**Complexity:** ⭐⭐ Intermediate
**Features:**
- File path validation
- Line number ranges
- Pattern matching for code search
- Test execution validation

**Example Usage:**
```bash
toolscore eval examples/datasets/code_assistant.json your_trace.json --html report.html
```

### 4. RAG Agent (`rag_agent.json`)
**Use Case:** Retrieval Augmented Generation pipeline
**Tools:** `vector_search`, `rerank_results`, `generate_answer`, `cite_sources`
**Complexity:** ⭐⭐⭐ Advanced
**Features:**
- Vector search with thresholds
- Array validation for documents
- Token limits for generation
- Multi-stage retrieval workflow

**Example Usage:**
```bash
toolscore eval examples/datasets/rag_agent.json your_trace.json --llm-judge
```

### 5. Multi-Tool Agent (`multi_tool_agent.json`)
**Use Case:** Complex research and documentation workflow
**Tools:** `web_search`, `extract_text`, `summarize_text`, `create_file`, `send_email`
**Complexity:** ⭐⭐⭐ Advanced
**Features:**
- URL pattern validation
- Email format validation
- Side-effect checking (file creation)
- Multi-step dependencies

**Example Usage:**
```bash
toolscore eval examples/datasets/multi_tool_agent.json your_trace.json --verbose --llm-judge
```

## Schema Features Demonstrated

All datasets include schema validation examples:

- **Type Validation:** string, integer, number, boolean, array, object
- **Numeric Constraints:** minimum, maximum values
- **String Constraints:** minLength, maxLength, pattern (regex)
- **Enums:** Allowed value lists
- **Optional Parameters:** required: false
- **Side Effects:** file_exists, http_ok, sql_rows

## Creating Your Own Dataset

1. **Define Expected Tools:**
   ```json
   {
     "tool": "your_tool_name",
     "args": {"param1": "value1"},
     "description": "What this tool does"
   }
   ```

2. **Add Schema Validation (Optional):**
   ```json
   {
     "tool": "your_tool",
     "args": {"count": 5},
     "metadata": {
       "schema": {
         "count": {
           "type": "integer",
           "minimum": 1,
           "maximum": 100
         }
       }
     }
   }
   ```

3. **Add Side-Effect Checks (Optional):**
   ```json
   {
     "tool": "create_file",
     "args": {"path": "output.txt"},
     "metadata": {
       "side_effects": {
         "file_exists": "output.txt"
       }
     }
   }
   ```

## Tips for Effective Evaluation

1. **Start Simple:** Begin with `weather_agent.json` to understand the basics
2. **Add Schemas:** Use schema validation to catch type errors early
3. **Use LLM Judge:** Add `--llm-judge` flag for semantic matching (e.g., "search" vs "web_search")
4. **Test Incrementally:** Build up complexity gradually
5. **Document Intent:** Use `description` fields to explain why each tool is needed

## Need Help?

- See the [main README](../../README.md) for full documentation
- Check [TUTORIAL.md](../../TUTORIAL.md) for step-by-step guide
- View [examples/](../) for trace capture scripts
