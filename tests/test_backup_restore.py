# -*- coding: utf-8 -*-
"""Restoring a backup — the one path where the application reads a file
somebody else may have written.

A .zip handed to the restore form is not necessarily one this application
produced, and two places used to trust it completely:

  * column names came out of the archive's JSON and went into the generated
    INSERT with nothing around them but a pair of quotes, so a key carrying
    a quote wrote its own SQL;
  * the archive's uploads folder was copied in wholesale, into the directory
    the application serves from its own origin — so a .html in the archive
    became a page running as the site.

Both are covered here, along with the thing that fixing the first one also
fixed: an archive taken before a column was dropped used to abort the whole
restore, at the one moment a restore cannot be allowed to fail.
"""

import json

import pytest
from sqlalchemy import text

from utils import backup
from utils.backup import _schema_columns, restore_table, restore_uploads


def archived_table(tmp_path, table, rows):
    """Write `rows` as the archive would, and return the data directory."""

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    (data_dir / f"{table}.json").write_text(
        json.dumps(rows, ensure_ascii=False), encoding="utf-8"
    )

    return str(data_dir)


class TestColumnNamesComeFromTheSchema:

    def test_schema_columns_reports_what_the_table_really_has(self, db_session):
        assert {"id", "name", "hex_code"} <= _schema_columns("color")

    def test_an_ordinary_archive_restores(self, db_session, tmp_path):
        data_dir = archived_table(tmp_path, "color", [
            {"id": 1, "name": "أزرق", "hex_code": "#2563EB"},
            {"id": 2, "name": "أحمر", "hex_code": "#DC2626"},
        ])

        restore_table("color", data_dir)

        rows = db_session.execute(
            text('SELECT id, name, hex_code FROM "color" ORDER BY id')
        ).all()

        assert rows == [(1, "أزرق", "#2563EB"), (2, "أحمر", "#DC2626")]

    def test_a_crafted_column_name_cannot_write_its_own_sql(self, db_session, tmp_path):
        attack = 'hex_code" ) ; DROP TABLE "color" ; --'

        data_dir = archived_table(tmp_path, "color", [{
            "id": 1,
            "name": "أزرق",
            "hex_code": "#2563EB",
            attack: "pwned",
        }])

        restore_table("color", data_dir)

        assert _schema_columns("color"), "الجدول لازم يضل موجود"

        row = db_session.execute(
            text('SELECT name, hex_code FROM "color" WHERE id = 1')
        ).first()

        assert row == ("أزرق", "#2563EB"), "الأعمدة المعروفة لازم تنحفظ عادي"

    def test_a_column_the_schema_no_longer_has_is_dropped_not_fatal(
        self, db_session, tmp_path
    ):
        # an archive taken before the column was removed
        data_dir = archived_table(tmp_path, "color", [
            {"id": 1, "name": "أزرق", "hex_code": "#2563EB", "retired_column": "x"},
        ])

        restore_table("color", data_dir)

        row = db_session.execute(
            text('SELECT name FROM "color" WHERE id = 1')
        ).first()

        assert row == ("أزرق",), "عمود قديم ما لازم يوقّف الاسترجاع كله"

    def test_a_table_with_no_recognisable_column_is_skipped(self, db_session, tmp_path):
        data_dir = archived_table(tmp_path, "color", [{"nothing_real": 1}])

        restore_table("color", data_dir)

        count = db_session.execute(
            text('SELECT count(*) FROM "color"')
        ).scalar()

        assert count == 0

    def test_a_table_missing_from_the_archive_is_skipped(self, db_session, tmp_path):
        data_dir = archived_table(tmp_path, "color", [])

        restore_table("size", data_dir)  # no size.json at all

        assert db_session.execute(text('SELECT count(*) FROM "size"')).scalar() == 0


class TestOnlyImagesAreRestored:

    @pytest.fixture()
    def archive(self, tmp_path, monkeypatch):
        """An extracted archive, and the live uploads folder it restores into."""

        live = tmp_path / "uploads_live"
        live.mkdir()
        monkeypatch.setattr(backup, "UPLOAD_FOLDER", str(live))

        extracted = tmp_path / "extracted"
        (extracted / "uploads").mkdir(parents=True)

        return extracted, live

    def test_an_image_is_restored(self, archive):
        extracted, live = archive
        (extracted / "uploads" / "abc_photo.webp").write_bytes(b"RIFF----WEBPVP8 ")

        restored, refused = restore_uploads(str(extracted))

        assert restored == 1
        assert refused == []
        assert (live / "abc_photo.webp").exists()

    @pytest.mark.parametrize("name", [
        "evil.html",
        "evil.svg",      # carries script, and the browser runs it
        "evil.htm",
        "shell.php",
        "notes.txt",
        "noextension",
    ])
    def test_anything_that_is_not_an_image_is_refused(self, archive, name):
        extracted, live = archive
        (extracted / "uploads" / name).write_text("<script>alert(1)</script>")

        restored, refused = restore_uploads(str(extracted))

        assert restored == 0
        assert name in refused
        assert not (live / name).exists(), \
            f"«{name}» بمجلد الصور بينخدم من نفس أصل التطبيق"

    def test_the_extension_check_ignores_case(self, archive):
        extracted, live = archive
        (extracted / "uploads" / "PHOTO.PNG").write_bytes(b"\x89PNG\r\n\x1a\n")

        restored, refused = restore_uploads(str(extracted))

        assert restored == 1
        assert (live / "PHOTO.PNG").exists()

    def test_the_images_survive_an_archive_that_also_carries_a_page(self, archive):
        extracted, live = archive
        (extracted / "uploads" / "a.webp").write_bytes(b"RIFF----WEBPVP8 ")
        (extracted / "uploads" / "evil.html").write_text("<script>alert(1)</script>")
        (extracted / "uploads" / "b.jpg").write_bytes(b"\xff\xd8\xff")

        restored, refused = restore_uploads(str(extracted))

        assert restored == 2
        assert refused == ["evil.html"]
        assert (live / "a.webp").exists() and (live / "b.jpg").exists()
        assert not (live / "evil.html").exists()

    def test_an_archive_with_no_uploads_folder_is_fine(self, archive, tmp_path):
        empty = tmp_path / "no_uploads"
        empty.mkdir()

        assert restore_uploads(str(empty)) is None
