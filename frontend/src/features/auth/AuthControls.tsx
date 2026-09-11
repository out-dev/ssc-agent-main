import { InteractionStatus } from '@azure/msal-browser'
import { useMsal } from '@azure/msal-react'
import { LogOut } from 'lucide-react'

export function AuthControls() {
  const { accounts, instance, inProgress } = useMsal()
  const account = instance.getActiveAccount() ?? accounts[0]

  const signOut = async () => {
    await instance.logoutRedirect({
      account,
      postLogoutRedirectUri: window.location.origin,
    })
  }

  return (
    <div className="auth-controls">
      <span className="auth-user" title={account?.username}>
        {account?.name ?? account?.username}
      </span>
      <button
        className="icon-text-button"
        type="button"
        onClick={() => void signOut()}
        disabled={inProgress !== InteractionStatus.None}
      >
        <LogOut size={17} /> Sign out
      </button>
    </div>
  )
}
