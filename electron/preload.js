const { contextBridge } = require('electron')

contextBridge.exposeInMainWorld('phantom', {
  platform: process.platform,
  version: '1.0.0',
})
