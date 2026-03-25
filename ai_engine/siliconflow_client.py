"""
SiliconFlow AI客户端封装
支持 DeepSeek 和 Qwen 系列模型
使用流式模式彻底解决超时问题
"""

import json
import requests
import time
from typing import List, Dict, Optional, Generator


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

    def generate_testcases_batch(self, test_points: List[Dict], style_examples: str, batch_size: int = 30) -> List[Dict]:
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
        """格式化测试点"""
        sections = []
        current_module = ""

        for point in test_points:
            module = point.get('module', '')
            feature = point.get('feature', '')
            content = point.get('content', '')

            if module and module != current_module:
                current_module = module
                sections.append(f"\n【{current_module}】")

            if feature:
                sections.append(f"  - {feature}: {content}")
            else:
                sections.append(f"  - {content}")

        return "\n".join(sections)

    def _generate_single_batch(self, test_points_text: str, style_examples: str) -> List[Dict]:
        """生成单批测试用例"""
        system_prompt = """你是一位资深软件测试专家，擅长将测试点转化为标准化的测试用例。
请严格按照以下要求生成测试用例（核心要求）：

1. 用例标题必须以动词开头，明确预期结果，示例：打开、点击、输入、选择、删除、修改、查询、提交、验证等，必须清晰描述操作对象 + 操作行为，必须隐含 / 明确体现测试目的，禁止模糊描述，长度控制在 5–50 字，简洁无歧义，禁止使用疑问、感叹、描述性语句（强制！！！）
2. 优先级分为：高（核心功能、主流程、必测场景、用户高频操作、影响主业务的功能）、中（重要功能、异常场景、边界值、必填项校验、提示信息）、低（UI 细节、边缘场景、极低频操作、非核心展示类内容）
3. 前置条件必须是可执行的具体状态描述，必须具体、明确，禁止模糊、空话，多条前置条件必须分条描述，无前置条件时统一填写：无
4. 测试步骤必须使用数字编号（1、2、3…），操作和数据分离，每一步只描述一个独立操作，步骤必须连贯、可复现
5. 预期结果必须是可验证的断言，必须与测试步骤一一对应，必须明确：页面 / 提示 / 数据 / 状态变化，禁止使用 “应该正常”“可以使用” 等模糊描述
6. XMind 中所有叶子节点测试点，必须 100% 转换为测试用例，不允许遗漏、合并、丢弃任何一条测试点，父节点作为【测试项】，子节点作为【用例内容】（最重要！！！）

一句话总结：工具必须把 XMind 里每一条测试点，精准、完整、不遗漏地转换成一条符合企业标准的、可直接执行的正式测试用例。

# 项目背景
项目主要业务是开盲盒，用户充值后选择喜欢的盒子进行开盒，开盒结果是根据算法概率来的；
其次还有很多小业务例如对战，用户选择盒子后付款然后选择和机器人或者真人进行对战，那方胜利可以对方开出的所有的物品加上胜利方开出的物品，输方将不会获得任何物品。项目主要应用市场在海外。

输出格式必须是JSON数组，每个元素包含：
{
    "test_item": "测试项",
    "title": "用例标题",
    "priority": "高/中/低",
    "precondition": "前置条件",
    "steps": [{"step_no": 1, "action": "操作", "data": "测试数据"}],
    "expected_result": "预期结果"
}

只输出JSON，不要任何解释文字。"""

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