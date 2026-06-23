import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { FontSizeProvider } from './hooks/useFontSize';
import './styles/tokens.css';
import './styles/base.css';
import './styles/utilities.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <FontSizeProvider>
        <App />
      </FontSizeProvider>
    </BrowserRouter>
  </StrictMode>,
);
