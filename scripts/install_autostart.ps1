# Keep the warehouse app running without anyone starting it.
#
# The app has been running inside a VS Code terminal, which is why it is gone
# every morning: closing the editor (or letting it restart itself for an
# update) kills the shell, and the shell takes its child processes with it.
# A scheduled task has no console to close and no parent to lose.
#
# Registered to run as SYSTEM on purpose. The alternative — running as your own
# account "whether logged on or not" — requires Windows to store your password,
# and this needs no user profile of its own.
#
#   Run in PowerShell AS ADMINISTRATOR:
#       powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1
#
#   To remove it later:
#       Unregister-ScheduledTask -TaskName "WarehouseApp" -Confirm:$false

$ErrorActionPreference = "Stop"

$TaskName = "WarehouseApp"
$AppDir   = "E:\warehouse_app"
$Python   = Join-Path $AppDir "venv\Scripts\python.exe"

# ---------------------------------------------------------------- checks

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "لازم تشغّلي PowerShell كمسؤول (Run as administrator)." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $Python)) {
    Write-Host "ما لقيت بايثون على: $Python" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------- the task

$action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "wsgi.py" `
    -WorkingDirectory $AppDir

# At startup, so it comes back after a power cut or a Windows update reboot
# without waiting for anyone to sign in.
$trigger = New-ScheduledTaskTrigger -AtStartup

$principal = New-ScheduledTaskPrincipal `
    -UserId "NT AUTHORITY\SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -RestartCount 999 `
    -ExecutionTimeLimit ([TimeSpan]::Zero)   # never time out; the default kills it after 3 days

# a moment for the network and PostgreSQL to be up before the app reaches for them
$trigger.Delay = "PT30S"

# -Force replaces an existing task in one step. Deleting it first and
# registering afterwards leaves nothing registered at all if the second half
# fails — which is how a task can vanish while the process it already started
# keeps running, looking fine until the next reboot.
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force `
    -Description "يشغّل نظام المخازن عند إقلاع ويندوز ويعيد تشغيله لو وقف." | Out-Null

if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
    Write-Host "فشل التسجيل — المهمة مش موجودة." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "تم تسجيل المهمة «$TaskName»." -ForegroundColor Green

# ------------------------------------------------------------ port check

$busy = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue

if ($busy) {
    $owner = Get-Process -Id $busy.OwningProcess -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "المنفذ 5000 مشغول حالياً بـ PID $($busy.OwningProcess) ($($owner.ProcessName))." -ForegroundColor Yellow
    Write-Host "هاي على الأغلب النسخة اللي شغّالة من طرفية VS Code."
    Write-Host "سكّريها، وبعدين شغّلي المهمة:" -ForegroundColor Yellow
    Write-Host "    Start-ScheduledTask -TaskName $TaskName"
} else {
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 6
    $now = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
    if ($now) {
        Write-Host "المهمة اشتغلت والبرنامج يستمع على المنفذ 5000." -ForegroundColor Green
    } else {
        Write-Host "المهمة انسجّلت بس البرنامج ما ردّ بعد. افحصي:" -ForegroundColor Yellow
        Write-Host "    Get-ScheduledTaskInfo -TaskName $TaskName"
        Write-Host "    Get-Content $AppDir\logs\app.log -Tail 30"
    }
}

Write-Host ""
Write-Host "من الآن: بتشتغل مع إقلاع ويندوز، وبترجع لحالها لو وقفت." -ForegroundColor Green
