// Cầu nối an toàn giữa giao diện web và Electron (contextIsolation bật).
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('tripHotelData', {
  isElectron: true,
  getDataDir: () => ipcRenderer.invoke('data-dir:get'),
  chooseDataDir: () => ipcRenderer.invoke('data-dir:choose'),
  resetDataDir: () => ipcRenderer.invoke('data-dir:reset'),
});
