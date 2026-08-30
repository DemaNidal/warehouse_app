# الاختبارات

## التشغيل

```bash
venv/Scripts/python.exe -m pytest
```

أول تشغيل بينشئ قاعدة بيانات اسمها `warehouse_db_test` وبيشغّل عليها كل
الـmigrations. **ما بتلمس `warehouse_db` أبداً** — وفي حماية بـ`conftest.py`
بترفض التشغيل لو الاسم ما بينتهي بـ`_test`.

كل اختبار بيبلّش بقاعدة فاضية: بعد ما يخلص بينعمل `TRUNCATE` لكل الجداول.

## شو مغطّى

| الملف | العدد | بيغطي |
|---|---|---|
| `test_inventory.py` | 15 | حركات المخزون، التحويلات، وقيود قاعدة البيانات |
| `test_permissions.py` | 28 | مين بيقدر يوصل لشو |
| `test_categorization.py` | 31 | قواعد تصنيف المنتجات من الاسم |
| `test_validation.py` | 28 | التحقق من نماذج الإدخال |
| `test_images.py` | 20 | ضغط الصور ورفض الملفات المزيّفة |

## أهم الاختبارات

**`test_taking_more_than_there_is_changes_nothing`** — بيتأكد إنه محاولة سحب
كمية أكبر من الموجود **ما بتغيّر المخزون ولا بتسجّل حركة**. هاي أخطر حالة
بالنظام كله.

**`test_a_transfer_moves_stock_without_creating_any`** — التحويل بين موقعين
لازم يخلي الإجمالي زي ما هو. لو صار خلل بالمنطق، بيظهر هون.

**`TestDatabaseConstraints`** — بتتأكد إنه قاعدة البيانات نفسها بترفض الكميات
السالبة، حتى لو كود جديد نسي الفحص.

**`test_a_cap_for_glass_is_a_cap_not_glass`** — `غطاء حديد للزجاج` لازم
ينصنّف "أغطية" مش "زجاج"، بالإملائين الاتنين الموجودين بالكتالوج.

## إضافة اختبار جديد

في fixtures جاهزة بـ`conftest.py`:

```python
def test_something(db_session, client, login, make_user, make_product, make_location):
    admin = make_user(role="ADMIN")
    product = make_product(name="منتج", minimum_stock=5)
    location = make_location(product, quantity=100)
    login(admin)
    ...
```

## ملاحظة

الاختبارات بتشتغل بـ`STORAGE_BACKEND=local` دايماً، فما بترفع ولا صورة على R2.
