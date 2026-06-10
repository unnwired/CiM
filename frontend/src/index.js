import React from 'react';
import ReactDOM from 'react-dom/client';
import './styles/global.css';
import './styles/knowledgeBase.css';
import App from './App';

// Patch ResizeObserver to prevent CRA overlay from showing the benign loop warning
const OriginalResizeObserver = window.ResizeObserver;
window.ResizeObserver = class PatchedResizeObserver extends OriginalResizeObserver {
  constructor(cb) {
    super((entries, observer) => {
      window.requestAnimationFrame(() => {
        if (!Array.isArray(entries) || !entries.length) return;
        cb(entries, observer);
      });
    });
  }
};

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);