<template>
  <div class="pointcloud-viewer">
    <div ref="container" class="viewer-container"></div>
    
    <!-- 工具栏 -->
    <div class="viewer-toolbar">
      <el-button-group>
        <el-button 
          :type="controlMode === 'orbit' ? 'primary' : 'default'"
          @click="setControlMode('orbit')"
          title="轨道控制"
        >
          <el-icon><VideoCamera /></el-icon>
        </el-button>
        <el-button 
          :type="controlMode === 'fly' ? 'primary' : 'default'"
          @click="setControlMode('fly')"
          title="飞行控制"
        >
          <el-icon><Compass /></el-icon>
        </el-button>
      </el-button-group>
      
      <el-divider direction="vertical" />
      
      <el-button-group>
        <el-button @click="resetCamera" title="重置视角">
          <el-icon><RefreshRight /></el-icon>
        </el-button>
        <el-button @click="toggleFullscreen" title="全屏">
          <el-icon><FullScreen /></el-icon>
        </el-button>
      </el-button-group>
      
      <el-divider direction="vertical" />
      
      <el-button-group>
        <el-button @click="togglePointSize" title="点大小">
          <el-icon><CircleCheck /></el-icon>
        </el-button>
        <el-button @click="toggleColor" title="切换颜色">
          <el-icon><Brush /></el-icon>
        </el-button>
      </el-button-group>
    </div>
    
    <!-- 信息显示 -->
    <div class="viewer-info" v-if="pointInfo">
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="点数">{{ formatNumber(pointInfo.pointCount) }}</el-descriptions-item>
        <el-descriptions-item label="包围盒">{{ formatBoundingBox(pointInfo.boundingBox) }}</el-descriptions-item>
        <el-descriptions-item label="有颜色">{{ pointInfo.hasColor ? '是' : '否' }}</el-descriptions-item>
      </el-descriptions>
    </div>
    
    <!-- 加载状态 -->
    <div class="viewer-loading" v-if="loading">
      <el-loading-spinner />
      <span>加载中...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls'
import { FlyControls } from 'three/examples/jsm/controls/FlyControls'

interface PointCloudInfo {
  pointCount: number
  boundingBox: {
    min: number[]
    max: number[]
  }
  hasColor: boolean
  hasNormal: boolean
}

interface Props {
  pointsUrl?: string
  colorsUrl?: string
  pointInfo?: PointCloudInfo
  pointSize?: number
  backgroundColor?: string
}

const props = withDefaults(defineProps<Props>(), {
  pointSize: 1,
  backgroundColor: '#1a1a1a'
})

const emit = defineEmits<{
  cameraChange: [position: THREE.Vector3, target: THREE.Vector3]
}>()

// Refs
const container = ref<HTMLDivElement>()
const loading = ref(false)
const controlMode = ref<'orbit' | 'fly'>('orbit')

// Three.js 对象
let scene: THREE.Scene
let camera: THREE.PerspectiveCamera
let renderer: THREE.WebGLRenderer
let controls: OrbitControls | FlyControls
let pointCloud: THREE.Points
let animationId: number

// 初始化场景
const initScene = () => {
  if (!container.value) return
  
  // 场景
  scene = new THREE.Scene()
  scene.background = new THREE.Color(props.backgroundColor)
  
  // 相机
  const aspect = container.value.clientWidth / container.value.clientHeight
  camera = new THREE.PerspectiveCamera(60, aspect, 0.1, 10000)
  camera.position.set(10, 10, 10)
  
  // 渲染器
  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setSize(container.value.clientWidth, container.value.clientHeight)
  renderer.setPixelRatio(window.devicePixelRatio)
  container.value.appendChild(renderer.domElement)
  
  // 控制器
  setControlMode('orbit')
  
  // 网格辅助
  const gridHelper = new THREE.GridHelper(100, 100, 0x444444, 0x222222)
  scene.add(gridHelper)
  
  // 坐标轴辅助
  const axesHelper = new THREE.AxesHelper(5)
  scene.add(axesHelper)
  
  // 灯光
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.5)
  scene.add(ambientLight)
  
  const directionalLight = new THREE.DirectionalLight(0xffffff, 0.5)
  directionalLight.position.set(10, 10, 10)
  scene.add(directionalLight)
  
  // 开始渲染循环
  animate()
  
  // 监听窗口大小变化
  window.addEventListener('resize', onWindowResize)
}

// 设置控制模式
const setControlMode = (mode: 'orbit' | 'fly') => {
  controlMode.value = mode
  
  if (controls) {
    controls.dispose()
  }
  
  if (mode === 'orbit') {
    controls = new OrbitControls(camera, renderer.domElement)
    ;(controls as OrbitControls).enableDamping = true
    ;(controls as OrbitControls).dampingFactor = 0.05
  } else {
    controls = new FlyControls(camera, renderer.domElement)
    ;(controls as FlyControls).movementSpeed = 10
    ;(controls as FlyControls).rollSpeed = Math.PI / 6
  }
}

