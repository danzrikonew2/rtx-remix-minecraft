// SPDX-License-Identifier: Apache-2.0
// Read-only Windows Wait Chain Traversal diagnostic for an isolated probe PID.
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <TlHelp32.h>
#include <DbgHelp.h>
#include <wct.h>
#include <cstdio>
#include <cwchar>
#include <array>
#include <vector>

static const char* ObjectName(WCT_OBJECT_TYPE type) {
    switch (type) {
    case WctCriticalSectionType: return "critical-section";
    case WctSendMessageType: return "send-message";
    case WctMutexType: return "mutex";
    case WctAlpcType: return "alpc";
    case WctComType: return "com";
    case WctThreadWaitType: return "thread-wait";
    case WctProcessWaitType: return "process-wait";
    case WctThreadType: return "thread";
    case WctComActivationType: return "com-activation";
    case WctSocketIoType: return "socket-io";
    case WctSmbIoType: return "smb-io";
    default: return "unknown";
    }
}

static const char* StatusName(WCT_OBJECT_STATUS status) {
    switch (status) {
    case WctStatusNoAccess: return "no-access";
    case WctStatusRunning: return "running";
    case WctStatusBlocked: return "blocked";
    case WctStatusPidOnly: return "pid-only";
    case WctStatusPidOnlyRpcss: return "pid-only-rpcss";
    case WctStatusOwned: return "owned";
    case WctStatusNotOwned: return "not-owned";
    case WctStatusAbandoned: return "abandoned";
    case WctStatusError: return "error";
    default: return "unknown";
    }
}

// A fallback for optimized x64 modules where DbgHelp fails to unwind past
// an ntdll syscall stub. These are potential return addresses, not frames:
// data on the stack can resemble code pointers, and a scan cannot establish
// call order. Only committed executable addresses mapped into known modules
// are printed; no target memory is modified.
static void PrintStackCandidates(HANDLE process, DWORD tid, DWORD64 rsp) {
    constexpr SIZE_T kScanBytes = 4096;
    constexpr unsigned kMaxCandidates = 24;
    std::array<unsigned char, kScanBytes> bytes{};
    MEMORY_BASIC_INFORMATION stackRegion{};
    if (!VirtualQueryEx(process, reinterpret_cast<LPCVOID>(rsp), &stackRegion, sizeof(stackRegion)) ||
        stackRegion.State != MEM_COMMIT || (stackRegion.Protect & (PAGE_GUARD | PAGE_NOACCESS))) {
        printf("  STACK-CANDIDATES TID=%lu stack region unavailable\n", tid);
        return;
    }
    const auto regionEnd = reinterpret_cast<ULONG_PTR>(stackRegion.BaseAddress) + stackRegion.RegionSize;
    const auto remaining = regionEnd > rsp ? regionEnd - rsp : 0;
    const SIZE_T wanted = static_cast<SIZE_T>(remaining < kScanBytes ? remaining : kScanBytes);
    SIZE_T read = 0;
    if (!wanted || !ReadProcessMemory(process, reinterpret_cast<LPCVOID>(rsp), bytes.data(), wanted, &read)) {
        printf("  STACK-CANDIDATES TID=%lu ReadProcessMemory error=%lu bytes=%zu\n",
               tid, GetLastError(), static_cast<size_t>(read));
    }
    unsigned count = 0;
    for (SIZE_T offset = 0; offset + sizeof(DWORD64) <= read && count < kMaxCandidates; offset += sizeof(DWORD64)) {
        DWORD64 candidate = 0;
        memcpy(&candidate, bytes.data() + offset, sizeof(candidate));
        if (candidate < 0x10000 || candidate > 0x00007FFFFFFFFFFFull) continue;
        MEMORY_BASIC_INFORMATION mbi{};
        if (!VirtualQueryEx(process, reinterpret_cast<LPCVOID>(candidate), &mbi, sizeof(mbi))) continue;
        constexpr DWORD kExecutable = PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY;
        if (mbi.State != MEM_COMMIT || (mbi.Protect & kExecutable) == 0 || (mbi.Protect & PAGE_GUARD)) continue;
        IMAGEHLP_MODULE64 module{};
        module.SizeOfStruct = sizeof(module);
        if (!SymGetModuleInfo64(process, candidate, &module)) continue;
        printf("  STACK-CANDIDATE (UNVERIFIED) TID=%lu rsp+0x%zx %s+0x%llx\n",
               tid, static_cast<size_t>(offset), module.ModuleName,
               static_cast<unsigned long long>(candidate - module.BaseOfImage));
        ++count;
    }
    printf("  STACK-CANDIDATES TID=%lu found=%u scanned=%zu bytes (NOT an unwound backtrace)\n",
           tid, count, static_cast<size_t>(read));
}

