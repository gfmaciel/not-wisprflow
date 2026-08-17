# Safe Paste Target / Focus Guard

Status: proposed design for implementation

## Problem

`not-wisprflow` currently pastes or types into whichever control owns keyboard focus at the moment output becomes available.

That is correct for the simple case, but unsafe for a common dictation workflow:

1. Start dictating in a text field.
2. Keep recording while switching to other tabs/windows to read information.
3. Mono mode decides that an intermediate thought is complete and attempts an early paste.
4. The active cursor now belongs to another tab/window, so text may be inserted in the wrong place.
5. The user later returns to the original text field and stops recording.

The feature must preserve low-latency early paste without ever intentionally typing into a destination that cannot be identified as the original target.

## Safety invariant

> If target identity is uncertain, buffer the text. Never paste on uncertainty.

The application must never steal focus or activate a window just to paste.

## Goals

- Capture the intended paste target when recording begins.
- Allow incremental mono-mode paste only while that target is still focused.
- Buffer completed text while the user reads another tab/window.
- Flush the buffered text, in order, after the user returns to the original target.
- Apply the same safety rule to final clipboard paste and dual-mode streaming output.
- Fail safely if UI Automation cannot identify the control.
- Avoid storing/logging field contents, labels, document text, or other sensitive UI text.

## Non-goals

- Do not bring the original application to the foreground automatically.
- Do not click or refocus the original field automatically.
- Do not attempt DOM/browser-extension integration.
- Do not use screen coordinates as target identity.
- Do not silently fall back to "same browser window = same field" when UI Automation cannot distinguish controls.

## Platform approach

Use Microsoft UI Automation (UIA) to inspect the currently focused control. UIA exposes `GetFocusedElement`, and a UIA element exposes a runtime identifier that can be used as a strong identity signal while that element exists.

Implementation should isolate platform code behind a small adapter so the rest of the pipeline does not know about COM/UIA details.

Recommended Python wrapper for v1: `uiautomation==2.0.29`.

Why:

- It is a thin Python wrapper around Microsoft UI Automation.
- It supports Windows 10/11 and documents support for Chrome and other UIA providers.
- It exposes the underlying `IUIAutomationElement`, so the implementation can use native UIA identity when needed.
- Keeping it behind an adapter makes replacement possible later without changing pipeline logic.

References:

- Microsoft `IUIAutomation::GetFocusedElement`: https://learn.microsoft.com/en-us/windows/win32/api/uiautomationclient/nf-uiautomationclient-iuiautomation-getfocusedelement
- Microsoft UI Automation element retrieval: https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-obtainingelements
- Python UIAutomation for Windows: https://github.com/yinkaisheng/Python-UIAutomation-for-Windows
- PyPI release: https://pypi.org/project/uiautomation/2.0.29/

## Architecture

Introduce two pieces:

### 1. `FocusTracker`

Windows-specific, read-only UI inspection.

Suggested interface:

```python
@dataclass(frozen=True)
class FocusTarget:
    process_id: int
    top_level_hwnd: int
    runtime_id: tuple[int, ...] | None
    automation_id: str
    control_type: int
    class_name: str

class FocusTracker:
    def capture(self) -> FocusTarget | None: ...
    def is_same_target(self, target: FocusTarget) -> bool: ...
```

Important privacy rule: do **not** include UIA `Name`, `Value`, visible text, selected text, document title, or field contents in the fingerprint or logs.

### 2. `PasteTargetGuard`

Platform-independent routing and buffering.

Suggested interface:

```python
class PasteTargetGuard:
    def arm(self) -> None: ...
    def paste(self, text: str) -> bool: ...
    def paste_stream(self, deltas: Iterable[str]) -> str: ...
    def flush_if_safe(self) -> bool: ...
    def reset(self) -> None: ...
```

`PasteTargetGuard` owns the pending output buffer. It receives an ordinary paste function and a focus tracker through dependency injection so unit tests do not require a real desktop.

## Target fingerprint and matching

### Strong match

Treat the target as the same when all available strong identifiers agree:

- same process ID;
- same top-level HWND;
- same UIA runtime ID.

### Degraded capture

If UIA cannot provide a runtime ID but top-level window identity is available, do **not** permit incremental paste based on HWND alone. A browser can contain multiple tabs and multiple editable fields inside one HWND.

In degraded mode:

- buffer all incremental output;
- at stop, paste only if a fresh UIA target can be proven equivalent;
- otherwise leave the output recoverable through the clipboard and never send keystrokes automatically.

### Element replacement

Some web applications replace an editable element during a React/UI rerender. A new runtime ID must be considered a different/unknown target in v1, even if other metadata looks similar.

This is intentionally conservative. A later version may add a carefully tested stable ancestor fingerprint, but false negatives are preferable to text appearing in the wrong application or field.

## Session state machine

```text
IDLE
  |
  | recording starts
  v
ARMED(target)
  |
  | output ready + target focused
  +------------------------------> paste immediately
  |
  | output ready + other/unknown target
  v
BUFFERING(target, pending_text)
  |
  | next output or stop + original target focused
  +------------------------------> flush pending in order -> ARMED
  |
  | stop + target still wrong/unknown
  v
RECOVERY(pending_text in clipboard, no keystrokes)
```

