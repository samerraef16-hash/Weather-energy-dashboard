# Power BI Guide: Building the Dashboard Step by Step

> **The finished report is already in this repository** as
> `El Gouna weather.pbip`: open it in Power BI Desktop and click **Refresh**.
> This guide shows how to build the same thing by hand, which is the best way
> to learn how it works. Your page layout can differ from the finished report.

This guide assumes you have **never connected Power BI to online data before**.
Follow the steps in order. Plan for 2–4 hours the first time.

**What you will end up with:** a 4-page report that loads its data straight
from this GitHub repository. Whenever the daily pipeline has added new data,
one click on **Refresh** updates every chart.

```
GitHub (CSV files, updated daily by GitHub Actions)
        │  https://raw.githubusercontent.com/.../data/powerbi/*.csv
        ▼
Power Query (downloads + sets column types)  →  Data model (relationships)
        →  DAX measures (the numbers)  →  Report pages (the visuals)
```

---

## Step 0: Before you start

1. Install **Power BI Desktop** from the Microsoft Store (free).
2. Make sure the repository is **public** on GitHub and the pipeline has run
   at least once. Open this link in your browser; you should see CSV text:
   <https://raw.githubusercontent.com/samerraef16-hash/weather-energy-dashboard/main/data/powerbi/dim_building.csv>
3. Keep this repository folder open. You will copy text from
   `powerbi/power_query/` and `powerbi/measures.dax`.

> **Vocabulary**
> - **Query**: a recipe Power BI uses to fetch and clean one table.
> - **Power Query Editor**: the window where queries live (Home → Transform data).
> - **Relationship**: a link between two tables on a shared column (e.g. `building_id`).
> - **Measure**: a formula written in DAX that calculates a number for a visual (e.g. Total kWh).
> - **Fact table**: many rows of events/measurements (hourly kWh). **Dimension table**: descriptions (buildings, dates).

---

## Step 1: Create the `BaseUrl` parameter

All tables are loaded from the same GitHub folder. Storing that address once,
as a parameter, means you could point the whole report somewhere else by
changing one value.

1. Open Power BI Desktop → **Blank report**.
2. **Home → Transform data**. The Power Query Editor opens.
3. **Home → Manage Parameters → New Parameter**.
4. Fill in:
   - Name: `BaseUrl`
   - Type: **Text**
   - Current Value: `https://raw.githubusercontent.com/samerraef16-hash/weather-energy-dashboard/main/data/powerbi/`
     (keep the `/` at the end)
5. Click **OK**.

---

## Step 2: Load the 10 tables

You will do this 10 times, once per file in `powerbi/power_query/` (skip `BaseUrl.pq`).

1. In the Power Query Editor: **Home → New Source → Blank Query**.
2. **Home → Advanced Editor**. Delete everything in the box.
3. Open the matching `.pq` file (for example `powerbi/power_query/dim_building.pq`),
   copy **everything**, and paste it in. Click **Done**.
4. In the **Query Settings** pane on the right, rename the query from `Query1`
   to the file name **exactly**, e.g. `dim_building`. The DAX measures rely on these names.

The very first time, Power BI asks how to connect to `raw.githubusercontent.com`:
choose **Anonymous**, select the top-level URL `https://raw.githubusercontent.com/`
in the dropdown, then **Connect**.

Load these tables:

| Query name | What it contains |
|---|---|
| `dim_date` | one row per day (month names, Egyptian work week, season) |
| `dim_building` | the 3 buildings and their floor areas |
| `fact_energy_hourly` | hourly kWh, HVAC split, cost, CO₂ per building (the main table) |
| `fact_weather_hourly` | hourly weather, actual + 7-day forecast |
| `fact_energy_daily_model` | daily actual vs. model-predicted kWh |
| `fact_energy_forecast` | predicted kWh for the next 7 days |
| `fact_anomalies` | hours with abnormally high consumption |
| `model_metrics` | model accuracy per building per run |
| `pipeline_runs` | log of every automated run |
| `data_quality_checks` | results of the validation checks |

When all 10 are in the left-hand list: **Home → Close & Apply**. Loading takes a minute.

