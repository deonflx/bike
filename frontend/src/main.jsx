import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ClerkProvider } from '@clerk/clerk-react'
import './index.css'
import App from './App.jsx'

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

const root = createRoot(document.getElementById('root'))

const isClerkConfigured = Boolean(
  PUBLISHABLE_KEY &&
  PUBLISHABLE_KEY !== 'pk_test_placeholder' &&
  PUBLISHABLE_KEY.startsWith('pk_')
)

if (!isClerkConfigured) {
  console.info(
    "Clerk publishable key not configured yet. Add VITE_CLERK_PUBLISHABLE_KEY to frontend/.env from https://dashboard.clerk.com to enable authentication."
  )
}

root.render(
  <StrictMode>
    {isClerkConfigured ? (
      <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">
        <BrowserRouter>
          <App isClerkConfigured={true} />
        </BrowserRouter>
      </ClerkProvider>
    ) : (
      <BrowserRouter>
        <App isClerkConfigured={false} />
      </BrowserRouter>
    )}
  </StrictMode>,
)