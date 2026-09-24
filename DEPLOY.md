# النشر على سيرفر بدومين وHTTPS

دليل النقل من جهاز المكتب إلى سيرفر ثابت. بعده: رابط ثابت، HTTPS تلقائي،
والبيانات مش على جهازك.

**اللي بيسهّل الشغل:** الصور أصلاً على Cloudflare R2، وقاعدة البيانات ~10 ميجا.
النقل الفعلي دقايق؛ معظم الوقت بيروح على الإعداد الأول للسيرفر.

---

## التكلفة

| البند | التكلفة | ملاحظة |
|---|---|---|
| **الدومين** `.com` | ~12–15 دولار / **سنة** | أول سنة غالباً أرخص، التجديد أغلى شوي |
| **السيرفر (VPS)** | ~4–7 دولار / **شهر** | أصغر خطة كافية جداً لحجمك |
| **نسخ احتياطي للسيرفر** (اختياري) | ~1 دولار / شهر | ~20% من سعر السيرفر عند معظم المزوّدين |
| Cloudflare R2 (الصور) | مجاني | ضمن الحد المجاني (10 جيجا) — عندك 3 ميجا |
| شهادة HTTPS | مجاني | Let's Encrypt عبر Caddy |

**الإجمالي التقريبي: ~5–8 دولار بالشهر + ~15 دولار بالسنة للدومين.**

> الأسعار من معلوماتي وممكن تكون تغيّرت — تأكدي من صفحة المزوّد وقت الحجز.

**مزوّدين مقترحين للسيرفر** (كلهم بيقبلوا بطاقة دولية):
- **Hetzner** (ألمانيا) — الأرخص، جودة عالية، أقرب مركز بيانات لفلسطين. الخطة الأصغر (2 نواة / 4 جيجا) كافية.
- **DigitalOcean** — أغلى شوي، واجهة أسهل، توثيق ممتاز.

الجهاز اللي بتحتاجيه: **2 نواة، 2–4 جيجا رام، 40 جيجا قرص، Ubuntu 24.04**.

---

## ٠. قبل ما تبدأي — من جهازك

**احفظي الشغل على git وارفعيه.** السيرفر بيسحب الكود من GitHub، وعندك تعديلات كتير غير محفوظة:

```bash
cd E:\warehouse_app
git add -A
git commit -m "search, categories, duplicate guard, deployment files"
git push
```

تأكدي إنه `.env` **مش** ضمن اللي انرفع (هو بـ`.gitignore` أصلاً):

```bash
git ls-files | findstr /i "^.env$"
```

لازم ما يطلع شي.

---

## ١. الدومين

احجزي الدومين من أي مسجّل (Namecheap، Cloudflare Registrar، GoDaddy…).

بعد ما تنشئي السيرفر بالخطوة ٢ وتاخدي عنوانه، ارجعي لإعدادات DNS عند المسجّل
وأضيفي:

| النوع | الاسم | القيمة |
|---|---|---|
| A | `@` | عنوان السيرفر |
| A | `www` | عنوان السيرفر |

**انتظري لحد ما ينتشر** (من دقايق لساعة)، وتأكدي من جهازك:

```bash
nslookup yourdomain.com
```

لازم يرجّع عنوان السيرفر. **لا تكملي قبلها** — Caddy بدّه DNS صحيح عشان يجيب
الشهادة، وكل محاولة فاشلة بتتحسب عليكي عند Let's Encrypt (5 محاولات بالساعة).

---

## ٢. السيرفر

أنشئي السيرفر بالمواصفات فوق، واختاري مركز بيانات بأوروبا (ألمانيا أو فنلندا
عند Hetzner — أقرب من أمريكا والفرق بيبيّن).

وقت الإنشاء رح يطلب **مفتاح SSH** أو كلمة سر root. المفتاح أأمن. لو ما عندك:

```bash
ssh-keygen -t ed25519
```

وانسخي محتوى `C:\Users\Majd\.ssh\id_ed25519.pub` بخانة المفتاح عند المزوّد.

بعد الإنشاء، ادخلي:

```bash
ssh root@SERVER_IP
```

### تجهيز أساسي

```bash
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 git ufw
systemctl enable --now docker
```

### الجدار الناري

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

**5432 (قاعدة البيانات) و5000 (التطبيق) مش مفتوحين — مقصود.** Docker بيوصّلهم
داخلياً بين الحاويات، وما في داعي يكونوا مرئيين من الإنترنت.

### مستخدم غير root

```bash
adduser deploy
usermod -aG sudo,docker deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy/
```

اطلعي وادخلي كـ`deploy` — ومن هون ورايح كل الأوامر بهاد المستخدم:

```bash
ssh deploy@SERVER_IP
```

---

## ٣. المشروع والإعدادات

```bash
git clone https://github.com/USERNAME/REPO.git warehouse_app
cd warehouse_app
cp .env.example .env
nano .env
```

املئي كل القيم. للتوليد على السيرفر:

```bash
openssl rand -base64 32                                          # POSTGRES_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(48))"    # SECRET_KEY, RESTORE_SECRET, BOOTSTRAP_ADMIN_SECRET
```

