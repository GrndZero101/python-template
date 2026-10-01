# Spec: `geo` — look up coordinates for a place name

Add a `geo` command to the CLI that looks up the latitude and longitude of a town, village or city.

## Interface

```text
<tool> geo LOCATION... [--limit N] [--timeout SECONDS] [--output table|json]
```

- `LOCATION` is free text and may be several words: `geo cleve, south australia` searches for
  `cleve, south australia`. At least one word is required.
- `--limit` caps the number of matches. Default 10, minimum 1.
- `--timeout` is the request timeout in seconds. Default 10.
- `--output` / `-o` follows the existing scaffold option, including its environment variable.
- `--limit` and `--timeout` are settings: each also reads an environment variable, with the flag
  winning, exactly like `--output`.
- The global `--verbose` logs the outgoing query to stderr.

## The service

[Nominatim](https://nominatim.org/release-docs/latest/api/Search/), OpenStreetMap's geocoder:

```text
GET https://nominatim.openstreetmap.org/search?q=<query>&format=json&limit=<n>
```

- Its [usage policy](https://operations.osmfoundation.org/policies/nominatim/) **requires a
  descriptive `User-Agent`**. The default `httpx` one is rejected with HTTP 403.
- At most one request per second. One request per invocation satisfies that without throttling.
- The response is a JSON array. Each element carries `display_name`, `lat` and `lon` (both
  **strings**), and `type` (may be absent).

## Output

- **table**: one row per match — latitude and longitude to six decimal places, the place type, and
  the display name.
- **json**: one array of objects with `display_name`, `latitude`, `longitude` (numbers) and
  `place_type`. Note the field names differ from the API's.

## Failure

| Situation | Exit | stdout | stderr |
|---|---|---|---|
| No matches | 1 | empty | says nothing matched, naming the query |
| Service unreachable or HTTP error | 1 | empty | names the URL that failed |
| No `LOCATION` given | 2 | empty | the command's help, then the error |

## Tests that should exist

All offline — no test may reach the network.

- A match is parsed from the response body into the model, including the string-to-number
  conversion of `lat` and `lon`.
- Every match is returned; an empty array returns an empty list.
- An HTTP error status propagates from the lookup function.
- A client passed in by the caller is not closed by the lookup.
- The JSON rendering uses the output field names, not the API's.
- Multi-word locations are joined into one query.
- Both failure rows above: correct exit code, empty stdout.
