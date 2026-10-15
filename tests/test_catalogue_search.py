# -*- coding: utf-8 -*-
"""Searching and filtering from the products page itself.

The page used to have four dropdowns and no way to type a word: 224 products
over twelve pages, and finding one meant leaving for /search. It searches now,
through the same matcher /search uses — so what these tests really pin down is
that the two cannot drift apart, and that the card says WHERE a product is
rather than how many places it sits in.
"""

import re

import pytest

from utils.catalogue import browse_flat


def ids(pagination):
    return {product.id for product in pagination.items}


def product_ids_on(body):
    return set(re.findall(r'/product/(\d+)"', body))


@pytest.fixture()
def shelved(db_session, make_product, make_location):
    """Four products with known names, colours and shelves."""

    from models import Color
    from utils.search_text import refresh_search_text

    colours = {}
    for name, hex_code in [("أسود", "#000000"), ("ازرق", "#0000FF")]:
        colour = Color(name=name, hex_code=hex_code)
        db_session.add(colour)
        colours[name] = colour
    db_session.flush()

    def product(name, colour, quantity, location):
        made = make_product(name=name, color_id=colours[colour].id,
                            minimum_stock=10)
        refresh_search_text(made)
        make_location(made, quantity=quantity, location=location)
        return made

    made = {
        "black_cap": product("غطاء قطرة", "أسود", 100, "رف 5 خانة 1"),
        "blue_cap": product("غطاء قطرة", "ازرق", 60, "رف 7"),
        "spray": product("بخاخ", "أسود", 0, "رف 5 خانة 2"),
        "jar": product("جرة زجاج", "ازرق", 4, "رف 12"),
    }
    db_session.commit()
    return made


class TestSearching:

    def test_a_word_narrows_the_listing(self, shelved):
        pagination, *_ = browse_flat(q="بخاخ")
        assert ids(pagination) == {shelved["spray"].id}

    def test_spelling_does_not_decide_findability(self, shelved):
        """"اسود" and "أسود" are the same word to anyone but a computer."""
        pagination, *_ = browse_flat(q="اسود")
        assert ids(pagination) == {shelved["black_cap"].id, shelved["spray"].id}

    def test_a_second_word_narrows_instead_of_widening(self, shelved):
        both = browse_flat(q="غطاء ازرق")[0]
        assert ids(both) == {shelved["blue_cap"].id}

    def test_a_shelf_reference_is_read_as_a_shelf(self, shelved):
        """Not word by word: "5" would match a 500 مل bottle just as well."""
        pagination, *_ = browse_flat(q="رف 5")
        assert ids(pagination) == {shelved["black_cap"].id, shelved["spray"].id}

    def test_a_slot_narrows_the_shelf(self, shelved):
        pagination, *_ = browse_flat(q="رف 5 خانة 2")
        assert ids(pagination) == {shelved["spray"].id}

    def test_a_word_nobody_stocks_finds_nothing(self, shelved):
        pagination, *_ = browse_flat(q="خربطة")
        assert pagination.items == []
        assert pagination.total == 0

    def test_an_empty_query_changes_nothing(self, shelved):
        assert browse_flat(q="")[0].total == browse_flat()[0].total
        assert browse_flat(q="   ")[0].total == browse_flat()[0].total

    def test_search_and_filter_combine(self, shelved):
        """Typing a word must not quietly drop the filter already applied."""
        pagination, *_ = browse_flat(q="غطاء", stock_filter="low")
        # the blue cap holds 60 against a minimum of 10, so neither is low;
        # what matters is that the stock filter is still being honoured
        assert ids(pagination) <= {shelved["black_cap"].id,
                                   shelved["blue_cap"].id}
        assert all(
            product.total_quantity <= product.minimum_stock
            for product in pagination.items
        )


class TestTheSameMatcherAsSearch:
    """One implementation, two pages. A second copy drifted the first time
    either was fixed, which is why this is asserted and not assumed."""

    @pytest.mark.parametrize("query", ["غطاء", "اسود", "رف 5", "غطاء ازرق"])
    def test_both_pages_agree(self, shelved, make_user, login, query):
        from urllib.parse import quote

        client = login(make_user())
        products = client.get(f"/products?q={quote(query)}").get_data(as_text=True)
        search = client.get(f"/search?q={quote(query)}").get_data(as_text=True)

        assert product_ids_on(products) == product_ids_on(search)


class TestSortingByQuantity:

    def test_least_first_leads_with_the_empty_shelves(self, shelved):
        pagination, *_ = browse_flat(sort="quantity_asc")
        quantities = [p.total_quantity for p in pagination.items]
        assert quantities == sorted(quantities)
        assert quantities[0] == 0

    def test_most_first_is_unchanged(self, shelved):
        pagination, *_ = browse_flat(sort="quantity")
        quantities = [p.total_quantity for p in pagination.items]
        assert quantities == sorted(quantities, reverse=True)

    def test_both_orders_hold_the_same_products(self, shelved):
        assert ids(browse_flat(sort="quantity_asc")[0]) == \
               ids(browse_flat(sort="quantity")[0])