> **Why paste code instead of clicking Get Data → Web?** That also works, but
> you would then have to fix every column's data type by hand. The scripts set
> all types correctly, using `en-US` number format so decimals load the same on
> any Windows language setting.

---

## Step 3: Create the relationships

Click the **Model view** icon on the far left (the third icon, the one that
looks like a diagram). Power BI may have guessed some relationships; delete any
that are not in this list (right-click the line → Delete).

To create one, drag a column from one table and drop it onto the matching
column of the other table.

| From (one side, "1") | To (many side, "*") |
|---|---|
| `dim_date[date]` | `fact_energy_hourly[date]` |
| `dim_date[date]` | `fact_weather_hourly[date]` |
| `dim_date[date]` | `fact_energy_daily_model[date]` |
| `dim_date[date]` | `fact_energy_forecast[date]` |
| `dim_date[date]` | `fact_anomalies[date]` |
| `dim_building[building_id]` | `fact_energy_hourly[building_id]` |
| `dim_building[building_id]` | `fact_energy_daily_model[building_id]` |
| `dim_building[building_id]` | `fact_energy_forecast[building_id]` |
| `dim_building[building_id]` | `fact_anomalies[building_id]` |
| `dim_building[building_id]` | `model_metrics[building_id]` |

For each relationship, double-click the line and check:
**Cardinality = One to many (1:*)** and **Cross filter direction = Single**.

`pipeline_runs` and `data_quality_checks` stay unconnected; they are only
used on the Pipeline Health page.

This layout is called a **star schema**: dimensions in the middle filter the
fact tables around them. It's the layout Power BI is designed for, and a
good thing to mention in interviews.

---

## Step 4: Set up the date table

1. In the **Data view** (table icon on the left) select `dim_date`.
2. **Table tools → Mark as date table** → choose the `date` column → OK.
   This makes the "same period last year" measures work.
3. Fix the sort order, so months don't show alphabetically (April, August, …):
   - Click the `month_name` column → **Column tools → Sort by column → month_number**.
   - Do the same for `month_short` → `month_number`.
   - `day_name` → **Sort by column** → `day_of_week_number` (the week starts on Sunday, as in Egypt).

---

## Step 5: Add the measures

1. **Home → Enter Data**. Name the table `_Measures`, leave it empty, click **Load**.
2. Open `powerbi/measures.dax`. For **each** measure (each block starting with
   `Name =`):
   - Right-click `_Measures` in the Data pane → **New measure**.
   - Paste the whole block (name, `=`, and formula) into the formula bar → press **Enter**.
3. Once all measures are in, delete the default `Column1` from `_Measures`.
   The table jumps to the top of the field list with a calculator icon.
4. Format the measures (select a measure → **Measure tools** ribbon):
   - `HVAC Share %`, `kWh YoY %`, `Model Variance %`, `Successful Runs %` → **Percentage**, 1 decimal.
   - kWh, cost and tonne measures → **Whole number** with thousands separator.

If a measure shows a red underline, a table or column name doesn't match.
Check the query names from Step 2.

---

## Step 6: Build the report pages

Turn on **View → Gridlines** and **Snap to grid** for neat alignment.
Pick a theme under **View → Themes** (e.g. *Executive*) for consistent colours.

To create a visual: click an empty spot of the canvas, pick the visual type in
the **Visualizations** pane, then drag fields into its wells (X-axis, Y-axis, …).

### Page 1: Overview

| Visual | Settings |
|---|---|
| Slicer | Field: `dim_date[date]` → style **Between** |
| Slicer | Field: `dim_building[building_name]` → style **Dropdown** |
| 5 × Card | `Total kWh`, `Total Cost`, `CO2 Tonnes`, `Peak Demand kW`, `kWh YoY %` |
| Line and clustered column chart | X-axis: `dim_date[year_month]` · Column y-axis: `Total kWh` · Line y-axis: `Avg Temperature C` · Title: *Monthly consumption vs. temperature* |
| Clustered bar chart | Y-axis: `dim_building[building_name]` · X-axis: `Total kWh` |
| Card | `Data Freshness Label` (small, top-right corner) |

**What it shows:** consumption rises and falls with temperature through the year.

### Page 2: Weather Impact

