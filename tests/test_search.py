# -*- coding: utf-8 -*-
"""Search and filtering.

Two separate things are worth pinning down here. First, that Arabic spelling
does not decide whether a product is findable — "اسود" and "أسود" have to
behave identically, because whoever is at the counter types whichever one their
keyboard gives them. Second, that filters combine instead of replacing each
other: picking a colour must not throw away the category already chosen.
"""

import re

import pytest

from utils.search_text import build_search_text, tokenize_query


# ------------------------------------------------------------- search_text

class TestBuildSearchText:

    def test_includes_name_colour_and_sizes_but_not_category(self, db_session, make_product):
        from models import Color, Category, Size, SIZE_KIND_NECK

        colour = Color(name="أسود", hex_code="#000000")
        category = Category(name="أغطية", sort_order=1)
        neck = Size(name="28/410", kind=SIZE_KIND_NECK)
        db_session.add_all([colour, category, neck])
        db_session.flush()

        product = make_product(
            name="بخاخ",
            color_id=colour.id,
            category_id=category.id,
        )
        product.neck_size_id = neck.id
        db_session.flush()

        text = build_search_text(product)

        assert "بخاخ" in text
        assert "اسود" in text        # normalised on the way in
        assert "28/410" in text
        # the category is matched by the route, by its whole name — as a
        # substring here, "جار" would pull in all of "جارات وعلب"
        assert "اغطيه" not in text

    def test_normalises_hamza_and_taa_marbuta(self, db_session, make_product):
        from models import Color

        colour = Color(name="أحمر", hex_code="#FF0000")
        db_session.add(colour)
        db_session.flush()

        product = make_product(name="علبة", color_id=colour.id)
        text = build_search_text(product)

        assert "احمر" in text
        assert "أحمر" not in text
        assert "علبه" in text

    def test_drops_duplicate_words(self, db_session, make_product):
        from models import Color

        colour = Color(name="أزرق", hex_code="#0000FF")
        db_session.add(colour)
        db_session.flush()

        # the word already in the name should not be repeated by the colour
        product = make_product(name="غطاء ازرق", color_id=colour.id)

        assert build_search_text(product).split().count("ازرق") == 1

    def test_survives_missing_relationships(self, db_session, make_product):
        product = make_product(name="منتج بلا لون")

        # clear the relationships, not just the foreign keys: a loaded
        # relationship does not follow its id, and the routes expire them for
        # exactly this reason
        product.color = None
        product.secondary_color = None
        product.category = None
        product.size_data = None
        product.neck_size = None
        db_session.flush()

        assert build_search_text(product) == "منتج بلا لون"


class TestTokenizeQuery:

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_empty_input_yields_no_tokens(self, raw):
        assert tokenize_query(raw) == []

    def test_splits_and_normalises(self):
        assert tokenize_query("  غطاء  أزرق ") == ["غطاء", "ازرق"]


# ----------------------------------------------------------------- fixtures

@pytest.fixture()
def catalogue(db_session, make_product, make_location):
    """A small catalogue carrying the ambiguities that matter: two colours,
    two categories, and products whose words are split across tables."""

    from models import Color, Category, Size, SIZE_KIND_CAPACITY, SIZE_KIND_NECK
    from utils.search_text import refresh_search_text

    black = Color(name="أسود", hex_code="#000000")
    red = Color(name="أحمر", hex_code="#FF0000")
    caps = Category(name="أغطية", sort_order=1)
    pumps = Category(name="بمبات", sort_order=2)
    litre = Size(name="1 لتر", kind=SIZE_KIND_CAPACITY)
    neck = Size(name="28/410", kind=SIZE_KIND_NECK)
    db_session.add_all([black, red, caps, pumps, litre, neck])
    db_session.flush()

    specs = [
        ("بخاخ", black.id, pumps.id, neck.id, 50),
        ("بخاخ", red.id, pumps.id, neck.id, 0),
        ("غطاء", black.id, caps.id, neck.id, 3),
        ("علبة", red.id, caps.id, None, 40),
    ]

    products = []
    warehouse_id = None
    for name, colour_id, category_id, neck_id, quantity in specs:
        product = make_product(
            name=name,
            color_id=colour_id,
            category_id=category_id,
            size_id=litre.id,
            minimum_stock=10,
        )
        product.neck_size_id = neck_id
        db_session.flush()
        refresh_search_text(product)
        row = make_location(product, quantity=quantity)
        warehouse_id = row.warehouse_id
        products.append(product)

    db_session.commit()

    return {
        "products": products,
        "black": black, "red": red,
        "caps": caps, "pumps": pumps,
        "litre": litre, "neck": neck,
        "warehouse_id": warehouse_id,
    }


