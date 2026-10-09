# Must-pass support check: Samsung SM-S731U profile

Which `vk-default` must-pass cases (3,246,762) would run versus report
`NotSupported` on a device described by a Vulkan profile, without real hardware.

Profile: `sm_s731u.json` (gpuinfo report 52327, `VP_GPUINFO_samsung_SM_S731U_25_3_3_android_17_0`,
Vulkan 1.3.304).

## Result

| | Cases | Share |
|---|---|---|
| Would run (passed support checks) | 864,545 | 26.6% |
| NotSupported | 2,382,217 | 73.4% |

Per-group counts: `summary.csv` (`group,total,would_run,not_supported`).

"Would run" is every status other than `NotSupported`. Pass/Fail values are meaningless
on the mock driver; only the support verdict matters. Caveats:

- 1,519 cases (mostly `sparse_resources`) were cut off after 2 s without output and are
  counted as would run. `checkSupport()` runs before program build and execution
  (`vktTestPackage.cpp`), and unsupported sparse cases exit in ~60 ms.
- 288 cases crashed or produced no result twice and are counted as would run.

## Method

1. Build `deqp-vk` (`-DDEQP_TARGET=vulkan_headless`).
2. Build Vulkan-Loader, the Vulkan-Tools mock ICD and the Khronos profiles layer (v1.4.364).
3. Run with:
   ```
   VK_DRIVER_FILES=<mock_icd>/VkICD_mock_icd.json
   VK_ADD_LAYER_PATH=<profiles>/explicit_layer.d
   VK_INSTANCE_LAYERS=VK_LAYER_KHRONOS_profiles
   VK_KHRONOS_PROFILES_PROFILE_FILE=sm_s731u.json
   VK_KHRONOS_PROFILES_PROFILE_NAME=VP_GPUINFO_samsung_SM_S731U_25_3_3_android_17_0
   VK_KHRONOS_PROFILES_SIMULATE_CAPABILITIES=SIMULATE_API_VERSION_BIT,SIMULATE_FEATURES_BIT,SIMULATE_PROPERTIES_BIT,SIMULATE_EXTENSIONS_BIT,SIMULATE_FORMATS_BIT,SIMULATE_QUEUE_FAMILY_PROPERTIES_BIT
   ```
4. `tools/supportrun.py --deqp <deqp-vk> --caselist <list> --out results.csv --jobs 4 --batch 200 --timeout 2 -- --deqp-log-images=disable --deqp-log-shader-sources=disable --deqp-shadercache=disable`
5. `tools/finalize.py recheck-list` / `build` to recheck uncertain cases and write the lists.

`--deqp-runmode=txt-caselist` is not a substitute: it walks the test tree without creating
a device, so it lists every case regardless of the profile.

`supportrun.py` replaces deqp-runner 0.23.3, which kills `deqp-vk` right after the last
result line; a process still tearing down is then reported as a crash and its batch rerun.

Tests: `python3 tools/test_supportrun.py && python3 tools/test_finalize.py`.

The full lists (`would-run.txt`, `not-supported.txt`, `results.csv`; ~430 MB uncompressed)
are not committed.
