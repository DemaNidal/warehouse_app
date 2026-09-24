# -*- coding: utf-8 -*-
"""The catalogue listing.

One card per product. What is worth pinning down is that the filters partition
the catalogue cleanly and that paging neither loses nor repeats a product.
"""

import pytest

from utils.catalogue import browse_flat


@pytest.fixture()
def catalogue(db_session, make_product, make_location):
    """Seven products with known quantities, two names repeated.

    quantities: 100، 0 ثم 200، 300 ثم 50، 0، 5
    """

    from models import Color
    from utils.search_text import refresh_search_text

    colours = {}
    for name, hex_code in [("أسود", "#000"), ("احمر", "#F00"), ("ازرق", "#00F")]:
        colour = Color(name=name, hex_code=hex_code)
        db_session.add(colour)
        colours[name] = colour
    db_session.flush()

    def product(name, colour, quantity):
        made = make_product(name=name, color_id=colours[colour].id,
                            minimum_stock=10)
        refresh_search_text(made)
        make_location(made, quantity=quantity)
        return made

    caps = [product("غطاء قطرة", "أسود", 100), product("غطاء قطرة", "احمر", 0)]
    sprays = [product("بخاخ", "أسود", 200), product("بخاخ", "ازرق", 300)]
    loose = [
        product("علبة", "أسود", 50),
        product("جرة", "احمر", 0),
        product("مرطبان", "ازرق", 5),
    ]

    db_session.commit()

    return {"caps": caps, "sprays": sprays, "loose": loose}


class TestListing:

    def test_lists_every_product(self, catalogue):
        pagination, units, *_ = browse_flat()

        assert pagination.total == 7
        assert len(units) == 7

    def test_a_repeated_name_is_listed_once_per_product(self, catalogue):
        _, units, *_ = browse_flat()

        names = [u["product"].name for u in units]
        assert names.count("غطاء قطرة") == 2
        assert names.count("بخاخ") == 2

    def test_units_carry_quantity_and_status(self, catalogue):
        from models import STOCK_CRITICAL, STOCK_NORMAL

        _, units, *_ = browse_flat()
        by_quantity = {u["quantity"]: u for u in units}

        assert by_quantity[300]["status"] == STOCK_NORMAL
        assert by_quantity[0]["status"] == STOCK_CRITICAL

    def test_no_product_appears_twice(self, catalogue):
        _, units, *_ = browse_flat()

        ids = [u["product"].id for u in units]
        assert len(ids) == len(set(ids)) == 7


class TestStockFilter:

    @pytest.mark.parametrize("status,expected", [
        ("critical", 2),   # the red cap and the jar
        ("low", 1),        # مرطبان at 5, under a minimum of 10
        ("normal", 4),
    ])
    def test_buckets(self, catalogue, status, expected):
        pagination, *_ = browse_flat(stock_filter=status)
        assert pagination.total == expected

    def test_buckets_partition_the_catalogue(self, catalogue):
        total = browse_flat()[0].total
        counted = sum(
            browse_flat(stock_filter=s)[0].total
            for s in ("critical", "low", "normal")
        )
        assert counted == total

    def test_unknown_status_is_ignored(self, catalogue):
        pagination, _, _, stock_filter, *_ = browse_flat(stock_filter="nonsense")
        assert pagination.total == 7
        assert stock_filter == ""


class TestCategoryFilter:

    def test_filters_by_category(self, catalogue, db_session):
        from models import Category

        other = Category(name="تصنيف تاني", sort_order=9)
        db_session.add(other)
        db_session.flush()
        catalogue["loose"][0].category_id = other.id
        db_session.commit()

        pagination, units, *_ = browse_flat(category_filter=other.id)

        assert pagination.total == 1
        assert units[0]["product"].name == "علبة"

    def test_uncategorised_is_its_own_filter(self, catalogue, db_session):
        catalogue["loose"][1].category_id = None
        db_session.commit()

        pagination, units, *_ = browse_flat(category_filter="none")

        assert pagination.total == 1
        assert units[0]["product"].name == "جرة"

    def test_a_junk_category_is_ignored(self, catalogue):
        pagination, _, category_filter, *_ = browse_flat(category_filter="abc")
        assert pagination.total == 7
        assert category_filter == ""


