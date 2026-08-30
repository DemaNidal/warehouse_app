# -*- coding: utf-8 -*-
"""Who is allowed to do what.

The storefront will add a second kind of visitor, so the boundaries around the
internal system need to be pinned down before that lands.
"""

import pytest


@pytest.fixture()
def admin(make_user):
    return make_user(username="an-admin", role="ADMIN")


@pytest.fixture()
def manager(make_user):
    return make_user(username="a-manager", role="STORE_MANAGER")


@pytest.fixture()
def employee(make_user):
    return make_user(username="an-employee", role="EMPLOYEE")


class TestAnonymousVisitors:
    """Nothing internal is readable without logging in."""

    @pytest.mark.parametrize("path", [
        "/", "/products", "/dashboard", "/add-product", "/add-category",
        "/add-size", "/add-color", "/settings", "/users", "/backups",
        "/activity-logs", "/transactions",
    ])
    def test_every_internal_page_redirects_to_login(self, client, path):
        response = client.get(path)
        assert response.status_code in (301, 302)
        assert "/login" in response.headers.get("Location", "")

    def test_writes_are_refused_too(self, client):
        response = client.post("/add-category", data={"name": "متسلل"})
        assert response.status_code in (301, 302, 401, 403)


class TestEmployeeLimits:
    """An employee reads the catalogue but does not administer it."""

    @pytest.mark.parametrize("path", [
        "/add-product", "/add-category", "/add-size", "/add-color",
    ])
    def test_cannot_reach_admin_screens(self, client, login, employee, path):
        login(employee)
        assert client.get(path).status_code == 403

    def test_can_still_browse_products(self, client, login, employee):
        login(employee)
        assert client.get("/products").status_code == 200

    def test_cannot_manage_users(self, client, login, employee):
        login(employee)
        assert client.get("/users").status_code == 403


class TestManagerLimits:
    """A manager runs the warehouse but is not an administrator."""

    def test_can_add_a_product(self, client, login, manager):
        login(manager)
        assert client.get("/add-product").status_code == 200

    def test_cannot_manage_users(self, client, login, manager):
        login(manager)
        assert client.get("/users").status_code == 403

    def test_cannot_reach_backups(self, client, login, manager):
        login(manager)
        assert client.get("/backups").status_code == 403

    def test_cannot_delete_a_category(self, client, login, manager, db_session):
        from models import Category

        category = Category(name="تصنيف", sort_order=1)
        db_session.add(category)
        db_session.flush()

        login(manager)
        response = client.post(f"/category/{category.id}/delete")
        assert response.status_code == 403
        assert db_session.get(Category, category.id) is not None


class TestAdminReach:

    @pytest.mark.parametrize("path", [
        "/products", "/dashboard", "/add-product", "/add-category",
        "/add-size", "/add-color", "/settings", "/users", "/backups",
    ])
    def test_admin_reaches_everything(self, client, login, admin, path):
        login(admin)
        assert client.get(path).status_code == 200


class TestReferentialGuards:
    """Things in use cannot be deleted out from under a product."""

    def test_a_category_in_use_cannot_be_deleted(
        self, client, login, admin, db_session, make_product
    ):
        from models import Category

        product = make_product()
        category_id = product.category_id

        login(admin)
        client.post(f"/category/{category_id}/delete", follow_redirects=True)

        assert db_session.get(Category, category_id) is not None

    def test_a_size_in_use_cannot_be_deleted(
        self, client, login, admin, db_session, make_product
    ):
        from models import Size

        product = make_product()
        size_id = product.size_id

        login(admin)
        client.post(f"/size/{size_id}/delete", follow_redirects=True)

        assert db_session.get(Size, size_id) is not None

    def test_an_unused_category_can_be_deleted(self, client, login, admin, db_session):
        from models import Category

        category = Category(name="تصنيف فاضي", sort_order=9)
        db_session.add(category)
        db_session.commit()
        category_id = category.id

        login(admin)
        client.post(f"/category/{category_id}/delete", follow_redirects=True)

        assert db_session.get(Category, category_id) is None
