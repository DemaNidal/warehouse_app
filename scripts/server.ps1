# Start, stop, restart and inspect the warehouse server.
#
# The server runs as a scheduled task (SYSTEM, at boot), not from a terminal —
# see install_autostart.ps1 for why. That means closing VS Code no longer stops
# it, and neither does Ctrl+C anywhere. These are the controls instead.
#
#   powershell -ExecutionPolicy Bypass -File scripts\server.ps1 -Action status
#
# Or use the .bat shortcuts in the project folder.

param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "status"
)

$TaskName = "WarehouseApp"
$Port = 5000

function Get-Listener {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Wait-ForPort([bool]$WantListening, [int]$Seconds = 12) {
    for ($i = 0; $i -lt $Seconds; $i++) {
        $listening = $null -ne (Get-Listener)
        if ($listening -eq $WantListening) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Show-Status {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $conn = Get-Listener

    Write-Host ""
    if ($task) {
        Write-Host "المهمة المجدولة : مسجّلة ($($task.State))" -ForegroundColor Green
    } else {
        Write-Host "المهمة المجدولة : غير مسجّلة" -ForegroundColor Yellow
        Write-Host "  شغّلي كمسؤول:  powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1"
    }

    if (-not $conn) {
        Write-Host "السيرفر         : واقف" -ForegroundColor Red
        Write-Host ""
        return
    }

    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue
    Write-Host "السيرفر         : شغّال  (PID $($conn.OwningProcess))" -ForegroundColor Green

    # Which parent started it says whether this survives closing the editor.
    # "not the editor" is not the same as "the scheduler": the process info can
    # also be unreadable, and a task can be removed while the process it
    # started keeps running — which looks healthy until the next reboot.
    $id = if ($proc) { $proc.ParentProcessId } else { $null }
    $origin = if ($proc) { "unknown" } else { "unreadable" }

    for ($i = 0; $i -lt 6 -and $id; $i++) {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
        if (-not $p) { break }
        if ($p.Name -eq "Code.exe") { $origin = "editor"; break }
        $svc = Get-CimInstance Win32_Service -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
        if ($svc -and $svc.Name -eq "Schedule") { $origin = "scheduler"; break }
        $id = $p.ParentProcessId
    }

    switch ($origin) {
        "editor" {
            Write-Host "المصدر          : طرفية VS Code — بيوقف لما تسكّري المحرر" -ForegroundColor Yellow
        }
        "scheduler" {
            if ($task) {
                Write-Host "المصدر          : المهمة المجدولة — بينجو من إغلاق المحرر وإعادة التشغيل" -ForegroundColor Green
            } else {
                Write-Host "المصدر          : مهمة مجدولة انشالت بعدين" -ForegroundColor Yellow
                Write-Host "                  شغّال الآن، بس ما بيرجع بعد إعادة تشغيل الجهاز." -ForegroundColor Yellow
                Write-Host "                  سجّلي المهمة من جديد (كمسؤول):" -ForegroundColor Yellow
                Write-Host "                  powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1"
            }
        }
        "unreadable" {
            Write-Host "المصدر          : ما قدرت أقراه (عملية SYSTEM) — جرّبي كمسؤول" -ForegroundColor Yellow
        }
        default {
            Write-Host "المصدر          : غير معروف" -ForegroundColor Yellow
        }
    }

    Write-Host "العنوان         : http://localhost:$Port   ·   http://$env:COMPUTERNAME`:$Port"
    Write-Host ""
}

function Stop-Server {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }

    if (Wait-ForPort -WantListening $false -Seconds 8) {
        Write-Host "توقّف ✓" -ForegroundColor Green
        return $true
    }

    # Stop-ScheduledTask does not always end the process, and a server started
    # from a terminal has no task to stop at all.
    $conn = Get-Listener
    if ($conn) {
        try {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop
        } catch {
            Write-Host "ما قدرت أوقفه — العملية بتشتغل كـSYSTEM." -ForegroundColor Red
            Write-Host "افتحي PowerShell كمسؤول وشغّلي نفس الأمر." -ForegroundColor Yellow
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

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Host "المهمة غير مسجّلة." -ForegroundColor Red
        Write-Host "شغّلي كمسؤول:" -ForegroundColor Yellow
        Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1"
        return $false
    }

    Start-ScheduledTask -TaskName $TaskName

    if (Wait-ForPort -WantListening $true -Seconds 20) {
        Write-Host "اشتغل ✓" -ForegroundColor Green
        return $true
    }

    Write-Host "المهمة انطلقت بس السيرفر ما ردّ. افحصي:" -ForegroundColor Yellow
    Write-Host "  Get-Content E:\warehouse_app\logs\app.log -Tail 30"
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
