import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './index.css';

// An answer counts as fresh for a minute, so moving between pages doesn't ask
// again. A request that fails is tried once more before the page says so.
const queries = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: 1 } } });

const root = document.getElementById('root');
if (!root) throw new Error('index.html has no #root to render into');

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queries}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