No background focus stealing is needed.

For the user's normal workflow, they return to the original field before pressing the stop hotkey. The stop path performs a target check and flushes the accumulated buffer there.

## Mono-mode integration

Current mono mode calls `paste()` as soon as `completion_score >= paste_threshold`.

Replace the raw paste callback passed to `MonoProcessor` with `PasteTargetGuard.paste`.

Desired behavior:

```text
phrase complete + target focused -> paste now
phrase complete + reading elsewhere -> append to guard buffer
next phrase complete after returning -> flush old buffer + paste new phrase
stop after returning -> flush old buffer + mono pending text
```

The `MonoProcessor` should remain unaware of Windows focus details.

## Dual-mode integration

Dual mode currently uses `paste_stream()` after recording stops.

Streaming needs a slightly stronger rule because focus can change while tokens/deltas are arriving:

1. Before each write, verify target identity.
2. If focus changes, stop issuing keyboard events immediately.
3. Continue consuming the model stream into the guard buffer without typing.
4. When the target is safe again, paste the buffered remainder.

This prevents a stream that started correctly from continuing into a different application after Alt+Tab.

## Start/stop behavior

### Recording start

`Pipeline._start_recording()`:

1. Reset prior guard state.
2. Capture target.
3. Start recorder.

Target capture should happen immediately before recording begins so the focused field is the field the user intended to dictate into.

### Recording stop

`Pipeline._stop_recording()` / collection path:

- Never assume the current cursor is safe.
- Flush through `PasteTargetGuard`, not directly through `paste()`.
- If the target cannot be proven, do not send `Ctrl+V` or `keyboard.write()`.
- Put recoverable pending text in the clipboard and expose a visible/log state such as `paste_pending` without including the text itself.

## Failure handling

### UIA throws / target disappears

Microsoft documents that `GetFocusedElement` can fail when an element disappears between lookup and use. Treat all such errors as `unknown`, buffer, and continue recording.

### Browser does not expose a usable UIA child element

Disable incremental paste for that recording session. Do not weaken matching to top-level window identity.

### User closes the original tab/window

The target can no longer match. Preserve pending text in clipboard; do not activate another window.

### User intentionally wants to change destinations mid-recording

Not part of v1. A future explicit "retarget" command could re-arm the guard, but target changes must never be inferred automatically.

## Configuration and rollout

Add:

```env
SAFE_PASTE_TARGET=true
```

Recommended rollout:

1. Ship behind the flag, default `true` in development/manual testing.
2. Validate Windows behavior in common targets.
3. Make it the production default after the manual acceptance matrix passes.
4. Keep `SAFE_PASTE_TARGET=false` temporarily as an escape hatch while the implementation matures.

If disabled, preserve existing behavior exactly.

## Unit tests

`FocusTracker` should be represented by a fake in most tests.

Minimum test set:

1. Capture target when recording starts.
2. Same target -> incremental text pastes immediately.
3. Different top-level window -> text buffers, no keystroke call.
4. Different UIA runtime ID inside same browser HWND -> text buffers.
5. Return to target -> buffered phrases flush once, in original order.
6. Several away-target phrases coalesce without duplication.
7. Stop while back on target -> pending text flushes.
8. Stop while away -> no keystrokes; pending text copied for recovery.
9. UIA lookup exception -> buffer, never paste.
10. Original element disappears -> buffer/recovery path.
11. Streaming output changes focus mid-stream -> subsequent deltas are buffered, not typed elsewhere.
12. Guard reset between recordings -> no stale target or stale text.
13. No UI `Name`/`Value`/text is included in diagnostic output.

## Manual Windows acceptance matrix

Test at least:

- Chrome: same ChatGPT text box, switch to another tab, return, stop.
- Chrome: switch between two editable fields in the same tab.
- Edge: same scenarios.
- Notepad: switch to browser and return.
- VS Code editor: switch to browser and return.
- Close original tab while recording.
- Change focus exactly while an early paste becomes ready.
- Change focus during dual-mode streaming.

For every case, the hard acceptance criterion is: **zero text appears outside the originally armed target**.

## Expected code changes

Likely scope:

- new `focus_tracker.py` (Windows/UIA adapter);
- new `paste_guard.py` (state + buffer + safety policy);
- update `pipeline.py` to arm/reset/flush guard and route all output through it;
- small update to `paste_text.py` so raw keyboard operations remain low-level primitives;
- update `config.py`, `.env.example`, and `requirements.txt`;
- new focused unit tests plus existing CI;
- optional tray/UI state for `paste_pending`.

This is a medium-sized feature with a narrow blast radius. The AI/transcription architecture does not need to change.

## Definition of done

- No raw paste/write path in `Pipeline` or `MonoProcessor` can bypass the guard when `SAFE_PASTE_TARGET=true`.
- Incremental paste still feels immediate while the original field is focused.
- Switching tabs/windows never causes text to be inserted into the newly focused destination.
- Returning to the original field preserves output order and avoids duplication.
- Failure to identify focus always degrades toward buffering/recovery, never toward an unsafe paste.
- Full CI remains green on supported Python versions.
- Manual Windows acceptance matrix passes before removing the escape hatch.
