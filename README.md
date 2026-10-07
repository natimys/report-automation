# Практические работы

Локальное приложение для заполнения структурированных отчётов и экспорта в ODT по шаблону колледжа.

## Запуск через Docker Compose (Linux)

Нужны Docker Engine и Docker Compose v2. Из корня репозитория:

```bash
cp .env.example .env
nano .env  # задайте REPORT_STUDENT, REPORT_SPECIALTY, REPORT_GROUP, REPORT_TEACHER и REPORT_CITY
docker compose up -d --build
```

Откройте <http://localhost:8000>. Compose собирает React-интерфейс и FastAPI в один контейнер. SQLite, загруженные файлы и экспорты сохраняются в `./data`; они переживают пересборку контейнера. Для резервной копии остановите приложение (`docker compose down`) и скопируйте этот каталог.

Учетные записи создаёт только администратор из командной строки; самостоятельной регистрации в приложении нет. После запуска добавьте пользователя так:

```bash
docker compose exec app /app/.venv/bin/python -m app.main create-user преподаватель1
```

Команда дважды запросит пароль (от 8 символов). Повторите её для каждого преподавателя. Для HTTPS укажите `AUTH_COOKIE_SECURE=true` в `.env`.

Если хотите запустить уже опубликованный образ из GHCR, укажите его в `.env`:

```dotenv
APP_IMAGE=ghcr.io/natimys/report-automation:latest
```

Затем выполните:

```bash
docker compose pull
docker compose up -d --no-build
```

Для получения образа без авторизации его пакет GHCR должен иметь видимость **Public**.

После входа профиль для титульного листа настраивается в разделе «Профиль»; он хранится отдельно у каждой учетной записи.

## Windows PowerShell

В PowerShell из корня репозитория:

```powershell
Copy-Item .env.example .env
notepad .env  # задайте REPORT_STUDENT, REPORT_SPECIALTY, REPORT_GROUP, REPORT_TEACHER и REPORT_CITY
docker compose up -d --build
```

Откройте <http://localhost:8000>. Чтобы запустить опубликованный образ, добавьте в `.env` строку `APP_IMAGE=ghcr.io/natimys/report-automation:latest`, затем выполните:

```powershell
docker compose pull
docker compose up -d --no-build
```

Создайте учетную запись преподавателя:

```powershell
docker compose exec app /app/.venv/bin/python -m app.main create-user преподаватель1
```

Введите пароль дважды в приглашениях. Для HTTPS задайте `AUTH_COOKIE_SECURE=true` в `.env`.

После входа профиль для титульного листа настраивается в разделе «Профиль».

## Локальная разработка без Docker (Linux)

В первом терминале:

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

Во втором терминале:

```bash
cd frontend
npm ci
npm run dev
```

Откройте <http://127.0.0.1:5173>. Vite проксирует `/api` к FastAPI на порту 8000.

В отдельном терминале создайте учетную запись: `cd backend && uv run python -m app.main create-user преподаватель1`.

## Локальная разработка в Windows PowerShell

Терминал 1:

```powershell
Set-Location backend
uv sync
uv run uvicorn app.main:app --reload
```

Терминал 2:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Откройте <http://127.0.0.1:5173>.

В отдельном терминале создайте учетную запись: `uv run python -m app.main create-user преподаватель1` из папки `backend`.

## Проверки и публикация

Локальные проверки (Linux):

```bash
cd backend && uv run pytest
cd ../frontend && npm ci && npm run build
```

GitHub Actions выполняет тесты, собирает и отправляет контейнер в GHCR. Пуш в `main` публикует `ghcr.io/natimys/report-automation:latest`. Пуш тега версии вида `v1.2.3` публикует версионный образ и создаёт GitHub Release. Обычный запуск workflow для `main` помечает job `release` как skipped — release создаётся только при событии с тегом `v*`. Для успешного создания release сначала должна успешно завершиться публикация образа.

Сейчас workflow собирает `linux/amd64` на штатном GitHub runner. Попытка собрать `linux/arm64` через QEMU завершалась `SIGILL` при выполнении `npm ci`; arm64 добавим после настройки нативного ARM runner.

## Данные

- `./data/reports.sqlite3` — база учетных записей, общих предметов и личных отчётов/профилей;
- `./data/reports/` — загруженные скриншоты;
- `./data/exports/` — экспортированные документы.

Не удаляйте `./data`, если хотите сохранить отчёты и изображения. Исходный шаблон в `backend/templates/report-template.odt` используется только для чтения.

## Функции

- вход по логину и паролю, учетные записи выдаёт администратор;
- общий для всех пользователей список предметов и преподавателей;
- личные отчёты, скриншоты и профиль каждого пользователя;
- предметы, отчёты, задания и шаги с сохранением порядка;
- локальный черновик браузера и автосохранение;
- загрузка PNG/JPG/WebP через выбор файла, перетаскивание и буфер обмена;
- независимое хранение файлов и привязок к шагам;
- серверная проверка заполненности;
- генерация ODT с форматированием шаблона и автоматически нумеруемыми рисунками.
