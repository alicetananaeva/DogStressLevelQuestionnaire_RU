# DSLQ RU App

Русскоязычная версия Streamlit-приложения **Dog Stress Level Questionnaire (DSLQ)** для скрининга уровня хронического стресса у собак.

Приложение показывает опросник, автоматически считает балл хронического стресса и, при согласии участника, сохраняет исследовательские данные в Supabase.

> Research-based web application · Python 3.10+ · Streamlit · Supabase

## Запуск

Из папки проекта:

```bash
streamlit run dslq_ru_app.py
```

## Структура проекта

```text
DSLQ_RU_App/
├── dslq_ru_app.py
├── Source/
│   ├── DSLQ_App_BehaviorItems.csv
│   ├── DSLQ_App_Copy.csv
│   ├── DSLQ_App_OptionalModules.csv
│   ├── DSLQ_App_ResponseOptions.csv
│   └── DSLQ_App_ScoringConfig.csv
├── .streamlit/
│   └── secrets.toml.example
├── requirements.txt
├── DATA_PRIVACY.md
├── CHANGELOG.md
└── README.md
```

## Supabase

Рекомендуемая схема для русской версии: отдельные таблицы от англоязычного приложения.

| Table | Contents |
|---|---|
| `dslq_ru_sessions` | Исследовательские записи при согласии на передачу анкетных и/или демографических данных |
| `dslq_ru_contacts` | Контактные данные для будущих исследований, если участник отдельно согласился на связь |

В Streamlit Secrets:

```toml
[supabase]
url = "your_supabase_url"
key = "your_supabase_anon_or_service_key"
sessions_table = "dslq_ru_sessions"
contacts_table = "dslq_ru_contacts"
```

## Важно

Математика подсчета и ключи ответов сохранены от оригинального DSLQ-приложения. Русифицированы пользовательские тексты, варианты ответов и интерфейс.

DSLQ является исследовательским инструментом. Результат приложения предназначен для скрининга и не является клиническим диагнозом.
