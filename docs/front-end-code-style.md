# Front-end Code Style

- Strict type safety (any can only be used in type constraints)
- Functional programming patterns take precedence over OOP
- All state should be extracted into standalone hook files, except for tight-loop animation-like state which can be inline in components
- Always define and program against interfaces rather than implementations
- No mock implementations in production code paths. A hook or service that falls back to fake data when a precondition isn't met (not yet authenticated, missing config) should fail clearly instead — return a value whose methods reject with a real error message the caller can catch and surface, not one that pretends to work. If a mock is genuinely useful for local development, gate it behind an explicit dev-only flag, not a runtime condition ordinary users can hit (an empty auth token is a real, reachable state during app bootstrap, not just a defensive case).
- Colocate a module's `*.unit.test.ts` in the same folder as the file it tests, not in a shared `hooks/`-style catch-all directory.
- Prefer `Schema.decodeUnknownSync(schema)(value)` over `Effect.runSync(Schema.decodeUnknown(schema)(value))` when decoding outside an Effect generator (a plain `async function`, a synchronous utility) — the latter throws an untyped `FiberFailure` on a bad decode instead of a `ParseError` with a real `.message`. See [Effect Style § Prefer Schema.decodeUnknownSync outside an Effect context](./effect-style.md#prefer-schemadecodeunknownsync-outside-an-effect-context).
- **Wrap an async handler's mutation in try/catch, and reset UI state in `finally`, not just on the success path.** A handler that calls a service method and only handles the success case leaves the UI stuck (a dialog that never closes, a button that never re-enables) on failure, with no feedback the user can act on. On catch, surface the error with a message the user can read (an inline `Alert`, a snackbar) — don't let it become an unhandled promise rejection:

  ```tsx
  const handleDisconnect = useCallback(async () => {
    if (!target) return;
    try {
      await service.revokeConnection(target);
      addSnackbar({ title: 'Disconnected', body: `${target.name} disconnected.` });
    } catch {
      addSnackbar({ title: 'Disconnect failed', body: `Could not disconnect ${target.name}.`, color: 'error' });
    } finally {
      setTarget(null); // closes the confirmation dialog either way
    }
  }, [target, service, addSnackbar]);
  ```
