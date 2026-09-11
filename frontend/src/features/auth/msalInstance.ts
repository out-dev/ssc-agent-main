import { PublicClientApplication } from '@azure/msal-browser'
import { msalConfig } from './authConfig'

export const msalInstance = new PublicClientApplication(msalConfig)

let lastIdToken: string | undefined

export function setLastIdToken(idToken: string): void {
  lastIdToken = idToken
}

export function getLastIdToken(): string | undefined {
  return lastIdToken
}
