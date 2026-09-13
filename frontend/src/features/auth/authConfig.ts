import type { Configuration, RedirectRequest } from '@azure/msal-browser'

const tenantId = import.meta.env.VITE_MSAL_TENANT_ID || '13eb42f4-a065-4aed-a3da-ae0114f35f43'
const clientId = import.meta.env.VITE_MSAL_CLIENT_ID || '5a188e1c-6bda-4c95-a834-2c8a0388db88'
export const loginScopes = ['openid', 'profile', 'email']

export const msalConfig: Configuration = {
  auth: {
    clientId,
    authority: `https://login.microsoftonline.com/${tenantId}`,
    redirectUri: window.location.origin,
    postLogoutRedirectUri: window.location.origin,
  },
  cache: {
    cacheLocation: 'sessionStorage',
  },
}

export const loginRequest: RedirectRequest = {
  scopes: loginScopes,
}
