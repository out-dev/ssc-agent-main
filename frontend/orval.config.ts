import { defineConfig } from 'orval'

export default defineConfig({
  agentApi: {
    input: {
      target: 'http://localhost:5080/openapi/v1.json',
    },
    output: {
      mode: 'tags-split',
      target: './src/api/generated.ts',
      schemas: './src/api/model',
      client: 'react-query',
      httpClient: 'fetch',
      clean: true,
      override: {
        mutator: {
          path: './src/api-mutator.ts',
          name: 'customFetch',
        },
      },
    },
  },
})