def result_ids(response):
    """The product ids linked from a rendered results page."""
    body = response.get_data(as_text=True)
    return sorted({int(m) for m in re.findall(r'/product/(\d+)"', body)})


# -------------------------------------------------------------- the route

class TestSearchRoute:

    def test_requires_login(self, client):
        response = client.get("/search")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_empty_query_lists_everything(self, catalogue, make_user, login):
        response = login(make_user()).get("/search")
        assert response.status_code == 200
        assert len(result_ids(response)) == 4

    @pytest.mark.parametrize("written,expected", [
        ("أسود", 2), ("اسود", 2),
        ("أحمر", 2), ("احمر", 2),
        ("أغطية", 2), ("اغطيه", 2),
        ("علبة", 1), ("علبه", 1),
    ])
    def test_spelling_does_not_change_results(
        self, catalogue, make_user, login, written, expected
    ):
        response = login(make_user()).get("/search", query_string={"q": written})
        assert len(result_ids(response)) == expected

    def test_extra_words_narrow_the_search(self, catalogue, make_user, login):
        client = login(make_user())

        both = result_ids(client.get("/search", query_string={"q": "بخاخ"}))
        one = result_ids(client.get("/search", query_string={"q": "بخاخ اسود"}))

        assert len(both) == 2
        assert len(one) == 1
        assert one[0] in both

    def test_matches_words_that_live_in_different_tables(
        self, catalogue, make_user, login
    ):
        # "غطاء" is the product name, "اسود" sits on the colour row
        response = login(make_user()).get(
            "/search", query_string={"q": "غطاء اسود"}
        )
        assert len(result_ids(response)) == 1

    def test_unmatched_query_returns_nothing(self, catalogue, make_user, login):
        response = login(make_user()).get("/search", query_string={"q": "زززز"})
        assert result_ids(response) == []
        assert "لا توجد نتائج" in response.get_data(as_text=True)


class TestFilters:

    def test_category(self, catalogue, make_user, login):
        response = login(make_user()).get(
            "/search", query_string={"category": catalogue["caps"].id}
        )
        assert len(result_ids(response)) == 2

    def test_colour(self, catalogue, make_user, login):
        response = login(make_user()).get(
            "/search", query_string={"color": catalogue["black"].id}
        )
        assert len(result_ids(response)) == 2

    def test_neck_size(self, catalogue, make_user, login):
        response = login(make_user()).get(
            "/search", query_string={"neck": catalogue["neck"].id}
        )
        assert len(result_ids(response)) == 3

    def test_capacity(self, catalogue, make_user, login):
        response = login(make_user()).get(
            "/search", query_string={"capacity": catalogue["litre"].id}
        )
        assert len(result_ids(response)) == 4

    @pytest.mark.parametrize("status,expected", [
        ("critical", 1),   # quantity 0
        ("low", 1),        # 3, under a minimum of 10
        ("normal", 2),     # 50 and 40
    ])
    def test_stock_status(self, catalogue, make_user, login, status, expected):
        response = login(make_user()).get(
            "/search", query_string={"stock": status}
        )
        assert len(result_ids(response)) == expected

    def test_stock_buckets_cover_every_product_exactly_once(
        self, catalogue, make_user, login
    ):
        client = login(make_user())

        seen = []
        for status in ("critical", "low", "normal"):
            seen += result_ids(client.get("/search", query_string={"stock": status}))

        assert sorted(seen) == sorted(set(seen))
        assert len(seen) == 4

    def test_warehouse(self, catalogue, make_user, login):
        response = login(make_user()).get(
            "/search", query_string={"warehouse": catalogue["warehouse_id"]}
        )
        assert len(result_ids(response)) == 4

    def test_legacy_warehouse_id_parameter_still_filters(
        self, catalogue, make_user, login
    ):
        response = login(make_user()).get(
            "/search", query_string={"warehouse_id": catalogue["warehouse_id"]}
        )
        assert len(result_ids(response)) == 4

    def test_filters_combine_rather_than_replace(self, catalogue, make_user, login):
        response = login(make_user()).get("/search", query_string={
            "category": catalogue["pumps"].id,
            "color": catalogue["black"].id,
        })
        assert len(result_ids(response)) == 1

    def test_text_and_filter_combine(self, catalogue, make_user, login):
        response = login(make_user()).get("/search", query_string={
            "q": "بخاخ",
            "color": catalogue["red"].id,
        })
        assert len(result_ids(response)) == 1

    def test_removing_one_filter_keeps_the_others(self, catalogue, make_user, login):
        """The "×" on a chip links to the same search minus that one facet."""

        response = login(make_user()).get("/search", query_string={
            "q": "بخاخ",
            "category": catalogue["pumps"].id,
            "color": catalogue["black"].id,
        })
        body = response.get_data(as_text=True)

        # the link that drops the colour must still carry q and category
        links = re.findall(r'href="(/search\?[^"]*)"', body)
        without_colour = [
            link for link in links
            if "color=" not in link and "category=" in link
        ]
        assert without_colour, "no chip link drops the colour on its own"
        assert any("q=" in link for link in without_colour)


