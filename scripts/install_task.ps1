# Создаёт (или пересоздаёт) задание "jobagg" в Планировщике заданий Windows.
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_task.ps1
# Раз в сутки в 16:00; пропущенный запуск (компьютер спал/выключен) выполняется как можно скорее;
# только когда пользователь вошёл в систему, без сохранённого пароля Windows.
param([string]$At = "16:00")  # время ежедневного запуска
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "scripts\run_scheduled.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "jobagg" -Description "Вакансии из Telegram в Google-таблицу (jobsaggregator)" `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
$t = Get-ScheduledTask -TaskName "jobagg"
"Задание jobagg создано. Каждый день в $At, следующий запуск: $((Get-ScheduledTaskInfo jobagg).NextRunTime)"
