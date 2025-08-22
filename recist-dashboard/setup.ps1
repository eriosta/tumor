# RECIST Dashboard Setup Script
# Run this script to quickly set up the dashboard on any Windows machine

Write-Host "🚀 Setting up RECIST Dashboard..." -ForegroundColor Green

# Check if Node.js is installed
try {
    $nodeVersion = node --version
    Write-Host "✅ Node.js found: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Node.js not found. Please install Node.js LTS first:" -ForegroundColor Red
    Write-Host "   winget install OpenJS.NodeJS.LTS --silent" -ForegroundColor Yellow
    Write-Host "   Then reopen PowerShell and run this script again." -ForegroundColor Yellow
    exit 1
}

# Check if npm is available
try {
    $npmVersion = npm --version
    Write-Host "✅ npm found: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ npm not found. Please install Node.js with npm." -ForegroundColor Red
    exit 1
}

# Install dependencies
Write-Host "📦 Installing dependencies..." -ForegroundColor Blue
npm install

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Dependencies installed successfully!" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to install dependencies. Please check your internet connection." -ForegroundColor Red
    exit 1
}

# Start the development server
Write-Host "🌐 Starting development server..." -ForegroundColor Blue
Write-Host "   The app will open at http://localhost:5173" -ForegroundColor Yellow
Write-Host "   Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

npm run dev
