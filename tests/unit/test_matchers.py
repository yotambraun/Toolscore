"""Tests for toolscore.matchers — argument matcher objects."""

from __future__ import annotations

import re

import pytest

import toolscore
from toolscore import evaluate
from toolscore.matchers import ANY, Approx, Contains, IsType, Matcher, OneOf, Regex

# ---------------------------------------------------------------------------
# Matcher ABC
# ---------------------------------------------------------------------------


class TestMatcherABC:
    """Verify the ABC contract."""

    def test_any_is_matcher_instance(self) -> None:
        assert isinstance(ANY, Matcher)

    def test_regex_is_matcher_instance(self) -> None:
        assert isinstance(Regex("x"), Matcher)

    def test_approx_is_matcher_instance(self) -> None:
        assert isinstance(Approx(1.0), Matcher)

    def test_contains_is_matcher_instance(self) -> None:
        assert isinstance(Contains(1), Matcher)

    def test_oneof_is_matcher_instance(self) -> None:
        assert isinstance(OneOf(1, 2), Matcher)

    def test_istype_is_matcher_instance(self) -> None:
        assert isinstance(IsType(int), Matcher)

    def test_matchers_are_hashable(self) -> None:
        """Overriding __eq__ must not destroy hashability."""
        s: set[Matcher] = {ANY, Regex("x"), Approx(1.0), Contains("a"), OneOf(1), IsType(str)}
        assert len(s) == 6


# ---------------------------------------------------------------------------
# ANY
# ---------------------------------------------------------------------------


class TestAny:
    def test_matches_string(self) -> None:
        assert ANY.matches("hello")

    def test_matches_integer(self) -> None:
        assert ANY.matches(42)

    def test_matches_none(self) -> None:
        assert ANY.matches(None)

    def test_matches_list(self) -> None:
        assert ANY.matches([1, 2, 3])

    def test_matches_dict(self) -> None:
        assert ANY.matches({"key": "value"})

    def test_eq_semantics(self) -> None:
        """ANY == x must be True for any x (gold is on the left)."""
        assert ANY == "anything"
        assert ANY == 0
        assert ANY == None  # noqa: E711
        assert ANY == []

    def test_repr(self) -> None:
        assert repr(ANY) == "ANY"


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------


class TestRegex:
    def test_fullmatch_passes(self) -> None:
        assert Regex(r"NYC|JFK").matches("NYC")

    def test_partial_match_fails(self) -> None:
        """fullmatch requires the whole string — partial substring should fail."""
        assert not Regex(r"NYC").matches("fly to NYC today")

    def test_non_str_fails(self) -> None:
        assert not Regex(r"\d+").matches(123)

    def test_none_fails(self) -> None:
        assert not Regex(r".*").matches(None)

    def test_flags_ignorecase(self) -> None:
        assert Regex(r"hello", re.IGNORECASE).matches("HELLO")

    def test_flags_case_sensitive_by_default(self) -> None:
        assert not Regex(r"hello").matches("HELLO")

    def test_empty_string_matches_empty_pattern(self) -> None:
        assert Regex(r"").matches("")

    def test_repr(self) -> None:
        assert repr(Regex("NYC|JFK")) == "Regex('NYC|JFK')"

    def test_repr_with_flags(self) -> None:
        assert repr(Regex("x", re.IGNORECASE)) == f"Regex('x', flags={re.IGNORECASE})"

    def test_eq_semantics(self) -> None:
        r = Regex(r"NYC|JFK")
        assert r == "NYC"
        assert r == "JFK"
        assert r != "LAX"


# ---------------------------------------------------------------------------
# Approx
# ---------------------------------------------------------------------------


