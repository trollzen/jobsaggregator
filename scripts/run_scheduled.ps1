# Запуск jobagg из Планировщика заданий Windows.
# Пишет вывод в logs\jobagg.log (дата и время в каждой строке, хранит 30 дней),
# при ошибке (код выхода не 0) показывает уведомление Windows.
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_scheduled.ps1
param(
    [string]$Config = "config.yaml",  # для проверки уведомления можно передать несуществующий файл
    [int]$KeepDays = 30
)
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$logDir = Join-Path $root "logs"
$log = Join-Path $logDir "jobagg.log"
$tmp = Join-Path $logDir "last_run.txt"
New-Item -ItemType Directory -Force $logDir | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Stamp { (Get-Date).ToString("yyyy-MM-dd HH:mm:ss") }

function Show-Toast([string]$title, [string]$text) {
    try {
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        $esc = { param($s) [System.Security.SecurityElement]::Escape($s) }
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$(& $esc $title)</text><text>$(& $esc $text)</text></binding></visual></toast>")
        # уведомление от имени Windows PowerShell (своего ярлыка приложения нам не нужно)
        $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show(
            [Windows.UI.Notifications.ToastNotification]::new($xml))
    } catch {
        msg.exe $env:USERNAME "$title`n$text" 2>$null  # запасной вариант: простое окно
    }
}

# 1. запуск программы (вывод во временный файл, так надёжнее с русским текстом)
$env:PYTHONIOENCODING = "utf-8"
$exe = Join-Path $root ".venv\Scripts\jobagg.exe"
$start = Stamp
if (Test-Path $exe) {
    cmd /c "`"$exe`" --config `"$Config`" > `"$tmp`" 2>&1"
    $code = $LASTEXITCODE
    $lines = if (Test-Path $tmp) { [IO.File]::ReadAllLines($tmp, $utf8) } else { @() }
} else {
    $code = 9009
    $lines = @("ERROR program not found: $exe")
}
Remove-Item $tmp -ErrorAction SilentlyContinue
$lines = @($lines | Where-Object { $_ -notmatch "HTTP Request:" -and $_.Trim() -ne "" })

# 2. дописать в лог: каждая строка с датой и временем
$out = @("$start ===== start =====")
$out += $lines | ForEach-Object { "$start $_" }
$out += "$(Stamp) ===== end, exit code $code ====="
[IO.File]::AppendAllLines($log, [string[]]$out, $utf8)

# 3. оставить в логе только последние $KeepDays дней
$cutoff = (Get-Date).AddDays(-$KeepDays).ToString("yyyy-MM-dd")
$all = [IO.File]::ReadAllLines($log, $utf8)
$keep = @($all | Where-Object { $_.Length -lt 10 -or $_.Substring(0, 10) -ge $cutoff })
if ($keep.Count -lt $all.Count) { [IO.File]::WriteAllLines($log, [string[]]$keep, $utf8) }

# 4. ошибка -> уведомление с короткой причиной
if ($code -ne 0) {
    $reason = ($lines | Where-Object { $_ -match "ERROR|Error|error" } | Select-Object -Last 1)
    if (-not $reason) { $reason = $lines | Select-Object -Last 1 }
    if (-not $reason) { $reason = "без вывода" }
    $reason = ($reason -replace "^(ERROR|INFO|WARNING)\s+", "")
    if ($reason.Length -gt 180) { $reason = $reason.Substring(0, 180) + "..." }
    Show-Toast "jobagg: запуск упал (код $code)" "$reason`nПодробности: logs\jobagg.log"
}
exit $code
