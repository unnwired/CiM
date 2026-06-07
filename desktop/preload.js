const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('flowxDesktop', {
  openExternal: (url) => ipcRenderer.invoke('flowx-open-external', url),
  quit: () => ipcRenderer.invoke('flowx-quit'),
  quitForUpdate: () => ipcRenderer.invoke('flowx-quit-for-update'),
  canRestartBackend: () => ipcRenderer.invoke('flowx-can-restart-backend'),
  restartBackend: () => ipcRenderer.invoke('flowx-restart-backend'),
  canReloadFrontend: () => ipcRenderer.invoke('flowx-can-reload-frontend'),
  reloadFrontend: () => ipcRenderer.invoke('flowx-reload-frontend'),
});