**قيم R2** انسخيها من `.env` اللي على جهازك كما هي — نفس الحاوية، نفس الصور،
ما في داعي ننقل ولا صورة.

**`SECRET_KEY` لازم يكون جديد**، مش نفس اللي على جهازك.

بعدها:

```bash
chmod 600 .env
```

---

## ٤. التشغيل

```bash
docker compose up -d --build
docker compose logs -f
```

أول تشغيل بياخد دقيقتين: بناء الصورة، انتظار قاعدة البيانات، الترحيلات،
وCaddy بيجيب الشهادة. لما تشوفي `certificate obtained successfully` اضغطي
Ctrl+C وافتحي:

```
https://yourdomain.com
```

لازم تشوفي صفحة الدخول **بقفل أخضر**.

---

## ٥. نقل البيانات

قاعدة البيانات الجديدة فاضية (الترحيلات بنت الجداول بس). ننقل بياناتك.

### على جهازك (PowerShell)

```powershell
cd E:\warehouse_app
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" --no-owner --no-acl --format=custom --file=warehouse.dump "postgresql://USER:PASSWORD@localhost/warehouse_db"
```

(القيم من `DATABASE_URL` بملف `.env` عندك.)

ثم ارفعيه:

```powershell
scp warehouse.dump deploy@SERVER_IP:~/warehouse_app/
```

### على السيرفر

```bash
cd ~/warehouse_app
docker compose cp warehouse.dump db:/tmp/warehouse.dump
docker compose exec db pg_restore --clean --if-exists --no-owner --no-acl \
  -U warehouse -d warehouse_db /tmp/warehouse.dump
docker compose restart web
```

### تأكدي إنه وصل

```bash
docker compose exec db psql -U warehouse -d warehouse_db -c "select count(*) from product;"
```

لازم يطابق عدد منتجاتك على جهازك. وافتحي الموقع، سجّلي دخول **بنفس حسابك
القديم** (المستخدمين انتقلوا مع البيانات)، جرّبي البحث عن «اسود»، وتأكدي إنه
الصور بتظهر (يعني R2 موصول صح).

بعد ما تتأكدي، احذفي الملف — فيه كل بياناتك:

```bash
shred -u ~/warehouse_app/warehouse.dump
```

وعلى جهازك احذفي `E:\warehouse_app\warehouse.dump` كمان.

---

## ٦. النسخ الاحتياطي اليومي

النسخة بتنكتب داخل الحاوية **وبترفع على R2** — نسخة على نفس السيرفر بتضيع مع
السيرفر.

```bash
crontab -e
```

أضيفي:

```
0 2 * * * cd /home/deploy/warehouse_app && docker compose exec -T web python scripts/run_backup.py >> /home/deploy/backup.log 2>&1
```

جرّبيها مرة يدوياً قبل ما تعتمدي عليها:

```bash
docker compose exec -T web python scripts/run_backup.py
```

لازم تشوفي `Archive uploaded off-server`. وافحصي من لوحة Cloudflare إنها فعلاً
وصلت تحت مجلد `backups/` بالحاوية.

**الأهم: جرّبي الاسترجاع مرة.** نسخة ما جرّبتي استرجاعها مش نسخة احتياطية.

---

## ٧. تحديث الكود لاحقاً

من جهازك: `git push`. ومن السيرفر:

```bash
cd ~/warehouse_app
git pull
docker compose up -d --build
```

الترحيلات بتنطبق لحالها عند الإقلاع.

---

## ٨. بعد ما يستقر كل إشي

**١. أغلقي تحويل المنفذ على راوتر المكتب.** النظام كان مفتوح على
`http://213.6.239.66:5000` بدون تشفير — بعد النقل ما ضل له داعي.

**٢. أوقفي المهمة على جهازك** (لو سجّلتيها):

```bash
Unregister-ScheduledTask -TaskName WarehouseApp -Confirm:$false
```

**٣. المستخدمين الثانيين** بيدخلوا على `https://yourdomain.com` من أي مكان.

---

## أوامر بتنفعك

```bash
docker compose ps                        # شو شغّال
docker compose logs -f web               # سجل التطبيق
docker compose logs -f caddy             # مشاكل الشهادة
docker compose restart web               # إعادة تشغيل
docker compose down                      # إيقاف (البيانات بتضل)
docker compose exec db psql -U warehouse -d warehouse_db   # القاعدة مباشرة
```

**`docker compose down -v` بيحذف الـvolumes ومعها قاعدة البيانات كلها.**
لا تستخدميه إلا لو قاصدة، وبعد ما تتأكدي إنه في نسخة احتياطية.

---

## لما يصير في مشكلة

| العرض | السبب الغالب | الفحص |
|---|---|---|
| الشهادة ما إجت | DNS ما انتشر، أو 80/443 مسكّرين | `docker compose logs caddy` + `nslookup` |
| 502 Bad Gateway | التطبيق ما اشتغل | `docker compose logs web` |
| الصور ما بتظهر | قيم R2 ناقصة أو غلط بـ`.env` | قارنيها مع اللي على جهازك |
| بينطردني من الجلسة | `SECRET_KEY` تغيّر | لازم يكون ثابت |
| `CSRF session token is missing` | كوكي Secure على HTTP | افتحي بـ`https://` مش `http://` |
