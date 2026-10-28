// pipeline_runs: paste into Home > Advanced Editor of a blank query named "pipeline_runs"
let
    Source = Csv.Document(
        Web.Contents(BaseUrl, [RelativePath = "pipeline_runs.csv"]),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Headers, {
        {"run_id", type text},
        {"started_at_utc", type datetime},
        {"finished_at_utc", type datetime},
        {"status", type text},
        {"weather_rows_fetched", Int64.Type},
        {"weather_rows_loaded", Int64.Type},
        {"energy_rows_loaded", Int64.Type},
        {"checks_passed", Int64.Type},
        {"checks_warned", Int64.Type},
        {"duration_seconds", type number},
        {"message", type text}
    }, "en-US")
in
    Typed