class TestApprox:
    def test_exact_match(self) -> None:
        assert Approx(1.0).matches(1.0)

    def test_within_rel_tolerance(self) -> None:
        assert Approx(100.0, rel=0.01).matches(100.5)

    def test_outside_rel_tolerance(self) -> None:
        assert not Approx(100.0, rel=0.001).matches(101.0)

    def test_abs_tolerance(self) -> None:
        assert Approx(0.0, abs=0.1).matches(0.05)

    def test_outside_abs_tolerance(self) -> None:
        assert not Approx(0.0, abs=0.1).matches(0.2)

    def test_int_value(self) -> None:
        assert Approx(1).matches(1)

    def test_int_actual(self) -> None:
        assert Approx(1.0).matches(1)

    def test_bool_not_matched(self) -> None:
        """Approx must NOT match booleans — True is int 1 but bool is excluded."""
        assert not Approx(1.0).matches(True)
        assert not Approx(0.0).matches(False)

    def test_string_fails(self) -> None:
        assert not Approx(1.0).matches("1.0")

    def test_none_fails(self) -> None:
        assert not Approx(1.0).matches(None)

    def test_repr(self) -> None:
        assert repr(Approx(1.0)) == "Approx(1.0)"

    def test_repr_with_rel(self) -> None:
        assert repr(Approx(1.0, rel=0.01)) == "Approx(1.0, rel=0.01)"

    def test_repr_with_abs(self) -> None:
        assert repr(Approx(1.0, abs=0.1)) == "Approx(1.0, abs=0.1)"

    def test_tolerance_boundary_inclusive(self) -> None:
        """Value exactly at boundary should match."""
        # rel=0.01 means |actual - 100| / 100 <= 0.01, i.e. 99..101
        assert Approx(100.0, rel=0.01).matches(101.0)

    def test_tolerance_boundary_exclusive(self) -> None:
        assert not Approx(100.0, rel=0.01).matches(101.001)


# ---------------------------------------------------------------------------
# Contains
# ---------------------------------------------------------------------------


class TestContains:
    def test_in_list(self) -> None:
        assert Contains(3).matches([1, 2, 3])

    def test_not_in_list(self) -> None:
        assert not Contains(4).matches([1, 2, 3])

    def test_in_tuple(self) -> None:
        assert Contains("b").matches(("a", "b", "c"))

    def test_in_set(self) -> None:
        assert Contains(7).matches({5, 6, 7})

    def test_in_dict_key(self) -> None:
        assert Contains("key").matches({"key": "value"})

    def test_not_in_dict_key(self) -> None:
        assert not Contains("missing").matches({"key": "value"})

    def test_substring_in_str(self) -> None:
        assert Contains("NYC").matches("fly to NYC today")

    def test_not_substring_in_str(self) -> None:
        assert not Contains("LAX").matches("fly to NYC today")

    def test_non_container_fails(self) -> None:
        assert not Contains(1).matches(42)

    def test_none_fails(self) -> None:
        assert not Contains(1).matches(None)

    def test_repr(self) -> None:
        assert repr(Contains("NYC")) == "Contains('NYC')"

    def test_repr_int(self) -> None:
        assert repr(Contains(3)) == "Contains(3)"

    def test_eq_semantics(self) -> None:
        c = Contains("NYC")
        assert c == "fly NYC home"
        assert c != "fly LAX home"


# ---------------------------------------------------------------------------
# OneOf
# ---------------------------------------------------------------------------


class TestOneOf:
    def test_matches_first(self) -> None:
        assert OneOf("a", "b", "c").matches("a")

    def test_matches_last(self) -> None:
        assert OneOf("a", "b", "c").matches("c")

    def test_no_match(self) -> None:
        assert not OneOf("a", "b").matches("c")

    def test_nested_matcher(self) -> None:
        """OneOf values may themselves be Matchers; match via == (i.e. Matcher.__eq__)."""
        m = OneOf(Regex(r"NYC|JFK"), Regex(r"LAX|SFO"))
        assert m.matches("NYC")
        assert m.matches("LAX")
        assert not m.matches("ORD")

    def test_nested_any(self) -> None:
        m = OneOf(ANY, "specific")
        assert m.matches("anything at all")

    def test_repr(self) -> None:
        assert repr(OneOf(1, 2, 3)) == "OneOf(1, 2, 3)"

    def test_repr_single(self) -> None:
        assert repr(OneOf("x")) == "OneOf('x')"

    def test_eq_semantics(self) -> None:
        o = OneOf("a", "b")
        assert o == "a"
        assert o != "c"


