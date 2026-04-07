# CLAUDE.md
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
## 项目背景
测试点转测试用例工具 - 一个PyQt6 GUI应用程序，使用AI学习上传的历史测试用例风格，将测试点（来自Markdown或XMind文件）转换为标准化测试用例。
## 业务背景
hapa 是海外电商+游戏化网站，核心业务是神秘盒子随机开盒，用户支付购买盒子后随机获得物品。
主要玩法包括：开盒、upgrade（升级挑战）、battle（对战）、treasure hunting（寻宝）、bingo、daily lottery、活动等。
开盒获得的物品可回收换取金额或收下发货。
## 代码规范
变量 / 函数：蛇形命名
类：大驼峰
常量：全大写
缩进 4 空格
注释清晰、函数简短、不写重复代码
## 常用命令
python3 main.py
pip install -r requirements.txt
## 关键数据流
1. **Style Learning**: Historical Excel → `ExcelReader.extract_style_samples()` → style text
2. **Parse Test Points**: `.md` or `.xmind` file → Parser → `List[Dict]` with keys: `module`, `feature`, `content`, `level`
3. **Generate**: Test points + style samples → `SiliconFlowClient.generate_testcases_batch()` → JSON test cases
4. **Export**: `List[Dict]` test cases → `ExcelExporter.export()` → `.xlsx` file
