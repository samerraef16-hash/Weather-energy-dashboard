// dim_date: paste into Home > Advanced Editor of a blank query named "dim_date"
let
    Source = Csv.Document(
        Web.Contents(BaseUrl, [RelativePath = "dim_date.csv"]),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Headers, {
        {"date", type date},
        {"year", Int64.Type},
        {"quarter", type text},
        {"month_number", Int64.Type},
        {"month_name", type text},
        {"month_short", type text},
        {"year_month", type text},
        {"day_of_week_number", Int64.Type},
        {"day_name", type text},
        {"is_workday", type logical},
        {"season", type text}
    }, "en-US")
in
    Typed
