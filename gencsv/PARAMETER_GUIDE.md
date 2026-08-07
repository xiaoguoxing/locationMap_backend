# Date Range Runner - Parameter Guide

## Basic Usage

```bash
python date_range_runner.py [OPTIONS]
```

## Parameters Explained

### `--days N`
How many days back from today to process.
- Example: `--days 14` means "start from 14 days ago"
- Default: 30

### `--range-days N` 
Size of each date range window in days.
- Example: `--range-days 7` creates 7-day windows
- Default: 14

### `--from YYYY-MM-DD` and `--to YYYY-MM-DD`
Specific date range to process (instead of "days back").
- Example: `--from 2025-12-01 --to 2025-12-31`

### `--single-day`
Process each day individually (no ranges).
- Creates one query per day
- Useful for daily snapshots

## Example Scenarios

### Scenario 1: Last 30 days in 14-day chunks
```bash
python date_range_runner.py --days 30 --range-days 14
```
Result: 2-3 queries covering 30 days

### Scenario 2: Specific month with weekly windows
```bash
python date_range_runner.py --from 2025-12-01 --to 2025-12-31 --range-days 7
```
Result: ~5 queries, each 7 days

### Scenario 3: Daily snapshots for past week
```bash
python date_range_runner.py --days 7 --single-day
```
Result: 7 queries, one per day

### Scenario 4: Backward-looking 14-day window for each day
```bash
python date_range_runner.py --days 30 --range-days 14
```
For each date, looks back 14 days (inclusive):
- Dec 1: Nov 18 - Dec 1 (14 days)
- Dec 2: Nov 19 - Dec 2 (14 days)
- etc.

## Output File Naming

Generated CSV files follow this pattern:
```
{template_name}_{date_from}_{date_to}_{timestamp}.csv
```

Example:
```
cl2_free_1_2025-12-01_2025-12-14_20260327_120219.csv
```

## Date Format in SQL Templates

Use `[date_from]` and `[date_to]` placeholders in your SQL:

```sql
SELECT * FROM samples
WHERE coldate BETWEEN [date_from] AND [date_to]
```

These will be replaced with actual dates like:
```sql
WHERE coldate BETWEEN '2025-12-01' AND '2025-12-14'
```
