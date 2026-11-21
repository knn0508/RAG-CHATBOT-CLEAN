# RAG Chatbot (Azərbaycan dili)

Azərbaycan dilində HR/ofis sualları üçün sənədə əsaslanan çatbot. Admin sənədləri (PDF, DOCX, TXT, Excel) yükləyir;
backend mətni çıxarır, hissələrə bölür, ChromaDB-də indeksləyir və OpenAI modeli tapılan hissələrə əsasən cavab verir.
Əlavə olaraq əlaqə kitabçası axtarışı və şablon (məs. məzuniyyət ərizəsi) yükləmə imkanı var.

Repozitoriyada yalnız **uydurma demo məlumatlar** var.

## Sürətli başlanğıc

```bash
cp .env.example .env     # OPENAI_API_KEY, SECRET_KEY, JWT_SECRET_KEY doldurun
docker compose up --build
docker compose exec backend python scripts/seed_demo_data.py
```

http://localhost:3000 ünvanını açın. `ADMIN_PASSWORD` boş qalıbsa, təsadüfi admin parolu bir dəfə
`docker compose logs backend` çıxışında göstərilir.

Tam təlimat, konfiqurasiya cədvəli və API siyahısı üçün [README.md](README.md) faylına baxın (İngiliscə).
