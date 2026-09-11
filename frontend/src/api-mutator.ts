import { InteractionRequiredAuthError } from '@azure/msal-browser'
import { loginScopes } from './features/auth/authConfig'
import { getLastIdToken, msalInstance, setLastIdToken } from './features/auth/msalInstance'

async function acquireTenantToken(): Promise<string | undefined> {
  const account = msalInstance.getActiveAccount() ?? msalInstance.getAllAccounts()[0]
  if (!account) return undefined

  const cachedIdToken = getLastIdToken()
  if (cachedIdToken) return cachedIdToken

  try {
    const result = await msalInstance.acquireTokenSilent({ account, scopes: loginScopes })
    const token = result.idToken || result.accessToken
    if (token) setLastIdToken(token)
    return token
  } catch (error) {
    if (error instanceof InteractionRequiredAuthError) {
      await msalInstance.acquireTokenRedirect({ account, scopes: loginScopes })
    }
    throw error
  }
}

export const authenticatedFetch = async (
  url: string,
  options: RequestInit = {},
): Promise<Response> => {
  const baseUrl = import.meta.env.VITE_API_BASE_URL ?? ''
  const accessToken = await acquireTenantToken()
  const headers = new Headers(options.headers)
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  return fetch(url.startsWith('http') ? url : `${baseUrl}${url}`, {
    ...options,
    headers,
  })
}

export const customFetch = async <T>(
  url: string,
  options: RequestInit = {},
): Promise<T> => {
  const response = await authenticatedFetch(url, options)

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`)
  }

  return response.json() as Promise<T>
}
