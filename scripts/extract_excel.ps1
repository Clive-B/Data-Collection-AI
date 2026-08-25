param(
    [Parameter(Mandatory = $true)]
    [string]$InputDirectory,

    [Parameter(Mandatory = $true)]
    [string]$OutputFile,

    [Parameter(Mandatory = $true)]
    [string]$Operator,

    [Parameter(Mandatory = $true)]
    [string]$SourceArchive
)

$ErrorActionPreference = 'Stop'

function Convert-ToIsoMonth {
    param(
        [object]$Value,
        [string]$DisplayText,
        [string]$FileName
    )

    $text = ($DisplayText -replace [char]0xA0, ' ').Trim()
    if ($text -eq '') { return $null }

    $formats = @(
        'MMM-yy', 'MMMM-yy', 'yy-MMM', 'yy-MMMM',
        "MMM ''yy", "MMMM ''yy", "MMM'yy", "MMMM'yy",
        'MMM yyyy', 'MMMM yyyy'
    )
    $culture = [Globalization.CultureInfo]::InvariantCulture
    foreach ($format in $formats) {
        $parsed = [datetime]::MinValue
        if ([datetime]::TryParseExact($text, $format, $culture, [Globalization.DateTimeStyles]::AllowWhiteSpaces, [ref]$parsed)) {
            return $parsed.ToString('yyyy-MM')
        }
    }

    $normalized = $text -replace '(?i)sept', 'Sep' -replace "['’]", ''
    foreach ($format in @('MMM-yy', 'MMMM-yy', 'yy-MMM', 'yy-MMMM', 'MMMyy', 'MMM yyyy', 'MMMM yyyy')) {
        $parsed = [datetime]::MinValue
        if ([datetime]::TryParseExact($normalized, $format, $culture, [Globalization.DateTimeStyles]::AllowWhiteSpaces, [ref]$parsed)) {
            return $parsed.ToString('yyyy-MM')
        }
    }

    if ($text -match '^(?i)(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)$') {
        $yearMatch = [regex]::Match($FileName, '(20\d{2})')
        if ($yearMatch.Success) {
            $parsed = [datetime]::ParseExact(($text -replace '(?i)Sept', 'Sep'), 'MMM', $culture)
            return ('{0}-{1:00}' -f [int]$yearMatch.Groups[1].Value, $parsed.Month)
        }
    }

    if ($Value -is [double] -or $Value -is [int]) {
        try {
            $date = [datetime]::FromOADate([double]$Value)
            if ($date.Year -ge 2010 -and $date.Year -le 2100 -and $text -match '(?i)jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec') {
                return $date.ToString('yyyy-MM')
            }
        } catch {}
    }
    return $null
}

function Select-PrimaryWorksheet {
    param([object]$Workbook)

    $patterns = @(
        '^REVISED MNOs MONTHLY DATA',
        '^Operators _Data_Monthly$',
        '^Operator Data Monthly\s*$'
    )
    foreach ($pattern in $patterns) {
        foreach ($sheet in $Workbook.Worksheets) {
            if ($sheet.Name -match $pattern) { return $sheet }
            [void][Runtime.InteropServices.Marshal]::ReleaseComObject($sheet)
        }
    }
    return $Workbook.Worksheets.Item(1)
}

function Find-HeaderLayout {
    param([object]$Worksheet)

    $used = $Worksheet.UsedRange
    $maxHeaderRow = [Math]::Min(10, $used.Row + $used.Rows.Count - 1)
    $lastColumn = $used.Column + $used.Columns.Count - 1
    $metricColumn = 0
    $headerRow = 0
    $definitionColumn = 0
    $unitColumn = 0

    for ($row = 1; $row -le $maxHeaderRow; $row++) {
        for ($column = 1; $column -le [Math]::Min($lastColumn, 8); $column++) {
            $text = ("$($Worksheet.Cells.Item($row, $column).Text)").Trim()
            if ($text -match '(?i)^Industry\s+Data$') {
                $metricColumn = $column
                $headerRow = $row
            } elseif ($text -match '(?i)^Definitions?$') {
                $definitionColumn = $column
            } elseif ($text -match '(?i)^Data\s*Type$') {
                $unitColumn = $column
            }
        }
    }
    if ($metricColumn -eq 0) { $metricColumn = 2 }
    if ($headerRow -eq 0) { $headerRow = 8 }

    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($used)
    return @{
        MetricColumn = $metricColumn
        HeaderRow = $headerRow
        DefinitionColumn = $definitionColumn
        UnitColumn = $unitColumn
    }
}

function Write-JsonLine {
    param([IO.StreamWriter]$Writer, [hashtable]$Record)
    $Writer.WriteLine(($Record | ConvertTo-Json -Compress -Depth 8))
}

$resolvedInput = (Resolve-Path -LiteralPath $InputDirectory).Path
$outputParent = Split-Path -Parent $OutputFile
if ($outputParent -and -not (Test-Path -LiteralPath $outputParent)) {
    New-Item -ItemType Directory -Path $outputParent | Out-Null
}

