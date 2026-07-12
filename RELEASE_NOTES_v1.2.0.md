## Reaper v1.2.0

This release fixes the big one: the interactive shell froze or dropped your keystrokes when you typed into it.

### Fixed
- **Frozen / dropped input in sessions.** A background liveness watchdog was calling `recv(1)` on every session socket. While you were attached to a shell, that thread fought the interactive reader for the same stream and stole bytes out of the shell's output, so typing looked frozen or corrupted. The watchdog now peeks with `MSG_PEEK` and consumes nothing, so every byte reaches your terminal.
- **Window resize no longer eats output.** Resizing your terminal during a session used to drain the socket. It now only forwards the new size.
- **A bad command can no longer crash Reaper.** Every command runs inside a guard and returns you to the prompt on error.
- **`serve` with a non-numeric port** reports the mistake instead of raising.

### New
- `killall` closes every session at once.
- `name <id> <label>` puts a friendly label on a session.
- `go` with no id attaches to the only live session.

### Changed
- New steel-blue theme, tuned for readability on dark terminals. Errors stay red.
- No em dashes anywhere in the codebase or docs.
- Rewritten, example-driven README.

Install:
```
pipx install --editable .
```
