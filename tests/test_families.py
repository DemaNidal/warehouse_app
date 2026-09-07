# -*- coding: utf-8 -*-
"""Grouping products into families.

The rule the whole feature rests on is that nothing groups itself. Two earlier
attempts guessed families from product names and both were discarded, so the
tests here care as much about what the code refuses to do on its own as about
what it does when asked.
"""

import pytest

from utils.families import (
    suggest_families,
    create_family,
    link_product,
    unlink_product,
    dismiss_suggestion,
)


# ------------------------------------------------------------- suggestions

class TestSuggestions:

    def test_groups_products_sharing_a_name(self, caps):
        proposals = suggest_families()

        assert len(proposals) == 1
        assert proposals[0]["name"] == "غطاء قطرة"
        assert len(proposals[0]["products"]) == 3

    def test_leaves_a_lone_product_alone(self, caps):
        names = [p["name"] for p in suggest_families()]
        assert "بمب PUMP" not in names

    def test_ignores_products_already_grouped(self, caps, db_session):
        create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        assert suggest_families() == []

    def test_reports_what_differs(self, caps, db_session, make_product, colours):
        from models import Size, SIZE_KIND_CAPACITY

        assert suggest_families()[0]["differs"] == "اللون"

        big = Size(name="2 لتر", kind=SIZE_KIND_CAPACITY)
        db_session.add(big)
        db_session.flush()

        make_product(name="بمب PUMP", color_id=colours["احمر"].id, size_id=big.id)
        db_session.commit()

        pumps = [p for p in suggest_families() if p["name"] == "بمب PUMP"][0]
        assert pumps["differs"] == "اللون والمقاس"

    def test_flags_products_that_differ_in_nothing(
        self, db_session, make_product, colours
    ):
        for _ in range(2):
            make_product(name="علبة", color_id=colours["أسود"].id)
        db_session.commit()

        assert suggest_families()[0]["differs"] == "لا شيء ظاهر"

    def test_matches_across_spelling(self, db_session, make_product, colours):
        # the hamza differs but it is plainly the same product
        make_product(name="غطاء أزرق", color_id=colours["أسود"].id)
        make_product(name="غطاء ازرق", color_id=colours["احمر"].id)
        db_session.commit()

        assert len(suggest_families()) == 1

    def test_dismissed_suggestion_does_not_come_back(self, caps, db_session):
        key = suggest_families()[0]["key"]

        dismiss_suggestion(key)
        db_session.commit()

        assert suggest_families() == []

    def test_dismissing_twice_is_harmless(self, caps, db_session):
        key = suggest_families()[0]["key"]

        assert dismiss_suggestion(key) is True
        db_session.commit()
        assert dismiss_suggestion(key) is False
        db_session.commit()


# ----------------------------------------------------------------- families

class TestCreateFamily:

    def test_links_every_member(self, caps, db_session):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        assert len(family.variants) == 3
        assert all(p.family_id == family.id for p in caps["caps"])

    def test_refuses_a_family_of_one(self, caps):
        with pytest.raises(ValueError):
            create_family("غطاء قطرة", caps["caps"][:1])

    def test_inherits_a_category_the_members_agree_on(self, caps, db_session):
        from models import Category

        category = db_session.query(Category).first()
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        assert family.category_id == category.id

    def test_leaves_category_empty_when_members_disagree(
        self, caps, db_session
    ):
        from models import Category

        other = Category(name="تصنيف تاني", sort_order=9)
        db_session.add(other)
        db_session.flush()
        caps["caps"][0].category_id = other.id

        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        assert family.category_id is None

    def test_does_not_touch_stock(self, caps, db_session, make_location):
        before = [make_location(p, quantity=7).quantity for p in caps["caps"]]

        create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        after = [p.total_quantity for p in caps["caps"]]
        assert after == before

    def test_family_name_becomes_searchable(self, caps, db_session):
        create_family("كبسة قطارة", caps["caps"])
        db_session.commit()

        assert all("كبسه" in p.search_text for p in caps["caps"])


