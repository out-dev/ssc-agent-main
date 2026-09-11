import {
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router'
import App from './App'
import { RootLayout } from './core/layouts/RootLayout'

const rootRoute = createRootRoute({
  component: RootLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: App,
})

const routeTree = rootRoute.addChildren([indexRoute])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
