"""
测试用例生成器核心逻辑
支持分批处理避免超时
"""

from typing import List, Dict
from ai_engine.siliconflow_client import SiliconFlowClient
from file_handler import ExcelReader, MarkdownParser, XMindParser


class TestcaseGenerator:
    """测试用例生成器"""

    def __init__(self, ai_client: SiliconFlowClient):
        self.ai_client = ai_client
        self.style_samples = ""

    def learn_style(self, excel_path: str, sample_count: int = 10):
        """
        从历史用例学习风格

        Args:
            excel_path: 历史用例Excel路径
            sample_count: 学习样本数量
        """
        reader = ExcelReader(excel_path)
        self.style_samples = reader.extract_style_samples(max_samples=sample_count)
        return self

    def generate_from_markdown(self, md_path: str, batch_size: int = 3) -> List[Dict]:
        """
        从Markdown测试点生成用例

        Args:
            md_path: Markdown文件路径
            batch_size: 每批处理的测试点数量（建议3-5）

        Returns:
            生成的测试用例列表
        """
        parser = MarkdownParser(md_path)
        test_points = parser.parse()  # 获取结构化数据

        if not self.style_samples:
            raise ValueError("请先学习历史用例风格（调用learn_style方法）")

        print(f"共解析到 {len(test_points)} 个测试点，将分批次处理...")

        # 使用分批处理
        return self.ai_client.generate_testcases_batch(
            test_points,
            self.style_samples,
            batch_size=batch_size
        )

    def generate_from_xmind(self, xmind_path: str, batch_size: int = 3) -> List[Dict]:
        """
        从XMind测试点生成用例

        Args:
            xmind_path: XMind文件路径
            batch_size: 每批处理的测试点数量（建议3-5）

        Returns:
            生成的测试用例列表
        """
        parser = XMindParser(xmind_path)
        test_points = parser.parse()  # 获取结构化数据

        if not self.style_samples:
            raise ValueError("请先学习历史用例风格（调用learn_style方法）")

        print(f"共解析到 {len(test_points)} 个测试点，将分批次处理...")

        return self.ai_client.generate_testcases_batch(
            test_points,
            self.style_samples,
            batch_size=batch_size
        )