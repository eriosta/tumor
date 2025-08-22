@echo off
echo 🚀 Setting up RECIST Dashboard...

REM Check if Node.js is installed
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Node.js not found. Please install Node.js LTS first:
    echo    winget install OpenJS.NodeJS.LTS --silent
    echo    Then reopen your terminal and run this script again.
    pause
    exit /b 1
)

REM Check if npm is available
npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ npm not found. Please install Node.js with npm.
    pause
    exit /b 1
)

echo ✅ Node.js and npm found
echo 📦 Installing dependencies...

REM Install dependencies
npm install
if %errorlevel% neq 0 (
    echo ❌ Failed to install dependencies. Please check your internet connection.
    pause
    exit /b 1
)

echo ✅ Dependencies installed successfully!
echo 🌐 Starting development server...
echo    The app will open at http://localhost:5173
echo    Press Ctrl+C to stop the server
echo.

npm run dev
