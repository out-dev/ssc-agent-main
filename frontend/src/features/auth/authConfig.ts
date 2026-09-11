import type { Configuration, RedirectRequest } from '@azure/msal-browser'

const tenantId = import.meta.env.VITE_MSAL_TENANT_ID || '505cca53-5750-4134-9501-8d52d5df3cd1'
const clientId = import.meta.env.VITE_MSAL_CLIENT_ID || '74ecbe9f-2767-4fc9-848d-c2232cf1311a'
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
