"""Argument matcher objects for use inside expected-args dicts.

Matchers are placed as *values* inside the ``expected`` argument dicts passed
to :func:`toolscore.evaluate`.  They work via operator overloading:
``Matcher.__eq__(other)`` performs the match, so they compose transparently
with plain dict equality and with the argument-comparison logic in
:mod:`toolscore.metrics.arguments`.

Example::

    from toolscore import evaluate, ANY, Regex, Approx

    result = evaluate(
        expected=[{"tool": "get_weather", "args": {"city": Regex(r"NYC|JFK")}}],
        actual=[{"tool": "get_weather", "args": {"city": "NYC"}}],
    )
    assert result.argument_f1 == 1.0
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod


class Matcher(ABC):
    """Abstract base class for all argument matchers.

    Subclasses implement :meth:`matches` which is called by ``__eq__``.
    Because ``__eq__`` is overridden, ``__hash__`` must be explicitly
    preserved — we delegate to :meth:`object.__hash__` so matchers
    remain usable as dict keys / set members.
    """

    @abstractmethod
    def matches(self, value: object) -> bool:
        """Return True if *value* satisfies this matcher."""

    def __eq__(self, other: object) -> bool:
        return self.matches(other)

    # Explicitly preserve hash: overriding __eq__ would otherwise set it to
    # None (which breaks sets/dicts and makes mypy strict complain).
    __hash__ = object.__hash__

    @abstractmethod
    def __repr__(self) -> str: ...


# ---------------------------------------------------------------------------
# ANY singleton
# ---------------------------------------------------------------------------


class _AnyMatcher(Matcher):
    """Singleton matcher that matches any value."""

    _instance: _AnyMatcher | None = None

    def __new__(cls) -> _AnyMatcher:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def matches(self, value: object) -> bool:  # noqa: ARG002
        return True

    def __repr__(self) -> str:
        return "ANY"


ANY: _AnyMatcher = _AnyMatcher()
"""Module-level singleton; matches any value."""


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------


class Regex(Matcher):
    """Full-match a string against a regular expression pattern.

    Non-string values never match.

    Args:
        pattern: Regular expression pattern string.
        flags: Optional :mod:`re` flags (e.g. ``re.IGNORECASE``).
    """

    def __init__(self, pattern: str, flags: int = 0) -> None:
        self._pattern = pattern
        self._flags = flags
        self._compiled = re.compile(pattern, flags)

    def matches(self, value: object) -> bool:
        if not isinstance(value, str):
            return False
        return self._compiled.fullmatch(value) is not None

    def __repr__(self) -> str:
        if self._flags:
            return f"Regex({self._pattern!r}, flags={self._flags})"
        return f"Regex({self._pattern!r})"


# ---------------------------------------------------------------------------
# Approx
# ---------------------------------------------------------------------------


class Approx(Matcher):
    """Numeric closeness matcher (similar to ``pytest.approx`` semantics).

    Matches ``int`` and ``float`` values but explicitly excludes ``bool``
    (even though ``bool`` is a subclass of ``int`` in Python).

    The comparison uses the *larger* of the relative and absolute tolerances::

        |actual - expected| <= max(rel * |expected|, abs_tol)

    Args:
        value: The expected numeric value.
        rel: Relative tolerance (default 1e-6).
        abs: Absolute tolerance (default 0.0).
    """

    def __init__(self, value: float, rel: float = 1e-6, abs: float = 0.0) -> None:
        self._value = value
        self._rel = rel
        self._abs = abs

    def matches(self, value: object) -> bool:
        # Explicitly reject booleans (bool is a subclass of int)
        if isinstance(value, bool):
            return False
        if not isinstance(value, (int, float)):
            return False
        tolerance = max(self._rel * math.fabs(self._value), self._abs)
        return math.fabs(float(value) - float(self._value)) <= tolerance

    def __repr__(self) -> str:
        parts = [repr(self._value)]
        if self._rel != 1e-6:
            parts.append(f"rel={self._rel!r}")
        if self._abs != 0.0:
            parts.append(f"abs={self._abs!r}")
        return f"Approx({', '.join(parts)})"


# ---------------------------------------------------------------------------
# Contains
# ---------------------------------------------------------------------------


class Contains(Matcher):
    """Membership matcher: checks ``item in value``.

    Works for ``str``, ``list``, ``tuple``, ``set``, and ``dict`` (key
    membership for dicts).  Non-container types never match.

    Args:
        item: The item to look for inside the value.
    """

    def __init__(self, item: object) -> None:
        self._item = item

    def matches(self, value: object) -> bool:
        if not isinstance(value, (str, list, tuple, set, dict, frozenset)):
            return False
        try:
            return self._item in value
        except TypeError:
            return False

    def __repr__(self) -> str:
        return f"Contains({self._item!r})"


# ---------------------------------------------------------------------------
# OneOf
# ---------------------------------------------------------------------------


class OneOf(Matcher):
    """Value-is-one-of matcher.

    Checks whether *value* equals any of the provided *values*.  The
    comparison uses ``==`` so the provided values may themselves be
    :class:`Matcher` instances (their ``__eq__`` will be invoked).

    Args:
        *values: Candidate values (or Matchers) to test against.
    """

    def __init__(self, *values: object) -> None:
        self._values: tuple[object, ...] = values

    def matches(self, value: object) -> bool:
        # candidate == value triggers Matcher.__eq__ if candidate is a Matcher
        return any(candidate == value for candidate in self._values)

    def __repr__(self) -> str:
        inner = ", ".join(repr(v) for v in self._values)
        return f"OneOf({inner})"


# ---------------------------------------------------------------------------
# IsType
# ---------------------------------------------------------------------------


class IsType(Matcher):
    """Type-check matcher using :func:`isinstance`.

    .. note::
        ``IsType(int)`` does **not** match ``True`` or ``False`` even though
        ``bool`` is a subclass of ``int`` in Python.  This avoids a common
        footgun when you want to match plain integers but not accidental
        booleans.  Use ``IsType(bool)`` explicitly to match booleans.

    Args:
        *types: One or more types to check against.
    """

    def __init__(self, *types: type) -> None:
        self._types: tuple[type, ...] = types

    def matches(self, value: object) -> bool:
        # Special-case: if bool is not in the requested types, reject booleans
        # even though isinstance(True, int) is True.
        if isinstance(value, bool) and bool not in self._types:
            return False
        return isinstance(value, self._types)

    def __repr__(self) -> str:
        names = ", ".join(t.__name__ for t in self._types)
        return f"IsType({names})"


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------

__all__ = [
    "ANY",
    "Approx",
    "Contains",
    "IsType",
    "Matcher",
    "OneOf",
    "Regex",
]