class TestFamilyProperties:

    def test_total_quantity_sums_the_variants(
        self, caps, db_session, make_location
    ):
        for product, qty in zip(caps["caps"], (10, 20, 30)):
            make_location(product, quantity=qty)

        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        assert family.total_quantity == 60

    def test_colors_are_distinct_and_ordered(self, caps, db_session):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        names = [c.name for c in family.colors]
        assert names == ["أسود", "احمر", "ازرق"]

    def test_status_reports_the_worst_variant(
        self, caps, db_session, make_location
    ):
        from models import STOCK_CRITICAL, STOCK_LOW, STOCK_NORMAL

        # plenty, plenty, none — the family must not read as "متوفر"
        make_location(caps["caps"][0], quantity=500)
        make_location(caps["caps"][1], quantity=500)
        make_location(caps["caps"][2], quantity=0)

        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        assert family.stock_status == STOCK_CRITICAL

        caps["caps"][2].locations[0].quantity = 5     # under a minimum of 10
        db_session.commit()
        assert family.stock_status == STOCK_LOW

        caps["caps"][2].locations[0].quantity = 500
        db_session.commit()
        assert family.stock_status == STOCK_NORMAL


class TestLinkAndUnlink:

    def test_link_moves_a_product_in(self, caps, db_session, make_product, colours):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        newcomer = make_product(name="غطاء قطرة", color_id=colours["ازرق"].id)
        link_product(newcomer, family)
        db_session.commit()

        assert newcomer.family_id == family.id
        assert len(family.variants) == 4

    def test_unlink_leaves_the_rest_intact(self, caps, db_session):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        odd_one = caps["caps"][0]
        unlink_product(odd_one)
        db_session.commit()

        assert odd_one.family_id is None
        assert len(family.variants) == 2

    def test_unlinking_down_to_one_removes_the_family(self, caps, db_session):
        from models import ProductFamily

        family = create_family("غطاء قطرة", caps["caps"][:2])
        db_session.commit()
        family_id = family.id

        unlink_product(caps["caps"][0])
        db_session.commit()

        # a family of one is just a product with extra indirection
        assert db_session.get(ProductFamily, family_id) is None
        assert caps["caps"][1].family_id is None

    def test_unlink_refreshes_the_search_text(self, caps, db_session):
        product = caps["caps"][0]
        create_family("كبسة قطارة", caps["caps"])
        db_session.commit()
        assert "كبسه" in product.search_text

        unlink_product(product)
        db_session.commit()
        assert "كبسه" not in product.search_text


# ------------------------------------------------------------------ routes

class TestRoutes:

    @pytest.mark.parametrize("path", [
        "/families", "/families/suggestions",
    ])
    def test_require_login(self, client, path):
        response = client.get(path)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_suggestions_screen_is_manager_only(self, caps, make_user, login):
        staff = login(make_user(username="staff", role="STAFF"))
        assert staff.get("/families/suggestions").status_code in (302, 403)

    def test_suggestions_screen_lists_the_proposal(self, caps, make_user, login):
        response = login(make_user()).get("/families/suggestions")

        assert response.status_code == 200
        assert "غطاء قطرة" in response.get_data(as_text=True)

    def test_approving_creates_the_family(self, caps, make_user, login, db_session):
        from models import ProductFamily

        ids = [p.id for p in caps["caps"]]
        response = login(make_user()).post("/families/suggestions/approve", data={
            "name": "غطاء قطرة",
            "product_ids": ids,
        })
        assert response.status_code == 302

        family = ProductFamily.query.one()
        assert family.name == "غطاء قطرة"
        assert len(family.variants) == 3

    def test_approving_a_subset_leaves_the_rest_out(
        self, caps, make_user, login
    ):
        from models import ProductFamily

        ids = [p.id for p in caps["caps"][:2]]
        login(make_user()).post("/families/suggestions/approve", data={
            "name": "غطاء قطرة",
            "product_ids": ids,
        })

        assert len(ProductFamily.query.one().variants) == 2
        assert caps["caps"][2].family_id is None

    def test_approving_one_product_is_rejected(self, caps, make_user, login):
        from models import ProductFamily

        login(make_user()).post("/families/suggestions/approve", data={
            "name": "غطاء قطرة",
            "product_ids": [caps["caps"][0].id],
        })

        assert ProductFamily.query.count() == 0

    def test_approving_without_a_name_is_rejected(self, caps, make_user, login):
        from models import ProductFamily

        login(make_user()).post("/families/suggestions/approve", data={
            "name": "   ",
            "product_ids": [p.id for p in caps["caps"]],
        })

        assert ProductFamily.query.count() == 0

    def test_dismissing_hides_the_proposal(self, caps, make_user, login):
        client = login(make_user())
        key = suggest_families()[0]["key"]

        client.post("/families/suggestions/dismiss", data={"key": key})

        body = client.get("/families/suggestions").get_data(as_text=True)
        assert "ما في اقتراحات" in body

    def test_family_list_renders(self, caps, make_user, login, db_session):
        create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        body = login(make_user()).get("/families").get_data(as_text=True)
        assert "غطاء قطرة" in body
        assert "3 ألوان" in body

    def test_product_page_shows_its_siblings(
        self, caps, make_user, login, db_session
    ):
        create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        product = caps["caps"][0]
        body = login(make_user()).get(
            f"/product/{product.id}"
        ).get_data(as_text=True)

        assert "المجموعة" in body
        for colour in ("أسود", "احمر", "ازرق"):
            assert colour in body

    def test_unlink_route_detaches(self, caps, make_user, login, db_session):
        create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        product = caps["caps"][0]
        response = login(make_user()).post(
            f"/product/{product.id}/unlink-family"
        )

        assert response.status_code == 302
        assert product.family_id is None

    def test_unlink_route_is_manager_only(
        self, caps, make_user, login, db_session
    ):
        create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        product = caps["caps"][0]
        staff = login(make_user(username="staff", role="STAFF"))
        staff.post(f"/product/{product.id}/unlink-family")

        assert product.family_id is not None

    def test_link_route_attaches(
        self, caps, make_user, login, db_session, make_product, colours
    ):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        newcomer = make_product(name="غطاء قطرة", color_id=colours["ازرق"].id)
        db_session.commit()

        response = login(make_user()).post(
            f"/product/{newcomer.id}/link-family",
            data={"family_id": family.id},
        )

        assert response.status_code == 302
        assert newcomer.family_id == family.id

    def test_link_route_rejects_an_unknown_family(
        self, caps, make_user, login
    ):
        product = caps["caps"][0]
        response = login(make_user()).post(
            f"/product/{product.id}/link-family",
            data={"family_id": 999999},
        )

        assert response.status_code == 404
        assert product.family_id is None


