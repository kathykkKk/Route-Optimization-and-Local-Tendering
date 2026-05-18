# Route Optimization and Local Tendering

Система оптимизации маршрутов курьеров для логистики Ozon: назначение полигонов, TSP внутри и между полигонами, simulated annealing, rebalance и финальная доводка (LKH). Проект — модульный рефакторинг ноутбука `final optimization solution-Copy4.ipynb`.

---

## Технологии

| Категория | Стек |
|-----------|------|
| Язык | **Python 3.10+** |
| Данные | **Polars** (JSON), **SQLite** → memory-mapped **NumPy** |
| Оптимизация маршрутов | **Google OR-Tools** (Christofides, CBC MIP) |
| Ускорение | **Numba** (TSP DP в rebalance/SA) |
| Метаэвристики | **Simulated Annealing**, **DEAP** (генетический алгоритм в `SOTA/`) |
| Визуализация | **Matplotlib** |
| TSP (опционально) | **LKH-3** (бинарник), **AMPL + Gurobi** (`amplpy`) |
| Сборка пакета | **setuptools**, `pyproject.toml` |

---

## Требования

- **Python** ≥ 3.10  
- **RAM** — зависит от размера `distances.db` (mmap `distances.dat` загружается целиком)  
- **LKH-3** — только если `--polish-tsp-solver lkh` (по умолчанию)  
- **Gurobi + AMPL** — только если `--inner-tsp-solver branch_and_cut_gurobi`  

Опциональные зависимости:

```bash
pip install -e ".[dev]"    # pytest, ruff
pip install -e ".[ampl]"   # amplpy для Gurobi TSP
```

---

## Быстрый старт

### 1. Клонирование и переход в каталог

```bash
cd Route-Optimization-and-Local-Tendering
```

### 2. Виртуальное окружение

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Установка зависимостей

Минимальный набор (пайплайн + GA):

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Или установка пакета в editable-режиме (удобно для разработки):

```bash
pip install -e .
pip install -e ".[dev]"   # по желанию: тесты и линтер
```

### 4. Данные

Положите файлы в `data/raw/`:

| Файл | Описание |
|------|----------|
| `ml_ozon_logistic_dataSetOrders.json` | заказы по полигонам (MpId) |
| `ml_ozon_logistic_dataSetCouriers.json` | курьеры и service time по полигонам |
| `distances.db` | SQLite, таблица `distances(from_location, to_location, distance)` |

### 5. Подготовка индекса расстояний

Один раз (или после обновления `distances.db`):

```bash
python scripts/build_distances.py
```

Создаётся `data/processed/distances.dat` (отсортированный mmap-массив).

### 6. LKH (для polish по умолчанию)

