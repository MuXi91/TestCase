"""
Markdown格式测试点解析器
"""

import re
from pathlib import Path
from typing import List, Dict


class MarkdownParser:
    """Markdown测试点解析类"""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.content = ""

    def load(self):
        """加载Markdown文件"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")

        self.content = self.file_path.read_text(encoding='utf-8')
        return self

    def parse(self) -> List[Dict]:
        """
        解析测试点为结构化数据
        """
        if not self.content:
            self.load()

        test_points = []
        lines = self.content.split('\n')

        current_module = ""
        current_feature = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 判断标题层级
            if line.startswith('# '):
                current_module = line.replace('# ', '').strip()
                current_feature = ""

            elif line.startswith('## '):
                current_feature = line.replace('## ', '').strip()

            elif line.startswith('- ') or line.startswith('* ') or re.match(r'^\d+\.', line):
                # 测试点项
                content = re.sub(r'^[-*\d.]\s*', '', line).strip()
                if content:
                    test_points.append({
                        'module': current_module,
                        'feature': current_feature,
                        'content': content,
                        'level': self._get_level(line)
                    })

        return test_points

    def _get_level(self, line: str) -> int:
        """获取缩进层级"""
        if re.match(r'^\s{4,}', line):
            return 2
        elif re.match(r'^\s{2,}', line):
            return 1
        return 0

    def to_text(self) -> str:
        """转换为纯文本格式（兼容旧代码）"""
        points = self.parse()

        sections = []
        current_section = ""

        for point in points:
            if point['module'] != current_section:
                current_section = point['module']
                sections.append(f"\n【{current_section}】")
                if point['feature']:
                    sections.append(f"  - {point['feature']}")

            prefix = "    " if point['level'] > 0 else "  "
            sections.append(f"{prefix}- {point['content']}")

        return '\n'.join(sections)