"""
SiliconFlow AI客户端封装
支持 DeepSeek 和 Qwen 系列模型
使用流式模式彻底解决超时问题
"""

import json
import requests
import time
from typing import List, Dict, Optional, Generator
from pathlib import Path


class SiliconFlowClient:
    """SiliconFlow API客户端 - 流式版本"""

    MODEL_MAPPING = {
        "deepseek-chat": "deepseek-ai/DeepSeek-V3",
        "deepseek-v3": "deepseek-ai/DeepSeek-V3",
        "deepseek-reasoner": "deepseek-ai/DeepSeek-R1",
        "deepseek-r1": "deepseek-ai/DeepSeek-R1",
        "qwen-72b": "Qwen/Qwen2.5-72B-Instruct",
        "qwen-32b": "Qwen/Qwen2.5-32B-Instruct",
        "qwen-14b": "Qwen/Qwen2.5-14B-Instruct"
    }

    def __init__(self, api_key: str, model: str = "Qwen/Qwen2.5-72B-Instruct", base_url: str = "https://api.siliconflow.cn/v1"):
        self.api_key = api_key
        self.model = self._normalize_model_name(model)
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # 初始化时读取业务流程记忆（只读一次）
        self.business_flow = self._load_business_flow()
        if self.business_flow:
            print(f"[DEBUG] SiliconFlow 已加载业务流程记忆，共 {len(self.business_flow)} 字符")

    def _normalize_model_name(self, model: str) -> str:
        if "/" in model:
            return model
        return self.MODEL_MAPPING.get(model, "deepseek-ai/DeepSeek-V3")

    def chat_completion_stream(self, messages: List[Dict[str, str]], temperature: float = 0.3) -> str:
        """
        使用流式模式发送请求，彻底解决超时问题
        SiliconFlow官方推荐：非流式请求长输出容易504超时
        """
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": max(0.0, min(2.0, temperature)),
            "stream": True,  # 关键：启用流式模式
            "max_tokens": 4096
        }

        full_content = ""
        full_reasoning = ""

        try:
            # 使用流式请求，连接超时30秒，读取无限制（流式不会超时）
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                stream=True,  # 关键：requests流式模式
                timeout=(30, None)  # 连接超时30秒，读取无超时
            )

            if response.status_code != 200:
                error_detail = response.text[:500]
                raise Exception(f"API错误 {response.status_code}: {error_detail}")

            # 逐行读取流式响应
            for line in response.iter_lines():
                if not line:
                    continue

                line_str = line.decode('utf-8').strip()

                # 跳过SSE格式的前缀
                if line_str.startswith('data: '):
                    line_str = line_str[6:]

                # 结束标记
                if line_str == "[DONE]":
                    break

                if not line_str:
                    continue

                try:
                    chunk = json.loads(line_str)
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("delta", {})

                        # 提取内容
                        content = delta.get("content", "")
                        if content:
                            full_content += content

                        # 提取推理内容（DeepSeek R1）
                        reasoning = delta.get("reasoning_content", "")
                        if reasoning:
                            full_reasoning += reasoning

                except json.JSONDecodeError:
                    continue

            # 优先返回content，如果没有则返回reasoning
            return full_content if full_content else full_reasoning

        except requests.exceptions.ConnectionError as e:
            raise Exception(f"网络连接错误: {str(e)}")
        except Exception as e:
            raise Exception(f"流式请求失败: {str(e)}")

    def chat_completion_with_retry(self, messages: List[Dict[str, str]], temperature: float = 0.3, max_retries: int = 3) -> str:
        """带重试机制的流式请求"""
        for attempt in range(max_retries):
            try:
                return self.chat_completion_stream(messages, temperature)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"请求失败，{wait_time}秒后重试...")
                    time.sleep(wait_time)
                else:
                    raise Exception(f"请求失败，已重试{max_retries}次: {str(e)}")

    def generate_testcases_batch(self, test_points: List[Dict], style_examples: str, batch_size: int = 10) -> List[Dict]:
        """分批生成测试用例，使用流式模式"""
        all_testcases = []
        total_batches = (len(test_points) + batch_size - 1) // batch_size

        for i in range(0, len(test_points), batch_size):
            batch = test_points[i:i+batch_size]
            batch_text = self._format_test_points(batch)
            current_batch = i // batch_size + 1

            print(f"正在处理第 {current_batch}/{total_batches} 批，共 {len(batch)} 个测试点...")

            try:
                batch_cases = self._generate_single_batch(batch_text, style_examples)
                all_testcases.extend(batch_cases)
                print(f"  ✓ 本批生成 {len(batch_cases)} 条用例")

                # 批次间延迟，避免触发限流（SiliconFlow免费用户RPM较低）
                if i + batch_size < len(test_points):
                    time.sleep(2)

            except Exception as e:
                print(f"  ✗ 批次 {current_batch} 处理失败: {str(e)}")
                continue

        return all_testcases

    def _format_test_points(self, test_points: List[Dict]) -> str:
        """格式化测试点 - 明确标注叶子节点数量"""
        sections = []
        current_module = ""

        # 统计叶子节点数量
        leaf_count = sum(1 for p in test_points if p.get('is_leaf'))

        # 在开头明确告知叶子节点数量
        sections.append(f"【本批测试点共 {leaf_count} 个叶子节点(🍃标记)，必须生成 {leaf_count} 条用例】")

        for point in test_points:
            module = point.get('module', '')
            feature = point.get('feature', '')
            content = point.get('content', '')
            is_leaf = point.get('is_leaf', False)

            if module and module != current_module:
                current_module = module
                sections.append(f"\n【一级测试点: {current_module}】（所有用例的test_item必须是'{current_module}'）")

            leaf_mark = " 🍃" if is_leaf else ""
            if feature:
                sections.append(f"  - {feature}: {content}{leaf_mark}")
            else:
                sections.append(f"  - {content}{leaf_mark}")

        return "\n".join(sections)

    def _load_business_flow(self) -> str:
        """加载业务流程记忆文件"""
        memory_path = Path.home() / ".claude/projects/-Users-mac-PycharmProjects/memory/business_flow.md"
        if memory_path.exists():
            try:
                with open(memory_path, 'r') as f:
                    return f.read()
            except:
                pass
        return ""

    def _generate_single_batch(self, test_points_text: str, style_examples: str) -> List[Dict]:
        """生成单批测试用例"""
        # 使用初始化时加载的业务流程记忆（不再重复读取）
        business_flow = self.business_flow

        system_prompt = """你是测试用例生成专家。将测试点转为标准测试用例。

【绝对强制规则 - 违反即为错误】：
1. **叶子节点(🍃标记)数量 = 用例数量，必须100%转换，一条都不能少！**
   - 输入10个叶子节点，必须输出10条用例
   - 输入63个叶子节点，必须输出63条用例
2. **test_item必须等于一级测试点名称，禁止使用其他任何内容**
   - 一级测试点是"新客流程优化"，所有用例test_item只能写"新客流程优化"
   - 禁止使用二级、三级测试点作为test_item
3. **只输出纯JSON数组，禁止输出任何其他文字**
   - 禁止输出"根据测试点生成..."等开场白
   - 禁止输出"共X条"等统计文字
   - 直接以 [ 开头，以 ] 结尾
4. **测试步骤data字段处理**
   - 有数据时填写具体数据
   - 无数据时data字段留空字符串""，禁止写"无"

JSON格式（严格遵守）：
[
  {"test_item":"新客流程优化","title":"用例标题","priority":"高/中/低","precondition":"前置条件","steps":[{"step_no":1,"action":"操作","data":""}],"expected_result":"预期结果"}
]

立即输出JSON数组，不要任何开场白。"""

        # 构建完整prompt，注入业务流程
        if business_flow:
            user_prompt = f"""{system_prompt}

【业务流程参考】
{business_flow}

【历史风格参考】
{style_examples}

【待转化测试点】
{test_points_text}

请根据业务流程参考中的步骤规则生成测试用例，每个测试点对应一条用例，以JSON格式返回。"""
        else:
            user_prompt = f"""{system_prompt}

【历史风格参考】
{style_examples}

【待转化测试点】
{test_points_text}

请生成标准测试用例，以JSON格式返回。"""

        messages = [{"role": "user", "content": user_prompt}]

        response = self.chat_completion_with_retry(messages, temperature=0.3)
        return self._extract_json(response)

    def _extract_json(self, text: str) -> List[Dict]:
        """提取JSON"""
        import re

        text = text.strip()

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 从代码块提取
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'\[\s*\{[\s\S]*\}\s*\]'
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    json_str = match.group(1) if match.groups() else match.group(0)
                    return json.loads(json_str)
                except:
                    continue

        # 尝试方括号
        bracket_match = re.search(r'\[.*\]', text, re.DOTALL)
        if bracket_match:
            try:
                return json.loads(bracket_match.group(0))
            except:
                pass

        # 尝试花括号
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            try:
                data = json.loads(brace_match.group(0))
                return [data] if isinstance(data, dict) else data
            except:
                pass

        raise Exception(f"无法解析JSON，原始内容: {text[:500]}")