// 加载点云数据
const loadPointCloud = async () => {
  if (!props.pointsUrl) return
  
  loading.value = true
  
  try {
    // 移除旧的点云
    if (pointCloud) {
      scene.remove(pointCloud)
      pointCloud.geometry.dispose()
      if (Array.isArray(pointCloud.material)) {
        pointCloud.material.forEach(m => m.dispose())
      } else {
        pointCloud.material.dispose()
      }
    }
    
    // 加载点坐标
    const pointsResponse = await fetch(props.pointsUrl)
    const pointsBuffer = await pointsResponse.arrayBuffer()
    const pointsArray = new Float32Array(pointsBuffer)
    
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(pointsArray, 3))
    
    // 加载颜色（如果有）
    if (props.colorsUrl && props.pointInfo?.hasColor) {
      const colorsResponse = await fetch(props.colorsUrl)
      const colorsBuffer = await colorsResponse.arrayBuffer()
      const colorsArray = new Uint8Array(colorsBuffer)
      
      // 将颜色归一化到 0-1
      const normalizedColors = new Float32Array(colorsArray.length)
      for (let i = 0; i < colorsArray.length; i++) {
        normalizedColors[i] = colorsArray[i] / 255
      }
      
      geometry.setAttribute('color', new THREE.BufferAttribute(normalizedColors, 3, true))
    }
    
    // 创建点云材质
    const material = new THREE.PointsMaterial({
      size: props.pointSize,
      vertexColors: props.pointInfo?.hasColor || false,
      color: props.pointInfo?.hasColor ? undefined : 0x00ff00,
      sizeAttenuation: true
    })
    
    pointCloud = new THREE.Points(geometry, material)
    scene.add(pointCloud)
    
    // 调整相机位置以适应点云
    fitCameraToPointCloud()
    
  } catch (error) {
    console.error('Failed to load point cloud:', error)
  } finally {
    loading.value = false
  }
}

// 调整相机以适应点云
const fitCameraToPointCloud = () => {
  if (!pointCloud || !props.pointInfo) return
  
  const bbox = props.pointInfo.boundingBox
  const center = new THREE.Vector3(
    (bbox.min[0] + bbox.max[0]) / 2,
    (bbox.min[1] + bbox.max[1]) / 2,
    (bbox.min[2] + bbox.max[2]) / 2
  )
  
  const size = new THREE.Vector3(
    bbox.max[0] - bbox.min[0],
    bbox.max[1] - bbox.min[1],
    bbox.max[2] - bbox.min[2]
  )
  
  const maxDim = Math.max(size.x, size.y, size.z)
  const fov = camera.fov * (Math.PI / 180)
  const cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2)) * 2
  
  camera.position.set(center.x + cameraZ, center.y + cameraZ, center.z + cameraZ)
  camera.lookAt(center)
  
  if (controls instanceof OrbitControls) {
    controls.target.copy(center)
    controls.update()
  }
}

// 重置相机
const resetCamera = () => {
  fitCameraToPointCloud()
}

// 全屏切换
const toggleFullscreen = () => {
  if (!document.fullscreenElement) {
    container.value?.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}

// 切换点大小
const togglePointSize = () => {
  if (pointCloud) {
    const material = pointCloud.material as THREE.PointsMaterial
    material.size = material.size === 1 ? 2 : 1
  }
}

// 切换颜色
const toggleColor = () => {
  if (pointCloud) {
    const material = pointCloud.material as THREE.PointsMaterial
    if (material.vertexColors) {
      material.vertexColors = false
      material.color.setHex(Math.random() * 0xffffff)
    } else {
      material.vertexColors = props.pointInfo?.hasColor || false
    }
    material.needsUpdate = true
  }
}

// 渲染循环
const animate = () => {
  animationId = requestAnimationFrame(animate)
  
  if (controls instanceof FlyControls) {
    controls.update(0.016) // 假设60fps
  } else if (controls instanceof OrbitControls) {
    controls.update()
  }
  
  renderer.render(scene, camera)
}

// 窗口大小变化处理
const onWindowResize = () => {
  if (!container.value) return
  
  const width = container.value.clientWidth
  const height = container.value.clientHeight
  
  camera.aspect = width / height
  camera.updateProjectionMatrix()
  
  renderer.setSize(width, height)
}

// 格式化数字
const formatNumber = (num: number) => {
  return num?.toLocaleString() || '0'
}

// 格式化包围盒
const formatBoundingBox = (bbox: { min: number[], max: number[] }) => {
  if (!bbox) return '-'
  return `(${bbox.min.map(v => v.toFixed(2)).join(', ')}) - (${bbox.max.map(v => v.toFixed(2)).join(', ')})`
}

// 监听属性变化
watch(() => props.pointsUrl, loadPointCloud)
watch(() => props.pointSize, (newSize) => {
  if (pointCloud) {
    (pointCloud.material as THREE.PointsMaterial).size = newSize
  }
})

// 生命周期
onMounted(() => {
  initScene()
  if (props.pointsUrl) {
    loadPointCloud()
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize)
  cancelAnimationFrame(animationId)
  
  if (pointCloud) {
    pointCloud.geometry.dispose()
    if (Array.isArray(pointCloud.material)) {
      pointCloud.material.forEach(m => m.dispose())
    } else {
      pointCloud.material.dispose()
    }
  }
  
  renderer?.dispose()
})
</script>

<style scoped lang="scss">
.pointcloud-viewer {
  position: relative;
  width: 100%;
  height: 100%;
  
  .viewer-container {
    width: 100%;
    height: 100%;
    background: #1a1a1a;
    border-radius: 8px;
    overflow: hidden;
  }
  
  .viewer-toolbar {
    position: absolute;
    top: 16px;
    left: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px;
    background: rgba(0, 0, 0, 0.7);
    border-radius: 8px;
    backdrop-filter: blur(10px);
    
    .el-divider {
      background-color: rgba(255, 255, 255, 0.2);
    }
  }
  
  .viewer-info {
    position: absolute;
    top: 16px;
    right: 16px;
    width: 200px;
    padding: 12px;
    background: rgba(0, 0, 0, 0.7);
    border-radius: 8px;
    backdrop-filter: blur(10px);
    color: #fff;
    
    :deep(.el-descriptions__label) {
      color: #aaa;
    }
    
    :deep(.el-descriptions__content) {
      color: #fff;
    }
  }
  
  .viewer-loading {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    color: #fff;
    font-size: 14px;
  }
}
</style>
