"""Smoke tests for the MCP server tool surface.

These guard against tools silently dropping out of registration (e.g. a
decorator typo or an import error in a tool module) and keep the public
tool list in sync with the docs.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("fastmcp", reason="mcp extra not installed")

from mcp_server.server import mcp  # noqa: E402

EXPECTED_TOOLS = {
    "batch_diagrams",
    "batch_plots",
    "continue_diagram",
    "continue_plot",
    "continue_run",
    "download_references",
    "evaluate_diagram",
    "evaluate_plot",
    "generate_diagram",
    "generate_plot",
    "orchestrate_figures",
}


def _list_tools():
    return asyncio.run(mcp.list_tools())


def test_all_expected_tools_registered():
    names = {t.name for t in _list_tools()}
    missing = EXPECTED_TOOLS - names
    assert not missing, f"MCP tools missing from registration: {missing}"


def test_no_unexpected_tools():
    """New tools are welcome — add them to EXPECTED_TOOLS and the README."""
    names = {t.name for t in _list_tools()}
    unexpected = names - EXPECTED_TOOLS
    assert not unexpected, (
        f"New MCP tools {unexpected} — update EXPECTED_TOOLS, the server "
        "docstring, and the README MCP section together."
    )


def test_every_tool_has_description():
    undocumented = [t.name for t in _list_tools() if not (t.description or "").strip()]
    assert not undocumented, f"MCP tools without descriptions: {undocumented}"
