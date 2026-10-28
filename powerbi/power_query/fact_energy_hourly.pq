// fact_energy_hourly: paste into Home > Advanced Editor of a blank query named "fact_energy_hourly"
let
    Source = Csv.Document(
        Web.Contents(BaseUrl, [RelativePath = "fact_energy_hourly.csv"]),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Headers, {
        {"datetime_local", type datetime},
        {"date", type date},
        {"hour", Int64.Type},
        {"timestamp_utc", type datetime},
        {"building_id", type text},
        {"energy_kwh", type number},
        {"hvac_kwh", type number},
        {"base_kwh", type number},
        {"occupancy_factor", type number},
        {"temperature_2m", type number},
        {"is_detected_anomaly", Int64.Type},
        {"cost", type number},
        {"co2_kg", type number}
    }, "en-US")
in
    Typed
