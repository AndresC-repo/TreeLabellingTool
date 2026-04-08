import { createRouter, createWebHistory } from 'vue-router'
import UploadView from '../views/UploadView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: UploadView },
    {
      path: '/session/:id/view',
      component: () => import('../views/View2D.vue'),
    },
    {
      path: '/session/:id/patch/:patchId',
      component: () => import('../views/PatchView3D.vue'),
    },
  ],
})
