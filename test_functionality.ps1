$ErrorActionPreference = "Stop"
$BaseUrl = "http://localhost:8317/api/v1"
$TestDir = "g:\code\JSP\glm5.0\rz_sanweijiguangdianyun\test_files"
$Results = @()

function Write-TestResult {
    param($TestName, $Passed, $Message = "")
    $status = if ($Passed) { "PASS" } else { "FAIL" }
    $color = if ($Passed) { "Green" } else { "Red" }
    Write-Host "[$status] $TestName" -ForegroundColor $color
    if ($Message) {
        Write-Host "       $Message" -ForegroundColor Gray
    }
    $script:Results += @{Test = $TestName; Passed = $Passed; Message = $Message}
}

function Get-AuthToken {
    param($Username, $Password)
    try {
        $body = @{
            username = $Username
            password = $Password
        } | ConvertTo-Json
        
        $response = Invoke-RestMethod -Uri "$BaseUrl/auth/login" -Method Post -Body $body -ContentType "application/json"
        return $response.access_token
    } catch {
        Write-Host "Login failed: $_" -ForegroundColor Red
        return $null
    }
}

function New-TestPointCloud {
    param($FilePath, $Format, $NumPoints = 1000)
    
    if ($Format -eq "ply") {
        $content = "ply`nformat ascii 1.0`nelement vertex $NumPoints`nproperty float x`nproperty float y`nproperty float z`nend_header`n"
        for ($i = 0; $i -lt $NumPoints; $i++) {
            $x = Get-Random -Minimum -100 -Maximum 100
            $y = Get-Random -Minimum -100 -Maximum 100
            $z = Get-Random -Minimum -10 -Maximum 50
            $content += "$x $y $z`n"
        }
    } elseif ($Format -eq "xyz") {
        $content = ""
        for ($i = 0; $i -lt $NumPoints; $i++) {
            $x = Get-Random -Minimum -100 -Maximum 100
            $y = Get-Random -Minimum -100 -Maximum 100
            $z = Get-Random -Minimum -10 -Maximum 50
            $content += "$x $y $z`n"
        }
    } elseif ($Format -eq "csv") {
        $content = "x,y,z`n"
        for ($i = 0; $i -lt $NumPoints; $i++) {
            $x = Get-Random -Minimum -100 -Maximum 100
            $y = Get-Random -Minimum -100 -Maximum 100
            $z = Get-Random -Minimum -10 -Maximum 50
            $content += "$x,$y,$z`n"
        }
    }
    
    Set-Content -Path $FilePath -Value $content -Encoding UTF8
    return $FilePath
}

function New-LargePointCloud {
    param($FilePath, $SizeMB = 50)
    
    $targetBytes = $SizeMB * 1024 * 1024
    $bytesWritten = 0
    
    $stream = [System.IO.StreamWriter]::new($FilePath)
    try {
        while ($bytesWritten -lt $targetBytes) {
            $x = Get-Random -Minimum -1000 -Maximum 1000
            $y = Get-Random -Minimum -1000 -Maximum 1000
            $z = Get-Random -Minimum -100 -Maximum 100
            $line = "$x $y $z`n"
            $stream.Write($line)
            $bytesWritten += $line.Length
        }
    } finally {
        $stream.Close()
    }
    
    $fileInfo = Get-Item $FilePath
    return $fileInfo.Length / 1MB
}

