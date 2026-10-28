// fact_energy_forecast: paste into Home > Advanced Editor of a blank query named "fact_energy_forecast"
let
    Source = Csv.Document(
        Web.Contents(BaseUrl, [RelativePath = "fact_energy_forecast.csv"]),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Headers, {
        {"datetime_local", type datetime},
        {"date", type date},
        {"hour", Int64.Type},
        {"timestamp_utc", type datetime},
        {"building_id", type text},
        {"predicted_kwh", type number},
        {"temperature_2m", type number}
    }, "en-US")
in
    Typed
