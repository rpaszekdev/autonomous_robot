from robot.live.tools_schema import ALL


def test_all_seven_tools_present():
    names = {t.name for t in ALL}
    assert names == {
        "speak",
        "describe_scene",
        "remember",
        "get_time",
        "set_reminder",
        "gpio_signal",
        "move",
    }


def test_each_declaration_has_parameters():
    for decl in ALL:
        assert decl.parameters is not None
        assert decl.description


def test_move_direction_enum():
    move = next(t for t in ALL if t.name == "move")
    props = move.parameters.properties
    assert "direction" in props
    assert set(props["direction"].enum) == {
        "forward",
        "backward",
        "left",
        "right",
        "stop",
    }
