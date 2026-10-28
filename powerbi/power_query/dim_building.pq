// dim_building: paste into Home > Advanced Editor of a blank query named "dim_building"
let
    Source = Csv.Document(
        Web.Contents(BaseUrl, [RelativePath = "dim_building.csv"]),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Headers, {
        {"building_id", type text},
        {"building_name", type text},
        {"building_type", type text},
        {"floor_area_m2", Int64.Type}
    }, "en-US")
in
    Typed