class TestBadInput:
    """A hand-edited URL should widen the search, never raise."""

    @pytest.mark.parametrize("query", [
        {"category": "abc"},
        {"color": "'; drop table product; --"},
        {"stock": "whatever"},
        {"sort": "; delete"},
        {"page": "-3"},
        {"page": "99999"},
        {"neck": "999999"},
    ])
    def test_survives(self, catalogue, make_user, login, query):
        response = login(make_user()).get("/search", query_string=query)
        assert response.status_code == 200


class TestSorting:

    @pytest.mark.parametrize("sort", ["recent", "oldest", "name", "quantity"])
    def test_every_order_returns_the_same_set(self, catalogue, make_user, login, sort):
        response = login(make_user()).get("/search", query_string={"sort": sort})
        assert response.status_code == 200
        assert len(result_ids(response)) == 4


class TestSearchTextStaysCurrent:
    """The column is a copy of data that lives elsewhere, so the write paths
    have to refresh it — otherwise a product silently stops being findable."""

    def test_adding_a_product_populates_it(self, db_session, make_user, login):
        from models import Product, Color, Category, Size, SIZE_KIND_CAPACITY

        colour = Color(name="أخضر", hex_code="#00FF00")
        category = Category(name="زجاج", sort_order=1)
        size = Size(name="250 مل", kind=SIZE_KIND_CAPACITY)
        db_session.add_all([colour, category, size])
        db_session.commit()

        client = login(make_user(role="ADMIN"))
        response = client.post("/add-product", data={
            "name": "قنينة",
            "color_id": colour.id,
            "secondary_color_id": "",
            "size_id": size.id,
            "neck_size_id": "",
            "category_id": category.id,
            "minimum_stock": "5",
        })
        assert response.status_code == 302

        product = Product.query.filter_by(name="قنينة").one()
        assert "اخضر" in product.search_text
        assert "زجاج" not in product.search_text   # category is matched by the route

        # and it is findable by the normalised spelling of its colour
        assert product.id in result_ids(
            client.get("/search", query_string={"q": "اخضر"})
        )

    def test_editing_a_product_refreshes_it(
        self, catalogue, db_session, make_user, login
    ):
        from models import Product

        product_id = catalogue["products"][0].id      # "بخاخ" in أسود
        client = login(make_user(role="ADMIN"))

        response = client.post(f"/product/{product_id}/edit", data={
            "name": "مرشة",
            "color_id": catalogue["red"].id,
            "secondary_color_id": "",
            "size_id": catalogue["litre"].id,
            "neck_size_id": catalogue["neck"].id,
            "category_id": catalogue["pumps"].id,
            "minimum_stock": "10",
        })
        assert response.status_code == 302

        refreshed = db_session.get(Product, product_id)
        assert "مرشه" in refreshed.search_text
        assert "احمر" in refreshed.search_text
        assert "بخاخ" not in refreshed.search_text    # the old name is gone
        assert "اسود" not in refreshed.search_text    # and the old colour


