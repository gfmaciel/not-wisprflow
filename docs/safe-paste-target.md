# Safe Paste Target / Focus Guard

Status: implemented behind `SAFE_PASTE_TARGET` (default: `true`)

## Why this exists

`not-wisprflow` can paste mono-mode thoughts before recording stops. That is useful for latency, but raw `Ctrl+V` / `keyboard.write()` targets whichever control owns keyboard focus at that instant.

A common workflow is:

1. Start dictating in a text field.
2. Keep recording while switching tabs/windows to read information.
3. Return to the original field.
4. Stop recording and continue working there.

Without a focus guard, an early mono paste could land in the tab or application being used only for reading.

## Safety policy

> If the original target cannot be strongly verified, buffer output. Never intentionally paste on uncertainty.

The application does not steal focus, activate windows, click fields, or infer a new destination.

There is one unavoidable platform limitation: synthetic keyboard input is not atomic with focus state. The implementation rechecks focus immediately before sending `Ctrl+V` (including a second check after clipboard preparation), but Windows cannot provide a universal transaction that locks an arbitrary Chrome/contenteditable/VS Code field to a synthetic key event. The remaining check-to-key interval is therefore extremely small but not mathematically zero. The manual acceptance matrix below remains important.

## Current architecture

### `paste_target.py`

Owns target identity, Windows UI Automation capture, buffering, and routing policy.

#### `FocusIdentity`

Stores only technical identity metadata:

- UI Automation runtime ID;
- process ID;
- optional top-level runtime ID;
- optional top-level HWND;
- control type/class/automation/framework identifiers for technical diagnostics.

It does **not** capture UIA `Name`, `Value`, visible text, selected text, document title, URL, or field contents.

A strong match requires:

- non-empty runtime IDs;
- valid/equal process IDs;
- exact focused-element runtime ID equality;
- top-level runtime ID equality when both sides provide it;
- top-level HWND equality when both sides provide it.

A matching browser HWND alone is never sufficient. A different field/tab inside the same browser window therefore fails closed when UI Automation exposes it as a different focused element.

#### `WindowsUIAFocusProvider`

Uses `uiautomation==2.0.29` as a wrapper over Microsoft UI Automation.

Every focus capture runs inside `UIAutomationInitializerInThread()` because paste work can execute from different worker/collector threads. The code stores immutable identity data rather than passing live UI Automation controls across threads.

Capture returns `None` on:

- UI Automation error;
- no focused control;
- a control that does not report keyboard focus;
- a password field;
- missing runtime ID;
- invalid process ID.

`None` is a safe state: output buffers instead of falling back to active-cursor paste.

#### `PasteTargetGuard`

Owns the pending-output buffer for the recording session.

Its state is intentionally small:

```text
IDLE
  |
  | begin recording
  v
ARMED(original target)
  |
  | output + target strongly matches
  +-------------------------------> paste/type
  |
  | output + mismatch/unknown
  v
BUFFERING(original target, pending text)
  |
  | next output or stop after return
  +-------------------------------> flush pending in order
  |
  | stop while still away/unknown
  v
RECOVERY(copy pending text only; no keystroke)
```

The guard is protected by an `RLock` because recording start, mono processing, and final collection can occur on different threads.

## Paste hardening

A guarded clipboard paste is deliberately split into two operations rather than reusing the legacy `paste()` primitive as one opaque action:

1. Verify that the original UIA target is focused.
2. Prepare the clipboard.
3. Verify the original UIA target **again**.
4. Only then send `Ctrl+V`.

If focus changes during clipboard preparation, step 3 fails and `Ctrl+V` is not sent. The text remains buffered/recoverable.

For streaming keyboard writes, target identity is checked before each delta. If focus changes, subsequent deltas are buffered. As with all synthetic keyboard input, a focus change during the physical emission of one delta cannot be made universally atomic across applications; keeping deltas small limits that residual window.

## `paste_text.py`

The old low-level behavior remains available for the escape hatch:

- `_paste_now()` -> clipboard + `Ctrl+V` at active cursor;
- `_type_now()` -> `keyboard.write()`.

When a guarded session is active:

- `paste()` routes through `PasteTargetGuard.submit()`;
- `paste_stream()` routes through `PasteTargetGuard.stream()`.

When safe paste is disabled, these functions preserve the legacy active-cursor behavior.

At recovery, the app logs only that pending text was copied to the clipboard; the pending text itself is not logged.

## Pipeline lifecycle

### Recording start

`Pipeline._start_recording()` calls:

```python
start_paste_session(enabled=config.safe_paste_target)
```

**before** the `recording` state callback and before starting the recorder. This ordering prevents the app's own visual state transition from accidentally becoming the captured destination.

If recorder startup fails, the paste session is immediately finished/reset and `_active` is cleared.

### Recording end / collection

`Pipeline._collect_and_paste()` always calls `finish_paste_session()` in its outer `finally` block, including paths with no futures or processing errors.

