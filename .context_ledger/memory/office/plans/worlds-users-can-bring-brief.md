# Brief — letting people bring their own world

**Raised by the user, 2026-09-23**, to be settled before more world work lands.
Written by Mara (S004). The contract a world must satisfy is **ADR-4** and is not
re-argued here; this is about how one gets registered.

## Where it stands today

The `Environment` protocol is four members — `name`, `tools()`, `probe()`, `is_read_only()` —
and the README already promises *"a new world is one `World` row, not app work."* That is
true for someone editing this repo. For anyone else it is false in the strongest way:

- `server/appserver/worlds.py` holds a **hardcoded dict**. That is the only registry.
- There is **no discovery mechanism at all** — no entry points, no plugin directory, no
  config file. Checked: neither `pyproject.toml` declares an entry-point group.
- The app's world picker is `describe()` over that dict, so a world that is not in the
  source cannot appear in the window.

So the engine is extensible and the product is not.

## The three ways in, and what each costs

### A. Python entry points — `ti_matrix.worlds`

A user pip-installs a package that declares the group; the sidecar enumerates it at
startup. Standard, no new invention, works with virtualenvs, and the world ships with
its own dependencies (it lives outside `ti_matrix`, so ADR-2's standard-library rule does
not bind it — that rule is about what *we* ship, not what a user installs).

Cost: the user has to package something. That is a real barrier for "I want to point this
at my own thing", which is the actual request.

### B. A worlds directory — `~/.ti-matrix/worlds/*.py`

Drop a file in, restart, it appears. This is the shape people expect, and it is the one
that makes the feature feel like a feature.

Cost, and it must be stated plainly: **this executes arbitrary Python in the sidecar's
process.** It is the user's own machine and their own file, which is the same bargain a
`conftest.py` or a shell profile makes — but it deserves a deliberate decision, a visible
directory, and no auto-import of anything downloaded. It should never be a path the app
writes to on a user's behalf.

### C. Declarative worlds — no code

A TOML/JSON file naming actions, each bound to a shell command or an HTTP request, with a
template for arguments and a rule for turning stdout into observation text. No execution
beyond what the user literally wrote down.

Cost: it can only express worlds that are one request per action. That is genuinely a lot
of them — an HTTP API, a CLI tool, a database query — but it cannot hold state-carrying
actions well, and ADR-4 rule 1 says actions must carry their position. Workable if every
action's arguments are explicit, which a declarative form naturally forces.

**Recommendation: A and B, in that order, sharing one loader.** Entry points for worlds
that are distributed; a directory for worlds that are personal. C is attractive and should
not be first — a declarative layer designed before anyone has written two real worlds will
be designed for the wrong two.

## The part that will actually decide whether this works

Not the loader. **Rule 1 of ADR-4** — an action carries its own position, the world holds
no cursor. It is the rule nobody guesses, the shipped browser world already breaks it, and
a user whose world breaks it sees a run that looks like the model hallucinating rather than
like their code misbehaving. That debugging session is where this feature will be judged.

So the mechanism should make the rule hard to get wrong, not merely documented:

- **Ship a template world** that is correct by construction, with the position-carrying
  action as the obvious pattern, and comments saying why.
- **Check it at registration.** A world can be probed twice with two different actions from
  a fresh instance and the results compared against probing them in the other order — if a
  world is order-dependent, that catches it at load rather than mid-run.
- **Say it in the failure.** When a custom world raises, the error should name the world and
  the action, not surface as an engine stack trace.

## The other thing users will want, and should not get yet

A world that **writes**. Every shipped world is read-only, `read_only` is the safety
boundary, and the confirmer exists for actions that change something. A user-defined world
that deletes files or posts to an API is exactly where this gets dangerous, and it is also
obviously what someone will try first. v1 should accept `read_only=False` declarations,
route them through the existing confirmer, and **not** offer a way to pre-grant them.

## Questions for the user

1. **Who is the audience — you, or strangers?** A personal worlds directory and a published
   plugin ecosystem are different products with different safety bars, and it changes
   whether B is fine or alarming.
2. **Should a custom world appear in the app's picker automatically, or be enabled per run?**
   Automatic is friendlier; explicit is honest about running someone's code.
3. **Is a declarative world (option C) the real want?** If the motivating case is "point it
   at my HTTP API", C is a better fit than either A or B and changes the order.
