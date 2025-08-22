# RECIST Dashboard

A React-based dashboard for visualizing and analyzing RECIST (Response Evaluation Criteria in Solid Tumors) data.

## Features

- Interactive data visualization with Recharts
- Draggable and resizable dashboard components
- Real-time data updates
- Responsive design with Tailwind CSS

## Prerequisites

- Node.js (version 18 or higher)
- npm or yarn package manager

## Installation

### Quick Setup (Windows)

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd tumor/recist-dashboard
   ```

2. **Run the setup script:**
   ```powershell
   # PowerShell
   .\setup.ps1
   
   # Or Command Prompt
   setup.bat
   ```

The setup script will:
- Check if Node.js is installed
- Install all dependencies
- Start the development server automatically

### Manual Setup

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd tumor/recist-dashboard
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Start the development server:**
   ```bash
   npm run dev
   ```

4. **Open your browser:**
   Navigate to `http://localhost:5173` to view the application.

## Available Scripts

- `npm run dev` - Start development server with hot reload
- `npm run build` - Build for production
- `npm run preview` - Preview production build locally
- `npm run lint` - Run ESLint to check code quality

## Project Structure

```
recist-dashboard/
├── src/
│   ├── App.tsx          # Main application component
│   ├── main.tsx         # Application entry point
│   └── index.css        # Global styles
├── public/              # Static assets
├── package.json         # Dependencies and scripts
└── vite.config.ts       # Vite configuration
```

## Troubleshooting

### Common Issues

1. **Port already in use:**
   - The dev server will automatically try the next available port
   - Check the terminal output for the correct URL

2. **Dependencies not installing:**
   - Delete `node_modules` and `package-lock.json`
   - Run `npm install` again

3. **TypeScript errors:**
   - Run `npm run lint` to check for issues
   - Ensure all dependencies are properly installed

### Windows PowerShell Issues

If PowerShell blocks npm scripts, run:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Development

This project uses:
- **React 19** with TypeScript
- **Vite** for fast development and building
- **Tailwind CSS** for styling
- **Recharts** for data visualization
- **React Grid Layout** for draggable components

## Building for Production

```bash
npm run build
```

The built files will be in the `dist/` directory, ready for deployment.
