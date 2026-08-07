# Date-Range SQL Template Processing Architecture

## Overview

This architecture enables dynamic date-range queries by:
1. Using SQL templates with placeholder tokens `[date_from]` and `[date_to]`
2. Processing templates for multiple date ranges (e.g., last 30 days)
3. Generating CSV files with appropriate naming conventions

## Folder Structure

```
gencsv/
├── sqltemplate/              # SQL templates with placeholders
│   ├── cl2_free_1.sql        # Contains [date_from], [date_to]
│   ├── ecoli_sql.sql
│   └── turby.sql
├── sql/                      # Generated SQL files (optional - for debugging)
├── output/                   # Generated CSV files
│   └── cl2_free_1_20260327_120219.csv
├── date_range_runner.py      # Main runner script
└── template_processor.py     # Template processing utilities
```

## SQL Template Format

Templates use `[date_from]` and `[date_to]` placeholders:

```sql
SELECT 
    sa.sampno,
    sa.loccode,
    sa.locdescr,
    sa.coldate,
    re.result
FROM samples sa
JOIN results re ON sa.sampno = re.sampno
WHERE sa.coldate BETWEEN '[date_from]' AND '[date_to]'
ORDER BY sa.coldate;
```

## Date Range Iteration Logic

For "last 30 days with 14-day ranges":

```
Run 1: date_from = 2026-02-25, date_to = 2026-03-11 (14 days)
Run 2: date_from = 2026-02-11, date_to = 2026-02-25 (14 days)
...
Run N: Continue until we cover 30 days back
```

## Output File Naming

Format: `{template_name}_{date_from}_{date_to}_{timestamp}.csv`

Example: `cl2_free_1_20260225_20260311_20260327_120219.csv`

## Usage

### Run for last 30 days with 14-day ranges:
```bash
cd gencsv
python date_range_runner.py --days 30 --range-days 14
```

### Run for a specific date range:
```bash
python date_range_runner.py --from 2026-03-01 --to 2026-03-15
```

### Run single day (today minus N days):
```bash
python date_range_runner.py --days 7 --single-day
```

## Integration with Existing Code

The `date_range_runner.py` will:
1. Read templates from `sqltemplate/`
2. Replace `[date_from]` and `[date_to]` placeholders
3. Call `execute_sql_to_csv()` from `db_connector.py`
4. Generate appropriately named CSV files in `output/`

This architecture maintains backward compatibility with the existing `main.py` for non-date-range operations.
