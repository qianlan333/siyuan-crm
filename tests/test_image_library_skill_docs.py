"""image-library-curator Skill 文档的 contract 测试。

防止 SKILL.md / references / README.md 与代码漂移：
- SKILL.md frontmatter 形态正确
- SKILL.md 引用的 5 个 MCP 工具名跟 image_library/mcp_tools._TOOL_SPECS 一致
- SKILL.md / README 引用的 references/*.md 必须存在
- references 文件互引完整（SKILL.md 提到的 reference 都在）
"""
from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "image-library-curator"
SKILL_MD = SKILL_DIR / "SKILL.md"
README_MD = SKILL_DIR / "README.md"
REFERENCES_DIR = SKILL_DIR / "references"


@pytest.fixture(scope="module")
def skill_source() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def readme_source() -> str:
    return README_MD.read_text(encoding="utf-8")


# ---------- 文件存在 ---------- #

def test_skill_md_exists():
    assert SKILL_MD.exists(), f"SKILL.md missing at {SKILL_MD}"


def test_readme_exists():
    assert README_MD.exists()


def test_all_required_references_present():
    expected = {
        "system-prompt.md",
        "workflow-a-batch-annotate.md",
        "workflow-b-upload-annotate.md",
        "workflow-c-recommend.md",
    }
    actual = {p.name for p in REFERENCES_DIR.glob("*.md")}
    missing = expected - actual
    assert not missing, f"missing references: {missing}"


# ---------- frontmatter ---------- #

def test_skill_frontmatter_has_name_and_description(skill_source: str):
    """Claude Code Skill 要求顶部 yaml frontmatter 包含 name + description。"""
    assert skill_source.startswith("---\n"), "SKILL.md 必须以 yaml frontmatter 开头"
    head_end = skill_source.find("\n---\n", 4)
    assert head_end > 0, "frontmatter 必须用 --- 闭合"
    head = skill_source[4:head_end]
    assert "name: image-library-curator" in head
    # description 必须有触发场景关键词，以让 Claude 决定何时激活
    assert "description:" in head
    # 触发关键词覆盖三条工作流：description 必须含这些词，否则 Claude
    # 在用户提到这类需求时不会激活本 Skill
    for kw in ("打标", "推荐", "素材库"):
        assert kw in head, f"frontmatter description 缺关键词「{kw}」，会影响 Skill 触发准确率"


# ---------- 工具名同步 ---------- #

# 跟 mcp_tools._TOOL_SPECS 同步的硬编码列表 —— 改 mcp_tools 时本测试会强制
# 同步更新这里和 SKILL.md
EXPECTED_TOOLS = [
    "image_library_list",
    "image_library_get",
    "image_library_update_metadata",
    "image_library_upload",
    "image_library_facets",
]


def test_skill_md_mentions_all_mcp_tools(skill_source: str):
    """SKILL.md 必须把 5 个工具名都提到，让 Claude 知道有哪些工具可用。"""
    for tool in EXPECTED_TOOLS:
        assert tool in skill_source, f"SKILL.md 没提到 MCP 工具「{tool}」"


def test_skill_tools_match_mcp_tool_specs():
    """SKILL.md 提到的工具名必须跟 image_library.mcp_tools._TOOL_SPECS 完全对齐，
    防止文档和代码漂移。

    PR-C（mcp_tools 模块）合并前 import 会失败 — 此时 skip，等 PR-C 合并后这
    个测试自动激活，开始把关漂移问题。
    """
    try:
        from wecom_ability_service.domains.image_library.mcp_tools import (
            list_image_library_tool_specs,
        )
    except ImportError:
        pytest.skip(
            "image_library.mcp_tools 还没引入（PR-C 未合并）；本测试在 "
            "PR-C 合并后自动启用，验证 SKILL.md 和 _TOOL_SPECS 不漂移"
        )
    actual = {s["name"] for s in list_image_library_tool_specs()}
    expected = set(EXPECTED_TOOLS)
    assert actual == expected, (
        f"mcp_tools 注册了 {actual}，但 SKILL.md / 测试预期 {expected}。"
        "改了 mcp_tools 别忘了同步 SKILL.md 和本测试。"
    )


# ---------- 工作流引用完整 ---------- #

def test_skill_md_links_to_three_workflow_references(skill_source: str):
    """SKILL.md 必须把三条工作流的 reference 链都给到。"""
    assert "workflow-a-batch-annotate.md" in skill_source
    assert "workflow-b-upload-annotate.md" in skill_source
    assert "workflow-c-recommend.md" in skill_source


def test_skill_md_links_to_system_prompt(skill_source: str):
    """vision 输出约束的 reference 必须被引用，否则 Skill 不知道要按 schema 输出。"""
    assert "system-prompt.md" in skill_source


# ---------- README 内容 ---------- #

def test_readme_explains_mcp_json_config(readme_source: str):
    """README 必须教用户怎么配 .mcp.json 连 CRM。"""
    assert ".mcp.json" in readme_source
    assert "MCP_BEARER_TOKEN" in readme_source
    assert "/mcp" in readme_source


def test_readme_explains_install_path(readme_source: str):
    """README 必须告诉用户 Skill 装到哪。"""
    assert "~/.claude/skills/" in readme_source


# ---------- system-prompt 关键约束 ---------- #

def test_system_prompt_defines_json_schema_fields():
    sp = (REFERENCES_DIR / "system-prompt.md").read_text(encoding="utf-8")
    # 4 个核心字段都要有 schema 描述
    for field in ("description", "tags", "category", "ai_metadata"):
        assert field in sp, f"system-prompt 缺字段约束「{field}」"


def test_system_prompt_warns_against_token_blowup():
    """system-prompt 必须提醒"复用现有标签"避免造碎片化新词。"""
    sp = (REFERENCES_DIR / "system-prompt.md").read_text(encoding="utf-8")
    assert "facets" in sp.lower()
    assert "复用" in sp or "reuse" in sp.lower()


# ---------- 工作流文档关键步骤 ---------- #

def test_workflow_a_uses_overwrite_false_default():
    """批量打标必须默认 overwrite=false 保护人工编辑。"""
    wa = (REFERENCES_DIR / "workflow-a-batch-annotate.md").read_text(encoding="utf-8")
    assert "overwrite: false" in wa or "overwrite=false" in wa
    assert "image_library_update_metadata" in wa


def test_workflow_b_one_shot_upload():
    wb = (REFERENCES_DIR / "workflow-b-upload-annotate.md").read_text(encoding="utf-8")
    assert "image_library_upload" in wb
    assert "image_library_facets" in wb  # 上传前也要拉 facets


def test_workflow_c_uses_list_then_rerank():
    wc = (REFERENCES_DIR / "workflow-c-recommend.md").read_text(encoding="utf-8")
    assert "image_library_list" in wc
    # 不能直接对所有候选都拉 base64（贵）
    assert "with_data: true" in wc or "with_data=true" in wc
    # 应该用 with_data 只对 top 几张做二次确认，不对全部
    assert "top" in wc.lower()
