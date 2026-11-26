# Обзор проекта — «Service Company»

> Статус: сверено с кодом и запуском **2026-11-25**.
> Активный канал — VK; папка проекта очищена от старого кода и артефактов.
> При изменениях архитектуры править этот файл целиком и дописывать `changes.md`.

## Что это

Система записи и учёта автосервиса (кузовной ремонт / PDR). Клиенты записываются
через VK-бота, смотрят свои записи, авто, историю работ и контакты. Администратор
ведёт клиентов, услуги, записи, журнал работ, статистику и расписание через
**веб-админку** `http://localhost:8000/admin`. Бэкенд — FastAPI, использует
заголовки `platform` (`vk`) и `user-id`. Клиенты склеиваются по номеру телефона,
поэтому дубли карточек при повторной регистрации не создаётся.

## Стек и сервисы (`docker-compose.yml`)

| Сервис | Стек | Порт | Назначение |
|---|---|---|---|
| `postgres` | postgres:15 | 5432 | БД `autoservice` |
| `redis` | redis:7 | — | брокер Celery |
| `minio` | bitnamilegacy/minio:latest | 9000/9001 | остался в compose, но в текущем коде не используется; официальный образ исчез с Docker Hub |
| `migrate` | Alembic | — | одноразово применяет миграции после готовности PostgreSQL и до старта backend/воркера |
| `backend` | FastAPI, SQLAlchemy(async), asyncpg, Alembic, openpyxl | 8000 | REST API (`/docs`, `/health`) + раздача веб-админки `/admin` |
| `vk_bot` | vkbottle | — | клиентский сценарий записи + уведомления админу в VK |
| `celery_worker` | Celery + Beat | — | напоминания о записях в VK (две стадии, каждые 5 минут) |

Конфиг: `pydantic-settings` в backend (`app/core/config.py`) читает только
`DB_*` и `HMAC_SECRET`; бот и воркер читают нужные переменные через `os.getenv`.
Корневой `.env` подключается через `env_file: .env`, лишние ключи backend игнорирует.

Переменные окружения:
- backend: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
  `HMAC_SECRET` (пароль веб-админки, заголовок `x-admin-secret`).
- Redis/Celery: `REDIS_URL` — брокер для `celery_worker` и polling-кэш VK-бота.
- MinIO: `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` использует только сервис `minio`
  в compose; кодом проекта не применяется. `ENCRYPTION_KEY` зарезервирован,
  шифрования нет. `BACKEND_INTERNAL_URL` нужен VK-боту.
- VK: `VK_GROUP_TOKEN`, `VK_GROUP_ID` (для `messages.send` и `group_id`),
  `ADMIN_VK_ID` — VK id администратора для уведомлений; без него нотификации
  пишут только предупреждение в лог.
- Сборка Python-образов использует build-арги `HTTP_PROXY`/`HTTPS_PROXY`
  (`http://http.docker.internal:3128`) и `PIP_INDEX_URL`
  (`https://mirrors.aliyun.com/pypi/simple/`). VK-боту важен
  `AiohttpClient(trust_env=True)`, иначе aiohttp не использует прокси.

## Запуск на этом ПК (2026-11-25)

- Windows 11 IoT LTSC + WSL2 (`Ubuntu`) + Docker Desktop 29.9.3.
- `docker compose up -d --build --wait` поднимает сервисы: PostgreSQL и Redis имеют
  healthcheck, сервис `migrate` применяет Alembic-ревизии, backend/vk_bot/celery_worker
  стартуют только после успешных миграций. Ручной `alembic upgrade head` больше не нужен.
  В локальной БД применены все 10 ревизий (включая уникальность `completed_works`).
- `GET /health` → `{"status":"ok"}`; `GET /admin` → веб-админка (HTTP 200);
  `/api/v1/schedule` отдаёт `timezone: "UTC"`, `/api/v1/services` → `[]`,
  `/api/v1/contacts` — дефолтный текст.
- `GET /api/v1/admin/schedule` без `x-admin-secret` → 403, с правильным
  `HMAC_SECRET` → 200. Проверено через FastAPI TestClient и живой curl.
- Контейнеры `backend`, `celery_worker`, `vk_bot` перезапущены после правок;
  VK-бот вышел в polling, Celery Beat + воркер готовы, traceback в логах нет.
- В реальном `.env` заданы VK-переменные; `ADMIN_VK_ID` нужно проверить перед
  приёмом уведомлений администратором.

## Структура каталогов

