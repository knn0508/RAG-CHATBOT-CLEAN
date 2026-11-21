"""Seed the app with SYNTHETIC demo data.

Creates:
  * a demo ``contacts`` table (30 fictional people) in ``CONTACTS_DB_FILE``
  * 3 sample HR documents (Azerbaijani, generic policy text) in ``example_docs/``

All names, positions and extensions are fictional.

Usage (from ``backend/``):
    python scripts/seed_demo_data.py
"""
import os
import sqlite3
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
EXAMPLE_DOCS = Path(os.getenv("EXAMPLE_DOCS_DIR", BACKEND_DIR.parent / "example_docs"))
CONTACTS_DB = Path(os.getenv("CONTACTS_DB_FILE", BACKEND_DIR / "contacts.db"))

DEPARTMENTS = [
    ("İnsan Resursları şöbəsi", "Kadr sektoru"),
    ("İnsan Resursları şöbəsi", "Əmək münasibətləri sektoru"),
    ("İT şöbəsi", "Dəstək sektoru"),
    ("İT şöbəsi", "Proqram təminatı sektoru"),
    ("Maliyyə şöbəsi", "Mühasibat sektoru"),
    ("Hüquq şöbəsi", "Müqavilələr sektoru"),
]
POSITIONS = ["Şöbə müdiri", "Sektor müdiri", "Baş mütəxəssis", "Aparıcı mütəxəssis", "Mütəxəssis"]


def build_contacts(count: int = 30):
    rows = []
    for i in range(1, count + 1):
        dept, sector = DEPARTMENTS[(i - 1) % len(DEPARTMENTS)]
        rows.append((
            "Demo",
            f"User {i:02d}",
            POSITIONS[(i - 1) % len(POSITIONS)],
            dept,
            sector,
            f"+994 50 000 {i:04d}",  # clearly fictional range
            str(1000 + i),
            "Demo City",
            f"demo.user{i:02d}@example.com",
        ))
    return rows


def seed_contacts(path: Path = CONTACTS_DB) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("DROP TABLE IF EXISTS contacts")
        conn.execute(
            """CREATE TABLE contacts (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   Ad TEXT, Soyad TEXT, "Vəzifə" TEXT, "Şöbə" TEXT, Sektor TEXT,
                   Mobil TEXT, Daxili TEXT, "Şəhər" TEXT, Email TEXT)"""
        )
        conn.executemany(
            'INSERT INTO contacts (Ad, Soyad, "Vəzifə", "Şöbə", Sektor, Mobil, Daxili, "Şəhər", Email) '
            "VALUES (?,?,?,?,?,?,?,?,?)",
            build_contacts(),
        )
        conn.commit()
        return conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    finally:
        conn.close()


DOCS = {
    "demo_leave_policy.txt": """Demo Şirkət – Məzuniyyət Siyasəti (nümunə sənəd)

1. Əsas ödənişli məzuniyyət
Hər bir işçi üçün illik əsas ödənişli məzuniyyət 21 təqvim günüdür.

2. Məzuniyyətin verilməsi qaydası
Məzuniyyət ərizəsi planlaşdırılan başlanğıc tarixindən ən azı 10 iş günü əvvəl
İnsan Resursları şöbəsinə təqdim olunmalıdır. Ərizə birbaşa rəhbər tərəfindən təsdiqlənir.

3. Əlavə məzuniyyət
Staja görə əlavə məzuniyyət: 5 ildən 10 ilədək staj üçün 2 gün, 10 ildən yuxarı staj üçün 4 gün.

4. Ödəniş
Məzuniyyət haqqı məzuniyyətin başlanmasından ən geci 3 iş günü əvvəl ödənilir.

Bu sənəd tamamilə uydurmadır və yalnız demo məqsədi daşıyır.
""",
    "demo_business_trip_rules.txt": """Demo Şirkət – Ezamiyyət Qaydaları (nümunə sənəd)

1. Ezamiyyət əmri
İşçinin ezamiyyətə göndərilməsi rəhbərin əmri ilə rəsmiləşdirilir. Əmrdə təyinat yeri,
müddət və məqsəd göstərilir.

2. Xərclər
Gündəlik yemək xərci, yaşayış və nəqliyyat xərcləri şirkət tərəfindən ödənilir.
Yaşayış xərcləri üçün gündəlik limit 80 manatdır.

3. Hesabat
Ezamiyyətdən qayıtdıqdan sonra 5 iş günü ərzində xərc sənədləri ilə birlikdə hesabat təqdim edilməlidir.

Bu sənəd tamamilə uydurmadır və yalnız demo məqsədi daşıyır.
""",
    "demo_work_rules.txt": """Demo Şirkət – Daxili Əmək Nizamnaməsi (nümunə sənəd)

1. İş saatları
İş vaxtı həftədə 5 gün, gündə 8 saatdır: saat 09:00-dan 18:00-dək, nahar fasiləsi 1 saatdır.

2. Xəstəlik vərəqəsi
Xəstəlik halında işçi bu barədə rəhbərinə dərhal məlumat verməli və xəstəlik vərəqəsini
işə qayıtdıqdan sonra 2 iş günü ərzində təqdim etməlidir.

3. Distant iş
Distant iş həftədə ən çox 2 gün olmaqla rəhbərlə razılaşdırılaraq həyata keçirilir.

Bu sənəd tamamilə uydurmadır və yalnız demo məqsədi daşıyır.
""",
}


def seed_documents(target: Path = EXAMPLE_DOCS) -> int:
    target.mkdir(parents=True, exist_ok=True)
    for name, body in DOCS.items():
        (target / name).write_text(body, encoding="utf-8")
    return len(DOCS)


if __name__ == "__main__":
    n = seed_contacts()
    d = seed_documents()
    print(f"Seeded {n} demo contacts into {CONTACTS_DB}")
    print(f"Wrote {d} demo documents into {EXAMPLE_DOCS}")
