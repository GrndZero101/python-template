---
name: python-fastapi
description: >-
  Conventions for FastAPI services — the FAST lint rules, Annotated dependency injection, keeping
  route handlers thin, sync-versus-async choice, lifespan setup, and offline testing with
  ASGITransport. Use when writing or changing FastAPI routes, routers, dependencies or app setup,
  or when configuring lint for a FastAPI project.
---

# FastAPI conventions

## Enable the FAST rules

FastAPI is the one project type that unlocks extra lint. Add `"FAST"` to `select` in
`pyproject.toml`:

| Rule | Catches |
|---|---|
| `FAST001` | `response_model=` duplicating the return annotation — always fixable |
| `FAST002` | `Depends()`/`Query()` in a default instead of `Annotated` |
| `FAST003` | a path parameter in the route string that the signature never declares |

`FAST003` is the valuable one: without it, `@app.get("/items/{item_id}")` with a handler that forgot
`item_id` fails at request time, not at lint time.

**No lint relaxation is needed for a FastAPI project.** In particular do not add a `B008`
per-file-ignore for route modules — see below.

## `Annotated` dependencies, always

```python
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/items/{item_id}")
async def read_item(item_id: int, session: SessionDep) -> Item:
    """Return one item."""
    return await fetch_item(item_id, session=session)
```

Never `session: Session = Depends(get_session)`. That form trips `FAST002` always, and `B008`
additionally whenever the annotation is mutable or non-stdlib — which is nearly always for a real
dependency, since `Session` is not a stdlib immutable. With `Annotated`, `Depends()` lives inside the
annotation rather than the default slot and **neither rule fires**.

Aliasing the annotation (`SessionDep`) is the idiom worth adopting: it is declared once, greppable,
and keeps signatures short enough to stay under `max-args`.

`Depends()` is CLAUDE.md's "inject dependencies as parameters" rule expressed in framework form.
They agree — FastAPI is doing the injection for you at the boundary. The rule still binds *below*
the boundary: a function called by a handler takes its session, clock and client as ordinary
parameters, and never reaches for a module-level singleton.

## Route handlers stay thin

A handler translates HTTP to a call and back. Nothing else:

```python
@router.post("/orders")
async def create_order(payload: OrderCreate, session: SessionDep) -> OrderRead:
    """Create an order."""
    try:
        order = await place_order(payload.to_command(), session=session)
    except InsufficientStock as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OrderRead.model_validate(order)
```

- `place_order` knows nothing about HTTP. It is callable from a test, a script, or a breakpoint with
  literal arguments, and it raises domain exceptions.
- `HTTPException` is raised only in the handler layer, and always `from exc` so the traceback
  survives (`B904` enforces this).
- Never `raise HTTPException` from a service or repository function. That makes it unusable from
  anything but a request, which is the same defect as calling `sys.exit()` in library code.

Request and response models are separate types (`OrderCreate`, `OrderRead`). Do not accept and
return the same model — that is how internal fields leak into a public payload.

## Structure

One responsibility per module, per CLAUDE.md:

```text
src/pkg/
  main.py          # app object, middleware, lifespan, router registration only
  dependencies.py  # get_session, get_settings, the Annotated aliases
  routers/
    orders.py      # APIRouter, handlers only
  services/
    orders.py      # the real work — plain annotated functions
  models.py
  schemas.py
```

`main.py` should contain no route logic. Every router is an `APIRouter` with its own `prefix` and
`tags`, registered in `main.py` with `app.include_router`.

## `async def` or `def` — pick correctly

This is the one FastAPI decision with a real performance cliff.

- **`async def`** only when the body is genuinely awaitable throughout. A blocking call inside an
  `async def` handler stalls the entire event loop for every concurrent request.
- **`def`** when the work is blocking — a sync database driver, `requests`, file I/O, CPU work.
  FastAPI runs it in a threadpool, which is correct and costs you nothing.

A sync `def` handler is not a compromise. Reaching for `async def` and then calling a blocking
driver inside it is the actual mistake.

## Lifespan, not `on_event`

`@app.on_event("startup")` is deprecated. Use the async context manager:

```python
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open and close long-lived resources."""
    async with build_engine() as engine:
        app.state.engine = engine
        yield


app = FastAPI(lifespan=lifespan)
```

## Testing: offline, no live server

Use `httpx.ASGITransport` to call the app in-process. No port, no subprocess, no network:

```python
transport = httpx.ASGITransport(app=app)
async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
    response = await client.get("/items/1")
assert response.status_code == 200
```

Override dependencies rather than patching modules — this is what `Depends` is for:

```python
app.dependency_overrides[get_session] = _test_session
```

Clear the overrides in fixture teardown, or they leak into the next test and the failure appears in
an unrelated file.

Test services directly with plain function calls; reserve HTTP-level tests for status codes,
serialization and auth. Most of the suite should not go through the transport at all.
