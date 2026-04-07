"""
Claude CLI客户端封装
通过调用本地 Claude Code 命令实现会话记忆功能
"""

import json
import subprocess
import time
import sys
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Callable
from datetime import datetime


def load_claude_config_from_zshrc() -> dict:
    """
    从 ~/.zshrc 读取 Claude 配置
    返回: {"base_url": "...", "token": "..."}
    """
    config = {"base_url": None, "token": None}

    zshrc_path = Path.home() / ".zshrc"
    if not zshrc_path.exists():
        return config

    try:
        with open(zshrc_path, 'r') as f:
            content = f.read()

        # 匹配 AI_BASE_URL="xxx" 或 export AI_BASE_URL="xxx"
        base_url_match = re.search(r'(?:export\s+)?AI_BASE_URL\s*=\s*["\']([^"\']+)["\']', content)
        if base_url_match:
            config["base_url"] = base_url_match.group(1)

        # 匹配 AI_TOKEN="xxx"
        token_match = re.search(r'(?:export\s+)?AI_TOKEN\s*=\s*["\']([^"\']+)["\']', content)
        if token_match:
            config["token"] = token_match.group(1)

    except Exception as e:
        print(f"[DEBUG] 读取 zshrc 失败: {e}")

    return config


class ClaudeCLIClient:
    """Claude CLI客户端 - 支持会话记忆"""

    # 支持的模型列表
    SUPPORTED_MODELS = [
        "glm-5",
        "kimi-k2.5",
        "claude-opus-4-6",
        "claude-sonnet-4-6"
    ]

    def __init__(self, session_dir: str = "~/.claude/sessions", progress_callback: Optional[Callable[[str], None]] = None, model: str = "glm-5"):
        self.session_dir = Path(session_dir).expanduser()
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.session_dir / "testcase_session.json"
        self.session_id: Optional[str] = None
        self.progress_callback = progress_callback  # 进度回调函数（注意：仅在主线程安全）
        self.model = model  # 默认使用 glm-5
        self._is_main_thread = True  # 标记是否在主线程

        # 从 ~/.zshrc 加载配置
        self.config = load_claude_config_from_zshrc()
        print(f"[DEBUG] 从 zshrc 加载配置: base_url={self.config['base_url']}, token={self.config['token'][:10] if self.config['token'] else 'None'}...")

        # 初始化时读取业务流程记忆（只读一次）
        self.business_flow = self._load_business_flow()
        if self.business_flow:
            print(f"[DEBUG] 已加载业务流程记忆，共 {len(self.business_flow)} 字符")

        self._load_session()

    def _report_progress(self, message: str):
        """报告进度信息 - 线程安全版本"""
        # 打印到控制台（线程安全）
        print(message)
        sys.stdout.flush()

        # 注意：不要在子线程中调用 progress_callback
        # PyQt UI 更新必须在主线程进行
        # GeneratorThread 通过 signal 机制安全地更新 UI

    def _load_session(self) -> dict:
        """从session_file加载会话信息"""
        if self.session_file.exists():
            try:
                with open(self.session_file, 'r') as f:
                    data = json.load(f)
                    self.session_id = data.get("session_id")
                    return data
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_session(self, session_id: str):
        """保存会话ID到session_file"""
        data = {
            "session_id": session_id,
            "last_active": datetime.now().isoformat()
        }
        with open(self.session_file, 'w') as f:
            json.dump(data, f, indent=2)
        self.session_id = session_id

    def test_connection(self) -> tuple[bool, str]:
        """
        测试Claude CLI连接是否正常
        返回: (是否成功, 消息)
        """
        import os

        cmd = [
            "claude",
            "--model", self.model,
            "-p", "OK",
            "--output-format", "stream-json",
            "--verbose"
        ]

        env = os.environ.copy()
        # 使用从 zshrc 加载的配置
        if self.config.get("base_url"):
            env["ANTHROPIC_BASE_URL"] = self.config["base_url"]
        if self.config.get("token"):
            env["ANTHROPIC_AUTH_TOKEN"] = self.config["token"]

        print(f"[DEBUG] 测试连接命令: {' '.join(cmd)}")
        print(f"[DEBUG] 环境变量: ANTHROPIC_BASE_URL={env.get('ANTHROPIC_BASE_URL')}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                stdin=subprocess.DEVNULL,  # 不等待stdin输入
                timeout=120  # 增加到120秒超时
            )

            print(f"[DEBUG] 返回码: {result.returncode}")
            print(f"[DEBUG] stdout长度: {len(result.stdout)}")
            print(f"[DEBUG] stderr: {result.stderr[:200] if result.stderr else 'None'}")

            output = result.stdout

            # 检查是否有有效响应（即使返回码为1，stdout有内容也视为成功）
            if output and ('"type":"system"' in output or '"type":"result"' in output or '"type":"assistant"' in output):
                # 解析获取 session_id（可选，不保存）
                for line in output.strip().split('\n'):
                    try:
                        data = json.loads(line)
                        if data.get("type") == "result":
                            if not data.get("is_error"):
                                return True, f"连接成功 (模型: {self.model})"
                            else:
                                return False, f"API错误: {data.get('result', '')[:100]}"
                    except:
                        pass
                return True, f"连接成功 (模型: {self.model})"

            if result.returncode != 0:
                return False, f"Claude CLI 返回错误: {result.stderr[:200] if result.stderr else '未知错误'}"

            return False, f"响应格式异常: {output[:200] if output else '无输出'}"

        except subprocess.TimeoutExpired:
            return False, "连接超时 (120秒)，请检查网络或代理服务"
        except FileNotFoundError:
            return False, "未找到 claude 命令"
        except Exception as e:
            return False, f"异常: {str(e)}"

    def _call_claude_cli(self, prompt: str) -> str:
        """
        调用claude命令 - 简单可靠版本
        注意：每次都创建新会话，不使用 --resume
        因为测试用例生成不需要记住之前的对话上下文
        """
        import os

        # 始终使用新会话，指定模型
        cmd = ["claude", "--model", self.model]

        cmd.extend([
            "-p", prompt,
            "--output-format", "stream-json",
            "--verbose"
        ])

        self._report_progress(f"调用 Claude CLI (模型: {self.model})...")

        env = os.environ.copy()
        # 使用从 zshrc 加载的配置
        if self.config.get("base_url"):
            env["ANTHROPIC_BASE_URL"] = self.config["base_url"]
        if self.config.get("token"):
            env["ANTHROPIC_AUTH_TOKEN"] = self.config["token"]

        print(f"[DEBUG] _call_claude_cli 环境变量: ANTHROPIC_BASE_URL={env.get('ANTHROPIC_BASE_URL')}")

        try:
            # 使用 run 方法，设置足够长的超时
            self._report_progress(f"  等待响应...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                stdin=subprocess.DEVNULL,  # 不等待stdin输入
                timeout=300  # 5分钟总超时
            )

            self._report_progress(f"  CLI返回码: {result.returncode}")

            output = result.stdout

            # 即使返回码不为0，也先检查是否有有效输出
            # --resume 时可能返回码为1但stdout仍有内容
            if output and ('"type":"system"' in output or '"type":"assistant"' in output or '"type":"result"' in output):
                self._report_progress(f"  收到响应，正在解析...")
            elif result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "返回码非0但无stderr"
                self._report_progress(f"  ✗ 错误: {error_msg[:200]}")
                raise Exception(f"Claude CLI 错误: {error_msg}")
            elif not output:
                raise Exception("无输出")

            # 解析输出
            full_content = ""
            session_id = None

            for line in output.strip().split('\n'):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    msg_type = data.get("type", "unknown")

                    if "session_id" in data:
                        session_id = data["session_id"]

                    if msg_type == "assistant":
                        message = data.get("message", {})
                        content_blocks = message.get("content", [])
                        for block in content_blocks:
                            if isinstance(block, dict) and block.get("type") == "text":
                                full_content += block.get("text", "")

                    elif msg_type == "result":
                        if data.get("is_error"):
                            error_msg = data.get("result", "")
                            raise Exception(f"API错误: {error_msg}")

                except json.JSONDecodeError:
                    if line and not line.startswith('{'):
                        full_content += line

            # 保存 session_id
            if session_id:
                self._save_session(session_id)

            self._report_progress(f"  解析完成，共 {len(full_content)} 字符")

            # 限制响应大小，防止内存溢出
            if len(full_content) > 100000:
                self._report_progress(f"  ⚠️ 响应过大，截断到100KB")
                full_content = full_content[:100000]

            return full_content

        except subprocess.TimeoutExpired:
            self._report_progress(f"  ✗ 请求超时 (5分钟)")
            raise Exception("请求超时 (5分钟)")
        except FileNotFoundError:
            self._report_progress(f"  ✗ 未找到 claude 命令")
            raise Exception("未找到 claude 命令")
        except MemoryError:
            self._report_progress(f"  ✗ 内存不足")
            raise Exception("内存不足，请减少批次大小")
        except Exception as e:
            self._report_progress(f"  ✗ 调用异常: {str(e)}")
            if "Claude CLI" in str(e) or "API错误" in str(e) or "请求超时" in str(e) or "内存不足" in str(e):
                raise
            raise Exception(f"调用失败: {str(e)}")

    def generate_testcases_batch(self, test_points: List[Dict], style_examples: str, batch_size: int = 10) -> List[Dict]:
        """分批生成测试用例"""
        all_testcases = []
        total_batches = (len(test_points) + batch_size - 1) // batch_size

        self._report_progress(f"========== 开始生成测试用例 ==========")
        self._report_progress(f"共 {len(test_points)} 个测试点，分 {total_batches} 批处理")

        for i in range(0, len(test_points), batch_size):
            batch = test_points[i:i+batch_size]
            batch_text = self._format_test_points(batch)
            current_batch = i // batch_size + 1

            self._report_progress(f"")
            self._report_progress(f"【批次 {current_batch}/{total_batches}】处理 {len(batch)} 个测试点...")

            try:
                batch_cases = self._generate_single_batch(batch_text, style_examples)
                all_testcases.extend(batch_cases)
                self._report_progress(f"  ✓ 本批生成 {len(batch_cases)} 条用例")

                # 批次间延迟
                if i + batch_size < len(test_points):
                    self._report_progress(f"  等待 1 秒后继续...")
                    time.sleep(1)

            except Exception as e:
                self._report_progress(f"  ✗ 批次 {current_batch} 处理失败: {str(e)}")
                import traceback
                self._report_progress(f"  错误堆栈: {traceback.format_exc()[:500]}")
                continue

        self._report_progress(f"")
        self._report_progress(f"========== 生成完成 ==========")
        self._report_progress(f"总计生成 {len(all_testcases)} 条测试用例")

        # 强制垃圾回收
        import gc
        gc.collect()
        sys.stdout.flush()

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
1. 叶子节点(🍃标记)数量 = 用例数量，必须100%转换，一条都不能少！
2. 只输出纯JSON数组，禁止输出任何其他文字
3. 测试步骤data字段：无数据时留空字符串
4. 优先级根据我的规定来，不要把UI上的模块位置或者文案设置为高或中