# ---------------------------------------------------------------------------
# IsType
# ---------------------------------------------------------------------------


class TestIsType:
    def test_str(self) -> None:
        assert IsType(str).matches("hello")

    def test_int(self) -> None:
        assert IsType(int).matches(42)

    def test_float(self) -> None:
        assert IsType(float).matches(3.14)

    def test_multiple_types(self) -> None:
        m = IsType(int, float)
        assert m.matches(1)
        assert m.matches(1.0)

    def test_wrong_type(self) -> None:
        assert not IsType(int).matches("hello")

    def test_bool_trap(self) -> None:
        """IsType(int) must NOT match True/False even though bool is a subclass of int."""
        assert not IsType(int).matches(True)
        assert not IsType(int).matches(False)

    def test_bool_matched_by_istype_bool(self) -> None:
        """IsType(bool) should match booleans."""
        assert IsType(bool).matches(True)
        assert IsType(bool).matches(False)

    def test_none_type(self) -> None:
        assert IsType(type(None)).matches(None)
        assert not IsType(type(None)).matches(0)

    def test_repr_single(self) -> None:
        assert repr(IsType(str)) == "IsType(str)"

    def test_repr_multiple(self) -> None:
        assert repr(IsType(int, float)) == "IsType(int, float)"

    def test_eq_semantics(self) -> None:
        t = IsType(str)
        assert t == "hello"
        assert t != 42


