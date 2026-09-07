# -*- coding: utf-8 -*-
"""The grouping offer made on a product page.

This is the entry point that decides whether grouping survives contact with a
growing catalogue. A review screen visited on purpose works while there are
fifteen decisions on it; at several thousand products it becomes a backlog and
the catalogue drifts back to one card per colour. Offering the link on the page
someone is already looking at is what keeps it current.

What these tests guard is the line between offering and acting: the banner
appears, and nothing at all happens until it is clicked.
"""

import re

import pytest

from utils.families import (
    create_family,
    dismiss_suggestion,
    find_match,
    rename_family,
)


class TestFindMatch:

    def test_finds_the_other_products_with_the_same_name(self, caps):
        match = find_match(caps["caps"][0])

        assert match is not None
        assert match["family"] is None
        assert {p.id for p in match["siblings"]} == {
            caps["caps"][1].id, caps["caps"][2].id
        }

    def test_finds_nothing_for_a_unique_name(self, caps):
        assert find_match(caps["other"]) is None

    def test_offers_an_existing_family_rather_than_a_second_one(
        self, caps, db_session, make_product, colours
    ):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        newcomer = make_product(name="غطاء قطرة", color_id=colours["ازرق"].id)
        db_session.commit()

        match = find_match(newcomer)

        assert match["family"].id == family.id
        assert len(match["siblings"]) == 3

    def test_says_nothing_about_a_product_already_grouped(
        self, caps, db_session
    ):
        create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        assert find_match(caps["caps"][0]) is None

    def test_respects_a_dismissal(self, caps, db_session):
        dismiss_suggestion(caps["caps"][0].normalized_name)
        db_session.commit()

        assert find_match(caps["caps"][0]) is None

    def test_matches_across_spelling(self, db_session, make_product, colours):
        first = make_product(name="غطاء أزرق", color_id=colours["أسود"].id)
        make_product(name="غطاء ازرق", color_id=colours["احمر"].id)
        db_session.commit()

        assert find_match(first) is not None


class TestBanner:

    def test_appears_on_the_product_page(self, caps, make_user, login):
        body = login(make_user()).get(
            "/product/%d" % caps["caps"][0].id
        ).get_data(as_text=True)

        assert "منتج تاني بنفس الاسم" in body

    def test_absent_for_a_unique_product(self, caps, make_user, login):
        body = login(make_user()).get(
            "/product/%d" % caps["other"].id
        ).get_data(as_text=True)

        assert "منتج تاني بنفس الاسم" not in body

    def test_hidden_from_staff(self, caps, make_user, login):
        client = login(make_user(username="staff", role="STAFF"))
        body = client.get(
            "/product/%d" % caps["caps"][0].id
        ).get_data(as_text=True)

        assert "منتج تاني بنفس الاسم" not in body

    def test_names_the_family_when_one_exists(
        self, caps, db_session, make_user, login, make_product, colours
    ):
        create_family("كبسة قطارة", caps["caps"])
        db_session.commit()

        newcomer = make_product(name="غطاء قطرة", color_id=colours["ازرق"].id)
        db_session.commit()

        body = login(make_user()).get(
            "/product/%d" % newcomer.id
        ).get_data(as_text=True)

        assert "كبسة قطارة" in body


class TestOneClickGrouping:

    def test_creates_the_family(self, caps, make_user, login):
        from models import ProductFamily

        response = login(make_user()).post(
            "/product/%d/group-with-match" % caps["caps"][0].id
        )
        assert response.status_code == 302

        family = ProductFamily.query.one()
        assert len(family.variants) == 3
        assert family.name == "غطاء قطرة"

    def test_joins_an_existing_family_instead_of_making_a_second(
        self, caps, db_session, make_user, login, make_product, colours
    ):
        from models import ProductFamily

        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        newcomer = make_product(name="غطاء قطرة", color_id=colours["ازرق"].id)
        db_session.commit()

        login(make_user()).post("/product/%d/group-with-match" % newcomer.id)

        assert ProductFamily.query.count() == 1
        assert newcomer.family_id == family.id

    def test_leaves_stock_untouched(
        self, caps, db_session, make_user, login, make_location
    ):
        before = [make_location(p, quantity=9).quantity for p in caps["caps"]]
        db_session.commit()

        login(make_user()).post(
            "/product/%d/group-with-match" % caps["caps"][0].id
        )

        assert [p.total_quantity for p in caps["caps"]] == before

    def test_is_manager_only(self, caps, make_user, login):
        from models import ProductFamily

        staff = login(make_user(username="staff", role="STAFF"))
        staff.post("/product/%d/group-with-match" % caps["caps"][0].id)

        assert ProductFamily.query.count() == 0

    def test_a_product_with_no_match_is_refused(self, caps, make_user, login):
        from models import ProductFamily

        login(make_user()).post(
            "/product/%d/group-with-match" % caps["other"].id
        )
        assert ProductFamily.query.count() == 0