class TestSorting:

    @pytest.mark.parametrize("sort", ["recent", "oldest", "name", "quantity"])
    def test_every_order_keeps_the_same_products(self, catalogue, sort):
        pagination, units, *_ = browse_flat(sort=sort)
        assert pagination.total == 7
        assert len(units) == 7

    def test_by_name(self, catalogue):
        _, units, *_ = browse_flat(sort="name")

        names = [u["product"].name for u in units]
        assert names == sorted(names)

    def test_by_quantity_puts_the_biggest_first(self, catalogue):
        _, units, *_ = browse_flat(sort="quantity")

        quantities = [u["quantity"] for u in units]
        assert quantities == sorted(quantities, reverse=True)
        assert quantities[0] == 300

    def test_a_junk_sort_falls_back(self, catalogue):
        sort = browse_flat(sort="; drop table product")[-1]
        assert sort == "recent"


class TestPaging:

    def test_pages_cover_every_product_exactly_once(self, catalogue):
        seen = []
        page = 1
        while True:
            pagination, units, *_ = browse_flat(page=page, per_page=3)
            seen += [u["product"].id for u in units]
            if not pagination.has_next:
                break
            page += 1

        assert len(seen) == 7
        assert len(set(seen)) == 7

    def test_page_metadata(self, catalogue):
        pagination, units, *_ = browse_flat(page=1, per_page=3)

        assert pagination.pages == 3
        assert pagination.has_prev is False
        assert pagination.has_next is True
        assert len(units) == 3

    def test_a_page_past_the_end_is_empty_not_an_error(self, catalogue):
        pagination, units, *_ = browse_flat(page=99, per_page=3)

        assert units == []
        assert pagination.total == 7


class TestRoute:

    def test_requires_login(self, client):
        response = client.get("/products")
        assert response.status_code == 302

    def test_renders_one_card_per_product(self, catalogue, make_user, login):
        import re

        response = login(make_user()).get("/products")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert len(set(re.findall(r'/product/(\d+)"', body))) == 7

    def test_stock_filter_narrows_the_page(self, catalogue, make_user, login):
        import re

        client = login(make_user())

        everything = client.get("/products").get_data(as_text=True)
        critical = client.get("/products?stock=critical").get_data(as_text=True)

        assert len(set(re.findall(r'/product/(\d+)"', everything))) == 7
        assert len(set(re.findall(r'/product/(\d+)"', critical))) == 2

    def test_pagination_links_carry_every_filter(
        self, catalogue, make_user, login
    ):
        import re

        # force more than one page so the links are rendered at all
        response = login(make_user()).get("/products?stock=normal&sort=name")
        body = response.get_data(as_text=True)

        links = re.findall(r'href="(/products\?[^"]*page=\d+[^"]*)"', body)
        for link in links:
            assert "stock=normal" in link
            assert "sort=name" in link