# ---------------------------------------------------------------------------
# End-to-end through evaluate()
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """Matchers working through evaluate() in both strict and lenient modes."""

    # -- ANY --

    def test_any_top_level_lenient(self) -> None:
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": ANY}}],
            actual=[{"tool": "search", "args": {"q": "NYC weather"}}],
        )
        assert result.argument_f1 == 1.0

    def test_any_top_level_strict(self) -> None:
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": ANY}}],
            actual=[{"tool": "search", "args": {"q": "NYC weather"}}],
            strict=True,
        )
        assert result.argument_f1 == 1.0

    def test_any_non_match_lowers_score(self) -> None:
        """Mismatched tool name should still lower score even with ANY in args."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": ANY}}],
            actual=[{"tool": "lookup", "args": {"q": "NYC weather"}}],
        )
        assert result.argument_f1 == 0.0  # call matched by position but tool differs

    # -- Regex --

    def test_regex_top_level_lenient(self) -> None:
        result = evaluate(
            expected=[{"tool": "get_weather", "args": {"city": Regex(r"NYC|JFK")}}],
            actual=[{"tool": "get_weather", "args": {"city": "NYC"}}],
        )
        assert result.argument_f1 == 1.0

    def test_regex_top_level_strict(self) -> None:
        result = evaluate(
            expected=[{"tool": "get_weather", "args": {"city": Regex(r"NYC|JFK")}}],
            actual=[{"tool": "get_weather", "args": {"city": "NYC"}}],
            strict=True,
        )
        assert result.argument_f1 == 1.0

    def test_regex_non_match_lowers_arg_f1(self) -> None:
        result = evaluate(
            expected=[{"tool": "get_weather", "args": {"city": Regex(r"NYC|JFK")}}],
            actual=[{"tool": "get_weather", "args": {"city": "LAX"}}],
        )
        assert result.argument_f1 < 1.0

    # -- Approx --

    def test_approx_top_level_lenient(self) -> None:
        result = evaluate(
            expected=[{"tool": "compute", "args": {"value": Approx(3.14, rel=0.01)}}],
            actual=[{"tool": "compute", "args": {"value": 3.14159}}],
        )
        assert result.argument_f1 == 1.0

    def test_approx_top_level_strict(self) -> None:
        result = evaluate(
            expected=[{"tool": "compute", "args": {"value": Approx(3.14, rel=0.01)}}],
            actual=[{"tool": "compute", "args": {"value": 3.14159}}],
            strict=True,
        )
        assert result.argument_f1 == 1.0

    # -- Nested inside dicts --

    def test_matcher_nested_in_dict(self) -> None:
        """Matchers nested inside dicts should work in strict mode (recursion)."""
        result = evaluate(
            expected=[
                {
                    "tool": "book_flight",
                    "args": {"destination": Regex(r"NYC|JFK"), "seats": Approx(2, abs=1)},
                }
            ],
            actual=[
                {
                    "tool": "book_flight",
                    "args": {"destination": "NYC", "seats": 2},
                }
            ],
            strict=True,
        )
        assert result.argument_f1 == 1.0

    def test_full_score_with_matchers(self) -> None:
        """result.score == 1.0 when all matchers pass."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": ANY, "limit": Approx(10, abs=5)}}],
            actual=[{"tool": "search", "args": {"q": "anything", "limit": 10}}],
        )
        assert result.score == pytest.approx(1.0, abs=0.01)

    def test_matchers_in_list_of_calls(self) -> None:
        """Matchers work across multiple calls."""
        result = evaluate(
            expected=[
                {"tool": "step1", "args": {"x": ANY}},
                {"tool": "step2", "args": {"y": Regex(r"\d+")}},
            ],
            actual=[
                {"tool": "step1", "args": {"x": "hello"}},
                {"tool": "step2", "args": {"y": "42"}},
            ],
        )
        assert result.argument_f1 == 1.0

    # -- trajectory / tool_correctness flow --

    def test_overall_score_perfect_with_matchers(self) -> None:
        """Trajectory and tool_correctness also flow through dict ==; verify score."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": ANY}}],
            actual=[{"tool": "search", "args": {"q": "some query"}}],
        )
        # selection, sequence should all be perfect
        assert result.selection_accuracy == 1.0
        assert result.sequence_accuracy == 1.0

    def test_contains_in_evaluate(self) -> None:
        result = evaluate(
            expected=[{"tool": "filter", "args": {"tags": Contains("urgent")}}],
            actual=[{"tool": "filter", "args": {"tags": ["urgent", "billing"]}}],
        )
        assert result.argument_f1 == 1.0

    def test_oneof_in_evaluate(self) -> None:
        result = evaluate(
            expected=[{"tool": "route", "args": {"method": OneOf("GET", "POST")}}],
            actual=[{"tool": "route", "args": {"method": "GET"}}],
        )
        assert result.argument_f1 == 1.0

    def test_istype_in_evaluate(self) -> None:
        result = evaluate(
            expected=[{"tool": "log", "args": {"level": IsType(int)}}],
            actual=[{"tool": "log", "args": {"level": 3}}],
        )
        assert result.argument_f1 == 1.0

    def test_istype_bool_trap_in_evaluate(self) -> None:
        """IsType(int) in evaluate should reject True."""
        result = evaluate(
            expected=[{"tool": "log", "args": {"level": IsType(int)}}],
            actual=[{"tool": "log", "args": {"level": True}}],
        )
        assert result.argument_f1 < 1.0


# ---------------------------------------------------------------------------
# Public API surface — importable from toolscore top-level
# ---------------------------------------------------------------------------


class TestPublicImports:
    def test_any_importable(self) -> None:
        assert toolscore.ANY is ANY

    def test_regex_importable(self) -> None:
        assert toolscore.Regex is Regex

    def test_approx_importable(self) -> None:
        assert toolscore.Approx is Approx

    def test_contains_importable(self) -> None:
        assert toolscore.Contains is Contains

    def test_oneof_importable(self) -> None:
        assert toolscore.OneOf is OneOf

    def test_istype_importable(self) -> None:
        assert toolscore.IsType is IsType

    def test_matcher_importable(self) -> None:
        assert toolscore.Matcher is Matcher
