// SPDX-License-Identifier: Apache-2.0
// A loadable d3d9.dll-shaped module with no Remix C API exports, for the
// registration fail-closed regression test.
extern "C" __declspec(dllexport) int MfgTestNoRemixApi() noexcept {
    return 1;
}

// The second fixture deliberately has the expected export but a different
// binary identity. This must fail the runtime SHA-256/PE profile check, not
// merely the earlier missing-export check. Never use as an actual runtime.
#ifdef MFG_TEST_EXPORT_FAKE_REMIX_API
extern "C" __declspec(dllexport) int remixapi_InitializeLibrary() noexcept {
    return 1;
}
#endif