JSON格式：
[{"test_item":"一级测试点","title":"用例标题","priority":"高/中/低","precondition":"前置条件","steps":[{"step_no":1,"action":"操作","data":""}],"expected_result":"预期结果"}]

立即输出JSON数组。"""

        # 构建完整prompt，注入业务流程
        if business_flow:
            prompt = f"""{system_prompt}

【业务流程参考】
{business_flow}

【风格参考】
{style_examples}

【测试点】
{test_points_text}

请根据业务流程参考中的步骤规则生成测试用例，每个测试点对应一条用例，输出JSON数组。"""
        else:
            prompt = f"""{system_prompt}

【风格参考】
{style_examples}

【测试点】
{test_points_text}

输出JSON数组。"""

        response = self._call_claude_cli(prompt)
        return self._extract_json(response)

    def _extract_json(self, text: str) -> List[Dict]:
        """提取JSON"""
        import re
        import gc

        self._report_progress(f"  正在解析JSON响应...")

        # 限制文本大小
        if len(text) > 100000:
            self._report_progress(f"  ⚠️ 响应文本过大({len(text)}字符)，截断处理")
            text = text[:100000]

        text = text.strip()

        # 尝试直接解析
        try:
            result = json.loads(text)
            self._report_progress(f"  ✓ JSON解析成功，提取到 {len(result)} 条用例")
            gc.collect()  # 强制垃圾回收
            return result
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
                    result = json.loads(json_str)
                    self._report_progress(f"  ✓ 从代码块提取JSON成功")
                    return result
                except:
                    continue

        # 尝试方括号
        bracket_match = re.search(r'\[.*\]', text, re.DOTALL)
        if bracket_match:
            try:
                result = json.loads(bracket_match.group(0))
                self._report_progress(f"  ✓ 从方括号提取JSON成功")
                return result
            except:
                pass

        # 尝试花括号
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            try:
                data = json.loads(brace_match.group(0))
                result = [data] if isinstance(data, dict) else data
                self._report_progress(f"  ✓ 从花括号提取JSON成功")
                return result
            except:
                pass

        self._report_progress(f"  ✗ JSON解析失败")
        self._report_progress(f"  响应内容前500字符: {text[:500]}")
        raise Exception(f"无法解析JSON，原始内容: {text[:500]}")