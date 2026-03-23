# Test Harness & Visual Verification

Write a test script (e.g., `test/test_feature.gd`) — a SceneTree script that loads the scene under test and **thoroughly verifies the expected behavior**. Do NOT call `quit()` — the movie writer handles exit.

**Define what success looks like** and write a test that would convince a skeptic. A decoration change needs multiple camera angles to check placement and scale. A movement change needs the camera to follow the action over time. A UI change needs the full interface visible. Match the test to the goal.

## SceneTree Script Contract

Tests must `extend SceneTree` (not Node). Key details:
- `_initialize()` for setup (not `_ready()`)
- `_process(delta: float) -> bool` — return `false` to keep running
- Camera needs `_cam.current = true` to activate

## Console Assertions

The test harness stdout is captured alongside screenshots. Use `print("ASSERT PASS/FAIL: ...")` to verify behavioral properties that are hard to judge visually (exact positions, velocities, state changes). After capture, check stdout for any `ASSERT FAIL` lines — these must be fixed before the task is complete.

## Simulated Input

For tests needing player input, use a Timer to trigger actions:

```gdscript
    var timer := Timer.new()
    timer.wait_time = 1.0
    timer.one_shot = true
    timer.timeout.connect(func(): Input.action_press("move_forward"))
    root.add_child(timer)
    timer.start()
```
