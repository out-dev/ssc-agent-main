import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MsalProvider } from '@azure/msal-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import './index.css'
import { AuthGate, msalInstance, setLastIdToken } from './features/auth'
import { router } from './router'

const queryClient = new QueryClient()

async function bootstrap() {
  await msalInstance.initialize()

  const redirectResponse = await msalInstance.handleRedirectPromise()
  if (redirectResponse?.account) {
    msalInstance.setActiveAccount(redirectResponse.account)
    setLastIdToken(redirectResponse.idToken)
  }

  const accounts = msalInstance.getAllAccounts()
  if (!msalInstance.getActiveAccount() && accounts.length > 0) {
    msalInstance.setActiveAccount(accounts[0])
  }

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <MsalProvider instance={msalInstance}>
        <QueryClientProvider client={queryClient}>
          <AuthGate>
            <RouterProvider router={router} />
          </AuthGate>
        </QueryClientProvider>
      </MsalProvider>
    </StrictMode>,
  )
}

void bootstrap()
