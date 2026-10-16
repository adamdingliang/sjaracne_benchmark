param(
    [Parameter(Mandatory = $true)][string]$PlanPath,
    [string]$PythonPath = 'C:\Users\adamd\miniconda3\python.exe'
)
$ErrorActionPreference = 'Stop'
$resolvedPlan = (Resolve-Path -LiteralPath $PlanPath).Path
$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
$runnerPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'generate.py')).Path
$runDirectory = Split-Path -Parent $resolvedPlan
$repositoryDirectory = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$stdoutPath = Join-Path $runDirectory ('controller_' + $stamp + '.stdout.log')
$stderrPath = Join-Path $runDirectory ('controller_' + $stamp + '.stderr.log')
# The controller validates the immutable plan, takes its OS lock and records its
# own PID/heartbeat. Quoted path arguments also support workspace paths with spaces.
$nativeArguments = @('-u', ('"' + $runnerPath + '"'), 'run', '--plan',
                     ('"' + $resolvedPlan + '"'), '--workers', '12', '--resume')
$controllerProcess = Start-Process -FilePath $resolvedPython -ArgumentList $nativeArguments `
    -WorkingDirectory $repositoryDirectory -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
[pscustomobject]@{
    controller_pid = $controllerProcess.Id
    launched_utc = [DateTime]::UtcNow.ToString('o')
    python = $resolvedPython
    runner = $runnerPath
    plan = $resolvedPlan
    workers = 12
    stdout = $stdoutPath
    stderr = $stderrPath
} | ConvertTo-Json
