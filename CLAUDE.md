# jobsaggregator: заметки для Claude Code

## Что это
Робот, который читает вакансии из Telegram-каналов и складывает их в Google-таблицу без дублей.
Владелец не программист (врач, BA/PM): объясняй простыми словами, по-русски, иди по одному шагу,
перед каждым шагом коротко говори, что сейчас будет сделано и зачем.

## Как устроено
- `src/jobagg/sources/telegram_web.py`: открытые каналы через https://t.me/s/<канал>, без аккаунта.
- `src/jobagg/sources/telethon_src.py`: закрытые каналы через Telegram API (Telethon) от аккаунта владельца.
- `prefilter.py` (отсев мусора), `extract.py` (поля правилами, без AI), `dedupe.py` (дубли),
  `store.py` (CSV или Google Sheets), `main.py` (запуск, команда `jobagg`).
- Настройки: `config.yaml`. Ключи: `.env` (по образцу `.env.example`).
- Тесты: `.venv\Scripts\python -m pytest -q` (нужно `pip install -e ".[dev,telegram]"`).

## Где запускается
Компьютер владельца, Windows, PowerShell. Программа стоит в `.venv` в этой папке:
`.venv\Scripts\jobagg --dry-run` (без записи), `.venv\Scripts\jobagg` (запись в таблицу: `store.type: sheets`).
GitHub Actions используется только для проверки кода (CI) и ручной выгрузки постов, не для расписания:
закрытые каналы требуют постоянного IP, поэтому расписание на этом компьютере.

## Что уже сделано (2026-11-08)
- Программа установлена, пробный запуск по `opento_dev` работает.
- Вход в Telegram выполнен: файл `tg.session` в этой папке.
- Google-таблица «Телеграм», SHEET_ID `17PfgRq3nJ3aCnavsJZ0wA5IBCLNbxgBE7rB9Ok0vBOU`:
  лист «Вакансии» (выпадающий «Статус», закреплённая шапка), скрытый лист `_state`.
- Шаг 3 (2026-11-08): добавлены 5 каналов владельца. У всех открыта веб-версия, поэтому они в `channels`, а не в `telethon`:
  zarubezhom_jobs, runello_rus_datascience, dataviz_jobs, remote_jobs_relocate, choicy_work.
  `telethon.channels` пока пуст. Пробный `--dry-run`: 6 каналов прочитаны, 73 поста, 4 отсеяно, 69 вакансий.
- Фильтр поправлен: «вакансия» → «ваканси» (ловит «вакансии/вакансий»); в исключения добавлены `t.me/addlist`
  и «забрать папку» (реклама папок каналов). `scripts/tg_login.py` больше не падает на русских названиях.
- Замечено, но не исправлено (это работа извлечения, не фильтра): дайджесты дают одну строку с заголовком
  дайджеста вместо списка вакансий; в remote_jobs_relocate название берётся из компании/страны, а не из должности;
  в opento_dev отсеивается набор без слов-маркеров (например, «tech-набор в 01.tech»).

- Фильтрация в 3 шага, без AI (2026-11-08): 1) «вакансия» (prefilter), 2) «сфера» (`domain_keywords`,
  перед проверкой вырезаются бонусы из `domain_ignore_phrases`, например ДМС), 3) «роль» (`role_keywords`).
  Код: `src/jobagg/keywords.py`, списки в `config.yaml`, синтаксис `[слово]` / `слово*` описан там же.
  В таблице две новые колонки в конце: «Сфера (совпадение)», «Роль (совпадение)».
  SUMMARY считает not_vacancy / not_domain / not_role, в логе строка `channel ...` по каждому каналу.
  Проверка на 60 днях (431 пост, 6 каналов): осталось 13. Из подходящих: Veeva, CSM (Pharmacovigilance).
  Известные слабые места: дайджест проходит целиком из-за одной строки; `[МО]` срабатывает на
  «Московская область».
- Профиль владельца в фильтрах (2026-11-08): сфера и роли дополнены (онкология, геномика, медицинский AI,
  clinical data/research, medical affairs и др.), в роли добавлены «системным анализом», «solution(s) specialist».
  Новый шаг `role_exclude` («не мои роли»): слово оттуда и нет моих ролей → отброс (not_mine);
  есть и то, и другое → пост остаётся с пометкой «не моё: ...» в колонке «Роль (совпадение)».
  `my_experience` → колонки «Приоритет» (≥ `priority.high_from` совпадений = высокий, 1+ = средний) и «Совпадения».
  Короткие сокращения в my_experience стоят в [скобках] (AI, MD, NGS...), иначе ловятся внутри слов.
  Слова, одинаковые после «ё = е» (удален*/удалён*), считаются один раз.
  Проверка на 60 днях: осталось 14, высокий приоритет 0, средний 12. Каналы IT-шные; для профиля нужны
  медицинские/фарма-каналы.
