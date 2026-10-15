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


def result_order(response):
    """The same ids, in the order the page put them."""
    body = response.get_data(as_text=True)
    seen, order = set(), []
    for match in re.findall(r'/product/(\d+)"', body):
        number = int(match)
        if number not in seen:
            seen.add(number)
            order.append(number)
    return order


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

    @pytest.mark.parametrize(
        "sort", ["recent", "oldest", "name", "quantity", "quantity_asc"]
    )
    def test_every_order_returns_the_same_set(self, catalogue, make_user, login, sort):
        response = login(make_user()).get("/search", query_string={"sort": sort})
        assert response.status_code == 200
        assert len(result_ids(response)) == 4

    def test_the_two_quantity_orders_are_mirrors(
        self, catalogue, make_user, login
    ):
        client = login(make_user())

        most = result_order(client.get("/search", query_string={"sort": "quantity"}))
        least = result_order(
            client.get("/search", query_string={"sort": "quantity_asc"})
        )

        assert least == list(reversed(most))

    def test_both_pages_offer_the_same_orders(self, catalogue, make_user, login):
        """/search and /products used to disagree about what "quantity" was
        called, which made one of them wrong whichever you read."""
        client = login(make_user())

        def offered(path):
            """Every sort the page offers, as {key: label}.

            The two pages spell an option differently — /products submits a
            form, so the value is the key, while /search navigates, so the
            value is a URL carrying it — and the labels are what has to
            agree, not the plumbing.
            """
            body = client.get(path).get_data(as_text=True)
            found = {}
            for value, label in re.findall(
                r'<option value="([^"]*)"[^>]*>([^<]+)</option>', body
            ):
                key = re.search(r"sort=(\w+)", value)
                key = key.group(1) if key else value
                if key in ("recent", "oldest", "name", "quantity",
                           "quantity_asc"):
                    found[key] = label.strip()
            return found

        theirs, ours = offered("/search"), offered("/products")

        assert theirs, "the search page stopped offering any order"
        assert set(theirs) == set(ours)
        assert theirs == ours

    @pytest.mark.parametrize(
        "sort", ["recent", "oldest", "name", "quantity", "quantity_asc"]
    )
    def test_every_order_settles_its_ties(self, app, sort):
        """Rows tied on the sort key must not be left to the database's mood.

        Asserted on the ORDER BY rather than by paging through tied rows:
        PostgreSQL happened to return a stable order for a small table either
        way, so the paging version passed with the tiebreaker taken out — it
        looked like a guard and was not one.
        """
        from sqlalchemy import func

        from models import InventoryLocation, Product
        from utils.catalogue import apply_sort

        with app.app_context():
            qty = func.coalesce(func.sum(InventoryLocation.quantity), 0)
            ordered, used = apply_sort(Product.query, sort, qty)

            clause = str(
                ordered.statement.compile(
                    compile_kwargs={"literal_binds": True}
                )
            ).rsplit("ORDER BY", 1)[-1]

        assert used == sort
        assert "product.id" in clause, clause

    def test_an_unknown_order_falls_back_instead_of_failing(self, app):
        from sqlalchemy import func

        from models import InventoryLocation, Product
        from utils.catalogue import apply_sort

        with app.app_context():
            qty = func.coalesce(func.sum(InventoryLocation.quantity), 0)
            _, used = apply_sort(Product.query, "; drop table product", qty)

        assert used == "recent"


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


