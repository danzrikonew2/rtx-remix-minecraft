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

struct VisualFeatures {
    uint64_t hash = 14695981039346656037ull;
    uint64_t orangePixels = 0;
    double orangeCentroidX = -1.0;
    double orangeCentroidY = -1.0;
    int orangeMinX = -1;
    int orangeMinY = -1;
    int orangeMaxX = -1;
    int orangeMaxY = -1;
    uint64_t edgePixels = 0;
    double edgeCentroidX = -1.0;
    double edgeCentroidY = -1.0;
    uint64_t edgeWeight = 0;
    double meanR = 0.0;
    double meanG = 0.0;
    double meanB = 0.0;
};

VisualFeatures AnalyzeMappedPixels(const D3D11_MAPPED_SUBRESOURCE& mapped) {
    VisualFeatures features{};
    uint64_t redSum = 0;
    uint64_t greenSum = 0;
    uint64_t blueSum = 0;
    uint64_t orangeX = 0;
    uint64_t orangeY = 0;
    uint64_t edgeX = 0;
    uint64_t edgeY = 0;
    UINT orangeMinX = kCrop;
    UINT orangeMinY = kCrop;
    UINT orangeMaxX = 0;
    UINT orangeMaxY = 0;

    for (UINT row = 0; row < kCrop; ++row) {
        const auto* pixels = static_cast<const uint8_t*>(mapped.pData) +
                             static_cast<size_t>(row) * mapped.RowPitch;
        const auto* previousRow = row == 0 ? nullptr :
            static_cast<const uint8_t*>(mapped.pData) +
            static_cast<size_t>(row - 1) * mapped.RowPitch;
        for (UINT col = 0; col < kCrop; ++col) {
            const auto* color = pixels + col * 4;
            const uint8_t blue = color[0];
            const uint8_t green = color[1];
            const uint8_t red = color[2];
            redSum += red;
            greenSum += green;
            blueSum += blue;

            unsigned gradient = 0;
            if (col != 0) {
                const auto* left = color - 4;
                gradient += static_cast<unsigned>(std::abs(int(red) - int(left[2])));
                gradient += static_cast<unsigned>(std::abs(int(green) - int(left[1])));
                gradient += static_cast<unsigned>(std::abs(int(blue) - int(left[0])));
            }
            if (previousRow != nullptr) {
                const auto* up = previousRow + col * 4;
                gradient += static_cast<unsigned>(std::abs(int(red) - int(up[2])));
                gradient += static_cast<unsigned>(std::abs(int(green) - int(up[1])));
                gradient += static_cast<unsigned>(std::abs(int(blue) - int(up[0])));
            }
            if (gradient >= 48) {
                ++features.edgePixels;
                features.edgeWeight += gradient;
                edgeX += static_cast<uint64_t>(gradient) * col;
                edgeY += static_cast<uint64_t>(gradient) * row;
            }

            if ((row % kStride) == 0 && (col % kStride) == 0) {
                for (UINT channel = 0; channel < 3; ++channel) {
                    features.hash ^= color[channel];
                    features.hash *= 1099511628211ull;
                }
            }

            // Broad enough to tolerate Remix tonemapping while rejecting the dark background.
            if (red >= 72 && red >= green + 14 && green >= blue + 6 &&
                static_cast<unsigned>(red) + green >= 150) {
                ++features.orangePixels;
                orangeX += col;
                orangeY += row;
                orangeMinX = std::min(orangeMinX, col);
                orangeMinY = std::min(orangeMinY, row);
                orangeMaxX = std::max(orangeMaxX, col);
                orangeMaxY = std::max(orangeMaxY, row);
            }
        }
    }

    constexpr double pixelCount = static_cast<double>(kCrop) * kCrop;
    features.meanR = redSum / pixelCount;
    features.meanG = greenSum / pixelCount;
    features.meanB = blueSum / pixelCount;
    if (features.orangePixels) {
        features.orangeCentroidX = static_cast<double>(orangeX) / features.orangePixels;
        features.orangeCentroidY = static_cast<double>(orangeY) / features.orangePixels;
        features.orangeMinX = static_cast<int>(orangeMinX);
        features.orangeMinY = static_cast<int>(orangeMinY);
        features.orangeMaxX = static_cast<int>(orangeMaxX);
        features.orangeMaxY = static_cast<int>(orangeMaxY);
    }
    if (features.edgeWeight) {
        features.edgeCentroidX = static_cast<double>(edgeX) / features.edgeWeight;
        features.edgeCentroidY = static_cast<double>(edgeY) / features.edgeWeight;
    }
    return features;
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
    log << "sample,captureQpc,desktopPresentQpc,accumulatedFrames,hashChanged,roiHash,qpcHz,"
           "orangePixels,orangeCentroidX,orangeCentroidY,orangeMinX,orangeMinY,orangeMaxX,orangeMaxY,"
           "edgePixels,edgeCentroidX,edgeCentroidY,edgeWeight,meanR,meanG,meanB\n";
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
                const VisualFeatures features = AnalyzeMappedPixels(mapped);
                capture.context->Unmap(capture.staging.Get(), 0);
                LARGE_INTEGER stamp{};
                QueryPerformanceCounter(&stamp);
                const bool changed = !haveHash || previousHash != features.hash;
                distinct += changed ? 1u : 0u;
                ++samples;
                log << samples << ',' << stamp.QuadPart << ',' << info.LastPresentTime.QuadPart
                    << ',' << info.AccumulatedFrames << ',' << (changed ? 1 : 0)
                    << ',' << features.hash << ',' << frequency.QuadPart
                    << ',' << features.orangePixels << ',' << features.orangeCentroidX
                    << ',' << features.orangeCentroidY << ',' << features.orangeMinX
                    << ',' << features.orangeMinY << ',' << features.orangeMaxX
                    << ',' << features.orangeMaxY << ',' << features.edgePixels
                    << ',' << features.edgeCentroidX << ',' << features.edgeCentroidY
                    << ',' << features.edgeWeight << ',' << features.meanR
                    << ',' << features.meanG << ',' << features.meanB << '\n';
                haveHash = true;
                previousHash = features.hash;
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
