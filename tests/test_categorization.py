# -*- coding: utf-8 -*-
"""The keyword rules that classify a product from its name.

These are the rules the back-fill script and the add-product form both use, so
a regression here silently mis-files new stock.
"""

import pytest

from utils.categorization import normalize, suggest_category_name


class TestNormalize:

    @pytest.mark.parametrize("raw, expected", [
        ("أبيض", "ابيض"),
        ("إبريق", "ابريق"),
        ("آخر", "اخر"),
        ("مصطفى", "مصطفي"),
        ("علبة", "علبه"),
        # collapses the spaces and folds the ة in one pass
        ("  مسافات   زايدة  ", "مسافات زايده"),
    ])
    def test_arabic_spelling_variants_collapse(self, raw, expected):
        assert normalize(raw) == expected

    def test_backslash_and_slash_are_the_same_neck_size(self):
        # the catalogue held both "28\\410" and "24/410"
        assert normalize("28\\410") == normalize("28/410")

    def test_empty_input_is_safe(self):
        assert normalize(None) == ""
        assert normalize("") == ""


class TestSuggestCategory:

    @pytest.mark.parametrize("name, expected", [
        # the real product names from the catalogue
        ("بمب PUMP", "بمبات وبخاخات"),
        ("بخاخ رخيص", "بمبات وبخاخات"),
        ("بمب سبريه مع غطاء", "بمبات وبخاخات"),
        ("غطاء بروتين", "أغطية"),
        ("غطاء كبس يوناني", "أغطية"),
        ("جار زجاج", "زجاج"),
        ("علب زجاج مطبوع DeSheli", "زجاج"),
        ("مرطبان PE", "جارات وعلب"),
        ("فانتوم اردني", "جارات وعلب"),
        ("تيوب DeSheli", "تيوبات وايرلس"),
        ("ايرلس مطبوع Soleimer", "تيوبات وايرلس"),
        ("بريفورم", "بريفورم وسدادات"),
        ("سدادة قطرة", "بريفورم وسدادات"),
        ("خل مائدة ابو تاج", "عبوات غذائية"),
        ("لبنة يوناني البينار", "عبوات غذائية"),
        ("علب خل مائدة الشنار", "عبوات غذائية"),
    ])
    def test_real_catalogue_names(self, name, expected):
        assert suggest_category_name(name) == expected

    def test_pump_beats_cap_when_both_words_appear(self):
        # "بمب سبريه مع غطاء" is a pump that ships with a cap, not a cap
        assert suggest_category_name("بمب سبريه مع غطاء") == "بمبات وبخاخات"

    def test_jar_with_a_cap_is_still_a_jar(self):
        # regression: this was filed under أغطية because "غطاء" appears
        assert suggest_category_name("جار زجاج مطبوع مع غطاء فضي") == "زجاج"

    @pytest.mark.parametrize("name", [
        "غطاء حديد للزجاج",
        "غطاء حديد للزجاح",   # the spelling actually in the catalogue
    ])
    def test_a_cap_for_glass_is_a_cap_not_glass(self, name):
        # "للزجاج" means *used for* glass — both spellings must behave the same
        assert suggest_category_name(name) == "أغطية"

    def test_polish_is_not_glass_packaging(self):
        assert suggest_category_name("ملمع زجاج") == "جارات وعلب"

    def test_food_wins_over_the_generic_container_rule(self):
        assert suggest_category_name("علب خل مائدة بدون ليبل") == "عبوات غذائية"

    def test_unknown_name_returns_none_rather_than_guessing(self):
        assert suggest_category_name("شغلة مش معروفة") is None
        assert suggest_category_name("") is None