class TestShelfSearch:
    """Typing a shelf finds what sits on it.

    This was in the original search and was lost in the rewrite: shelves are
    not part of search_text because they change with every stock movement, so
    they are matched live against the locations instead.
    """

    def test_finds_products_by_their_shelf(
        self, catalogue, make_user, login, db_session
    ):
        from models import InventoryLocation

        product = catalogue["products"][0]
        row = InventoryLocation.query.filter_by(product_id=product.id).first()
        row.location = "رف 77"
        db_session.commit()

        found = result_ids(
            login(make_user()).get("/search", query_string={"q": "رف 77"})
        )
        assert found == [product.id]

    def test_a_shelf_word_combines_with_a_product_word(
        self, catalogue, make_user, login, db_session
    ):
        from models import InventoryLocation
        from utils.search_text import refresh_search_text

        # two products on the same shelf, only one of them a بخاخ
        for product in catalogue["products"][:2]:
            row = InventoryLocation.query.filter_by(product_id=product.id).first()
            row.location = "رف 77"
        catalogue["products"][1].name = "علبة"
        refresh_search_text(catalogue["products"][1])
        db_session.commit()

        found = result_ids(
            login(make_user()).get("/search", query_string={"q": "بخاخ 77"})
        )
        assert found == [catalogue["products"][0].id]

    def test_an_unknown_shelf_finds_nothing(self, catalogue, make_user, login):
        response = login(make_user()).get("/search", query_string={"q": "رف 999"})
        assert result_ids(response) == []

    def test_shelf_spelling_is_folded_like_everything_else(
        self, catalogue, make_user, login, db_session
    ):
        """The query is normalised before matching; the shelf text must be
        folded the same way or "خانة" on a shelf never matches "خانه"."""
        from models import InventoryLocation

        product = catalogue["products"][0]
        row = InventoryLocation.query.filter_by(product_id=product.id).first()
        row.location = "رف 199 خانة 1"
        db_session.commit()

        client = login(make_user())
        for written in ("رف 199 خانة 1", "رف 199 خانه 1", "خانه", "خانة"):
            found = result_ids(client.get("/search", query_string={"q": written}))
            assert found == [product.id], written


class TestCategoryWords:
    """A word that is part of a category's name must not summon the category.

    "جار" used to return every product filed under "جارات وعلب" — sixty-odd
    results for a word eleven products actually carried. A category is matched
    only by its whole name, and even then alongside the word matches rather
    than instead of them.
    """

    def test_a_fragment_of_a_category_name_matches_only_names(
        self, catalogue, make_user, login
    ):
        # "بمب" is a fragment of the category "بمبات"; only the two products
        # literally named بخاخ… no — the fixture has no بمب names at all
        found = result_ids(login(make_user()).get("/search", query_string={"q": "بمب"}))
        assert found == []

    def test_the_whole_category_name_finds_its_products(
        self, catalogue, make_user, login
    ):
        found = result_ids(login(make_user()).get("/search", query_string={"q": "بمبات"}))
        assert len(found) == 2

    def test_a_word_that_is_both_a_category_and_a_product_word_finds_both(
        self, catalogue, make_user, login, db_session
    ):
        """Typing "زجاج" must find "ملمع زجاج" even though that is filed
        under jars, as well as everything in the زجاج category."""
        from models import Category
        from utils.search_text import refresh_search_text

        glass = Category(name="زجاج", sort_order=5)
        db_session.add(glass)
        db_session.flush()

        # one product IN the category, named something else
        catalogue["products"][0].category_id = glass.id
        # one product named with the word, filed elsewhere
        polish = catalogue["products"][3]
        polish.name = "ملمع زجاج"
        refresh_search_text(polish)
        db_session.commit()

        found = result_ids(login(make_user()).get("/search", query_string={"q": "زجاج"}))
        assert found == sorted([catalogue["products"][0].id, polish.id])
