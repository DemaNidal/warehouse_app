# -*- coding: utf-8 -*-
"""Keeping object storage in step with the database.

A photo goes to the bucket, the row goes to the database, and the two can fail
independently. Every combination that leaves them disagreeing shows up later as
either a file nobody references or a product whose image is a broken link, and
neither announces itself — the first only wastes space, the second is noticed
weeks later by whoever opens the page.

These tests pin down the ordering that keeps them together.
"""

import io

import pytest

from PIL import Image


def a_photo(name="photo.jpg", size=(80, 60), colour=(200, 60, 60)):
    """A real JPEG, because the upload path decodes and re-encodes it."""
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="JPEG")
    buffer.seek(0)
    return (buffer, name)


@pytest.fixture()
def bucket(monkeypatch):
    """Stand in for object storage and record every call."""

    saved = {}
    deleted = []

    def fake_save(data, key):
        saved[key] = data
        return key

    def fake_delete(key):
        deleted.append(key)
        saved.pop(key, None)
        return True

    monkeypatch.setattr("routes.product_routes.save_image", fake_save)
    monkeypatch.setattr("routes.product_routes.delete_image", fake_delete)

    return {"saved": saved, "deleted": deleted}


@pytest.fixture()
def form_bits(db_session):
    from models import Color, Category, Size, SIZE_KIND_CAPACITY

    colour = Color(name="أزرق اختبار", hex_code="#0000FF")
    category = Category(name="تصنيف اختبار للصور", sort_order=1)
    size = Size(name="700 مل اختبار", kind=SIZE_KIND_CAPACITY)
    db_session.add_all([colour, category, size])
    db_session.commit()

    return {"colour": colour, "category": category, "size": size}


def payload(form_bits, **over):
    data = {
        "name": "منتج بصورة",
        "color_id": form_bits["colour"].id,
        "secondary_color_id": "",
        "size_id": form_bits["size"].id,
        "neck_size_id": "",
        "category_id": form_bits["category"].id,
        "minimum_stock": "5",
    }
    data.update(over)
    return data


class TestAddingAProduct:

    def test_a_valid_add_stores_the_photo(
        self, bucket, form_bits, make_user, login
    ):
        from models import Product

        response = login(make_user()).post(
            "/add-product",
            data=payload(form_bits, image=a_photo()),
            content_type="multipart/form-data",
        )
        assert response.status_code == 302

        product = Product.query.filter_by(name="منتج بصورة").one()
        assert product.image
        assert product.image in bucket["saved"]
        assert bucket["deleted"] == []

    def test_a_rejected_form_uploads_nothing(
        self, bucket, form_bits, make_user, login
    ):
        """The bug this file exists for.

        The upload used to run before validation, so a form the server then
        refused still left its photo in the bucket forever.
        """
        from models import Product

        response = login(make_user()).post(
            "/add-product",
            # neither a capacity nor a neck size — the form is refused
            data=payload(form_bits, size_id="", neck_size_id="", image=a_photo()),
            content_type="multipart/form-data",
        )
        assert response.status_code == 302

        assert Product.query.filter_by(name="منتج بصورة").first() is None
        assert bucket["saved"] == {}

    def test_a_missing_name_uploads_nothing(
        self, bucket, form_bits, make_user, login
    ):
        login(make_user()).post(
            "/add-product",
            data=payload(form_bits, name="   ", image=a_photo()),
            content_type="multipart/form-data",
        )
        assert bucket["saved"] == {}

    def test_an_unsupported_file_type_uploads_nothing(
        self, bucket, form_bits, make_user, login
    ):
        from models import Product

        login(make_user()).post(
            "/add-product",
            data=payload(form_bits, image=(io.BytesIO(b"not a picture"), "notes.txt")),
            content_type="multipart/form-data",
        )

        assert bucket["saved"] == {}
        assert Product.query.filter_by(name="منتج بصورة").first() is None

    def test_a_failed_save_takes_the_photo_back_out(
        self, bucket, form_bits, make_user, login
    ):
        """A photo already in the bucket must not survive a row that was not."""
        from models import Product

        client = login(make_user())

        # a colour id that does not exist gets past the form check and fails on
        # the foreign key at commit time
        with pytest.raises(Exception):
            client.post(
                "/add-product",
                data=payload(form_bits, color_id=999999, image=a_photo()),
                content_type="multipart/form-data",
            )

        assert Product.query.filter_by(name="منتج بصورة").first() is None
        assert bucket["saved"] == {}, "the photo was left behind"
        assert len(bucket["deleted"]) == 1

    def test_adding_without_a_photo_is_fine(
        self, bucket, form_bits, make_user, login
    ):
        from models import Product

        response = login(make_user()).post(
            "/add-product",
            data=payload(form_bits),
            content_type="multipart/form-data",
        )
        assert response.status_code == 302

        product = Product.query.filter_by(name="منتج بصورة").one()
        assert product.image == ""
        assert bucket["saved"] == {}


class TestReplacingAPhoto:

    @pytest.fixture()
    def existing(self, db_session, make_product, form_bits):
        product = make_product(
            name="منتج قديم",
            color_id=form_bits["colour"].id,
            size_id=form_bits["size"].id,
            category_id=form_bits["category"].id,
        )
        product.image = "old-file.webp"
        db_session.commit()
        return product

    def test_the_old_file_is_removed_after_a_successful_save(
        self, bucket, existing, form_bits, make_user, login
    ):
        response = login(make_user()).post(
            "/product/%d/edit" % existing.id,
            data=payload(form_bits, name="منتج قديم", image=a_photo()),
            content_type="multipart/form-data",
        )
        assert response.status_code == 302

        assert existing.image != "old-file.webp"
        assert existing.image in bucket["saved"]
        assert bucket["deleted"] == ["old-file.webp"]

    def test_a_failed_save_keeps_the_old_file(
        self, bucket, existing, form_bits, make_user, login
    ):
        """The dangerous half of the same bug.

        Deleting the old file before the commit means a rolled-back product
        keeps a filename whose file is gone — a permanently broken image.
        """
        client = login(make_user())

        with pytest.raises(Exception):
            client.post(
                "/product/%d/edit" % existing.id,
                data=payload(form_bits, name="منتج قديم",
                             color_id=999999, image=a_photo()),
                content_type="multipart/form-data",
            )

        assert "old-file.webp" not in bucket["deleted"]
        # what was rolled back is the new upload, not the picture in use
        assert len(bucket["deleted"]) == 1
        assert bucket["saved"] == {}

    def test_editing_without_a_new_photo_touches_nothing(
        self, bucket, existing, form_bits, make_user, login
    ):
        response = login(make_user()).post(
            "/product/%d/edit" % existing.id,
            data=payload(form_bits, name="اسم جديد"),
            content_type="multipart/form-data",
        )
        assert response.status_code == 302

        assert existing.image == "old-file.webp"
        assert bucket["deleted"] == []
        assert bucket["saved"] == {}

    def test_a_rejected_edit_uploads_nothing(
        self, bucket, existing, form_bits, make_user, login
    ):
        login(make_user()).post(
            "/product/%d/edit" % existing.id,
            data=payload(form_bits, name="منتج قديم",
                         size_id="", neck_size_id="", image=a_photo()),
            content_type="multipart/form-data",
        )

        assert existing.image == "old-file.webp"
        assert bucket["saved"] == {}
        assert bucket["deleted"] == []
