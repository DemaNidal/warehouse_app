# -*- coding: utf-8 -*-
"""Shelf references in search.

"رف 199 خانة 2" means shelf 199, slot 2 — not the words "رف", "199", "خانة"
and "2" scattered anywhere. Matched loosely, the digit 2 found a 250 مل bottle
on the same shelf and the search returned two products for a slot holding one.
"""

import pytest

from utils.shelves import parse_shelf, location_matches, strip_shelf


class TestParseShelf:

    def test_whole_shelf(self):
        ref = parse_shelf("رف 199")
        assert ref["shelf"] == "199"
        assert ref["slots"] == set()

    def test_one_slot(self):
        ref = parse_shelf("رف 199 خانة 2")
        assert ref["shelf"] == "199"
        assert ref["slots"] == {"2"}

    def test_several_slots_written_out(self):
        assert parse_shelf("رف 199 خانة 1-2-3")["slots"] == {"1", "2", "3"}

    def test_dashes_are_a_list_not_a_range(self):
        # the convention writes every slot; "1-3" names two of them
        assert parse_shelf("رف 5 خانة 1-3")["slots"] == {"1", "3"}

    @pytest.mark.parametrize("text", ["رف 7 خانه 4", "رف7 خانة4", "رف 7  خانة  4"])
    def test_spelling_and_spacing_do_not_matter(self, text):
        ref = parse_shelf(text)
        assert (ref["shelf"], ref["slots"]) == ("7", {"4"})

    def test_reference_inside_a_longer_query(self):
        ref = parse_shelf("بخاخ اسود رف 12 خانة 3")
        assert (ref["shelf"], ref["slots"]) == ("12", {"3"})

    @pytest.mark.parametrize("text", ["اسود", "خانة 2", "اصانصيل كبير", "", "199"])
    def test_no_reference(self, text):
        assert parse_shelf(text) is None


class TestLocationMatches:

    def test_slot_query_matches_a_location_naming_that_slot(self):
        assert location_matches("رف 199 خانة 1-2-3", parse_shelf("رف 199 خانة 2"))

    def test_slot_query_does_not_match_another_slot(self):
        assert not location_matches("رف 199 خانة 1", parse_shelf("رف 199 خانة 2"))

    def test_slot_query_does_not_match_the_bare_shelf(self):
        # a location with no slot is the shelf, not slot 2
        assert not location_matches("رف 199", parse_shelf("رف 199 خانة 2"))

    def test_shelf_query_matches_everything_on_it(self):
        wanted = parse_shelf("رف 199")
        for loc in ("رف 199", "رف 199 خانة 1", "رف 199 خانة 1-2-3"):
            assert location_matches(loc, wanted), loc

    def test_another_shelf_never_matches(self):
        assert not location_matches("رف 19 خانة 2", parse_shelf("رف 199 خانة 2"))
        assert not location_matches("رف 1990", parse_shelf("رف 199"))

    def test_free_text_location_never_matches(self):
        assert not location_matches("اصانصيل كبير", parse_shelf("رف 199"))
        assert not location_matches(None, parse_shelf("رف 199"))


class TestStripShelf:

    def test_leaves_the_rest_of_the_query(self):
        q = "بخاخ اسود رف 12 خانة 3"
        assert strip_shelf(q, parse_shelf(q)) == "بخاخ اسود"

    def test_a_pure_reference_leaves_nothing(self):
        q = "رف 199 خانة 2"
        assert strip_shelf(q, parse_shelf(q)) == ""


# ------------------------------------------------------------ through search

@pytest.fixture()
def shelf_199(db_session, make_product, make_location):
    """The exact situation that produced the wrong answer.

    Three products on shelf 199: the bare shelf, slot 1, and a pile across
    slots 1–3. The 250 مل size on the second is the trap — its "2" used to
    satisfy "خانة 2".
    """
    from models import Size, SIZE_KIND_CAPACITY
    from utils.search_text import refresh_search_text

    # make_product falls back to the first Size row, so give it a plain one
    # to fall back to — otherwise every product here would be 250 مل
    plain = Size(name="1 لتر", kind=SIZE_KIND_CAPACITY)
    size = Size(name="250 مل", kind=SIZE_KIND_CAPACITY)
    db_session.add_all([plain, size])
    db_session.flush()

    bare = make_product(name="جلن", size_id=plain.id)
    slot1 = make_product(name="علبة", size_id=size.id)
    pile = make_product(name="غطاء", size_id=plain.id)
    for p in (bare, slot1, pile):
        refresh_search_text(p)

    make_location(bare, quantity=10, location="رف 199")
    make_location(slot1, quantity=10, location="رف 199 خانة 1")
    make_location(pile, quantity=10, location="رف 199 خانة 1-2-3")
    db_session.commit()

    return {"bare": bare, "slot1": slot1, "pile": pile}


def found(client, q):
    import re
    body = client.get("/search", query_string={"q": q}).get_data(as_text=True)
    return sorted({int(m) for m in re.findall(r'/product/(\d+)"', body)})


class TestShelfSearch:

    def test_slot_two_finds_only_the_pile_that_spans_it(
        self, shelf_199, make_user, login
    ):
        client = login(make_user())
        assert found(client, "رف 199 خانة 2") == [shelf_199["pile"].id]

    def test_slot_one_finds_both_that_name_it(self, shelf_199, make_user, login):
        client = login(make_user())
        assert found(client, "رف 199 خانة 1") == sorted(
            [shelf_199["slot1"].id, shelf_199["pile"].id]
        )

    def test_the_bare_shelf_finds_everything_on_it(
        self, shelf_199, make_user, login
    ):
        client = login(make_user())
        assert len(found(client, "رف 199")) == 3

    def test_a_size_that_shares_digits_is_not_confused_for_a_slot(
        self, shelf_199, make_user, login
    ):
        client = login(make_user())
        # 250 مل is on the shelf but not in slot 5
        assert found(client, "رف 199 خانة 5") == []

    def test_a_product_word_narrows_within_the_shelf(
        self, shelf_199, make_user, login
    ):
        client = login(make_user())
        assert found(client, "غطاء رف 199") == [shelf_199["pile"].id]
        assert found(client, "رف 199 علبة") == [shelf_199["slot1"].id]

    def test_an_unknown_shelf_finds_nothing(self, shelf_199, make_user, login):
        client = login(make_user())
        assert found(client, "رف 999") == []

    def test_ordinary_search_is_unchanged(self, shelf_199, make_user, login):
        client = login(make_user())
        assert found(client, "غطاء") == [shelf_199["pile"].id]
        assert found(client, "250") == [shelf_199["slot1"].id]
