"""媒体素材库共享层（阶段 1：仅放共享工具函数）

把 ``image_library`` 与 ``miniprogram_library`` 重复的工具函数集中到
``_utils``。两边 ``__init__.py`` 通过 backward-compat 别名 import，先消重，
不破坏既有 API / 测试。

后续规划（独立 PR）：
- 阶段 2：引入 ``media_library`` 表（``asset_type`` 区分 image / miniprogram_card），
  写路径双写半年
- 阶段 3：把读路径切到 ``media_library``，旧表只读

本模块当前不暴露公共 API；外部继续走 ``image_library`` / ``miniprogram_library``。
"""
from __future__ import annotations
