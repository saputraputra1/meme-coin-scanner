if (-not [Console]::OutputEncoding.IsSingleByte) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
}
python "$PSScriptRoot\main.py" @args