// The only threads suspended here are the two in a WCT thread-wait dependency.
// The diagnostic process has a separate 10-second timeout in the probe runner.
static void PrintThreadStack(HANDLE process, DWORD tid) {
    HANDLE thread = OpenThread(THREAD_GET_CONTEXT | THREAD_SUSPEND_RESUME | THREAD_QUERY_INFORMATION,
                               FALSE, tid);
    if (!thread) {
        printf("STACK TID=%lu OpenThread error=%lu\n", tid, GetLastError());
        return;
    }
    const DWORD previousSuspend = SuspendThread(thread);
    if (previousSuspend == static_cast<DWORD>(-1)) {
        printf("STACK TID=%lu SuspendThread error=%lu\n", tid, GetLastError());
        CloseHandle(thread);
        return;
    }
    CONTEXT context{};
    context.ContextFlags = CONTEXT_FULL;
    if (!GetThreadContext(thread, &context)) {
        printf("STACK TID=%lu GetThreadContext error=%lu\n", tid, GetLastError());
    } else {
        const DWORD64 savedRsp = context.Rsp;
        STACKFRAME64 stack{};
        stack.AddrPC = {context.Rip, AddrModeFlat};
        // x64 optimized frames are RSP based; RBP is often reused as a general register.
        stack.AddrFrame = {context.Rsp, AddrModeFlat};
        stack.AddrStack = {context.Rsp, AddrModeFlat};
        printf("STACK TID=%lu (module offsets; symbol names best-effort)\n", tid);
        for (unsigned level = 0; level < 24 && stack.AddrPC.Offset; ++level) {
            const DWORD64 address = stack.AddrPC.Offset;
            IMAGEHLP_MODULE64 module{};
            module.SizeOfStruct = sizeof(module);
            const bool hasModule = SymGetModuleInfo64(process, address, &module) != FALSE;
            alignas(SYMBOL_INFO) unsigned char buffer[sizeof(SYMBOL_INFO) + MAX_SYM_NAME]{};
            auto* symbol = reinterpret_cast<SYMBOL_INFO*>(buffer);
            symbol->SizeOfStruct = sizeof(SYMBOL_INFO);
            symbol->MaxNameLen = MAX_SYM_NAME;
            DWORD64 displacement = 0;
            const bool hasSymbol = SymFromAddr(process, address, &displacement, symbol) != FALSE;
            printf("  #%02u %s+0x%llx %s\n", level,
                   hasModule ? module.ModuleName : "unknown-module",
                   static_cast<unsigned long long>(hasModule ? address - module.BaseOfImage : address),
                   hasSymbol ? symbol->Name : "[no symbols]");
            if (!StackWalk64(IMAGE_FILE_MACHINE_AMD64, process, thread, &stack, &context,
                             nullptr, SymFunctionTableAccess64, SymGetModuleBase64, nullptr)) {
                printf("  unwind stopped at #%02u win32=%lu\n", level, GetLastError());
                break;
            }
        }
        PrintStackCandidates(process, tid, savedRsp);
    }
    // Unconditionally resume our one suspension, including on context failures.
    if (ResumeThread(thread) == static_cast<DWORD>(-1))
        printf("STACK TID=%lu ResumeThread error=%lu\n", tid, GetLastError());
    CloseHandle(thread);
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 2 || argc > 3 || (argc == 3 && wcscmp(argv[2], L"--stacks") != 0)) {
        fwprintf(stderr, L"Usage: MfgWaitChainProbe.exe PID [--stacks]\n");
        return 2;
    }
    wchar_t* end = nullptr;
    const unsigned long pid = wcstoul(argv[1], &end, 10);
    if (!pid || !end || *end != L'\0') return 2;

    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snapshot == INVALID_HANDLE_VALUE) {
        printf("FAIL: thread snapshot error=%lu\n", GetLastError());
        return 1;
    }
    std::vector<DWORD> threads;
    THREADENTRY32 entry{};
    entry.dwSize = sizeof(entry);
    if (Thread32First(snapshot, &entry)) {
        do {
            if (entry.th32OwnerProcessID == pid) threads.push_back(entry.th32ThreadID);
            entry.dwSize = sizeof(entry);
        } while (Thread32Next(snapshot, &entry));
    }
    CloseHandle(snapshot);
    if (threads.empty()) {
        printf("FAIL: no live threads found for PID %lu\n", pid);
        return 1;
    }
    HWCT session = OpenThreadWaitChainSession(0, nullptr);
    if (!session) {
        printf("FAIL: WCT session error=%lu\n", GetLastError());
        return 1;
    }
    printf("Wait chain snapshot PID=%lu threads=%zu tick_ms=%llu\n",
           pid, threads.size(), static_cast<unsigned long long>(GetTickCount64()));
    unsigned failures = 0;
    unsigned blocked = 0;
    std::vector<DWORD> dependencyTids;
    for (DWORD tid : threads) {
        WAITCHAIN_NODE_INFO chain[WCT_MAX_NODE_COUNT]{};
        DWORD count = WCT_MAX_NODE_COUNT;
        BOOL cycle = FALSE;
        if (!GetThreadWaitChain(session, 0, 0, tid, &count, chain, &cycle)) {
            printf("TID=%lu WCT error=%lu\n", tid, GetLastError());
            ++failures;
            continue;
        }
        printf("TID=%lu nodes=%lu cycle=%u", tid, count, cycle);
        if (count && chain[0].ObjectStatus == WctStatusBlocked) ++blocked;
        if (argc == 3 && count >= 3 && chain[1].ObjectType == WctThreadWaitType &&
            chain[count - 1].ObjectType == WctThreadType &&
            chain[count - 1].ThreadObject.ProcessId == pid) {
            const DWORD ownerTid = chain[count - 1].ThreadObject.ThreadId;
            if (dependencyTids.empty()) {
                dependencyTids.push_back(tid);
                if (ownerTid != tid) dependencyTids.push_back(ownerTid);
            }
        }
        for (DWORD n = 0; n < count; ++n) {
            const auto& node = chain[n];
            printf(" | %s:%s", ObjectName(node.ObjectType), StatusName(node.ObjectStatus));
            if (node.ObjectType == WctThreadType) {
                printf("(%lu/%lu wait_ms=%lu switches=%lu)", node.ThreadObject.ProcessId,
                       node.ThreadObject.ThreadId, node.ThreadObject.WaitTime,
                       node.ThreadObject.ContextSwitches);
            } else if (node.LockObject.ObjectName[0]) {
                printf("(%ls)", node.LockObject.ObjectName);
            }
        }
        printf("\n");
    }
    CloseThreadWaitChainSession(session);
    if (argc == 3) {
        if (dependencyTids.empty()) {
            puts("STACK: WCT found no same-process thread-wait owner; no threads suspended.");
        } else {
            printf("STACK: WCT dependency blocked TID=%lu owner TID=%lu\n",
                   dependencyTids[0], dependencyTids.size() > 1 ? dependencyTids[1] : dependencyTids[0]);
            HANDLE process = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, FALSE, pid);
            if (!process) {
                printf("STACK OpenProcess error=%lu\n", GetLastError());
            } else {
                SymSetOptions(SYMOPT_NO_PROMPTS | SYMOPT_DEFERRED_LOADS | SYMOPT_UNDNAME);
                if (!SymInitialize(process, ".", TRUE)) {
                    printf("STACK SymInitialize error=%lu\n", GetLastError());
                } else {
                    for (DWORD threadId : dependencyTids) PrintThreadStack(process, threadId);
                    SymCleanup(process);
                }
                CloseHandle(process);
            }
        }
    }
    printf("WCT complete: threads=%zu blocked=%u errors=%u; stack capture %s.\n",
           threads.size(), blocked, failures, argc == 3 ? "requested" : "disabled");
    return failures == threads.size() ? 1 : 0;
}