$writer = [IO.StreamWriter]::new($OutputFile, $false, [Text.UTF8Encoding]::new($false))
$excel = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false
    $excel.AutomationSecurity = 3

    $files = Get-ChildItem -LiteralPath $resolvedInput -File | Where-Object { $_.Extension -match '^\.(xls|xlsx|xlsb)$' } | Sort-Object Name
    foreach ($file in $files) {
        $workbook = $null
        $worksheet = $null
        try {
            $workbook = $excel.Workbooks.Open($file.FullName, 0, $true)
            $worksheet = Select-PrimaryWorksheet -Workbook $workbook
            $layout = Find-HeaderLayout -Worksheet $worksheet
            $used = $worksheet.UsedRange
            $lastRow = $used.Row + $used.Rows.Count - 1
            $lastColumn = $used.Column + $used.Columns.Count - 1

            $monthColumns = @()
            for ($column = 1; $column -le $lastColumn; $column++) {
                for ($row = 1; $row -le [Math]::Min(10, $lastRow); $row++) {
                    $cell = $worksheet.Cells.Item($row, $column)
                    $period = Convert-ToIsoMonth -Value $cell.Value2 -DisplayText ("$($cell.Text)") -FileName $file.Name
                    if ($period) {
                        $monthColumns += @{ column = $column; row = $row; period = $period; display = ("$($cell.Text)").Trim() }
                        break
                    }
                }
            }

            $links = 0
            try {
                $sources = @($workbook.LinkSources(1))
                if ($sources.Count -gt 0 -and $sources[0]) { $links = $sources.Count }
            } catch {}

            Write-JsonLine -Writer $writer -Record @{
                type = 'workbook'
                operator = $Operator
                source_archive = $SourceArchive
                file_name = $file.Name
                file_path = $file.FullName
                sheet_name = $worksheet.Name
                external_link_count = $links
                metric_column = $layout.MetricColumn
                definition_column = $layout.DefinitionColumn
                unit_column = $layout.UnitColumn
                used_rows = $used.Rows.Count
                used_columns = $used.Columns.Count
                months = $monthColumns
            }

            $currentSection = ''
            for ($row = 1; $row -le $lastRow; $row++) {
                $label = ("$($worksheet.Cells.Item($row, $layout.MetricColumn).Text)").Trim()
                if ($label -eq '') { continue }

                $definition = ''
                if ($layout.DefinitionColumn -gt 0) {
                    $definition = ("$($worksheet.Cells.Item($row, $layout.DefinitionColumn).Text)").Trim()
                }
                $unit = ''
                if ($layout.UnitColumn -gt 0) {
                    $unit = ("$($worksheet.Cells.Item($row, $layout.UnitColumn).Text)").Trim()
                }

                $values = @()
                $nonBlankCount = 0
                foreach ($month in $monthColumns) {
                    $cell = $worksheet.Cells.Item($row, $month.column)
                    $display = ("$($cell.Text)").Trim()
                    if ($display -ne '') { $nonBlankCount++ }
                    $status = 'blank'
                    $numeric = $null
                    $rawValue = $cell.Value2
                    if ($null -ne $rawValue -and "$rawValue" -ne '') {
                        if ($rawValue -is [System.Runtime.InteropServices.ErrorWrapper]) {
                            $status = 'error'
                        } elseif ($rawValue -is [double] -or $rawValue -is [int] -or $rawValue -is [decimal]) {
                            $status = 'numeric'
                            $numeric = [double]$rawValue
                        } else {
                            $status = 'text'
                        }
                    }
                    $formula = ''
                    if ($cell.HasFormula) { $formula = "$($cell.Formula)" }
                    $values += @{
                        period = $month.period
                        source_cell = $cell.Address($false, $false)
                        value_numeric = $numeric
                        value_text = $display
                        value_status = $status
                        has_formula = [bool]$cell.HasFormula
                        formula_text = $formula
                    }
                }

                $looksLikeSection = ($label -match '^\s*\d{1,2}[\.)]' -or $label -match '(?i)^\s*\d{1,2}[a-z]?\s*[-:]') -and $nonBlankCount -eq 0
                if ($looksLikeSection) {
                    $currentSection = $label
                    continue
                }

                if ($nonBlankCount -eq 0 -and $unit -eq '') { continue }
                Write-JsonLine -Writer $writer -Record @{
                    type = 'metric_row'
                    file_name = $file.Name
                    sheet_name = $worksheet.Name
                    row = $row
                    label = $label
                    section = $currentSection
                    definition = $definition
                    unit = $unit
                    values = $values
                }
            }
            [void][Runtime.InteropServices.Marshal]::ReleaseComObject($used)
        } catch {
            Write-JsonLine -Writer $writer -Record @{
                type = 'error'
                file_name = $file.Name
                message = $_.Exception.Message
            }
        } finally {
            if ($workbook) { $workbook.Close($false) }
            if ($worksheet) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($worksheet) }
            if ($workbook) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($workbook) }
        }
    }
} finally {
    $writer.Dispose()
    if ($excel) {
        $excel.Quit()
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

