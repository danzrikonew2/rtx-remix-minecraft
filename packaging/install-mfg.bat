:: SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
:: SPDX-License-Identifier: Apache-2.0
@echo off
setlocal
set "PSModulePath="
powershell.exe -NoProfile -NoLogo -ExecutionPolicy Bypass -File "%~dp0installer.ps1" -Mode Install -Launcher Prism -EnableMfgUnlocker %*
exit /b %ERRORLEVEL%
