# STREAM history fixtures

`stream_md_examples.json` holds the response examples of stream.md, section
"Historical data" (POST /iot-open/sign/device/quota/data), one per metric code,
for the request `beginTime` 2025-09-18 00:00:00 / `endTime` 2025-09-18 23:59:59
on the main SN. Copied verbatim, including the mix of numeric and string
`indexValue` and the lowercase `"wh"` unit.

Responses for other days are derived from these in the tests (values scaled per
day); malformed and error responses are written in the tests themselves and
are not recordings.
