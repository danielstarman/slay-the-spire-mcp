# Prevent Windows from sleeping by simulating activity
# Run with: powershell -ExecutionPolicy Bypass -File prevent-sleep.ps1
# Stop with: Ctrl+C or kill the PowerShell process

Add-Type -AssemblyName System.Windows.Forms

Write-Host "Sleep prevention active. Press Ctrl+C to stop."
Write-Host "Computer will stay awake until this script is stopped."

while ($true) {
    # Send F15 key (does nothing visible but prevents sleep)
    [System.Windows.Forms.SendKeys]::SendWait('{F15}')
    Start-Sleep -Seconds 60
}
