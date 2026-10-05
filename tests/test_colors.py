# -*- coding: utf-8 -*-
"""Colour codes.

A colour's hex is what the swatches everywhere are drawn from — the filter
sidebar, the product cards, the detail page. Two colours sharing a code look
identical on screen while reading as different in the list, which is how
"أخضر" and "اخضر فاتح" both ended up #16A34A: same colour, different case, no
way to tell them apart at a glance.
"""

import pytest

from utils.validation.color import validate_color_name


@pytest.fixture()
def existing(db_session):
    from models import Color

    colour = Color(name="أخضر", hex_code="#16A34A")
    db_session.add(colour)
    db_session.commit()
    return colour


class TestHexFormat:

    def test_accepts_a_plain_code(self, db_session):
        result = validate_color_name("بنفسجي", "#7C3AED")
        assert result.valid
        assert result.data["hex_code"] == "#7C3AED"

    def test_adds_a_missing_hash(self, db_session):
        # pasted codes often arrive bare
        result = validate_color_name("بنفسجي", "7C3AED")
        assert result.valid
        assert result.data["hex_code"] == "#7C3AED"

    def test_stores_one_case(self, db_session):
        """Lower and upper are the same colour; storing both is what let two
        identical greens look like two entries."""
        result = validate_color_name("بنفسجي", "#7c3aed")
        assert result.data["hex_code"] == "#7C3AED"

    @pytest.mark.parametrize("bad", ["#XYZ", "#12345", "#1234567", "red", "##123456"])
    def test_rejects_malformed(self, db_session, bad):
        assert not validate_color_name("لون", bad).valid

    def test_blank_is_allowed(self, db_session):
        # "غير محدد" legitimately has none
        result = validate_color_name("غير محدد", "")
        assert result.valid
        assert result.data["hex_code"] is None


class TestDuplicateCodes:

    def test_rejects_a_code_another_colour_uses(self, existing):
        result = validate_color_name("أخضر ثاني", "#16A34A")

        assert not result.valid
        assert "أخضر" in result.message

    def test_rejects_it_in_the_other_case_too(self, existing):
        assert not validate_color_name("أخضر ثاني", "#16a34a").valid

    def test_a_different_code_is_fine(self, existing):
        assert validate_color_name("اخضر فاتح", "#4ADE80").valid

    def test_a_colour_may_keep_its_own_code_when_edited(self, existing):
        result = validate_color_name(
            "أخضر غامق", "#16A34A", exclude_id=existing.id
        )
        assert result.valid


class TestDuplicateNames:
    """Already enforced; held down so the new code check does not displace it."""

    def test_rejects_the_same_name(self, existing):
        assert not validate_color_name("أخضر", "#111111").valid

    def test_rejects_a_spelling_variant(self, existing):
        # hamza and alef are the same name
        assert not validate_color_name("اخضر", "#222222").valid


class TestRoutes:

    def test_the_form_offers_both_inputs(self, make_user, login):
        body = login(make_user()).get("/add-color").get_data(as_text=True)

        assert 'id="newColorHex"' in body          # the picker
        assert 'id="newColorHexText"' in body      # the pasteable box
        # the text box is the one that submits
        assert 'name="hex_code"' in body

    def test_adding_a_colour_stores_the_upper_case_code(
        self, db_session, make_user, login
    ):
        from models import Color

        login(make_user()).post("/add-color", data={
            "name": "بنفسجي", "hex_code": "7c3aed",
        })

        colour = Color.query.filter_by(name="بنفسجي").one()
        assert colour.hex_code == "#7C3AED"

    def test_a_clashing_code_is_refused(self, existing, make_user, login):
        from models import Color

        login(make_user()).post("/add-color", data={
            "name": "أخضر ثالث", "hex_code": "#16a34a",
        })

        assert Color.query.filter_by(name="أخضر ثالث").first() is None


class TestLiveDataHasNoClashes:
    """The condition the clean-up established, as a standing check."""

    def test_no_two_colours_share_a_code(self, db_session):
        from models import Color

        colour_a = Color(name="لون أ", hex_code="#AABBCC")
        colour_b = Color(name="لون ب", hex_code="#DDEEFF")
        db_session.add_all([colour_a, colour_b])
        db_session.commit()

        codes = [c.hex_code for c in Color.query.all() if c.hex_code]
        assert len(codes) == len(set(codes))