class TestGroupingIsNeverAutomatic:
    """The property that both earlier attempts violated."""

    def test_adding_a_matching_product_does_not_group_it(
        self, caps, db_session, make_user, login, colours
    ):
        from models import Product, Category, Size, SIZE_KIND_CAPACITY

        category = db_session.query(Category).first()
        size = db_session.query(Size).first()

        login(make_user()).post("/add-product", data={
            "name": "غطاء قطرة",           # same name as three existing ones
            "color_id": colours["ازرق"].id,
            "secondary_color_id": "",
            "size_id": size.id,
            "neck_size_id": "",
            "category_id": category.id,
            "minimum_stock": "5",
        })

        added = Product.query.order_by(Product.id.desc()).first()
        assert added.family_id is None

    def test_merely_viewing_suggestions_changes_nothing(
        self, caps, make_user, login
    ):
        from models import ProductFamily

        login(make_user()).get("/families/suggestions")

        assert ProductFamily.query.count() == 0
        assert all(p.family_id is None for p in caps["caps"])


class TestFamilyPage:
    """The page a family card links to — the only place the variants of one
    product are shown side by side."""

    def test_lists_every_variant(self, caps, make_user, login, db_session):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        response = login(make_user()).get(f"/family/{family.id}")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        for variant in family.variants:
            assert f"/product/{variant.id}" in body

    def test_shows_each_colour(self, caps, make_user, login, db_session):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        body = login(make_user()).get(
            f"/family/{family.id}"
        ).get_data(as_text=True)

        for colour in ("أسود", "احمر", "ازرق"):
            assert colour in body

    def test_warns_when_a_colour_has_run_out(
        self, caps, make_user, login, db_session, make_location
    ):
        make_location(caps["caps"][0], quantity=500)
        make_location(caps["caps"][1], quantity=500)
        make_location(caps["caps"][2], quantity=0)

        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        body = login(make_user()).get(
            f"/family/{family.id}"
        ).get_data(as_text=True)

        # the total is 1000, which on its own would read as healthy
        assert "خالص من المخزون" in body

    def test_unknown_family_is_404(self, caps, make_user, login):
        assert login(make_user()).get("/family/999999").status_code == 404

    def test_family_list_links_to_each_family(
        self, caps, make_user, login, db_session
    ):
        family = create_family("غطاء قطرة", caps["caps"])
        db_session.commit()

        body = login(make_user()).get("/families").get_data(as_text=True)
        assert f"/family/{family.id}" in body
