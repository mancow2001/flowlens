"""Unit tests for classification rule import/export helper functions."""

import pytest

from flowlens.api.routers.classification import _parse_is_internal, _export_is_internal


class TestParseIsInternal:
    """Test cases for _parse_is_internal helper function."""

    @pytest.mark.parametrize("value,expected", [
        # True cases
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("yes", True),
        ("Yes", True),
        ("YES", True),
        ("1", True),
        ("internal", True),
        ("Internal", True),
        ("INTERNAL", True),
        # False cases
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("no", False),
        ("No", False),
        ("NO", False),
        ("0", False),
        ("external", False),
        ("External", False),
        ("EXTERNAL", False),
        # None (Not Specified) cases
        ("", None),
        (None, None),
        ("none", None),
        ("None", None),
        ("NONE", None),
        ("null", None),
        ("Null", None),
        ("NULL", None),
        ("not specified", None),
        ("Not Specified", None),
        # Edge cases - unrecognized values default to None
        ("unknown", None),
        ("maybe", None),
        ("  ", None),  # whitespace only
    ])
    def test_parse_is_internal(self, value, expected):
        """Test that _parse_is_internal correctly parses various input values."""
        result = _parse_is_internal(value)
        assert result is expected, f"Expected {expected!r} for input {value!r}, got {result!r}"

    def test_parse_is_internal_with_whitespace(self):
        """Test that _parse_is_internal handles whitespace correctly."""
        assert _parse_is_internal("  true  ") is True
        assert _parse_is_internal("  false  ") is False
        assert _parse_is_internal("  internal  ") is True
        assert _parse_is_internal("  external  ") is False


class TestExportIsInternal:
    """Test cases for _export_is_internal helper function."""

    @pytest.mark.parametrize("value,expected", [
        (True, "true"),
        (False, "false"),
        (None, ""),
    ])
    def test_export_is_internal(self, value, expected):
        """Test that _export_is_internal correctly formats output values."""
        result = _export_is_internal(value)
        assert result == expected, f"Expected {expected!r} for input {value!r}, got {result!r}"


class TestRoundTrip:
    """Test that export and import round-trip correctly."""

    @pytest.mark.parametrize("original", [True, False, None])
    def test_export_import_roundtrip(self, original):
        """Test that values survive export/import round-trip."""
        exported = _export_is_internal(original)
        imported = _parse_is_internal(exported)
        assert imported is original, f"Round-trip failed: {original!r} -> {exported!r} -> {imported!r}"
