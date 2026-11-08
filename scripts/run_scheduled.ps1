# Запуск jobagg из Планировщика заданий Windows.
# Пишет вывод в logs\jobagg.log (дата и время в каждой строке, хранит 30 дней),
# после запуска показывает уведомление Windows: сколько новых вакансий или причину ошибки.
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_scheduled.ps1
param(
    [string]$Config = "config.yaml",  # для проверки уведомления можно передать несуществующий файл
    [int]$KeepDays = 30,
    [switch]$NoSuccessToast  # не показывать уведомление при успешном запуске
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

function Show-Toast([string]$title, [string]$text, [string]$url = "") {
    try {
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        $esc = { param($s) [System.Security.SecurityElement]::Escape($s) }
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        # щелчок по уведомлению открывает $url (Google-таблицу)
        $launch = if ($url) { " activationType='protocol' launch='$(& $esc $url)'" } else { "" }
        $xml.LoadXml("<toast$launch><visual><binding template='ToastGeneric'><text>$(& $esc $title)</text><text>$(& $esc $text)</text></binding></visual></toast>")
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
# отметка о старте сразу: если запуск прервут, это будет видно в логе
[IO.File]::AppendAllLines($log, [string[]]@("$start ===== start ====="), $utf8)
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
$out = @()
$out += $lines | ForEach-Object { "$start $_" }
$out += "$(Stamp) ===== end, exit code $code ====="
[IO.File]::AppendAllLines($log, [string[]]$out, $utf8)

# 3. оставить в логе только последние $KeepDays дней
$cutoff = (Get-Date).AddDays(-$KeepDays).ToString("yyyy-MM-dd")
$all = [IO.File]::ReadAllLines($log, $utf8)
$keep = @($all | Where-Object { $_.Length -lt 10 -or $_.Substring(0, 10) -ge $cutoff })
if ($keep.Count -lt $all.Count) { [IO.File]::WriteAllLines($log, [string[]]$keep, $utf8) }

# ссылка на таблицу для щелчка по уведомлению (SHEET_ID из .env)
$sheetUrl = ""
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    $m = Select-String -Path $envFile -Pattern '^\s*SHEET_ID\s*=\s*"?([^"\s]+)' | Select-Object -First 1
    if ($m) { $sheetUrl = "https://docs.google.com/spreadsheets/d/$($m.Matches[0].Groups[1].Value)" }
}

function Plural([int]$n, [string]$one, [string]$few, [string]$many) {
    $n10 = $n % 10; $n100 = $n % 100
    if ($n10 -eq 1 -and $n100 -ne 11) { return $one }
    if ($n10 -ge 2 -and $n10 -le 4 -and ($n100 -lt 12 -or $n100 -gt 14)) { return $few }
    return $many
}

# 4. успех -> уведомление: сколько новых вакансий
if ($code -eq 0 -and -not $NoSuccessToast) {
    $summary = $lines | Where-Object { $_ -match "^SUMMARY " } | Select-Object -Last 1
    $num = { param($key) if ($summary -match "\b$key=(\d+)") { [int]$Matches[1] } else { 0 } }
    $written = & $num "written"; $high = & $num "high"; $medium = & $num "medium"
    if ($written -gt 0) {
        $title = "jobagg: $written " + (Plural $written "новая вакансия" "новые вакансии" "новых вакансий")
        $text = "высокий приоритет: $high, средний: $medium. Щёлкните, чтобы открыть таблицу"
    } else {
        $title = "jobagg: новых вакансий нет"
        $text = "Каналы проверены: " + (& $num "channels_ok") + ", прочитано постов: " + (& $num "read")
    }
    Show-Toast $title $text $sheetUrl
}

# 5. ошибка -> уведомление с короткой причиной
if ($code -ne 0) {
    $reason = ($lines | Where-Object { $_ -match "ERROR|Error|error" } | Select-Object -Last 1)
    if (-not $reason) { $reason = $lines | Select-Object -Last 1 }
    if (-not $reason) { $reason = "без вывода" }
    $reason = ($reason -replace "^(ERROR|INFO|WARNING)\s+", "")
    if ($reason.Length -gt 180) { $reason = $reason.Substring(0, 180) + "..." }
    Show-Toast "jobagg: запуск упал (код $code)" "$reason`nПодробности: logs\jobagg.log"
}
exit $code