```
backend/app/
  main.py                 # FastAPI: /health, include api_router, раздача /admin и /admin/
  web/admin.html          # single-file веб-админка (vanilla JS, без внешних ассетов)
  core/{config,database}.py
  api/v1/
    router.py             # префикс /api/v1
    clients.py            # register, clients/me, склейка клиентов по телефону
    cars.py               # список/добавление/правка/мягкое удаление авто
    services.py           # активные услуги (с is_pdr)
    appointments.py       # слоты, мои записи, создание, отмена, перенос, /works/my
    contacts.py           # публичные контакты из settings
    admin.py              # админ-эндпоинты; require_admin: только x-admin-secret=HMAC_SECRET;
                          # client_vk_id в записях/работах
  models/                 # SQLAlchemy-модели (см. ниже)
  services/
    schedule.py           # расписание + validate_schedule
    clients.py            # склейка клиентов по телефону
    contacts.py           # contacts_text с дефолтом
    works_export.py       # Excel журнала работ
    service_export.py     # Excel по одной услуге (оплаты + история цены)
    clients_export.py     # Excel базы клиентов и авто
  migrations/             # Alembic, 9 ревизий
bot_vk/
  bot.py                  # диспетчер по тексту кнопок + пошаговые сценарии
  api_client.py           # клиент backend с platform="vk", таймаут 10 c и лог не-2xx
  keyboards.py            # обычные клавиатуры, ≤4 кнопки в ряд, лимит подписи 40
  state.py                # сессии в памяти процесса
  schedule_utils.py       # доступные даты/время
  texts.py, config.py
  vk_notify.py            # уведомления админу в VK через messages.send
celery_worker/tasks.py    # Celery Beat: напоминания в VK (две стадии)
start.bat / start.sh      # запуск compose, миграций и логов vk_bot
PROJECT_MEMORY/           # overview.md, changes.md, README.md
```

## Модели БД (`backend/app/models/`)

- `User` + `PlatformAccount` — аккаунт на платформе (`vk`), `external_id`, имя,
  телефон; уникальность — по паре `(platform, external_id)`.
- `Client` — профиль (имя, телефон, `is_active` для мягкого удаления).
- `Car` — авто клиента (марка, модель, номер, VIN, комментарий, `is_active`).
- `Service` — услуга (цена «от», длительность, `is_active`, `is_pdr`) +
  `ServicePriceHistory` (история цены «от»).
- `Appointment` — запись (client/car/service, start/end, статус
  `booked`/`completed`/`cancelled`/`no_show`, `cancelled_by` = master/client,
  `reminded_at`, `reminded_soon_at`).
- `CompletedWork` — журнал работ (`actual_price`, `total_amount`, `master_comment`,
  `performed_at`, описание/доп. работы); создаётся при завершении записи.
- `Setting` — key-value: `timezone`, `work_hours`, `work_days`,
  `non_working_dates`, `remind_hours`, `remind_hours_2`, `contacts_text`.

> `DamageRequest`/`DamageRequestPhoto` и эндпоинты заявок на оценку вмятин в коде
> отсутствуют — таблицы остались только в первой миграции.

## API (`/api/v1`)

Клиентские запросы идут с заголовками `platform: vk` и `user-id`. Админ-эндпоинты
защищены `require_admin`: только `x-admin-secret: <HMAC_SECRET>`. Пустой секрет
не проходит. JWT и подписи bodies нет.

Клиентские:
- `GET /health` (корень), `GET /schedule`, `GET /services`, `GET /contacts`;
- `POST /users/register` (создаёт User + PlatformAccount + Client, склейка по телефону);
- `GET/PATCH /clients/me` (имя + телефон), `GET /works/my`;
- `GET/POST /cars`, `PATCH/DELETE /cars/{id}`;
- `GET /appointments/slots?date=YYYY-MM-DD&service_id=…` — занятые интервалы;
  PDR-услуги не пересекаются с обычными;
- `GET /appointments/my`, `POST /appointments` (проверка расписания и конфликтов → 409;
  перед проверкой слота `pg_advisory_xact_lock` по типу услуги, PDR и обычные отдельно),
  `POST /appointments/{id}/cancel`, `POST /appointments/{id}/reschedule` (тот же замок).

Админ (`/admin`, всё под `Depends(require_admin)`):
- clients: `GET/POST /clients`, `PATCH/DELETE /clients/{id}`,
  `POST /clients/merge`, `GET /clients/export`;
- services: `GET/POST /services`, `PATCH /services/{id}`,
  `GET /services/{id}/price-history`, `GET /services/{id}/export`;
- appointments: `GET /appointments` (включая `client_vk_id`),
  `PATCH /appointments/{id}` (при `status=completed` нужна фактическая цена → `CompletedWork`);
