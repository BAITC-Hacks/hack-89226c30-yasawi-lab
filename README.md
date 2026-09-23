# Wind Replay — HackAlem AI 2026

## О проекте

Проект разрабатывается в рамках **HackAlem AI 2026, Track 01 — Energy**.

Цель проекта — создать Agentic AI-систему для прогнозирования почасовой выработки ветроэлектростанции на горизонте **24–48 часов**.

Система должна использовать исторические данные работы двух ветротурбин, самостоятельно получать архивные прогнозы погоды, доступные на соответствующий момент времени, запускать модель прогнозирования и формировать почасовой прогноз нормализованной активной мощности.

## Официальная задача

Основные требования:

* построить модель прогнозирования на исторических данных;
* автоматически получать погодные прогнозы по координатам ВЭС;
* формировать прогноз на 24–48 часов с почасовой детализацией;
* реализовать Agentic AI workflow;
* воспроизвести исторический forecasting replay;
* использовать именно архивные прогнозы погоды, доступные на момент соответствующего прогноза;
* провести replay с 31 января 2026 года и далее в течение февраля 2026 года.

Подробное официальное ТЗ находится в:

```text
task.md
```

## Предоставленные данные

```text
data/
├── dataset_1.csv
└── dataset_2.csv
```

Принятое соответствие:

* `dataset_1.csv` → Wind Turbine 1
* `dataset_2.csv` → Wind Turbine 2

CSV содержат:

* ID;
* Statistical Time;
* Average Wind Speed, m/s;
* Normalized Active Power;
* Average Ambient Temperature, °C.

## Текущий стек

### Frontend

* React
* Vite

### Backend

* Python
* FastAPI
* Pydantic
* Uvicorn

### Data / ML

Будет определено по результатам реализации и проверки модели.

### Weather Data

Планируется использование архивных погодных прогнозов с подтверждаемым временем model run / availability.

## Архитектура

```text
React
  ↓
FastAPI
  ↓
Agentic Forecast Workflow
  ├── Historical Weather Retrieval
  ├── Data Validation
  ├── Forecast Model
  ├── Result Analysis
  └── Recalculation
  ↓
Structured JSON
  ↓
React Dashboard
```

## Структура проекта

```text
.
├── HACKATHON.md
├── task.md
├── README.md
├── data/
│   ├── dataset_1.csv
│   └── dataset_2.csv
├── backend/
└── frontend/
```

## Команда

### Developer 1

Frontend / Product / Demo

* React
* UI/UX
* charts
* forecast visualization
* API integration
* demo

### Developer 2

Backend / AI / Algorithms

* FastAPI
* data processing
* ML/modeling
* historical weather integration
* Agentic AI workflow
* API

## Статус

Проект находится в активной разработке в рамках 5-часовой соревновательной части HackAlem AI 2026.

Текущий этап:

```text
Task analysis
→ Dataset analysis
→ MVP definition
→ Implementation
```

## Важные допущения

На текущем этапе:

* CSV `Statistical Time` интерпретируется как `Asia/Almaty (UTC+05:00)` для MVP;
* это проектное допущение, а не подтверждённый факт официального датасета;
* прогнозируется только `Normalized Active Power`;
* MW/MWh не рассчитываются;
* формула нормализации мощности не предоставлена;
* исходные CSV не изменяются.

Все допущения будут явно документироваться и уточняться в процессе реализации.

## Запуск

Инструкции по установке и запуску будут добавлены после появления рабочего backend и frontend.

## Как проверить решение

Сценарий проверки будет добавлен после реализации первого end-to-end forecasting replay.

## Ограничения

Текущая версия находится в разработке.

Функции, которые ещё не реализованы, не должны считаться готовыми.

## Third-Party Components

Используемые библиотеки, API, AI-модели и внешние источники данных будут перечислены после фактической интеграции.
