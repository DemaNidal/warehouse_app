# Start, stop, restart and inspect the warehouse server.
#
# The server runs as a scheduled task (SYSTEM, at boot), not from a terminal —
# see install_autostart.ps1 for why. Closing VS Code no longer stops it and
# Ctrl+C has nothing to interrupt; these are the controls instead.
#
#   powershell -ExecutionPolicy Bypass -File scripts\server.ps1 -Action status
#
# Or use the .bat shortcuts in the project folder.
#
# A task that runs as SYSTEM is INVISIBLE to a session that is not elevated —
# Get-ScheduledTask, schtasks and the COM API all answer "access denied", which
# is indistinguishable from "no such task" unless you check for it. Reporting
# "not registered" on that evidence is wrong, and was: this script called a
# correctly registered task missing three times running.

param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "status"
)

$TaskName = "WarehouseApp"
$Port = 5000

function Test-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-Listener {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Get-TaskState {
    # registered - seen.  hidden - unreadable and we are not elevated, so
    # unknown.  absent - elevated and genuinely not there.
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) { return @{ State = "registered"; Task = $task } }
    if (-not (Test-Elevated)) { return @{ State = "hidden"; Task = $null } }
    return @{ State = "absent"; Task = $null }
}

function Get-Origin([int]$ProcessId) {
    # Walk the parents: Code.exe means it dies with the editor, the Schedule
    # service means it does not.
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $proc) { return "unreadable" }

    $id = $proc.ParentProcessId
    for ($i = 0; $i -lt 6 -and $id; $i++) {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
        if (-not $p) { break }
        if ($p.Name -eq "Code.exe") { return "editor" }
        $svc = Get-CimInstance Win32_Service -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
        if ($svc -and $svc.Name -eq "Schedule") { return "scheduler" }
        $id = $p.ParentProcessId
    }
    return "unknown"
}

function Wait-ForPort([bool]$WantListening, [int]$Seconds = 12) {
    for ($i = 0; $i -lt $Seconds; $i++) {
        if (($null -ne (Get-Listener)) -eq $WantListening) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Show-Status {
    $info = Get-TaskState
    $conn = Get-Listener

    Write-Host ""

    switch ($info.State) {
        "registered" {
            Write-Host "المهمة المجدولة : مسجّلة ($($info.Task.State))" -ForegroundColor Green
        }
        "hidden" {
            Write-Host "المهمة المجدولة : ما بقدر أشوفها من هون" -ForegroundColor DarkGray
            Write-Host "                  مهام SYSTEM مخفية عن الجلسات العادية — مش دليل إنها ناقصة." -ForegroundColor DarkGray
            Write-Host "                  للتأكيد: شغّلي status.bat كمسؤول." -ForegroundColor DarkGray
        }
        "absent" {
            Write-Host "المهمة المجدولة : غير مسجّلة" -ForegroundColor Red
            Write-Host "                  شغّلي كمسؤول: scripts\install_autostart.ps1" -ForegroundColor Yellow
        }
    }

    if (-not $conn) {
        Write-Host "السيرفر         : واقف" -ForegroundColor Red
        Write-Host ""
        return
    }

    Write-Host "السيرفر         : شغّال  (PID $($conn.OwningProcess))" -ForegroundColor Green

    switch (Get-Origin $conn.OwningProcess) {
        "editor" {
            Write-Host "المصدر          : طرفية VS Code — بيوقف لما تسكّري المحرر" -ForegroundColor Yellow
        }
        "scheduler" {
            if ($info.State -eq "absent") {
                Write-Host "المصدر          : مهمة مجدولة انشالت بعدين" -ForegroundColor Yellow
                Write-Host "                  شغّال الآن، بس ما بيرجع بعد إعادة تشغيل الجهاز." -ForegroundColor Yellow
            } else {
                Write-Host "المصدر          : المهمة المجدولة — بينجو من إغلاق المحرر وإعادة التشغيل" -ForegroundColor Green
            }
        }
        "unreadable" {
            Write-Host "المصدر          : ما قدرت أقراه (عملية SYSTEM)" -ForegroundColor DarkGray
        }
        default {
            Write-Host "المصدر          : غير معروف" -ForegroundColor DarkGray
        }
    }

    Write-Host "العنوان         : http://localhost:$Port   ·   http://$env:COMPUTERNAME`:$Port"
    Write-Host ""
}

function Stop-Server {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

    if (Wait-ForPort -WantListening $false -Seconds 8) {
        Write-Host "توقّف ✓" -ForegroundColor Green
        return $true
    }

    # Stop-ScheduledTask does not always end the process, and a server started
    # from a terminal has no task to stop at all.
    $conn = Get-Listener
    if ($conn) {
        try { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop }
        catch {
            Write-Host "ما قدرت أوقفه — العملية بتشتغل كـSYSTEM." -ForegroundColor Red
            Write-Host "شغّلي stop.bat كمسؤول." -ForegroundColor Yellow
            return $false
        }
    }

    if (Wait-ForPort -WantListening $false -Seconds 6) {
        Write-Host "توقّف ✓" -ForegroundColor Green
        return $true
    }

    Write-Host "لسا شغّال — جرّبي كمسؤول." -ForegroundColor Red
    return $false
}

function Start-Server {
    if (Get-Listener) {
        Write-Host "شغّال أصلاً." -ForegroundColor Yellow
        return $true
    }

    # Try regardless of whether the task is visible from here: it may well be
    # registered and merely unreadable, and the port is the honest answer.
    Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

    if (Wait-ForPort -WantListening $true -Seconds 20) {
        Write-Host "اشتغل ✓" -ForegroundColor Green
        return $true
    }

    $info = Get-TaskState
    Write-Host "ما اشتغل." -ForegroundColor Red

    if ($info.State -eq "absent") {
        Write-Host "المهمة غير مسجّلة — شغّلي كمسؤول:" -ForegroundColor Yellow
        Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1"
    } elseif ($info.State -eq "hidden") {
        Write-Host "المهمة مخفية عن جلستك — شغّلي start.bat كمسؤول." -ForegroundColor Yellow
    } else {
        Write-Host "افحصي السجل:" -ForegroundColor Yellow
        Write-Host "  Get-Content E:\warehouse_app\logs\app.log -Tail 30"
    }
    return $false
}

switch ($Action) {
    "status"  { Show-Status }
    "stop"    { Stop-Server | Out-Null; Show-Status }
    "start"   { Start-Server | Out-Null; Show-Status }
    "restart" {
        if (Stop-Server) { Start-Sleep -Seconds 2; Start-Server | Out-Null }
        Show-Status
    }
}