class TestTheCard:

    def test_names_the_shelf_rather_than_counting_places(self, shelved):
        """"المواقع: 1" answered a question nobody asks."""
        pagination, units, *_ = browse_flat(q="بخاخ")
        assert units[0]["shelf"] == "رف 5 خانة 2"

    def test_the_fullest_shelf_is_the_one_named(
        self, db_session, shelved, make_location
    ):
        jar = shelved["jar"]
        make_location(jar, quantity=900, location="رف 40")
        db_session.commit()

        unit = browse_flat(q="جرة")[1][0]
        assert unit["shelf"] == "رف 40"
        assert unit["others"] == 1

    def test_a_product_with_no_shelf_text_says_so(
        self, db_session, make_product, make_location
    ):
        from utils.search_text import refresh_search_text

        homeless = make_product(name="منتج بلا رف")
        refresh_search_text(homeless)
        make_location(homeless, quantity=5, location="")
        db_session.commit()

        unit = browse_flat(q="بلا رف")[1][0]
        assert unit["shelf"] == ""

    def test_the_whole_card_is_the_link(self, shelved, make_user, login):
        """The image and a separate "عرض" button both went to the same place;
        one of them was furniture."""
        body = login(make_user()).get("/products").get_data(as_text=True)

        assert 'class="catalogue-card' in body
        assert '<div class="card-footer">' not in body


class TestThePage:

    def test_the_search_box_keeps_what_was_typed(
        self, shelved, make_user, login
    ):
        body = login(make_user()).get(
            "/products?q=%D8%A8%D8%AE%D8%A7%D8%AE"
        ).get_data(as_text=True)

        assert 'name="q"' in body
        assert 'value="بخاخ"' in body

    def test_paging_keeps_the_search(self, shelved, make_user, login):
        body = login(make_user()).get(
            "/products?q=%D8%BA%D8%B7%D8%A7%D8%A1&sort=name"
        ).get_data(as_text=True)

        links = re.findall(r'href="(/products\?[^"]*page=\d+[^"]*)"', body)
        for link in links:
            assert "q=" in link, link

    def test_the_count_no_longer_calls_a_filtered_result_the_total(
        self, shelved, make_user, login
    ):
        """Filtering to one category used to announce "إجمالي المنتجات: 24"."""
        body = login(make_user()).get(
            "/products?stock=critical"
        ).get_data(as_text=True)

        line = re.search(
            r'<span class="catalogue-count">(.*?)</span>', body, re.S
        )
        assert line, "the result count is missing"

        text = re.sub(r"\s+", " ", line.group(1))
        assert "<strong>1</strong>" in text      # one product is at zero
        assert "من 4" in text                     # out of four in the catalogue
        assert "إجمالي المنتجات" not in body

    def test_a_category_chip_carries_its_count(
        self, db_session, shelved, make_user, login
    ):
        from models import Category

        category = Category.query.first()
        body = login(make_user()).get("/products").get_data(as_text=True)

        assert 'class="catalogue-chip' in body
        assert f"{category.name}<span>4</span>" in body

    def test_an_active_filter_can_be_removed_from_the_page(
        self, shelved, make_user, login
    ):
        body = login(make_user()).get(
            "/products?stock=critical"
        ).get_data(as_text=True)

        assert 'class="catalogue-tag"' in body
        assert "مسح الكل" in body

    def test_nothing_found_says_what_was_searched(
        self, shelved, make_user, login
    ):
        body = login(make_user()).get(
            "/products?q=%D8%AE%D8%B1%D8%A8%D8%B7%D8%A9"
        ).get_data(as_text=True)

        assert "خربطة" in body
        assert "ما في منتج مطابق" in body

    def test_the_least_quantity_order_is_offered(
        self, shelved, make_user, login
    ):
        body = login(make_user()).get("/products").get_data(as_text=True)
        assert 'value="quantity_asc"' in body

    def test_the_column_script_is_valid_javascript(
        self, shelved, make_user, login
    ):
        r"""A raw newline inside a string literal is a syntax error that kills
        every script on the page, and it has shipped twice in this project
        because nobody looked at the rendered attribute."""
        body = login(make_user()).get("/products").get_data(as_text=True)

        script = re.search(
            r"<script>\s*\(function \(\) \{(.*?)\}\)\(\);\s*</script>",
            body, re.S
        )
        assert script, "the column control lost its script"

        source = script.group(1)
        assert "catalogueColumns" in source
        assert source.count("{") == source.count("}")
        assert source.count("(") == source.count(")")

        # Walk it. Counting quotes per file does not catch this — a newline
        # inside a string leaves every count balanced and the script dead.
        quote, escaped = None, False
        for line_number, line in enumerate(source.splitlines(), 1):
            for character in line:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif quote and character == quote:
                    quote = None
                elif not quote and character in "\"'":
                    quote = character
            assert quote is None, (
                f"string literal left open at line {line_number}: {line!r}"
            )
            escaped = False

        # localStorage must stay wrapped: it throws outright where site data
        # is blocked, and the grid has to render anyway
        assert source.count("try {") >= 2
