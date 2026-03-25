# test_final.py
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QComboBox

from file_handler.xmind_parser import XMindParser


def test_parse(self):
    mode_select = QHBoxLayout()
    mode_select.addWidget(QLabel('类型:'))
    self.mode_select = QComboBox()
    self.mode_select.addItems([
        "活动",
        "个人中心",
        "battle",
        "treasure",
        "乐透",
        "bingo",
        "升级",
        "盒柜",
        "开盒",
        "充值送",
        "充值"
    ])