class TestDismissing:

    def test_stops_the_offer(self, caps, make_user, login):
        client = login(make_user())
        product_id = caps["caps"][0].id

        client.post("/product/%d/dismiss-match" % product_id)

        body = client.get("/product/%d" % product_id).get_data(as_text=True)
        assert "منتج تاني بنفس الاسم" not in body

    def test_creates_no_family(self, caps, make_user, login):
        from models import ProductFamily

        login(make_user()).post(
            "/product/%d/dismiss-match" % caps["caps"][0].id
        )
        assert ProductFamily.query.count() == 0

    def test_also_clears_it_from_the_suggestions_screen(
        self, caps, make_user, login
    ):
        client = login(make_user())

        client.post("/product/%d/dismiss-match" % caps["caps"][0].id)

        body = client.get("/families/suggestions").get_data(as_text=True)
        assert "ما في اقتراحات" in body


class TestNothingHappensByItself:
    """The property both discarded attempts violated."""

    def test_adding_a_matching_product_does_not_group_it(
        self, caps, db_session, make_user, login, colours
    ):
        from models import Product, Category, Size

        category = db_session.query(Category).first()
        size = db_session.query(Size).first()

        login(make_user()).post("/add-product", data={
            "name": "غطاء قطرة",
            "color_id": colours["ازرق"].id,
            "secondary_color_id": "",
            "size_id": size.id,
            "neck_size_id": "",
            "category_id": category.id,
            "minimum_stock": "5",
        })

        added = Product.query.order_by(Product.id.desc()).first()
        assert added.family_id is None

    def test_viewing_the_banner_changes_nothing(self, caps, make_user, login):
        from models import ProductFamily

        login(make_user()).get("/product/%d" % caps["caps"][0].id)

        assert ProductFamily.query.count() == 0
        assert all(p.family_id is None for p in caps["caps"])


class TestRename:

    def test_changes_the_name(self, caps, db_session):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        rename_family(family, "كبسة قطارة")
        db_session.commit()

        assert family.name == "كبسة قطارة"

    def test_reindexes_the_variants(self, caps, db_session):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        rename_family(family, "كبسة قطارة")
        db_session.commit()

        for variant in family.variants:
            assert "كبسه" in variant.search_text
            assert "قطاره" in variant.search_text

    def test_refuses_an_empty_name(self, caps, db_session):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        with pytest.raises(ValueError):
            rename_family(family, "   ")

    def test_route_renames(self, caps, db_session, make_user, login):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        response = login(make_user()).post(
            "/family/%d/rename" % family.id, data={"name": "كبسة قطارة"}
        )

        assert response.status_code == 302
        assert family.name == "كبسة قطارة"

    def test_route_rejects_an_empty_name(
        self, caps, db_session, make_user, login
    ):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        login(make_user()).post("/family/%d/rename" % family.id, data={"name": ""})

        assert family.name == "غطاء قطرة"

    def test_route_is_manager_only(self, caps, db_session, make_user, login):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        staff = login(make_user(username="staff", role="STAFF"))
        staff.post("/family/%d/rename" % family.id, data={"name": "اسم تاني"})

        assert family.name == "غطاء قطرة"

    def test_the_new_name_is_searchable(self, caps, db_session, make_user, login):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        client = login(make_user())
        client.post("/family/%d/rename" % family.id, data={"name": "كبسة قطارة"})

        body = client.get(
            "/search", query_string={"q": "كبسة"}
        ).get_data(as_text=True)
        found = {int(m) for m in re.findall(r'/product/(\d+)"', body)}

        assert found == {v.id for v in family.variants}