- works: `GET /works?month=YYYY-MM`, `GET /works/export`, `GET/PATCH /works/{id}`
  (в карточке `client_vk_id`, `client_vk_username`);
- `GET /stats?days=`, `GET/PATCH /schedule`, `GET/PATCH /contacts`.

Excel-выгрузки генерируются бэкендом (`openpyxl`) и скачиваются из веб-админки:
журнал работ, клиенты+авто, одна услуга (оплаты + история цены «от»). Все
колонки с nick/id теперь только VK.

## Расписание и напоминания

`services/schedule.py`: настройки в `Setting`; `timezone` = IANA-имя (по умолчанию
`UTC`), `work_hours` = `09:00-20:00` **в этой таймзоне**, `work_days` = `1..7`
(1 = Пн), `non_working_dates` = пусто, `remind_hours` = 24, `remind_hours_2` = 3.
`validate_schedule(start, end, schedule)` возвращает текст ошибки на русском или
`None`; проверка дней/часов идёт в таймзоне сервиса. В БД время хранится в UTC,
API и админка показывают его в настройке `timezone`.

`celery_worker/tasks.py`: Beat каждые 5 минут запускает `send_reminders`; две стадии
(за 24 ч → `reminded_at`, за 3 ч → `reminded_soon_at`), окно поиска 15–60 мин.
Выборка берёт только `platform_accounts.platform = 'vk'`, `peer_id` =
`external_id`. Напоминания уходят через VK API (`messages.send` от имени
сообщества); текст простой, без HTML. Метки в БД проставляются **только при
успешной отправке**. Ошибки VK API пишутся в лог; неудачные записи получают
`reminder_failures`/`reminder_last_error_at` и повторяются с задержкой 5→10→20→40→
60 минут вместо попытки каждые 5 минут.

## Веб-админка

`GET /admin` отдаёт `backend/app/web/admin.html` — один файл без внешних JS/CSS.
При входе запрашивает `HMAC_SECRET`, сохраняет его в `sessionStorage` и прикладывает
к админ-запросам как `x-admin-secret`. Разделы: Обзор (stats), Клиенты (поиск,
создание, правка, удаление, склейка, экспорт), Услуги (создание/правка, история цен,
экспорт), Записи (список с VK-id, смена статуса, фактическая цена), Работы (месяц,
правка, экспорт), Настройки (timezone, work_hours, work_days, non_working_dates,
remind_hours/remind_hours_2, contacts). В таблицах есть ссылки `vk.com/id…`.

## VK-бот (vkbottle)

- «🔧 Записаться» → услуга → авто (или добавить) → список ближайших дат с
  «Ещё даты» → время → телефон (если нет в профиле) → подтверждение;
- «📋 Мои записи» с отменой, «🚘 Мои авто», «🧾 История работ», «👤 Профиль»
  (имя/телефон), «📞 Контакты» (HTML-теги из backend срезаются);
- состояние диалога — `state.py` (словарь по `user_id` в памяти процесса);
  при старте `_ensure_registered` вызывает `/users/register` с `platform=vk`;
- занятость считается через `/appointments/slots` с `service_id` (PDR-услуги не
  пересекаются с обычными); даты/время — `schedule_utils.py`;
- `vk_notify.py` шлёт админу (`ADMIN_VK_ID`) уведомления о новой записи и отмене
  через VK API; при отсутствии токена/id только пишет предупреждение в лог;
- админ-панели в боте нет — управление только через браузер.

## Нюансы и хрупкие места

- «📞 Контакты» сбрасывает сессию так же, как остальные команды меню.
- `vkbottle`/`aiohttp` в `bot_vk/requirements.txt` без фиксации версий; автотестов
  нет — только ручные проверки API и static-сверка кнопок.
- Админ-эндпоинты защищены только заголовком `x-admin-secret`. Это не подпись
  запроса: секрет нужно хранить в `.env` и не отдавать клиентам. Браузер держит
  его в `sessionStorage`.
- Связанные lazy-load обрабатываются явной подгрузкой (`await db.get(User, …)`,
  `selectinload`) — известная проблема MissingGreenlet, не ломать.
- Compose публикует 5432/9000/9001 на хост и монтирует код через bind mounts —
  это dev-конфигурация; для прода нужен отдельный compose без монтирований и без
  открытых наружу портов БД/MinIO.
- `.env` содержит реальные секреты и исключён из git через `.gitignore`; сам
  git-репозиторий существует (`.git/`), первый коммит `e5c18b7` от 2026-08-09.
  История коммитов и append-only `changes.md` хранят старые записи — это
  исторический лог, не активный код.