Скачайте и соберите [LKH-3](http://webhotel4.ruc.dk/~keld/research/LKH-3/), затем положите исполняемый файл:

```
Route-Optimization-and-Local-Tendering/
└── LKH-3.0.13/
    └── LKH          # исполняемый файл
```

Путь настраивается в `Config.lkh_binary` (по умолчанию `LKH-3.0.13/LKH`).

Если LKH нет, при ошибке сработает fallback на Christofides (`polish_tsp_fallback_to_christofides=True`).

### 7. Запуск пайплайна

```bash
python -m optimization.pipeline.run_pipeline
```

Альтернатива (если установлен пакет через `pip install -e .`):

```bash
route-optimize
```

Результаты сохраняются в `output/`:

| Файл | Содержимое |
|------|------------|
| `optimized_routing.pkl` | маршруты после recombine |
| `each_polygon_opt_route.pkl` | маршруты внутри полигонов |
| `final_solution.pkl` | итог после polish |
| `final_each_polygon_opt_route.pkl` | обновлённые внутриполигональные маршруты |
| `time_history.pkl` | история целевой функции по времени |

---

## Структура проекта

```
Route-Optimization-and-Local-Tendering/
├── data/
│   ├── raw/                 # JSON, distances.db (не в git)
│   └── processed/           # distances.dat, cross_matrix.dat
├── optimization/
│   ├── config/              # Config — пути и гиперпараметры
│   ├── loaders/             # заказы, курьеры, расстояния
│   ├── preprocessing/       # матрицы, cross-memmap, маппинги
│   ├── solvers/
│   │   ├── tsp/             # TSP-оптимизаторы (см. ниже)
│   │   ├── courier_assignment.py
│   │   ├── recombine.py
│   │   ├── simulated_annealing.py
│   │   ├── rebalance.py
│   │   └── local_polish.py
│   ├── SOTA/                # генетический алгоритм (DEAP)
│   ├── models/
│   ├── utils/
│   └── pipeline/
│       └── run_pipeline.py  # точка входа
├── scripts/
│   └── build_distances.py
├── tests/
├── output/
├── docs/
│   └── GIT_WORKFLOW.md
├── requirements.txt
└── pyproject.toml
```

---

## Пайплайн: этапы

```mermaid
flowchart LR
  A[Load data] --> B[Assignment + inner TSP]
  B --> C[Cross matrix]
  C --> D[Recombine outer TSP]
  D --> E[Simulated annealing]
  E --> F[Rebalance]
  F --> G[Local polish LKH]
```

1. Загрузка заказов, курьеров, `distances.dat`  
2. **Assignment** — назначение полигонов курьерам (`solve_inner_tsp`)  
3. Построение **cross_matrix.dat** (расстояния между полигонами)  
4. **Recombine** — порядок полигонов у каждого курьера (`solve_outer_tsp`)  
5. **Simulated annealing** (можно отключить)  
6. **Rebalance** — swap/transfer перегруженных курьеров  
7. **Local polish** — порядок заказов внутри маршрута (`solve_polish_tsp`, по умолчанию LKH)  

---

## CLI: основной пайплайн

```bash
python -m optimization.pipeline.run_pipeline [OPTIONS]
```

| Флаг | Описание |
|------|----------|
| `--rebuild-distances` | Пересобрать `distances.dat` из SQLite |
| `--skip-sa` | Пропустить simulated annealing |
| `--skip-rebalance` | Пропустить rebalance |
| `--skip-polish` | Пропустить local polish |
| `--inner-tsp-solver` | `christofides` \| `branch_and_cut` \| `branch_and_cut_gurobi` (алиасы: `cbc_open`, `gurobi_ampl`) |
| `--polish-tsp-solver` | `lkh` (по умолчанию) \| `christofides` |

Примеры:

```bash
# Только базовые этапы (быстрее)
python -m optimization.pipeline.run_pipeline --skip-sa --skip-rebalance

# CBC для внутриполигонального TSP
python -m optimization.pipeline.run_pipeline --inner-tsp-solver branch_and_cut

# Polish без LKH
python -m optimization.pipeline.run_pipeline --polish-tsp-solver christofides
```

### Gurobi (опционально)

```bash
pip install amplpy
export AMPL_LICENSE_UUID=<ваш-uuid>
python -m optimization.pipeline.run_pipeline --inner-tsp-solver branch_and_cut_gurobi
```

---

## TSP-оптимизаторы

Каталог: `optimization/solvers/tsp/`

| Модуль | API | Этап |
|--------|-----|------|
| `christofides_inner.py` | `solve_inner_tsp()` | assignment |
| `christofides_outer.py` | `solve_outer_tsp()` | recombine, SA, rebalance |
| `branch_and_cut.py` | `solve_inner_tsp()` | assignment (MIP, CBC) |
| `branch_and_cut_gurobi.py` | `solve_inner_tsp()` | assignment (AMPL+Gurobi) |
| `lkh.py` | `solve_polish_tsp()` | local polish после rebalance |

Единая точка входа: `optimization/solvers/tsp/registry.py`.

Параметры в `optimization/config/config.py`: `inner_tsp_solver`, `polish_tsp_solver`, `lkh_binary`, `lkh_runs`, лимиты времени для MIP/Gurobi.

---

## SOTA: генетический алгоритм

Отдельный модуль `optimization/SOTA/` — DEAP-GA с seed из начального `routing_dict`.

```bash
# Подготовка (assignment + cross matrix) + GA
python -m optimization.SOTA.run_ga --quick-prep --population 300 --generations 100

# Seed из полного пайплайна
python -m optimization.SOTA.run_ga --use-pipeline-artifacts
```

Результаты: `output/ga_best_routing.pkl`, `ga_time_history.pkl`.

---

## Конфигурация

Все основные константы — в `optimization/config/config.py` (`Config`):

- лимит смены курьера: `max_courier_time_sec` (43 200 с)  
- штрафы: `penalty_per_order_sec`, `cross_polygon_punishment`  
- SA / rebalance: температуры, число итераций  
- TSP: `inner_tsp_solver`, `polish_tsp_solver`, `lkh_binary`  

Программно:

```python
from dataclasses import replace
from optimization.config.config import Config
from optimization.pipeline.run_pipeline import run_pipeline

cfg = replace(Config(), run_simulated_annealing=False, polish_tsp_solver="christofides")
run_pipeline(config=cfg)
```

---

## Тесты

```bash
pip install -e ".[dev]"
pytest
```

Или без pytest — smoke-проверка импортов TSP:

```bash
PYTHONPATH=. python -c "from optimization.solvers.tsp.registry import solve_inner_tsp; print('ok')"
```

---

## Устранение проблем

| Проблема | Решение |
|----------|---------|
| `FileNotFoundError: distances.db` | Положите БД в `data/raw/` |
| `FileNotFoundError: distances.dat` | Запустите `python scripts/build_distances.py` |
| `LKH binary not found` | Установите LKH в `LKH-3.0.13/LKH` или `--polish-tsp-solver christofides` |
| `No module named 'polars'` | `pip install -r requirements.txt` |
| `AMPL license UUID missing` | `export AMPL_LICENSE_UUID=...` или не используйте Gurobi solver |
| Долгий первый запуск | Нормально: построение `cross_matrix.dat` и SA |

---

## Разработка

```bash
# Линтер
ruff check optimization tests

# Git-история (ветки/коммиты)
# см. docs/GIT_WORKFLOW.md
```

---

## Лицензия

Уточните лицензию репозитория. Данные Ozon и бинарники LKH/Gurobi распространяются по своим условиям.
