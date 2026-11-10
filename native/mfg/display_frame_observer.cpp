// SPDX-License-Identifier: Apache-2.0
// Isolated native display-path sampler. Reads only the middle 256x256 pixels of
// this probe's own foreground window; never writes an image or captures another
// application's window. Desktop Duplication observes DWM output, not physical
// scanout, so these samples alone cannot certify monitor-displayed interpolation.
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cwchar>
#include <filesystem>
#include <fstream>

using Microsoft::WRL::ComPtr;

namespace {
constexpr UINT kCrop = 256;
constexpr UINT kStride = 4;

struct TargetWindow {
    DWORD pid = 0;
    HWND hwnd = nullptr;
};

BOOL CALLBACK FindWindowByPid(HWND candidate, LPARAM parameter) {
    auto* target = reinterpret_cast<TargetWindow*>(parameter);
    DWORD owner = 0;
    GetWindowThreadProcessId(candidate, &owner);
    if (owner != target->pid) return TRUE;
    wchar_t className[96]{};
    wchar_t title[128]{};
    GetClassNameW(candidate, className, 96);
    GetWindowTextW(candidate, title, 128);
    if (wcscmp(className, L"MfgRemixSmoke") == 0 &&
        wcscmp(title, L"Isolated Remix native test") == 0) {
        target->hwnd = candidate;
        return FALSE;
    }
    return TRUE;
}

bool IsOwnForeground(HWND window) {
    return IsWindowVisible(window) && !IsIconic(window) && GetForegroundWindow() == window;
}

uint64_t HashMappedPixels(const D3D11_MAPPED_SUBRESOURCE& mapped) {
    uint64_t hash = 14695981039346656037ull;
    for (UINT row = 0; row < kCrop; row += kStride) {
        const auto* pixels = static_cast<const uint8_t*>(mapped.pData) +
                             static_cast<size_t>(row) * mapped.RowPitch;
        for (UINT col = 0; col < kCrop; col += kStride) {
            const auto* color = pixels + col * 4;
            for (UINT channel = 0; channel < 3; ++channel) {
                hash ^= color[channel];
                hash *= 1099511628211ull;
            }
        }
    }
    return hash;
}

struct Capture {
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> context;
    ComPtr<IDXGIOutputDuplication> duplication;
    ComPtr<ID3D11Texture2D> staging;
    RECT desktop{};
};

HRESULT CreateCapture(HWND window, Capture& capture) {
    const HMONITOR monitor = MonitorFromWindow(window, MONITOR_DEFAULTTONEAREST);
    ComPtr<IDXGIFactory1> factory;
    HRESULT result = CreateDXGIFactory1(IID_PPV_ARGS(&factory));
    if (FAILED(result)) return result;
    for (UINT ai = 0; ; ++ai) {
        ComPtr<IDXGIAdapter1> adapter;
        if (factory->EnumAdapters1(ai, &adapter) == DXGI_ERROR_NOT_FOUND) break;
        for (UINT oi = 0; ; ++oi) {
            ComPtr<IDXGIOutput> output;
            if (adapter->EnumOutputs(oi, &output) == DXGI_ERROR_NOT_FOUND) break;
            DXGI_OUTPUT_DESC desc{};
            if (FAILED(output->GetDesc(&desc)) || desc.Monitor != monitor) continue;
            D3D_FEATURE_LEVEL level{};
            result = D3D11CreateDevice(adapter.Get(), D3D_DRIVER_TYPE_UNKNOWN, nullptr,
                                       D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0,
                                       D3D11_SDK_VERSION, &capture.device, &level,
                                       &capture.context);
            if (FAILED(result)) return result;
            ComPtr<IDXGIOutput1> output1;
            result = output.As(&output1);
            if (FAILED(result)) return result;
            result = output1->DuplicateOutput(capture.device.Get(), &capture.duplication);
            if (FAILED(result)) return result;
            DXGI_OUTDUPL_DESC duplicateDesc{};
            capture.duplication->GetDesc(&duplicateDesc);
            if (duplicateDesc.ModeDesc.Format != DXGI_FORMAT_B8G8R8A8_UNORM) {
                return DXGI_ERROR_UNSUPPORTED;
            }
            capture.desktop = desc.DesktopCoordinates;
            D3D11_TEXTURE2D_DESC stagingDesc{};
            stagingDesc.Width = kCrop;
            stagingDesc.Height = kCrop;
            stagingDesc.MipLevels = 1;
            stagingDesc.ArraySize = 1;
            stagingDesc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
            stagingDesc.SampleDesc.Count = 1;
            stagingDesc.Usage = D3D11_USAGE_STAGING;
            stagingDesc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
            return capture.device->CreateTexture2D(&stagingDesc, nullptr, &capture.staging);
        }
    }
    return DXGI_ERROR_NOT_FOUND;
}

bool OwnWindowCrop(HWND window, const RECT& desktop, D3D11_BOX& box) {
    RECT client{};
    POINT origin{};
    if (!GetClientRect(window, &client) || !ClientToScreen(window, &origin)) return false;
    const int width = client.right - client.left;
    const int height = client.bottom - client.top;
    if (width < static_cast<int>(kCrop) || height < static_cast<int>(kCrop)) return false;
    const int left = origin.x + (width - kCrop) / 2 - desktop.left;
    const int top = origin.y + (height - kCrop) / 2 - desktop.top;
    if (left < 0 || top < 0 || left + kCrop > desktop.right - desktop.left ||
        top + kCrop > desktop.bottom - desktop.top) return false;
    box = {static_cast<UINT>(left), static_cast<UINT>(top), 0,
           static_cast<UINT>(left + kCrop), static_cast<UINT>(top + kCrop), 1};
    return true;
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc != 4) {
        puts("Usage: MfgDisplayFrameObserver.exe PROBE_PID CSV_PATH MAX_SECONDS");
        return 2;
    }
    wchar_t* end = nullptr;
    const unsigned long pid = wcstoul(argv[1], &end, 10);
    if (!pid || !end || *end) return 2;
    end = nullptr;
    const unsigned long seconds = wcstoul(argv[3], &end, 10);
    if (!seconds || seconds > 1200 || !end || *end) return 2;
    HANDLE process = OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!process) { printf("FAIL: cannot open probe PID=%lu error=%lu\n", pid, GetLastError()); return 3; }
    std::ofstream log(std::filesystem::path(argv[2]), std::ios::out | std::ios::trunc);
    if (!log) { CloseHandle(process); puts("FAIL: cannot open isolated CSV path"); return 3; }
    log << "sample,captureQpc,desktopPresentQpc,accumulatedFrames,hashChanged,roiHash,qpcHz\n";
    LARGE_INTEGER frequency{};
    QueryPerformanceFrequency(&frequency);
    printf("Observer PID=%lu clockHz=%lld ROI=256x256 foreground-only; DWM duplication is not physical scanout\n",
           pid, static_cast<long long>(frequency.QuadPart));
    const ULONGLONG deadline = GetTickCount64() + static_cast<ULONGLONG>(seconds) * 1000;
    TargetWindow target{pid};
    while (!target.hwnd && GetTickCount64() < deadline && WaitForSingleObject(process, 0) == WAIT_TIMEOUT) {
        EnumWindows(FindWindowByPid, reinterpret_cast<LPARAM>(&target));
        if (!target.hwnd) Sleep(50);
    }
    if (!target.hwnd) {
        CloseHandle(process);
        puts("No owned test window found; no desktop data sampled");
        return 3;
    }
    Capture capture;
    const HRESULT setup = CreateCapture(target.hwnd, capture);
    if (FAILED(setup)) {
        printf("FAIL: Desktop Duplication unavailable hr=0x%08x (e.g. remote desktop/HDR/active duplication)\n",
               static_cast<unsigned>(setup));
        CloseHandle(process);
        return 3;
    }
    unsigned samples = 0;
    unsigned distinct = 0;
    unsigned skippedUnfocused = 0;
    unsigned skippedCrop = 0;
    uint64_t previousHash = 0;
    bool haveHash = false;
    while (GetTickCount64() < deadline && WaitForSingleObject(process, 0) == WAIT_TIMEOUT) {
        if (!IsWindow(target.hwnd)) break;
        DXGI_OUTDUPL_FRAME_INFO info{};
        ComPtr<IDXGIResource> desktopResource;
        const HRESULT acquire = capture.duplication->AcquireNextFrame(100, &info, &desktopResource);
        if (acquire == DXGI_ERROR_WAIT_TIMEOUT) continue;
        if (FAILED(acquire)) {
            printf("Capture stopped: duplication lost hr=0x%08x\n", static_cast<unsigned>(acquire));
            break;
        }
        if (!IsOwnForeground(target.hwnd)) {
            ++skippedUnfocused;
            capture.duplication->ReleaseFrame();
            continue;
        }
        D3D11_BOX region{};
        if (!OwnWindowCrop(target.hwnd, capture.desktop, region)) {
            ++skippedCrop;
            capture.duplication->ReleaseFrame();
            continue;
        }
        ComPtr<ID3D11Texture2D> desktopTexture;
        if (SUCCEEDED(desktopResource.As(&desktopTexture))) {
            capture.context->CopySubresourceRegion(capture.staging.Get(), 0, 0, 0, 0,
                                                  desktopTexture.Get(), 0, &region);
            D3D11_MAPPED_SUBRESOURCE mapped{};
            if (SUCCEEDED(capture.context->Map(capture.staging.Get(), 0, D3D11_MAP_READ, 0, &mapped))) {
                const uint64_t hash = HashMappedPixels(mapped);
                capture.context->Unmap(capture.staging.Get(), 0);
                LARGE_INTEGER stamp{};
                QueryPerformanceCounter(&stamp);
                const bool changed = !haveHash || previousHash != hash;
                distinct += changed ? 1u : 0u;
                ++samples;
                log << samples << ',' << stamp.QuadPart << ',' << info.LastPresentTime.QuadPart
                    << ',' << info.AccumulatedFrames << ',' << (changed ? 1 : 0)
                    << ',' << hash << ',' << frequency.QuadPart << '\n';
                haveHash = true;
                previousHash = hash;
            }
        }
        capture.duplication->ReleaseFrame();
    }
    log.flush();
    printf("DWM foreground samples=%u distinct ROI hashes=%u unfocused=%u badCrop=%u; no image bytes saved\n",
           samples, distinct, skippedUnfocused, skippedCrop);
    puts("CAUTION: this samples desktop-composed pixels, not physical monitor scanout or proven interpolated frames.");
    CloseHandle(process);
    return samples > 0 ? 0 : 4;
}
