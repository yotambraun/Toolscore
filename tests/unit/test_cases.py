"""Tests for the @toolscore.cases() parametrize decorator."""

import toolscore


class TestCases:
    """Tests for cases()."""

    def test_cases_basic(self):
        """Decorator produces correct pytest.mark.parametrize."""
        decorator = toolscore.cases([
            {"input": "weather NYC", "expected": [{"tool": "get_weather"}]},
            {"input": "email bob", "expected": [{"tool": "send_email"}]},
        ])
        # The decorator is a pytest.mark.parametrize instance
        assert hasattr(decorator, "args")
        # Check parameter names
        assert decorator.args[0] == ["input", "expected"]
        # Check values
        assert len(decorator.args[1]) == 2
        assert decorator.args[1][0] == ("weather NYC", [{"tool": "get_weather"}])
        assert decorator.args[1][1] == ("email bob", [{"tool": "send_email"}])

    def test_cases_custom_id_key(self):
        """id_key parameter controls which key is used for test IDs."""
        decorator = toolscore.cases(
            [
                {"name": "tc1", "input": "a", "expected": []},
                {"name": "tc2", "input": "b", "expected": []},
            ],
            id_key="name",
        )
        # Check that IDs are set from the 'name' key
        assert decorator.kwargs.get("ids") == ["tc1", "tc2"]

    def test_cases_default_id_key(self):
        """Default id_key='input' is used for test IDs."""
        decorator = toolscore.cases([
            {"input": "hello", "expected": []},
            {"input": "world", "expected": []},
        ])
        assert decorator.kwargs.get("ids") == ["hello", "world"]
