// SPDX-License-Identifier: Apache-2.0
// A loadable d3d9.dll-shaped module with no Remix C API exports, for the
// registration fail-closed regression test.
extern "C" __declspec(dllexport) int MfgTestNoRemixApi() noexcept {
    return 1;
}
