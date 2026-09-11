import {
  AuthenticatedTemplate,
  UnauthenticatedTemplate,
} from '@azure/msal-react'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { LoginView } from './LoginView'
import { LoggedInView } from './LoggedInView'

type AuthGateProps = {
  children: ReactNode
}

export function AuthGate({ children }: AuthGateProps) {
  return (
    <>
      <AuthenticatedTemplate>
        <AuthenticatedContent>{children}</AuthenticatedContent>
      </AuthenticatedTemplate>
      <UnauthenticatedTemplate>
        <LoginView />
      </UnauthenticatedTemplate>
    </>
  )
}

function AuthenticatedContent({ children }: AuthGateProps) {
  const [showWorkspace, setShowWorkspace] = useState(false)

  return showWorkspace
    ? children
    : <LoggedInView onContinue={() => setShowWorkspace(true)} />
}
