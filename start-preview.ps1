Set-Location -LiteralPath $PSScriptRoot
$env:CREATIVE_MODEL_TIMEOUT_SECONDS = '120'
$env:MODEL_TIMEOUT_SECONDS = '120'
& "$PSScriptRoot\.venv\Scripts\python.exe" -u -m ops.run_b_v6_preview --credential-file 'D:\myhub\Multi-agent\.env.creative' --port 8003 --demo-c
