// data_quality_checks: paste into Home > Advanced Editor of a blank query named "data_quality_checks"
let
    Source = Csv.Document(
        Web.Contents(BaseUrl, [RelativePath = "data_quality_checks.csv"]),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Headers, {
        {"run_id", type text},
        {"dataset", type text},
        {"check_name", type text},
        {"status", type text},
        {"rows_affected", Int64.Type},
        {"detail", type text},
        {"run_started_at_utc", type datetime}
    }, "en-US")
in
    Typed
