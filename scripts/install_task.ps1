# Создаёт (или пересоздаёт) задание "jobagg" в Планировщике заданий Windows.
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_task.ps1
# Каждые 4 часа; пропущенный запуск (компьютер спал/выключен) выполняется как можно скорее;
# только когда пользователь вошёл в систему, без сохранённого пароля Windows.
param([int]$EveryHours = 4)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "scripts\run_scheduled.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" `
    -WorkingDirectory $root
# первый запуск через 2 минуты, дальше повтор без ограничения срока
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Hours $EveryHours)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "jobagg" -Description "Вакансии из Telegram в Google-таблицу (jobsaggregator)" `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
$t = Get-ScheduledTask -TaskName "jobagg"
"Задание jobagg создано. Повтор: $($t.Triggers[0].Repetition.Interval), следующий запуск: $((Get-ScheduledTaskInfo jobagg).NextRunTime)"