| Visual | Settings |
|---|---|
| Scatter chart | Values: `dim_date[date]` · X-axis: `Avg Temperature C` · Y-axis: `Total kWh` · Legend: `dim_building[building_name]` · Title: *Daily kWh vs. temperature* |
| Matrix (heatmap) | Rows: `fact_energy_hourly[hour]` · Columns: `dim_date[day_name]` · Values: `Total kWh` → Format → **Cell elements → Background color: On** |
| Stacked area chart | X-axis: `dim_date[year_month]` · Y-axis: `HVAC kWh`, `Base kWh` |
| 3 × Card | `Cooling Sensitivity kWh per C`, `HVAC Share %`, `Hot Hours` |

**What it shows:** above roughly 24 °C every extra degree adds load (the scatter
"bends upward"). The heatmap shows the office's Sunday–Thursday working pattern.

### Page 3: Forecast & Model

| Visual | Settings |
|---|---|
| Line chart | X-axis: `fact_energy_forecast[datetime_local]` · Y-axis: `fact_energy_forecast[predicted_kwh]` (Sum) · Legend: `dim_building[building_name]` · Title: *Next 7 days predicted load* |
| Line chart | X-axis: `dim_date[date]` · Y-axis: `Model Actual kWh`, `Model Predicted kWh` · Filters pane → `dim_date[date]` → **Relative date** → *is in the last 90 days* |
| 4 × Card | `Forecast kWh Next 7 Days`, `Forecast Cost Next 7 Days`, `Latest Model MAPE %`, `Latest Model R2` |
| Table | `fact_anomalies[datetime_local]`, `dim_building[building_name]`, `fact_anomalies[actual_kwh]`, `[predicted_kwh]`, `[excess_kwh]`, `[temperature_2m]` · sort by `datetime_local` descending |

> When you drop a date/time field on an X-axis, Power BI may turn it into a
> "Date Hierarchy" (Year/Quarter/Month/Day). Click the small arrow next to
> the field in the X-axis well and choose the field name itself instead.

### Page 4: Pipeline Health

| Visual | Settings |
|---|---|
| 4 × Card | `Data Freshness Label`, `Latest Run Status`, `Successful Runs %`, `Checks Warned Latest Run` |
| Table | `pipeline_runs`: `started_at_utc`, `status`, `weather_rows_loaded`, `energy_rows_loaded`, `duration_seconds`, `message` · sort descending |
| Table | `data_quality_checks`: `run_started_at_utc`, `dataset`, `check_name`, `status`, `rows_affected`, `detail` · conditional formatting on `status` (pass = green, warn = amber, fail = red) |
| Line chart | X-axis: `pipeline_runs[started_at_utc]` · Y-axis: `duration_seconds` |

**What it shows:** that the automation works, with proof that every day's data
was checked before it reached the dashboard. Recruiters like this page.

---

## Step 7: Save and refresh

1. **File → Save as** → `powerbi/WeatherEnergyDashboard.pbix` inside this repository.
2. **To get new data:** open the file and click **Home → Refresh**. Power BI
   re-downloads the CSVs from GitHub, which GitHub Actions updated that morning.
   There's nothing to copy, export or paste.
3. Take screenshots of each page (Windows: `Win + Shift + S`), save them as
   `docs/images/overview.png`, `weather.png`, `forecast.png`, `pipeline.png`.
   The README displays them.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `DataSource.Error: 404 Not Found` | The repo is private, not pushed yet, or the URL in `BaseUrl` has a typo. Test the URL in a browser. |
| Asked for credentials again / access denied | **File → Options and settings → Data source settings** → select `raw.githubusercontent.com` → **Edit Permissions** → Anonymous. |
| `Formula.Firewall` error | **File → Options and settings → Options → Current File → Privacy** → *Ignore the Privacy Levels*. (Safe here: all data is public.) |
| Measure shows an error | The query names must match exactly: `fact_energy_hourly`, not `fact_energy_hourly (2)`. |
| Months sorted alphabetically | Step 4, *Sort by column*. |
| Refresh shows yesterday's data | GitHub caches raw files for ~5 minutes. Check the Actions tab to see whether today's run has finished. |
| `kWh YoY %` is blank | Normal for dates with no data a year earlier (history starts in January 2025). |

Stuck? Copy the exact error message, or a screenshot, into Claude Code and ask.
