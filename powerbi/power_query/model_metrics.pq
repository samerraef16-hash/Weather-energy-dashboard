// model_metrics: paste into Home > Advanced Editor of a blank query named "model_metrics"
let
    Source = Csv.Document(
        Web.Contents(BaseUrl, [RelativePath = "model_metrics.csv"]),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Headers, {
        {"run_id", type text},
        {"building_id", type text},
        {"trained_at_utc", type datetime},
        {"train_rows", Int64.Type},
        {"test_rows", Int64.Type},
        {"mae_kwh", type number},
        {"mape_pct", type number},
        {"r2", type number},
        {"kwh_per_cooling_degree", type number},
        {"kwh_per_heating_degree", type number},
        {"anomalies_detected", Int64.Type},
        {"anomaly_recall_pct", type number}
    }, "en-US")
in
    Typed