class TestWarehouseFilter:
    """Narrowing the catalogue to one warehouse.

    A product counts as belonging to a warehouse when it has a place there,
    even an empty one — asking "what is in this warehouse" should still show
    the shelf that ran out, since that is usually the row worth acting on.
    """

    def test_shows_only_products_stocked_there(
        self, catalogue, db_session, make_product, make_location
    ):
        from models import Warehouse

        other = make_product(name="منتج بمستودع تاني")
        make_location(other, quantity=12, warehouse_name="مستودع ثاني")
        db_session.commit()

        second = db_session.query(Warehouse).filter_by(name="مستودع ثاني").one()
        pagination, units, *_ = browse_flat(warehouse_filter=second.id)

        assert pagination.total == 1
        assert units[0]["product"].name == "منتج بمستودع تاني"

    def test_the_original_warehouse_keeps_its_products(
        self, catalogue, db_session, make_product, make_location
    ):
        from models import Warehouse

        first = db_session.query(Warehouse).filter_by(
            name="مستودع اختبار"
        ).one()

        pagination, *_ = browse_flat(warehouse_filter=first.id)
        assert pagination.total == 7

    def test_includes_a_shelf_that_ran_out(
        self, catalogue, db_session, make_product, make_location
    ):
        from models import Warehouse

        empty = make_product(name="منتج خالص")
        make_location(empty, quantity=0, warehouse_name="مستودع ثالث")
        db_session.commit()

        third = db_session.query(Warehouse).filter_by(name="مستودع ثالث").one()
        pagination, units, *_ = browse_flat(warehouse_filter=third.id)

        assert pagination.total == 1
        assert units[0]["quantity"] == 0

    def test_no_filter_shows_everything(self, catalogue):
        assert browse_flat(warehouse_filter="")[0].total == 7

    def test_a_junk_warehouse_is_ignored(self, catalogue):
        pagination, _, _, _, warehouse_filter, _ = browse_flat(
            warehouse_filter="abc"
        )
        assert pagination.total == 7
        assert warehouse_filter == ""

    def test_an_unknown_warehouse_matches_nothing(self, catalogue):
        assert browse_flat(warehouse_filter=999999)[0].total == 0

    def test_combines_with_the_stock_filter(
        self, catalogue, db_session, make_product, make_location
    ):
        from models import Warehouse

        first = db_session.query(Warehouse).filter_by(
            name="مستودع اختبار"
        ).one()

        pagination, *_ = browse_flat(
            warehouse_filter=first.id, stock_filter="critical"
        )
        assert pagination.total == 2


class TestWarehouseFilterRoute:

    def test_the_dropdown_is_offered(self, catalogue, make_user, login):
        body = login(make_user()).get("/products").get_data(as_text=True)

        assert 'name="warehouse"' in body
        assert "كل المستودعات" in body
        assert "مستودع اختبار" in body

    def test_filtering_narrows_the_page(
        self, catalogue, db_session, make_user, login, make_product, make_location
    ):
        import re
        from models import Warehouse

        other = make_product(name="منتج بمستودع تاني")
        make_location(other, quantity=12, warehouse_name="مستودع ثاني")
        db_session.commit()

        second = db_session.query(Warehouse).filter_by(name="مستودع ثاني").one()

        body = login(make_user()).get(
            "/products?warehouse=%d" % second.id
        ).get_data(as_text=True)

        assert set(re.findall(r'/product/(\d+)"', body)) == {str(other.id)}

    def test_the_choice_stays_selected(
        self, catalogue, db_session, make_user, login
    ):
        from models import Warehouse

        first = db_session.query(Warehouse).filter_by(
            name="مستودع اختبار"
        ).one()

        body = login(make_user()).get(
            "/products?warehouse=%d" % first.id
        ).get_data(as_text=True)

        assert 'value="%d" selected' % first.id in body

    def test_paging_keeps_the_warehouse(
        self, catalogue, db_session, make_user, login
    ):
        import re
        from models import Warehouse

        first = db_session.query(Warehouse).filter_by(
            name="مستودع اختبار"
        ).one()

        body = login(make_user()).get(
            "/products?warehouse=%d&sort=name" % first.id
        ).get_data(as_text=True)

        links = re.findall(r'href="(/products\?[^"]*page=\d+[^"]*)"', body)
        for link in links:
            assert "warehouse=%d" % first.id in link

    def test_a_junk_value_does_not_break_the_page(
        self, catalogue, make_user, login
    ):
        response = login(make_user()).get("/products?warehouse=abc")
        assert response.status_code == 200
