# Практические работы

Локальное приложение для заполнения структурированных отчётов и экспорта в ODT по шаблону колледжа.

## Запуск через Docker Compose

Нужен Docker Desktop с Compose v2. Скопируйте `.env.example` в `.env`, укажите данные студента и запустите из корня репозитория:

```powershell
Copy-Item .env.example .env
# Отредактируйте .env: REPORT_STUDENT, REPORT_SPECIALTY, REPORT_GROUP, REPORT_TEACHER, REPORT_CITY
docker compose up -d --build
```

Откройте <http://localhost:8000>. Compose собирает React-интерфейс и FastAPI в один контейнер. SQLite, загруженные файлы и экспорты сохраняются в локальном каталоге `./data`; данные переживают пересборку контейнера. Для резервной копии остановите приложение и скопируйте этот каталог.

Переменные профиля применяются только при первом создании базы. В уже существующей базе они не перезаписывают профиль. Его можно обновить через `PATCH /api/profile`, например:

```powershell
Invoke-RestMethod http://localhost:8000/api/profile -Method Patch -ContentType 'application/json' -Body '{"student":"Фамилия И.О.","specialty":"Специальность","group_name":"ГРУППА-1","teacher":"Преподаватель И.О.","city":"Город"}'
```

## Локальная разработка без Docker

Окно PowerShell 1:

```powershell
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

Окно PowerShell 2:

```powershell
cd frontend
npm ci
npm run dev
```

Откройте <http://127.0.0.1:5173>. Vite проксирует `/api` к FastAPI на порту 8000.

## Проверки

```powershell
cd backend
uv run pytest
cd ../frontend
npm run build
```

GitHub Actions выполняет эти проверки и собирает контейнер. Пуш в `main` публикует `ghcr.io/<владелец>/report-automation:latest`. Тег версии `v1.2.3` публикует версионный образ и создаёт GitHub Release.

Чтобы запустить опубликованный образ, задайте `APP_IMAGE=ghcr.io/<владелец>/report-automation:latest` в `.env`, затем выполните:

```powershell
docker compose pull
docker compose up -d --no-build
```

После первой публикации образа откройте его Package settings на GitHub и установите видимость **Public**, если он должен загружаться без авторизации.

## Данные

- `./data/reports.sqlite3` — база отчётов и профиля;
- `./data/reports/` — загруженные скриншоты;
- `./data/exports/` — экспортированные документы.

Не удаляйте `./data`, если хотите сохранить отчёты и изображения. Исходный шаблон в `backend/templates/report-template.odt` используется только для чтения.

## Функции

- предметы, отчёты, задания и шаги с сохранением порядка;
- локальный черновик браузера и автосохранение;
- загрузка PNG/JPG/WebP через выбор файла, перетаскивание и буфер обмена;
- независимое хранение файлов и привязок к шагам;
- серверная проверка заполненности;
- генерация ODT с форматированием шаблона и автоматически нумеруемыми рисунками.