class TestTheHeader:
    """Getting to the search at all.

    The magnifier in the header pointed at "/", a page whose only job was to
    hold a search box and forward it here — and nothing in the application
    linked to the results page itself. Both facts were invisible until
    someone followed the link.
    """

    def test_the_header_carries_a_search_field(self, make_user, login):
        body = login(make_user()).get("/products").get_data(as_text=True)

        assert 'class="header-search' in body
        assert 'action="/search"' in body

    def test_it_is_on_every_page_not_just_one(self, catalogue, make_user, login):
        client = login(make_user())
        for path in ("/products", "/search", "/", "/notifications"):
            body = client.get(path).get_data(as_text=True)
            assert 'class="header-search' in body, path

    def test_it_keeps_what_is_being_searched(self, catalogue, make_user, login):
        body = login(make_user()).get(
            "/search", query_string={"q": "غطاء"}
        ).get_data(as_text=True)

        field = re.search(
            r'<form class="header-search.*?</form>', body, re.S
        )
        assert field, "the header lost its search field"
        assert 'value="غطاء"' in field.group(0)

    def test_the_sidebar_search_goes_to_the_results(self, make_user, login):
        body = login(make_user()).get("/products").get_data(as_text=True)

        link = re.search(
            r'<a class="sidebar-link[^"]*"[^>]*href="([^"]+)">\s*'
            r'<i class="bi bi-search"></i>\s*البحث',
            body,
        )
        assert link, "the sidebar lost its search entry"
        assert link.group(1) == "/search"

    def test_the_home_page_is_still_reachable(self, make_user, login):
        """Repointing "البحث" would otherwise have orphaned it."""
        body = login(make_user()).get("/products").get_data(as_text=True)

        assert "الرئيسية" in body
        assert re.search(r'href="/"[^>]*>\s*<i class="bi bi-house', body)


class TestTheSearchCard:
    """The results page had kept the old card after the products page moved
    on, so the same product looked like two different things."""

    @pytest.fixture()
    def shelved(self, db_session, make_product, make_location):
        from models import Color
        from utils.search_text import refresh_search_text

        colour = Color(name="أزرق سماوي", hex_code="#7EC8E3")
        db_session.add(colour)
        db_session.flush()

        product = make_product(name="جرة اختبار", color_id=colour.id)
        refresh_search_text(product)
        make_location(product, quantity=40, location="رف 3")
        make_location(product, quantity=900, location="رف 90")
        db_session.commit()
        return product

    def test_it_is_the_same_card_as_the_products_page(
        self, shelved, make_user, login
    ):
        body = login(make_user()).get("/search").get_data(as_text=True)

        assert 'class="catalogue-card' in body
        assert "product-meta-grid" not in body
        assert '<div class="card-footer">' not in body

    def test_it_names_the_shelf(self, shelved, make_user, login):
        body = login(make_user()).get("/search").get_data(as_text=True)
        assert "رف 90" in body

    def test_the_shelf_asked_for_wins_here_too(self, shelved, make_user, login):
        """Same rule as the products page, from the same helper."""
        body = login(make_user()).get(
            "/search", query_string={"q": "رف 3"}
        ).get_data(as_text=True)

        card = re.search(r'<span class="catalogue-shelf">(.*?)</span>', body, re.S)
        assert card
        assert "رف 3" in card.group(1)
        assert "رف 90" not in card.group(1)

    def test_the_colour_is_named_not_just_dotted(
        self, shelved, make_user, login
    ):
        """A bare swatch is only readable by hovering it, which is no use on
        a phone and little use when colour is what you are scanning for."""
        client = login(make_user())

        for path in ("/search", "/products"):
            body = client.get(path).get_data(as_text=True)
            assert 'class="catalogue-colour"' in body, path
            assert "أزرق سماوي" in body, path

    def test_a_narrow_screen_keeps_a_search_box_on_the_page(
        self, shelved, make_user, login
    ):
        """The header's field is hidden below lg; without this one a phone
        would have no way to search from the results page."""
        body = login(make_user()).get("/search").get_data(as_text=True)

        form = re.search(r'<form[^>]*class="search-onpage[^"]*".*?</form>',
                         body, re.S)
        assert form, "the page lost its narrow-screen search box"
        assert "d-lg-none" in form.group(0)

    def test_that_box_does_not_throw_away_the_filters(
        self, shelved, make_user, login
    ):
        from models import Category

        category = Category.query.first()
        body = login(make_user()).get(
            "/search", query_string={"category": category.id}
        ).get_data(as_text=True)

        form = re.search(r'<form[^>]*class="search-onpage[^"]*".*?</form>',
                         body, re.S).group(0)
        assert f'name="category" value="{category.id}"' in form

    def test_an_empty_result_still_offers_the_box(
        self, shelved, make_user, login
    ):
        body = login(make_user()).get(
            "/search", query_string={"q": "خربطة"}
        ).get_data(as_text=True)

        assert "لا توجد نتائج" in body
        assert 'class="search-onpage' in body
