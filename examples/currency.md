# Spec: `currency` — convert an amount and show what an FX margin costs

Add a `currency` command that converts an amount between two currencies at the interbank rate,
then shows what a provider's margin on that rate costs the customer.

## Interface

```text
<tool> currency AMOUNT PAIR [--margin PERCENT] [--output table|json]
```

- `AMOUNT` is a decimal number, e.g. `1000` or `1234.56`.
- `PAIR` is `BASE/QUOTE`, e.g. `GBP/AUD`. Case-insensitive.
- `--margin` / `-m` is the provider's margin as a percentage of the rate. Default `0`.
- `--output` / `-o` follows the existing scaffold option, including its environment variable.

## The service

[Frankfurter](https://frankfurter.dev/), which needs no key:

```text
GET https://api.frankfurter.dev/v1/latest?base=<BASE>&symbols=<QUOTE>
```

- Use the `.dev` host directly. `api.frankfurter.app` answers with a 301, and `httpx` does not
  follow redirects by default.
- The response is `{"amount": 1.0, "base": ..., "date": "YYYY-MM-DD", "rates": {"<QUOTE>":
  <number>}}`.
- A currency code it does not publish, as base or quote, is a **404** with
  `{"message": "not found"}`. The same code on both sides is a **422** with
  `{"message": "bad currency pair"}`.

## Arithmetic

**Every monetary value is a `Decimal`, and no value ever passes through a `float`** — not the
command-line amount, and not the rate in the response body. This is the requirement the spec
exists to test; margin arithmetic on floats is how a tool like this is wrong invisibly.

- effective rate = rate × (100 − margin) ÷ 100, quantized to six decimal places
- at interbank = amount × rate, quantized to cents
- you receive = amount × effective rate, quantized to cents
- cost of margin = at interbank − you receive, which must reconcile **exactly**

The conversion itself should be a pure function of the rate, the amount and the margin.

## Output

- **table**: titled with the pair and the rate's date; rows for amount, interbank rate, margin,
  effective rate, the amount at interbank, the amount received, and the cost of the margin.
- **json**: one object holding the same values, with every decimal rendered as a **string**, so
  no consumer parses it back into a float.

## Failure

| Situation | Exit | stdout | stderr |
|---|---|---|---|
| `PAIR` is not `XXX/YYY`, or `AMOUNT` / `--margin` is not a number | 2 | empty | names the bad value and the expected form |
| Currency not published (404), or base equal to quote (422) | 1 | empty | names both currencies and the service's message |
| Service unreachable, or any other HTTP error | 1 | empty | names the URL that failed |
| `AMOUNT` or `PAIR` missing | 2 | empty | the command's help, then the error |

## Tests that should exist

All offline — no test may reach the network.

- Pair parsing, including malformed pairs (`GBP`, `GBP/`, `/AUD`, `GBP/AUD/USD`).
- Decimal parsing is exact: `"0.1"` is exactly one tenth.
- Zero margin leaves the interbank amount untouched; a positive margin reduces what is received.
- The margin cost reconciles exactly, and amounts round to cents.
- A rate in the response body never becomes a float, e.g. a long rate survives digit for digit.
- An unpublished currency (404) and a same-currency pair (422) are errors naming both currencies;
  any other HTTP error status propagates.
- A client passed in by the caller is not closed.
- JSON keeps decimals as strings.
- Each failure row above: correct exit code, empty stdout.