- Шаг 5, запись в Google Sheets (2026-11-08): проект Google Cloud `jobsaggregator-514104`, Sheets API включён,
  service account `jobagg-writer@jobsaggregator-514104.iam.gserviceaccount.com` (роль «Редактор» в таблице),
  ключ `service_account.json` в этой папке (в .gitignore), в `.env` заданы SHEET_ID и GOOGLE_SA_FILE.
  5 тестовых строк удалены. Первый `jobagg --store sheets`: written=1 (Veeva, CSM Pharmacovigilance),
  программа сама дописала 4 колонки в конец (теперь 27). Второй запуск сразу: written=0. `store.type: sheets`.
  Замечено в строке Veeva (извлечение): «Компания» пустая, «Ссылка на вакансию» взята из чужой ссылки в посте.
- Шаг 6, расписание (2026-11-08): задание «jobagg» в Планировщике заданий Windows, раз в сутки в 16:00
  (с 2026-11-08 по просьбе владельца; время — параметр `-At` у install_task.ps1),
  пропущенный запуск выполняется как можно скорее, только при входе пользователя (без пароля), лимит 1 час.
  Создаётся/пересоздаётся `scripts\install_task.ps1`; запускает `scripts\run_scheduled.ps1`:
  вывод в `logs\jobagg.log` (дата и время в каждой строке, хранит 30 дней, `logs/` в .gitignore),
  при коде выхода не 0 — уведомление Windows с причиной; при успехе — «N новых вакансий» (высокий/средний
  приоритет из SUMMARY `high=` / `medium=`) или «новых вакансий нет», щелчок открывает таблицу
  (`-NoSuccessToast` выключает уведомление об успехе). .ps1 сохранены в UTF-8 с BOM (иначе PowerShell 5.1
  ломает русский текст). Пробный запуск из Планировщика: код 0; тест падения (`-Config` на несуществующий файл): код 1.

- 31 новый канал от владельца (2026-11-08), владелец решил читать все, ничего не удалять без его решения.
  Открытые (в `channels`, 27): sberlogajobs2, pharmed_recruitment, sci_career, stemjobs, bigtechjobs, jobsbt,
  Microbiotechjobs, clinicalresearchjobvacancies, Baprofessionals, jobs_pm, forproducts, Remoteit,
  hh_vacancy_medicine, careerfactory, productjobgo, jobsbiotech, pharmer_career, jobfeeds, newhrvacancies,
  rfoundersjobs, neurotechjobs, jobs_product_managers, lapainpharma, cpo_job, bluesky_bioinf, ratracerebellion,
  jobs_inarmenia. Закрытые (в `telethon.channels`, владелец состоит): projects_jobs_feed, products_jobs (группа),
  projects_jobs (группа), findmyremote_product. Всего каналов 37 (33 открытых + 4 закрытых).
  Проверка `jobagg --dry-run --days 60 --max-posts 1000`: 37/37 прочитаны, 4974 поста, итог 209, высокий 32.
  Больше всего дают: pharmed_recruitment (51, но это дайджесты), clinicalresearchjobvacancies (50),
  pharmer_career (29), findmyremote_product (17, 9 из них дайджесты «15 found»).
  Мёртвый за 60 дней: hh_vacancy_medicine. Картинок без текста больше половины — ни у кого (всего 106 из 4974).
  products_jobs и projects_jobs — группы с болтовнёй (≈92% «не вакансия»), упёрлись в лимит 1000 постов за 60 дней.
  Дубли: 15 (10 в том же канале, 4 между каналами, 1 уже в таблице).
- Новое в коде: `--days N` (перечитать N дней без учёта сохранённого места, для проверок), `--max-posts N`;
  в логе по каналу duplicates/high/no_text, строка `duplicate: ... first seen in ...`;
  Telethon больше не пропускает картинки без подписи (они считаются, затем отсеиваются префильтром).
  Исправлен дедуп: `norm_url` отрезал весь `?query`, и все ссылки вида `detail.php?ID=...` одного сайта
  склеивались в одну (pharmed_recruitment: 51 → 1). Теперь отрезаются только utm_*, mc_*, fbclid, gclid, yclid,
  ref, source.

## Следующие шаги
4. Закрытые каналы (если появятся): `config.yaml` → `telethon.channels` (формат `{name: "...", id: -100...}`).
   Список каналов с id печатает `.venv\Scripts\python scripts\tg_login.py` (повторный вход не нужен).
Потом: лист «Каналы» в таблице вместо списка в config.yaml, разбор дайджестов, AI-извлечение (Claude Haiku), Match.

## Правила
- Никогда не показывай, не копируй и не коммить секреты: `.env`, `tg.session`, `service_account.json`
  (они в `.gitignore`). Не проси владельца вставлять ключи в чат: пусть вписывает их в файлы сам.
- Код от Telegram и пароль 2FA владелец вводит сам: интерактивные команды входа запускает он.
- В таблице пишем только новые строки и по названиям колонок; ручные правки («Статус», свои колонки) не трогаем.
- Перед коммитом: `ruff check .`, `ruff format .`, тесты зелёные. Коммиты небольшие, по шагам.
