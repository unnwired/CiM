const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('cimDesktop', {
  openExternal: (url) => ipcRenderer.invoke('cim-open-external', url),
  quit: () => ipcRenderer.invoke('cim-quit'),
  quitForUpdate: () => ipcRenderer.invoke('cim-quit-for-update'),
  canRestartBackend: () => ipcRenderer.invoke('cim-can-restart-backend'),
  restartBackend: (options) => ipcRenderer.invoke('cim-restart-backend', options),
  canReloadFrontend: () => ipcRenderer.invoke('cim-can-reload-frontend'),
  reloadFrontend: () => ipcRenderer.invoke('cim-reload-frontend'),
});