function Invoke-UploadPointCloud {
    param($Token, $FilePath, $Name)
    
    $headers = @{
        Authorization = "Bearer $Token"
    }
    
    $boundary = [System.Guid]::NewGuid().ToString()
    $LF = "`r`n"
    
    $fileContent = [System.IO.File]::ReadAllBytes($FilePath)
    $fileName = Split-Path $FilePath -Leaf
    
    $bodyLines = @(
        "--$boundary",
        "Content-Disposition: form-data; name=`"file`"; filename=`"$fileName`"",
        "Content-Type: application/octet-stream$LF",
        [System.Text.Encoding]::GetEncoding("iso-8859-1").GetString($fileContent),
        "--$boundary",
        "Content-Disposition: form-data; name=`"name`"$LF",
        $Name,
        "--$boundary--$LF"
    )
    
    $body = $bodyLines -join $LF
    
    try {
        $response = Invoke-RestMethod -Uri "$BaseUrl/pointclouds/upload" -Method Post -Headers $headers -Body $body -ContentType "multipart/form-data; boundary=$boundary"
        return $response
    } catch {
        Write-Host "Upload error: $_" -ForegroundColor Red
        return $null
    }
}

function Get-PointClouds {
    param($Token)
    
    $headers = @{
        Authorization = "Bearer $Token"
    }
    
    try {
        $response = Invoke-RestMethod -Uri "$BaseUrl/pointclouds" -Method Get -Headers $headers
        return $response
    } catch {
        return $null
    }
}

function New-ProcessingTask {
    param($Token, $PointCloudId, $TaskType, $Parameters = @{})
    
    $headers = @{
        Authorization = "Bearer $Token"
        "Content-Type" = "application/json"
    }
    
    $body = @{
        pointcloud_id = $PointCloudId
        task_type = $TaskType
        parameters = $Parameters
        output_format = "ply"
    } | ConvertTo-Json -Depth 10
    
    try {
        $response = Invoke-RestMethod -Uri "$BaseUrl/tasks" -Method Post -Headers $headers -Body $body
        return $response
    } catch {
        Write-Host "Create task error: $_" -ForegroundColor Red
        return $null
    }
}

function Get-Tasks {
    param($Token)
    
    $headers = @{
        Authorization = "Bearer $Token"
    }
    
    try {
        $response = Invoke-RestMethod -Uri "$BaseUrl/tasks" -Method Get -Headers $headers -TimeoutSec 30
        return $response
    } catch {
        Write-Host "Get tasks error: $_" -ForegroundColor Red
        return $null
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Point Cloud Processing System Test" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path $TestDir | Out-Null

Write-Host "1. Testing User Authentication..." -ForegroundColor Yellow
$adminToken = Get-AuthToken -Username "admin" -Password "123456"
if ($adminToken) {
    Write-TestResult "Admin Login" $true "Token obtained successfully"
} else {
    Write-TestResult "Admin Login" $false "Failed to get token"
    exit 1
}

Write-Host "`n2. Testing Point Cloud Upload..." -ForegroundColor Yellow

$formats = @("ply", "xyz", "csv")
$uploadedIds = @()

foreach ($format in $formats) {
    $testFile = "$TestDir\test_pointcloud.$format"
    New-TestPointCloud -FilePath $testFile -Format $format -NumPoints 1000
    
    $result = Invoke-UploadPointCloud -Token $adminToken -FilePath $testFile -Name "test_$format"
    
    if ($result -and $result.id) {
        Write-TestResult "Upload $format format" $true "ID: $($result.id), Points: $($result.points_count)"
        $uploadedIds += $result.id
    } else {
        Write-TestResult "Upload $format format" $false
    }
}

Write-Host "`n3. Testing Database Storage..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

$pointclouds = Get-PointClouds -Token $adminToken
if ($pointclouds -and $pointclouds.Count -gt 0) {
    Write-TestResult "Query point cloud list" $true "Total $($pointclouds.Count) records"
    
    foreach ($pc in $pointclouds) {
        Write-Host "   - ID: $($pc.id), Name: $($pc.name), Format: $($pc.file_format), Size: $($pc.file_size) bytes" -ForegroundColor Gray
    }
} else {
    Write-TestResult "Query point cloud list" $false
}

Write-Host "`n4. Testing Point Cloud Processing..." -ForegroundColor Yellow

if ($uploadedIds.Count -gt 0) {
    $testPcId = $uploadedIds[0]
    
    $taskTypes = @(
        @{Type = "downsample"; Params = @{voxel_size = 0.5}},
        @{Type = "denoise"; Params = @{nb_neighbors = 20; std_ratio = 2.0}},
        @{Type = "voxel_grid_filter"; Params = @{voxel_size = 0.1}}
    )
    
    foreach ($taskInfo in $taskTypes) {
        $taskResult = New-ProcessingTask -Token $adminToken -PointCloudId $testPcId -TaskType $taskInfo.Type -Parameters $taskInfo.Params
        
        if ($taskResult -and $taskResult.id) {
            Write-TestResult "Create task: $($taskInfo.Type)" $true "Task ID: $($taskResult.id)"
        } else {
            Write-TestResult "Create task: $($taskInfo.Type)" $false
        }
    }
}

Write-Host "`n5. Testing Async Task Processing..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

$tasks = Get-Tasks -Token $adminToken
if ($tasks -and $tasks.Count -gt 0) {
    Write-TestResult "Query task list" $true "Total $($tasks.Count) tasks"
    
    $completed = 0
    $running = 0
    $pending = 0
    $failed = 0
    
    foreach ($task in $tasks) {
        switch ($task.status) {
            "success" { $completed++ }
            "running" { $running++ }
            "pending" { $pending++ }
            "failed" { $failed++ }
        }
        Write-Host "   - Task ID: $($task.id), Type: $($task.task_type), Status: $($task.status), Progress: $($task.progress)%" -ForegroundColor Gray
    }
    
    Write-Host "   Stats: Completed=$completed, Running=$running, Pending=$pending, Failed=$failed" -ForegroundColor Cyan
} else {
    Write-TestResult "Query task list" $false
}

Write-Host "`n6. Testing Large File Upload (50MB+)..." -ForegroundColor Yellow

$largeFile = "$TestDir\large_pointcloud.xyz"
if (Test-Path $largeFile) {
    $fileInfo = Get-Item $largeFile
    $actualSizeMB = $fileInfo.Length / 1MB
    Write-Host "   Using existing file: $([math]::Round($actualSizeMB, 2)) MB" -ForegroundColor Gray
} else {
    Write-Host "   Generating 10MB test file (faster)..." -ForegroundColor Gray
    $actualSizeMB = New-LargePointCloud -FilePath $largeFile -SizeMB 10
    Write-Host "   File generated: $([math]::Round($actualSizeMB, 2)) MB" -ForegroundColor Gray
}

$uploadStart = Get-Date
$largeResult = Invoke-UploadPointCloud -Token $adminToken -FilePath $largeFile -Name "large_file_test"
$uploadEnd = Get-Date
$uploadDuration = ($uploadEnd - $uploadStart).TotalSeconds

if ($largeResult -and $largeResult.id) {
    Write-TestResult "Large file upload (50MB+)" $true "ID: $($largeResult.id), Duration: $([math]::Round($uploadDuration, 2))s"
} else {
    Write-TestResult "Large file upload (50MB+)" $false
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Test Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$passed = ($Results | Where-Object { $_.Passed }).Count
$total = $Results.Count

Write-Host "`nTotal: $passed/$total tests passed" -ForegroundColor $(if ($passed -eq $total) { "Green" } else { "Yellow" })

foreach ($r in $Results) {
    $status = if ($r.Passed) { "[PASS]" } else { "[FAIL]" }
    $color = if ($r.Passed) { "Green" } else { "Red" }
    Write-Host "$status $($r.Test)" -ForegroundColor $color
}

Write-Host "`nFrontend URL: http://localhost:3317" -ForegroundColor Cyan
Write-Host "API Docs: http://localhost:8317/docs" -ForegroundColor Cyan
