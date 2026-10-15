import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import './index.css'
import App from './App.tsx'

async function enableMocking() {
  // Use the explicit flag to toggle MSW on or off
  if (import.meta.env.VITE_USE_MOCK !== 'true') {
    console.log("MSW disabled. Routing traffic to real backend.");
    return;
  }
  
  const { worker } = await import('./mocks/browser')
  
  return worker.start({
    onUnhandledRequest(request, print) {
      const url = new URL(request.url)
      
      // Ignore requests that aren't meant for our API (like HTML documents, Vite HMR, or static assets)
      if (!url.pathname.startsWith('/api/')) {
        return
      }
      
      // If an /api/ request goes unhandled, print the standard warning
      print.warning()
    },
  })
}

enableMocking().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <BrowserRouter>
        <ThemeProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>
    </StrictMode>
  )
})