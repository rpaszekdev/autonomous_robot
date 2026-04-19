import asyncio

import pytest

from robot.live.dispatcher import ToolDispatcher


@pytest.mark.asyncio
async def test_dispatches_known_tool():
    async def echo(args: dict) -> dict:
        return {"ok": True, "args": args}

    dispatcher = ToolDispatcher({"echo": echo})
    result = await dispatcher("echo", {"x": 1})
    assert result == {"ok": True, "args": {"x": 1}}


@pytest.mark.asyncio
async def test_unknown_tool_returns_error():
    dispatcher = ToolDispatcher({})
    result = await dispatcher("nope", {})
    assert "error" in result


@pytest.mark.asyncio
async def test_handler_exception_is_captured():
    async def boom(_args):
        raise ValueError("kaboom")

    dispatcher = ToolDispatcher({"boom": boom})
    result = await dispatcher("boom", {})
    assert result == {"error": "kaboom"}
