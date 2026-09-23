param(
    [ValidateSet('openai', 'nvidia')]
    [string]$Provider = 'openai',
    [switch]$KeepOpen
)

$ErrorActionPreference = 'Stop'
$variableName = if ($Provider -eq 'openai') { 'OPENAI_API_KEY' } else { 'NVIDIA_API_KEY' }
$secretInput = $null
$keyPointer = [IntPtr]::Zero
$apiKeyValue = $null
$setupExitCode = 0

try {
    Write-Host "Save $variableName for your Windows user account."
    Write-Host 'Paste your API key at the prompt. The input is hidden.'
    $secretInput = Read-Host -Prompt $variableName -AsSecureString
    $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secretInput)
    $apiKeyValue = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer).Trim()

    if ([string]::IsNullOrWhiteSpace($apiKeyValue)) {
        Write-Host 'No key entered. The environment variable was not changed.'
        $setupExitCode = 1
    } else {
        [Environment]::SetEnvironmentVariable($variableName, $apiKeyValue, 'User')
        [Environment]::SetEnvironmentVariable($variableName, $apiKeyValue, 'Process')
        Write-Host "Saved $variableName as a Windows user environment variable."
        Write-Host 'Restart VS Code and the backend to use it in new processes.'
    }
} catch {
    Write-Host 'Could not save the environment variable. Try running this script in your own PowerShell terminal.'
    $setupExitCode = 1
} finally {
    if ($keyPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    }
    if ($null -ne $secretInput) {
        $secretInput.Dispose()
    }
    $apiKeyValue = $null
}

if ($KeepOpen) {
    Read-Host -Prompt 'Press Enter to close' | Out-Null
}
exit $setupExitCode
