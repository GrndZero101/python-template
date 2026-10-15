# pydantic, dataclasses and SQLModel

Which to use where, and how to model an API whose shape is not the one you want.

- **`BaseModel`** at the edges — API responses, config files, anything untrusted. Validate once on
  the way in, then pass the validated object around; do not re-validate in every function.
- **`dataclass`** for everything internal, per CLAUDE.md. Cheaper, and its `repr` is just as
  readable in the debugger.
- **`pydantic-settings`** for configuration precedence — see **Configuration** above. Pass the
  resolved `Settings` down as a parameter; never read it from a module-level global.
- **SQLModel**: create the session at the command boundary and pass it down; never open one in a
  leaf function. Tests bind an in-memory SQLite engine.

## When the API shape is not the model shape

`Model.model_validate(raw)` works directly only when the API happens to return the field names the
model wants. Plenty of APIs do not — they nest the payload under a single-element list, or
name things `temp_C`, or return numbers as strings. The tempting response is to reshape a
`dict[str, Any]` by hand and hand the result to the model, which puts an `Any` in the signature and
gives up validation on the way in.

Use an **alias and a validator** instead, so the model still owns parsing:

```python
class Reading(BaseModel):
    """One observation, as this API happens to express it."""

    model_config = ConfigDict(populate_by_name=True)

    temperature_c: float = Field(alias="temp_C")
    humidity_percent: int = Field(alias="humidity")

    @field_validator("temperature_c", "humidity_percent", mode="before")
    @classmethod
    def _coerce_numeric_string(cls, value: object) -> object:
        """This API returns its numbers as strings; let pydantic do the conversion."""
        return value
```

When the interesting object is buried, index to it and validate *that* — the indexing expression is
typed, the reshaping is not:

```python
def parse_reading(payload: dict[str, list[dict[str, str]]]) -> Reading:
    """Return the current observation from a `j1`-style body."""
    current = payload["current_condition"][0]
    return Reading.model_validate(current)
```

Both keep `Any` out of the signature and keep validation at the boundary where it belongs. Reach
for `Any` only when the payload is genuinely unknown in shape, and say why in a comment.
