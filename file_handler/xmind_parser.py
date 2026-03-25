"""
XMind格式测试点解析器
支持 XMind 8 (content.xml) 和 XMind Zen/2026 (content.json) 两种格式
"""

import zipfile
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict


class XMindParser:
    """XMind测试点解析类 - 支持新旧两种格式"""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.content = None
        self.file_type = None  # 'xml' 或 'json'

    def load(self):
        """加载XMind文件，自动检测格式类型"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")

        # XMind文件是ZIP格式
        with zipfile.ZipFile(self.file_path, 'r') as zf:
            namelist = zf.namelist()

            # 检查是新版还是旧版
            if 'content.json' in namelist:
                # XMind Zen/2026 格式 (JSON)
                self.file_type = 'json'
                with zf.open('content.json') as f:
                    self.content = json.loads(f.read().decode('utf-8'))
            elif 'content.xml' in namelist:
                # XMind 8/Legacy 格式 (XML)
                self.file_type = 'xml'
                with zf.open('content.xml') as f:
                    self.content = f.read().decode('utf-8')
            else:
                raise ValueError(f"无法识别的XMind文件格式，文件内容: {namelist}")

        return self

    def parse(self) -> List[Dict]:
        """
        解析测试点为结构化数据
        自动根据文件类型选择解析方式
        """
        if self.content is None:
            self.load()

        if self.file_type == 'json':
            return self._parse_json()
        else:
            return self._parse_xml()

    def _parse_json(self) -> List[Dict]:
        """解析XMind Zen/2026 (JSON格式)"""
        test_points = []

        # JSON格式可能有多个canvas/sheet
        if isinstance(self.content, list) and len(self.content) > 0:
            root_sheet = self.content[0]
        elif isinstance(self.content, dict):
            root_sheet = self.content
        else:
            return test_points

        # 获取rootTopic
        root_topic = root_sheet.get('rootTopic', {})
        if not root_topic:
            return test_points

        # 递归解析
        self._traverse_json_topic(root_topic, test_points, level=0)
        return test_points

    def _traverse_json_topic(self, topic: Dict, points: List[Dict], level: int, parent_module: str = ""):
        """递归遍历JSON格式的topic"""
        if not topic:
            return

        title = topic.get('title', '')
        if not title:
            return

        # 判断层级
        if level == 0:
            module = title
            feature = ""
        elif level == 1:
            module = parent_module
            feature = title
        else:
            # 作为测试点内容
            points.append({
                'module': parent_module,
                'feature': '',
                'content': title,
                'level': level - 1
            })
            module = parent_module
            feature = ""

        # 递归子主题
        children = topic.get('children', {}).get('attached', [])
        for child in children:
            self._traverse_json_topic(child, points, level + 1, module if level == 0 else parent_module)

    def _parse_xml(self) -> List[Dict]:
        """解析XMind 8/Legacy (XML格式)"""
        test_points = []

        root = ET.fromstring(self.content)

        # 定义命名空间
        ns = {
            'xmind': 'http://www.xmind.org/xmind/2.0/'
        }

        # 找到第一个sheet的root topic
        sheet = root.find('.//xmind:sheet', ns)
        if sheet is None:
            # 尝试不带命名空间
            sheet = root.find('.//sheet')

        if sheet is not None:
            root_topic = sheet.find('.//xmind:topic', ns)
            if root_topic is None:
                root_topic = sheet.find('.//topic')
        else:
            # 直接找topic
            root_topic = root.find('.//xmind:topic', ns)
            if root_topic is None:
                root_topic = root.find('.//topic')

        if root_topic is not None:
            self._traverse_xml_topic(root_topic, test_points, level=0)

        return test_points

    def _traverse_xml_topic(self, topic, points: List[Dict], level: int, parent_module: str = ""):
        """递归遍历XML格式的topic"""
        if topic is None:
            return

        # 尝试带命名空间和不带命名空间的方式
        title_elem = topic.find('.//xmind:title', {'xmind': 'http://www.xmind.org/xmind/2.0/'})
        if title_elem is None:
            title_elem = topic.find('title')

        if title_elem is None:
            return

        title = title_elem.text or ""
        if not title:
            return

        # 判断层级
        if level == 0:
            module = title
            feature = ""
        elif level == 1:
            module = parent_module
            feature = title
        else:
            # 作为测试点内容
            points.append({
                'module': parent_module,
                'feature': '',
                'content': title,
                'level': level - 1
            })
            module = parent_module
            feature = ""

        # 递归子主题 - 尝试多种方式查找
        ns = {'xmind': 'http://www.xmind.org/xmind/2.0/'}
        children = topic.findall('.//xmind:topic', ns)
        if not children:
            children = topic.findall('topic')

        for child in children:
            self._traverse_xml_topic(child, points, level + 1, module if level == 0 else parent_module)

    def to_text(self) -> str:
        """转换为纯文本格式"""
        points = self.parse()

        if not points:
            return "未解析到任何测试点"

        sections = []
        current_module = ""

        for point in points:
            if point['module'] != current_module:
                current_module = point['module']
                sections.append(f"\n【{current_module}】")

            indent = "  " * point['level']
            sections.append(f"{indent}- {point['content']}")

        return "\n".join(sections)