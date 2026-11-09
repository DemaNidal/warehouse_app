# -*- coding: utf-8 -*-
"""Which colour an Arabic colour name means.

The names and the matching rule used to live in base.html as a JavaScript
object, next to a second hand-written copy of the Arabic normaliser. Besides
being two copies of one thing, the rule itself was wrong twice over:

  * it walked the names in definition order and stopped at the first hit, so
    the broad colour always won over the one that narrows it — Arabic puts
    the qualifier second, so "اخضر زيتي" came back as grass green;
  * it asked whether a name appeared anywhere in the text, so "لبني" matched
    "بني" and was suggested as brown.

Six of the twelve ordinary names below used to come back wrong.
"""

import pytest

from models import Color
from utils.color_names import COLOR_NAME_HEX, EMPTY_SWATCH, suggest_hex, swatch


class TestTheQualifierWins:
    """The last recognised word decides, not the first."""

    @pytest.mark.parametrize("name,expected", [
        ("اخضر زيتي", "#6B7C3A"),     # olive, not grass green
        ("ازرق سماوي", "#38BDF8"),    # sky, not royal blue
        ("بني نحاسي", "#B87333"),     # copper, not brown
        ("احمر عنابي", "#7C1F2E"),    # maroon, not red
        ("اصفر ليموني", "#D9E021"),   # lemon, not plain yellow
    ])
    def test_the_narrowing_word_decides(self, name, expected):
        assert suggest_hex(name) == expected

    def test_an_unknown_qualifier_leaves_the_base_colour(self):
        # "فاتح" is not a colour of its own, so the blue stands
        assert suggest_hex("ازرق فاتح") == "#2563EB"
        assert suggest_hex("أبيض حليبي") == "#F8FAFC"

    def test_a_plain_name_still_works(self):
        assert suggest_hex("ابيض") == "#F8FAFC"
        assert suggest_hex("اسود") == "#111827"


class TestSpellingDoesNotMatter:

    @pytest.mark.parametrize("spelling", ["أحمر", "احمر", "إحمر", "آحمر"])
    def test_every_hamza_folds_onto_one_colour(self, spelling):
        assert suggest_hex(spelling) == "#DC2626"

    def test_extra_spacing_is_ignored(self):
        assert suggest_hex("   اخضر    زيتي  ") == "#6B7C3A"


class TestWholeWordsOnly:

    def test_a_name_that_merely_contains_another_is_not_matched(self):
        # "لبني" contains "بني" and used to be suggested as brown
        assert suggest_hex("لبني") is None

    def test_an_unknown_name_suggests_nothing(self):
        assert suggest_hex("شي مش لون") is None
        assert suggest_hex("") is None
        assert suggest_hex(None) is None

    def test_no_suggestion_beats_a_wrong_one(self):
        # the suggestion writes itself into the field, so silence is the
        # safe answer when nothing is recognised
        assert suggest_hex("كلمة غريبة") is None


class TestEveryNameMapsToARealColour:

    def test_all_keys_are_already_normalised(self):
        from utils.categorization import normalize

        for name in COLOR_NAME_HEX:
            assert normalize(name) == name, f"«{name}» مش مكتوب بالصيغة الموحّدة"

    def test_all_values_are_six_digit_hex(self):
        import re

        for name, value in COLOR_NAME_HEX.items():
            assert re.fullmatch(r"#[0-9A-F]{6}", value), f"{name}: {value}"


class TestTheEmptySwatch:

    def test_a_colour_with_no_code_gets_the_one_grey(self):
        assert swatch(None) == EMPTY_SWATCH
        assert swatch("") == EMPTY_SWATCH
        assert swatch("   ") == EMPTY_SWATCH

    def test_a_real_code_is_left_alone(self):
        assert swatch("#1E3A5F") == "#1E3A5F"

    def test_the_filter_is_registered_for_templates(self, app):
        assert "swatch" in app.jinja_env.filters
        assert app.jinja_env.filters["swatch"](None) == EMPTY_SWATCH

    def test_templates_can_read_the_default(self, app, client):
        with app.test_request_context("/"):
            rendered = app.jinja_env.from_string(
                "{{ nothing|swatch }}"
            ).render(nothing=None)

        assert rendered == EMPTY_SWATCH


class TestTheSuggestionEndpoint:

    def test_it_answers_with_the_qualifier_colour(
        self, client, login, make_user
    ):
        login(make_user(role="STORE_MANAGER"))

        response = client.get("/colors/suggest-hex?name=اخضر زيتي")

        assert response.status_code == 200
        assert response.get_json()["hex_code"] == "#6B7C3A"

    def test_an_unknown_name_answers_with_nothing(self, client, login, make_user):
        login(make_user(role="STORE_MANAGER"))

        response = client.get("/colors/suggest-hex?name=لبني")

        assert response.get_json()["hex_code"] is None

    def test_it_needs_a_signed_in_manager(self, client):
        assert client.get("/colors/suggest-hex?name=احمر").status_code in (302, 401)

    def test_an_employee_cannot_reach_it(self, client, login, make_user):
        login(make_user(username="worker", role="EMPLOYEE"))

        assert client.get("/colors/suggest-hex?name=احمر").status_code == 403


class TestQuickAddGetsAColour:
    """The modal on the product form sends only a name."""

    def test_a_known_name_is_stored_with_its_hex(
        self, client, login, make_user, db_session
    ):
        login(make_user(role="ADMIN"))

        response = client.post(
            "/add-color",
            data={"name": "أخضر زيتي"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert response.status_code == 200
        stored = db_session.query(Color).filter_by(name="أخضر زيتي").first()

        assert stored.hex_code == "#6B7C3A", \
            "لون مضاف من نموذج المنتج كان بينحفظ بدون كود"

    def test_an_unknown_name_is_still_accepted_without_one(
        self, client, login, make_user, db_session
    ):
        login(make_user(role="ADMIN"))

        client.post(
            "/add-color",
            data={"name": "لون ما إلو اسم معروف"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        stored = db_session.query(Color).filter_by(
            name="لون ما إلو اسم معروف"
        ).first()

        assert stored is not None
        assert stored.hex_code is None

    def test_a_suggestion_already_in_use_does_not_block_the_colour(
        self, client, login, make_user, db_session
    ):
        # the validator refuses a code another colour already carries, and a
        # suggestion nobody asked for must not be the reason this fails
        db_session.add(Color(name="زيتوني قديم", hex_code="#6B7C3A"))
        db_session.commit()

        login(make_user(role="ADMIN"))

        response = client.post(
            "/add-color",
            data={"name": "أخضر زيتي"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert response.status_code == 200, response.get_json()
        stored = db_session.query(Color).filter_by(name="أخضر زيتي").first()

        assert stored is not None, "اللون لازم ينحفظ حتى لو الكود المقترح محجوز"
        assert stored.hex_code is None

    def test_an_explicit_hex_is_never_overridden(
        self, client, login, make_user, db_session
    ):
        login(make_user(role="ADMIN"))

        client.post(
            "/add-color",
            data={"name": "أخضر زيتي", "hex_code": "#123456"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        stored = db_session.query(Color).filter_by(name="أخضر زيتي").first()
        assert stored.hex_code == "#123456"
