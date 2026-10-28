// fact_energy_daily_model: paste into Home > Advanced Editor of a blank query named "fact_energy_daily_model"
let
    Source = Csv.Document(
        Web.Contents(BaseUrl, [RelativePath = "fact_energy_daily_model.csv"]),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Headers, {
        {"date", type date},
        {"building_id", type text},
        {"actual_kwh", type number},
        {"predicted_kwh", type number},
        {"variance_kwh", type number}
    }, "en-US")
in
    Typed
