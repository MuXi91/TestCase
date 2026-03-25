# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

测试点转测试用例工具 - A PyQt6 GUI application that converts test points (from Markdown or XMind files) into standardized test cases using AI (SiliconFlow API with DeepSeek/Qwen models).

## Commands

```bash
# Run the application
python main.py

# Install dependencies
pip install -r requirements.txt
```

## Architecture

```
main.py (PyQt6 GUI)
    ├── config.py - API key management (env var SILICONFLOW_API_KEY or ~/.zshrc SILICONFLOW_KEY)
    ├── ai_engine/siliconflow_client.py - Streaming API client with batch processing
    ├── generator/testcase_generator.py - Orchestrates parsing + AI generation
    ├── file_handler/
    │   ├── markdown_parser.py - Parse .md test points
    │   ├── xmind_parser.py - Parse .xmind files (JSON/XML formats)
    │   └── excel_reader.py - Extract style samples from historical test cases
    └── exporter/excel_exporter.py - Export test cases to .xlsx
```

## Key Data Flow

1. **Style Learning**: Historical Excel → `ExcelReader.extract_style_samples()` → style text
2. **Parse Test Points**: `.md` or `.xmind` file → Parser → `List[Dict]` with keys: `module`, `feature`, `content`, `level`
3. **Generate**: Test points + style samples → `SiliconFlowClient.generate_testcases_batch()` → JSON test cases
4. **Export**: `List[Dict]` test cases → `ExcelExporter.export()` → `.xlsx` file

## AI Client Notes

- Uses streaming mode (`stream=True`) to avoid 504 timeouts on long outputs
- Supports DeepSeek-V3, DeepSeek-R1, Qwen2.5-72B/32B/14B models
- Batch processing with `batch_size` parameter (default 30) to handle large test point sets
- Includes retry mechanism with exponential backoff

## Test Case Output Format

```json
{
    "test_item": "测试项",
    "title": "用例标题",
    "priority": "高/中/低",
    "precondition": "前置条件",
    "steps": [{"step_no": 1, "action": "操作", "data": "测试数据"}],
    "expected_result": "预期结果"
}
```