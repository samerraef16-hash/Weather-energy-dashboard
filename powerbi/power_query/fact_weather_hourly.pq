// fact_weather_hourly: paste into Home > Advanced Editor of a blank query named "fact_weather_hourly"
let
    Source = Csv.Document(
        Web.Contents(BaseUrl, [RelativePath = "fact_weather_hourly.csv"]),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Headers, {
        {"datetime_local", type datetime},
        {"date", type date},
        {"hour", Int64.Type},
        {"timestamp_utc", type datetime},
        {"temperature_2m", type number},
        {"apparent_temperature", type number},
        {"relative_humidity_2m", type number},
        {"cloud_cover", type number},
        {"wind_speed_10m", type number},
        {"shortwave_radiation", type number},
        {"precipitation", type number},
        {"is_forecast", Int64.Type},
        {"source", type text}
    }, "en-US")
in
    Typed