If pending guarded text exists:

- original target focused -> paste it there;
- target different/unknown -> copy pending text to clipboard and send no keyboard event.

The pipeline then returns to `idle` normally.

## Mono behavior

`MonoProcessor` remains platform-agnostic. It still calls the injected `paste()` callback whenever `completion_score >= MONO_PASTE_THRESHOLD`.

The guard changes what happens underneath:

```text
complete thought + original field focused
    -> paste immediately

complete thought + user reading elsewhere
    -> append to guard buffer

user returns + another output arrives
    -> flush old buffer + new output in order

user returns + presses stop
    -> mono flush + guard finish -> paste pending output

user stops while still elsewhere
    -> pending output to clipboard only; no Ctrl+V
```

Once a mono thought is handed to the guard, the guard owns any unpasted copy. This prevents `MonoProcessor` from duplicating text later.

## Dual behavior

Dual mode still consumes cleanup output through `paste_stream()` after recording stops.

While the original target remains focused, deltas type normally. If focus becomes different/unknown, the guard stops issuing new writes and buffers later deltas. When a safe target is available on a later delta, the buffered remainder is flushed in order. On terminal recovery, pending text goes to clipboard only.

The existing stream-error contract is preserved:

- error before any delta is handled -> propagate so the caller can use its existing fallback;
- error after output has been typed **or buffered** -> do not re-paste the full result, avoiding duplication.

## Configuration

```env
SAFE_PASTE_TARGET=true
```

Default is `true`.

Set `SAFE_PASTE_TARGET=false` only to restore the previous behavior where output goes to whichever cursor is active at paste time. This is an escape hatch, not the recommended mode.

## Dependencies

The Windows focus adapter uses:

```text
uiautomation==2.0.29
```

References:

- Microsoft `IUIAutomation::GetFocusedElement`: https://learn.microsoft.com/en-us/windows/win32/api/uiautomationclient/nf-uiautomationclient-iuiautomation-getfocusedelement
- Microsoft UI Automation element retrieval: https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-obtainingelements
- Python UIAutomation for Windows: https://github.com/yinkaisheng/Python-UIAutomation-for-Windows
- PyPI release: https://pypi.org/project/uiautomation/2.0.29/

## Automated test coverage

The repository includes focused tests for:

- exact target matching;
- different control/runtime ID in the same browser window;
- different application;
- conflicting top-level identity;
- ordered buffer flush after returning;
- stop while away -> clipboard only / zero paste hotkeys;
- stop after returning -> pending paste;
- UI Automation capture failure;
- runtime UI Automation exception;
- password-field rejection;
- focus change **during clipboard preparation** -> second check blocks `Ctrl+V`;
- streaming focus changes and ordered recovery;
- stream failure before/after partial output;
- safe-paste configuration default and escape hatch;
- pipeline lifecycle (capture ordering, rollout flag, recorder-start failure cleanup, terminal cleanup);
- real `uiautomation` thread-initializer smoke test on Windows CI.

The normal CI matrix installs all dependencies, runs `pip check`, compiles Python syntax, and runs the full pytest suite on Windows with Python 3.10 and 3.13.

## Manual Windows acceptance matrix

Automated CI cannot reproduce a human switching real interactive browser tabs at arbitrary instants. Before removing the escape hatch, manually exercise at least:

- Chrome: ChatGPT/editor field -> another tab -> original field -> stop;
- Chrome: two editable fields in the same tab;
- Edge: equivalent tab/field cases;
- Notepad -> browser -> Notepad;
- VS Code editor -> browser -> VS Code;
- close the original tab while recording;
- change focus as an early mono paste becomes ready;
- change focus during dual streaming.

Hard acceptance criterion: **no text should appear outside the originally armed destination**. A conservative false negative (clipboard recovery instead of paste) is acceptable; a wrong-destination paste is not.

## Files changed for this feature

- `paste_target.py` — focus identity, UIA adapter, guard/buffer policy;
- `paste_text.py` — guarded routing + retained legacy primitives;
- `pipeline.py` — session lifecycle integration;
- `config.py` / `.env.example` — rollout flag;
- `requirements.txt` — UI Automation dependency;
- `tests/test_paste_target.py` — guard/provider behavior;
- `tests/test_safe_paste_config.py` — configuration;
- `tests/test_safe_paste_pipeline.py` — lifecycle integration;
- `tests/test_uiautomation_windows_smoke.py` — real Windows package/thread initialization.

## Definition of done

For the implemented v1:

- no pipeline/mono output bypasses the guard while `SAFE_PASTE_TARGET=true`;
- target uncertainty degrades to buffering/recovery, never a window-only guess;
- buffer order is preserved without duplication;
- stop-away recovery emits no keyboard event;
- failure paths do not leave the pipeline stuck in processing state;
- Windows CI is green on supported Python versions;
- the manual matrix above remains the final validation for real interactive browser behavior before the escape hatch is ever removed.