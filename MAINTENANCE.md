# Matrix iOS maintenance

This repository maintains Matrix iOS diagnostics source. The base is Tencent/matrix commit `3b8293bd65d47eeea7caf1f32a3a5d4d5eab60e7`. Upstream licensing remains in `LICENSE` and the original source headers.

The maintained iOS changes guard unreadable historical memory records and let CPU power sampling continue during main-runloop hangs. Hang dump classification keeps its original priority. The monitor's synchronous stop behavior is inherited from upstream.

Consumers pin an exact commit from this repository when building device and simulator XCFrameworks. Source fixes are committed here before those pins are advanced.

Run the CPU decision regression on a macOS host with Xcode command-line tools.

```sh
python3 matrix/matrix-iOS/tests/test_cpu_hang_sampling.py
```

The regression compiles the production `check()` method in a deterministic host harness. It verifies CPU sampling and window advancement during foreground and background hangs, hang-versus-CPU dump priority, and the suspended-process guard. Real stack collection and runtime overhead still require device validation.
